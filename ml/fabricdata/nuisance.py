"""Things on an inspection table that look suspicious but are NOT defects, drawn onto real fabric photos.

The app shows these grey and never scores them (backend/threadeye/core/nondefect.py); a detector that has
learned them reports e.g. ``sticker`` instead of a false ``stain``. Public defect sets contain none, so they
are composed here onto clean (and some defective) tiles of the real sources:

  sticker        inspector's paper sticker: fluorescent paper, printed / hand-drawn arrow, gloss, shadow,
                 slight perspective
  loose_thread   a cut thread lying on the fabric: smooth random curve, twist shading, fibre fuzz, shadow
  wrinkle        a handling fold: light / dark shading across a soft ridge and the weave squeezed along it
  hand           the inspector's hand and forearm entering from a tile edge: real hands cut out of EgoHands
                 (CC BY 4.0, scripts/egohands_cutouts.py), colour-matched to the fabric's light; a share
                 drawn like the simulator's cartoon hand so the demo video is covered too

Everything works on float32 RGB arrays (H, W, 3) in 0..255 and returns the boxes it drew. Sizes are drawn
relative to the tile because the sources' pixels per cm differ.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

from fabricdata.classes import NUISANCE_CLASSES

STICKER_COLOURS = [(255, 70, 60), (255, 140, 30), (250, 230, 40), (90, 220, 70), (255, 90, 170), (245, 245, 240),
                   (80, 170, 255)]
SS = 4
"""Supersampling for anti-aliased thin strokes."""


@dataclass
class Drawn:
    cls: str
    box: tuple[float, float, float, float]


def _alpha_box(alpha: np.ndarray, x0: int, y0: int, thr: float = 0.25) -> tuple[float, float, float, float] | None:
    ys, xs = np.nonzero(alpha > thr)
    if not len(xs):
        return None
    return float(x0 + xs.min()), float(y0 + ys.min()), float(x0 + xs.max() + 1), float(y0 + ys.max() + 1)


def composite(img: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, x0: int, y0: int,
              shadow: tuple[int, int, float, float] | None = None) -> tuple[float, float, float, float] | None:
    """Paste ``rgb`` with ``alpha`` (0..1) at (x0, y0), clipped to ``img``; optional soft drop shadow
    (dx, dy, blur, strength). Returns the visible box."""
    h, w = img.shape[:2]
    ph, pw = alpha.shape
    if shadow:
        dx, dy, blur, strength = shadow
        sh = ndimage.gaussian_filter(alpha, blur) * strength
        _blend(img, None, sh, x0 + dx, y0 + dy)
    box = None
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + pw), min(h, y0 + ph)
    if xb > xa and yb > ya:
        box = _alpha_box(alpha[ya - y0:yb - y0, xa - x0:xb - x0], xa, ya)
    _blend(img, rgb, alpha, x0, y0)
    return box


def _blend(img: np.ndarray, rgb: np.ndarray | None, alpha: np.ndarray, x0: int, y0: int) -> None:
    h, w = img.shape[:2]
    ph, pw = alpha.shape
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + pw), min(h, y0 + ph)
    if xb <= xa or yb <= ya:
        return
    a = alpha[ya - y0:yb - y0, xa - x0:xb - x0, None]
    region = img[ya:yb, xa:xb]
    if rgb is None:  # shadow: darken
        region *= 1 - a
    else:
        region[:] = region * (1 - a) + rgb[ya - y0:yb - y0, xa - x0:xb - x0] * a


def _light(img: np.ndarray) -> float:
    return float(img.mean())


# ------------------------------------------------------------------------------------------------- sticker
def sticker(img: np.ndarray, rng: np.random.Generator) -> Drawn | None:
    h, w = img.shape[:2]
    side = min(h, w)
    sw = int(rng.uniform(0.07, 0.2) * side)
    shape = rng.choice(["rect", "rect", "round", "arrow"])
    sh = sw if shape == "round" else int(sw * rng.uniform(0.45, 0.8))
    pad = sw // 2
    W, H = sw + 2 * pad, sw + 2 * pad
    mask = Image.new("L", (W * SS, H * SS), 0)
    d = ImageDraw.Draw(mask)
    bx0, by0 = (W - sw) // 2 * SS, (H - sh) // 2 * SS
    bx1, by1 = bx0 + sw * SS, by0 + sh * SS
    if shape == "round":
        d.ellipse((bx0, by0, bx1, by1), fill=255)
    elif shape == "arrow":
        mid = (by0 + by1) // 2
        tip = bx0 + int(0.7 * sw * SS)
        d.polygon([(bx0, by0), (tip, by0), (bx1, mid), (tip, by1), (bx0, by1)], fill=255)
    else:
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=int(rng.uniform(0, 0.15) * sh * SS), fill=255)
    colour = np.array(STICKER_COLOURS[rng.integers(len(STICKER_COLOURS))], np.float32)
    # Printed or hand-drawn mark: an arrow, a line or a scribble in dark ink.
    ink = Image.new("L", mask.size, 0)
    di = ImageDraw.Draw(ink)
    lw = max(1, int(rng.uniform(0.04, 0.09) * sh * SS))
    cy = (by0 + by1) // 2
    mark = rng.choice(["arrow", "line", "scribble", "none"])
    if mark == "arrow":
        a0, a1 = bx0 + int(0.2 * sw * SS), bx0 + int(0.75 * sw * SS)
        di.line((a0, cy, a1, cy), fill=255, width=lw)
        di.polygon([(a1 + lw * 2, cy), (a1 - lw * 2, cy - lw * 3), (a1 - lw * 2, cy + lw * 3)], fill=255)
    elif mark == "line":
        di.line((bx0 + int(0.2 * sw * SS), cy, bx0 + int(0.8 * sw * SS), cy), fill=255, width=lw)
    elif mark == "scribble":
        pts = [(bx0 + int(x * sw * SS), cy + int(rng.normal(0, 0.15) * sh * SS)) for x in np.linspace(0.2, 0.8, 7)]
        di.line(pts, fill=255, width=lw, joint="curve")
    mask = mask.resize((W, H), Image.Resampling.LANCZOS)
    ink = ink.resize((W, H), Image.Resampling.LANCZOS)
    m = np.asarray(mask, np.float32) / 255
    k = np.asarray(ink, np.float32) / 255 * m
    # Paper: slight grain, a light gradient (gloss) and darker edges.
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = rng.uniform(0, 2 * np.pi)
    grad = 1 + 0.12 * ((xx - W / 2) * math.cos(ang) + (yy - H / 2) * math.sin(ang)) / W
    grain = 1 + rng.normal(0, 0.03, (H, W)).astype(np.float32)
    edge = 0.85 + 0.15 * np.clip(ndimage.distance_transform_edt(m > 0.5) / 3, 0, 1)
    shade = (grad * grain * edge)[..., None]
    rgb = colour * shade * (_light(img) / 170) ** 0.5
    rgb = rgb * (1 - k[..., None]) + np.array([25, 25, 30], np.float32) * k[..., None]
    rgba = np.dstack([np.clip(rgb, 0, 255), m * 255]).astype(np.uint8)
    pil = Image.fromarray(rgba, "RGBA").rotate(rng.uniform(0, 360), Image.Resampling.BICUBIC, expand=True)
    pil = _perspective(pil, rng, 0.06)
    arr = np.asarray(pil, np.float32)
    x0 = int(rng.uniform(-0.1, 0.9) * w)
    y0 = int(rng.uniform(-0.1, 0.9) * h)
    box = composite(img, arr[..., :3], arr[..., 3] / 255, x0, y0, shadow=(2, 2, 1.5, 0.35))
    return Drawn("sticker", box) if box and _big_enough(box, 8) else None


def _perspective(pil: Image.Image, rng: np.random.Generator, amount: float) -> Image.Image:
    w, h = pil.size
    j = lambda: rng.uniform(-amount, amount)  # noqa: E731
    quad = (w * j(), h * j(), w * j(), h * (1 + j()), w * (1 + j()), h * (1 + j()), w * (1 + j()), h * j())
    return pil.transform((w, h), Image.Transform.QUAD, quad, Image.Resampling.BICUBIC)


def _big_enough(box: tuple[float, float, float, float], px: float) -> bool:
    return box[2] - box[0] >= px and box[3] - box[1] >= px


# ------------------------------------------------------------------------------------------- loose thread
def loose_thread(img: np.ndarray, rng: np.random.Generator) -> Drawn | None:
    h, w = img.shape[:2]
    side = min(h, w)
    length = rng.uniform(0.12, 0.6) * side
    n = 60
    turn = np.cumsum(rng.normal(0, 0.12, n)) + rng.uniform(0, 2 * np.pi)
    turn = ndimage.gaussian_filter1d(turn, 4)
    step = length / n
    pts = np.cumsum(np.stack([np.cos(turn), np.sin(turn)], 1) * step, 0)
    pts += [rng.uniform(0.05, 0.95) * w, rng.uniform(0.05, 0.95) * h] - pts.mean(0)
    width = rng.uniform(0.8, 2.6)
    x0, y0 = np.floor(pts.min(0)).astype(int) - 6
    x1, y1 = np.ceil(pts.max(0)).astype(int) + 6
    W, H = x1 - x0, y1 - y0
    canvas = Image.new("L", (W * SS, H * SS), 0)
    tone = Image.new("L", (W * SS, H * SS), 0)
    dc, dt = ImageDraw.Draw(canvas), ImageDraw.Draw(tone)
    local = (pts - [x0, y0]) * SS
    period = rng.uniform(2, 5)
    for i in range(n - 1):
        seg = (tuple(local[i]), tuple(local[i + 1]))
        dc.line(seg, fill=255, width=max(1, int(width * SS)))
        twist = 0.5 + 0.5 * math.sin(2 * math.pi * i * step / period)  # yarn twist: light / dark bands
        dt.line(seg, fill=int(80 + 175 * twist), width=max(1, int(width * SS)))
    # Fibre fuzz: a few short hairs sticking out.
    for _ in range(int(rng.integers(0, 12))):
        p = local[rng.integers(n)]
        a = rng.uniform(0, 2 * np.pi)
        r = rng.uniform(1.5, 5) * SS
        dc.line((tuple(p), (p[0] + r * math.cos(a), p[1] + r * math.sin(a))), fill=140, width=max(1, SS // 2))
    m = np.asarray(canvas.resize((W, H), Image.Resampling.LANCZOS), np.float32) / 255
    t = np.asarray(tone.resize((W, H), Image.Resampling.LANCZOS), np.float32) / 255
    t = np.where(m > 0.05, t / np.maximum(m, 1e-3), 0.6)
    region = img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    base = region.reshape(-1, 3).mean(0) if region.size else np.full(3, 128.0)
    kind = rng.choice(["same", "dark", "light", "colour"], p=[0.25, 0.3, 0.2, 0.25])
    colour = {"same": base * rng.choice([0.6, 1.45]), "dark": base * rng.uniform(0.2, 0.45),
              "light": np.full(3, rng.uniform(200, 245)), "colour": rng.uniform(40, 230, 3)}[kind]
    # A thread the eye cannot tell from the cloth is not a nuisance anyone would flag: keep it visible.
    if abs(float(colour.mean()) - float(base.mean())) < 35:
        colour = base * 0.35 if base.mean() > 110 else np.minimum(base * 1.8 + 40, 255)
    rgb = np.clip(colour[None, None, :] * (0.7 + 0.5 * t[..., None]), 0, 255).astype(np.float32)
    box = composite(img, rgb, m * rng.uniform(0.8, 1.0), int(x0), int(y0), shadow=(1, 1, 1.0, 0.3))
    return Drawn("loose_thread", box) if box and _big_enough(box, 3) else None


# ------------------------------------------------------------------------------------------------ wrinkle
def wrinkle(img: np.ndarray, rng: np.random.Generator) -> Drawn | None:
    h, w = img.shape[:2]
    side = min(h, w)
    length = rng.uniform(0.3, 1.2) * side
    width = rng.uniform(0.012, 0.04) * side
    amp = rng.uniform(0.09, 0.2)
    cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
    t = rng.uniform(0, np.pi)
    bend = rng.normal(0, 0.15)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    along = dx * math.cos(t) + dy * math.sin(t)
    across = -dx * math.sin(t) + dy * math.cos(t) - bend * along ** 2 / max(length, 1)
    fade = np.exp(-(along / (length / 2)) ** 4)
    d = across / width
    ridge = np.exp(-d * d) * fade
    # Light on the side facing the lamp, shadow on the other (derivative of a Gaussian), plus a soft
    # highlight on the crest.
    shade = 1 + amp * (2.33 * d * np.exp(-d * d) * fade * rng.choice([-1, 1]) + 0.4 * ridge)
    # The cloth folds: the weave is pulled towards the crest.
    squeeze = 0.35 * width * ridge * np.tanh(d)
    sx = xx + squeeze * -math.sin(t)
    sy = yy + squeeze * math.cos(t)
    warped = np.stack([ndimage.map_coordinates(img[..., c], [sy, sx], order=1, mode="reflect") for c in range(3)], -1)
    img[:] = np.clip(warped * shade[..., None], 0, 255)
    # The box covers the part of the fold that is clearly visible, not its faint tails.
    ys, xs = np.nonzero(np.abs(shade - 1) > max(0.04, amp * 0.35))
    if not len(xs):
        return None
    return Drawn("wrinkle", (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)))


# --------------------------------------------------------------------------------------------------- hand
@dataclass
class HandCutout:
    rgba: np.ndarray
    edge: str
    """Image border the forearm comes from: top, bottom, left or right."""


def load_hands(folder: Path) -> list[HandCutout]:
    meta = json.loads((folder / "hands.json").read_text())
    return [HandCutout(np.asarray(Image.open(folder / m["file"]).convert("RGBA"), np.float32), m["edge"]) for m in meta]


HAND_MIN_PX = 48
ROTATE_TO_BOTTOM = {"bottom": 0, "right": 90, "top": 180, "left": 270}
"""PIL rotate angle (counter-clockwise) that turns a cutout's entry edge to the bottom."""


def hand(img: np.ndarray, rng: np.random.Generator, hands: list[HandCutout]) -> Drawn | None:
    """A real hand cutout (or, with no cutouts or 1 in 8, a cartoon one) reaching in from a tile edge."""
    h, w = img.shape[:2]
    if not hands or rng.random() < 0.125:
        return _cartoon_hand(img, rng)
    cut = hands[rng.integers(len(hands))]
    pil = Image.fromarray(cut.rgba.astype(np.uint8), "RGBA").rotate(ROTATE_TO_BOTTOM[cut.edge], expand=True)
    target = rng.choice(["bottom", "top", "left", "right"])
    pil = pil.rotate({"bottom": 0, "left": 90, "top": 180, "right": 270}[target] + rng.normal(0, 12),
                     Image.Resampling.BICUBIC, expand=True)
    reach = rng.uniform(0.35, 0.9) * (h if target in ("top", "bottom") else w)
    long_side = pil.height if target in ("top", "bottom") else pil.width
    s = reach / long_side
    pil = pil.resize((max(1, int(pil.width * s)), max(1, int(pil.height * s))), Image.Resampling.LANCZOS)
    if rng.random() < 0.3:  # a moving hand is blurred
        pil = pil.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 2.0)))
    arr = np.asarray(pil, np.float32)
    rgb, a = arr[..., :3], arr[..., 3] / 255
    # Match the fabric's light: the hand is under the same lamp.
    skin = rgb[a > 0.5].mean() if (a > 0.5).any() else 128.0
    rgb = np.clip(rgb * (0.6 + 0.4 * _light(img) / max(skin, 1)) * rng.uniform(0.85, 1.15), 0, 255)
    ph, pw = a.shape
    along = rng.uniform(-0.2, 0.8)
    x0, y0 = {"bottom": (int(along * w), h - ph), "top": (int(along * w), 0),
              "left": (0, int(along * h)), "right": (w - pw, int(along * h))}[target]
    box = composite(img, rgb, a, x0, y0, shadow=(int(rng.uniform(4, 14)), int(rng.uniform(4, 14)), 6.0, 0.35))
    # A hand almost entirely outside the tile is a sliver nobody could name: not a label.
    return Drawn("hand", box) if box and _big_enough(box, HAND_MIN_PX) else None


def _cartoon_hand(img: np.ndarray, rng: np.random.Generator) -> Drawn | None:
    """Like tools/simulator/make_roll_video.py draw_hand: forearm from the bottom edge, palm, four fingers."""
    h, w = img.shape[:2]
    ppc = rng.uniform(4, 12)
    base = np.array([rng.uniform(0.1, 0.9) * w, h + 14 * ppc])
    tip = np.array([rng.uniform(0.2, 0.8) * w, rng.uniform(0.15, 0.7) * h])
    mask = Image.new("L", (w * 2, h * 2), 0)
    d = ImageDraw.Draw(mask)
    s = 2
    d.line((*(base * s), *(tip * s)), fill=255, width=int(8.5 * ppc * s))
    direction = (tip - base) / (np.linalg.norm(tip - base) + 1e-6)
    perp = np.array([-direction[1], direction[0]])
    palm = tip + direction * 2.0 * ppc
    r = np.array([4.2, 3.6]) * ppc
    d.ellipse((*(palm - r) * s, *(palm + r) * s), fill=255)
    for k in range(4):
        f0 = palm + direction * 3.0 * ppc + perp * (k - 1.5) * 1.6 * ppc
        f1 = f0 + direction * rng.uniform(3.0, 4.2) * ppc
        d.line((*(f0 * s), *(f1 * s)), fill=255, width=int(1.5 * ppc * s))
    m = np.asarray(mask.resize((w, h), Image.Resampling.LANCZOS), np.float32) / 255
    shade = ndimage.gaussian_filter(m, 1.5 * ppc)
    skin = np.array([190, 140, 105], np.float32) * rng.uniform(0.85, 1.1)
    rgb = skin[None, None, :] * (0.75 + 0.35 * shade[..., None])
    box = composite(img, rgb, m, 0, 0, shadow=(int(1.2 * ppc), int(1.0 * ppc), 1.2 * ppc, 0.35))
    return Drawn("hand", box) if box and _big_enough(box, 24) else None


# ------------------------------------------------------------------------------------------------ compose
CLEAR_MARGIN = 24
"""Drop shadows reach beyond a nuisance's box: kept-clear defects stay this far away."""


def _grow(box: tuple[float, float, float, float], m: float) -> tuple[float, float, float, float]:
    return box[0] - m, box[1] - m, box[2] + m, box[3] + m


def overlaps(box: tuple[float, float, float, float], others: list[tuple[float, float, float, float]]) -> bool:
    return any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in others)


def compose(img: np.ndarray, rng: np.random.Generator, hands: list[HandCutout],
            keep_clear: list[tuple[float, float, float, float]] | None = None, max_items: int = 3) -> list[Drawn]:
    """Draw 1..max_items nuisances onto ``img`` (in place). A nuisance that would cover a box in
    ``keep_clear`` (a real defect) is undone and skipped, so the defect labels stay true."""
    keep_clear = list(keep_clear or [])
    drawn: list[Drawn] = []
    kinds = rng.choice(NUISANCE_CLASSES, size=int(rng.integers(1, max_items + 1)), p=[0.27, 0.27, 0.2, 0.26])
    # Wrinkles first: a fold warps the cloth, and anything lying on the cloth is drawn after it.
    for kind in sorted(kinds, key=lambda k: k != "wrinkle"):
        before = img.copy()
        if kind == "sticker":
            d = sticker(img, rng)
        elif kind == "loose_thread":
            d = loose_thread(img, rng)
        elif kind == "wrinkle":
            d = wrinkle(img, rng)
        else:
            d = hand(img, rng, hands)
        if d is None or overlaps(_grow(d.box, CLEAR_MARGIN), keep_clear):
            img[:] = before
            continue
        drawn.append(d)
        if kind != "wrinkle":  # later items must not hide this one (others may lie on a wrinkle)
            keep_clear.append(d.box)
    return drawn
