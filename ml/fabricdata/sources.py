"""One reader per source: raw files in data/external/<source>/ → ImageRecords (boxes in image pixels).

Each reader also decides which images belong together (``group``): augmented copies of one original,
photos of the same physical defect taken seconds apart, or the AITEX fabric the demo roll is made from.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from fabricdata.records import Box, ImageRecord

ROBOFLOW_SUFFIX = re.compile(r"_(jpe?g|png)\.rf\.[0-9a-f]+\.(jpe?g|png)$", re.IGNORECASE)
SESSION_GAP_S = 120
"""Photos taken less than this apart (phone time stamps in the file name) show the same defect."""

AITEX_DEMO_FABRIC = "02"
"""data/sample_roll is rendered from AITEX fabric 02 (roll_meta.json "source"): always test."""


def original_name(file_name: str) -> str:
    """Roboflow renames ``x.jpg`` to ``x_jpg.rf.<hash>.jpg`` (once per augmented copy)."""
    return ROBOFLOW_SUFFIX.sub("", Path(file_name).name)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def mask_boxes(mask: np.ndarray, *, min_area: int = 6, join_px: int = 3) -> list[tuple[int, int, int, int]]:
    """Boxes (x0, y0, x1, y1) around the blobs of a binary mask. Fragments closer than ``join_px``
    are one defect (masks of thin yarn faults are often broken up)."""
    on = mask > 0
    if join_px:
        on = ndimage.binary_dilation(on, iterations=join_px)
    labels, n = ndimage.label(on)
    boxes = []
    for sl in ndimage.find_objects(labels):
        if sl is None:
            continue
        ys, xs = sl
        # Undo the dilation and measure the real pixels inside the blob.
        real = mask[ys, xs] > 0
        if real.sum() < min_area:
            continue
        rows, cols = np.nonzero(real)
        boxes.append((xs.start + int(cols.min()), ys.start + int(rows.min()),
                      xs.start + int(cols.max()) + 1, ys.start + int(rows.max()) + 1))
    return boxes


def session_groups(items: list[tuple[str, datetime | None]], prefix: str) -> dict[str, str]:
    """Group keys whose time stamps are within SESSION_GAP_S of the previous one; no stamp → own group."""
    out: dict[str, str] = {}
    stamped = sorted((t, k) for k, t in items if t is not None)
    session, last = 0, None
    for t, k in stamped:
        if last is None or (t - last).total_seconds() > SESSION_GAP_S:
            session += 1
        out[k] = f"{prefix}:session{session}"
        last = t
    for k, t in items:
        if t is None:
            out[k] = f"{prefix}:{k}"
    return out


def stamp(name: str, pattern: str, fmt: str) -> datetime | None:
    m = re.search(pattern, name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), fmt)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------- readers
def read_aitex(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted"
    for img in sorted((base / "Defect_images").glob("*.png")):
        _, code, fabric = img.stem.split("_")[:3]
        boxes: list[Box] = []
        for mp in sorted((base / "Mask_images").glob(img.stem + "_mask*.png")):
            mask = np.asarray(Image.open(mp).convert("L"))
            boxes += [Box(*b, src_cls=code) for b in mask_boxes(mask)]
        if not boxes:
            continue  # a defect image with an empty mask is neither labelled nor clean
        w, h = image_size(img)
        yield ImageRecord("aitex", img, w, h, boxes, group=f"aitex:{img.stem.split('_')[0]}",
                          force_split="test" if fabric == AITEX_DEMO_FABRIC else None)
    for img in sorted((base / "NODefect_images").glob("*/*.png")):
        fabric = img.stem.split("_")[2]
        w, h = image_size(img)
        yield ImageRecord("aitex", img, w, h, [], group=f"aitex:clean:{img.parent.name}:{img.stem}",
                          defect_free=True, force_split="test" if fabric == AITEX_DEMO_FABRIC else None)


def open_rgb(r: ImageRecord) -> Image.Image:
    """The record's image as its labels see it: the stored pixels turned by ``r.rotate``. EXIF orientation is
    not applied: every reader measures sizes and masks on the stored pixels, and the labelled photos carry no
    EXIF orientation (checked: all FabricSpotDefect photos have orientation 1)."""
    with Image.open(r.path) as im:
        out = im.convert("RGB")
    if r.rotate == 90:
        out = out.transpose(Image.Transpose.ROTATE_270)
    elif r.rotate == 270:
        out = out.transpose(Image.Transpose.ROTATE_90)
    return out


def _box_contrast(gray: np.ndarray, boxes: list[Box], scale: float) -> float:
    """Mean |inside - surrounding ring| brightness of the boxes: high when the boxes sit on the marks."""
    vals = []
    h, w = gray.shape
    for b in boxes:
        x0, y0, x1, y1 = (int(v * scale) for v in (b.x0, b.y0, b.x1, b.y1))
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        m = max(3, (max(x1 - x0, y1 - y0)) // 2)
        ring = gray[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)].astype(np.float64)
        inner = gray[y0:y1, x0:x1].astype(np.float64)
        n = ring.size - inner.size
        if inner.size == 0 or n <= 0:
            continue
        vals.append(abs(inner.mean() - (ring.sum() - inner.sum()) / n))
    return float(np.mean(vals)) if vals else 0.0


ROTATION_MARGIN = 1.5
"""A quarter turn is taken only when its box contrast beats the other one by this factor. FabricSpotDefect:
96 photos turn clockwise, 48 counter-clockwise, 65 are too faint to tell and are left out."""


def label_rotation(path: Path, width: int, height: int, boxes: list[Box]) -> int:
    """0 when the stored image has the labels' size; for a sideways image (sizes swapped) the quarter turn
    (90 or 270 degrees clockwise) that puts the boxes on the marks, judged by box contrast. Phones were
    held both ways, so this is decided per image; -1 when neither turn is clearly right."""
    with Image.open(path) as im:
        if im.size == (width, height) or im.size != (height, width):  # size only: no pixel decoding yet
            return 0
        im.draft("L", (im.width // 4, im.height // 4))
        small = im.convert("L")
    scale = small.width / height  # small is still sideways: its width belongs to the labels' height
    cw = _box_contrast(np.asarray(small.transpose(Image.Transpose.ROTATE_270)), boxes, scale)
    ccw = _box_contrast(np.asarray(small.transpose(Image.Transpose.ROTATE_90)), boxes, scale)
    if cw >= ccw * ROTATION_MARGIN:
        return 90
    if ccw >= cw * ROTATION_MARGIN:
        return 270
    return -1  # neither way is clearly right: the image is left out rather than trained with wrong boxes


def read_coco(source: str, ann_files: list[Path], group_of: Callable[[str], str],
              image_dir_of: Callable[[Path], Path] | None = None) -> Iterator[ImageRecord]:
    for ann in ann_files:
        j = json.loads(ann.read_text())
        cats = {c["id"]: c["name"] for c in j["categories"]}
        by_image: dict[int, list[Box]] = {}
        for a in j["annotations"]:
            x, y, w, h = a["bbox"]
            by_image.setdefault(a["image_id"], []).append(Box(x, y, x + w, y + h, src_cls=cats[a["category_id"]]))
        image_dir = image_dir_of(ann) if image_dir_of else ann.parent
        for im in j["images"]:
            path = image_dir / im["file_name"]
            boxes = by_image.get(im["id"], [])
            w, h = int(im["width"]), int(im["height"])
            rot = label_rotation(path, w, h, boxes) if path.exists() and boxes else 0
            if rot < 0:
                continue
            if not boxes and path.exists():
                w, h = image_size(path)  # no labels to match: the stored image's own size
            yield ImageRecord(source, path, w, h, boxes, group=group_of(im["file_name"]), rotate=rot)


def read_fabricspotdefect(root: Path) -> Iterator[ImageRecord]:
    anns = sorted(root.glob("extracted/*/FabricSpotDefect/Orginal/*/_annotations.coco.json"))
    yield from read_coco("fabricspotdefect", anns, lambda n: f"fabricspotdefect:{original_name(n)}")


def read_garment_defects(root: Path) -> Iterator[ImageRecord]:
    anns = sorted(root.glob("extracted/inner/*/_annotations.coco.json"))
    names = []
    for ann in anns:
        names += [im["file_name"] for im in json.loads(ann.read_text())["images"]]
    originals = {original_name(n) for n in names}
    groups = session_groups([(o, stamp(o, r"(\d{8}_\d{6})", "%Y%m%d_%H%M%S")) for o in originals], "garment")
    # Roboflow exported up to 3 augmented copies (flips, 90° turns, small rotations with black corners) per
    # original: keep one per original, the one with the least black border. Augmentation is ours to do.
    copies: dict[str, list[ImageRecord]] = {}
    for r in read_coco("garment_defects", anns, lambda n: groups[original_name(n)]):
        copies.setdefault(original_name(r.path.name), []).append(r)
    for recs in copies.values():
        yield min(recs, key=lambda r: (black_border(r.path), r.path.name))


def black_border(path: Path, width: int = 4) -> float:
    """Share of near-black pixels along the image edge (rotation padding)."""
    with Image.open(path) as im:
        a = np.asarray(im.convert("L"))
    edge = np.concatenate([a[:width].ravel(), a[-width:].ravel(), a[:, :width].ravel(), a[:, -width:].ravel()])
    return float((edge < 8).mean())


def read_tianchi(root: Path, images: Path | None = None) -> Iterator[ImageRecord]:
    """Annotations from the Roboflow export (annotations/<split>/_annotations.coco.json); the images live
    wherever the export was unpacked (on Kaggle), given as ``images`` with the same <split>/ folders."""
    anns = sorted((root / "annotations").glob("*/_annotations.coco.json"))
    img_root = images or root / "images"
    yield from read_coco("tianchi", anns, lambda n: f"tianchi:{original_name(n)}",
                         image_dir_of=lambda ann: img_root / ann.parent.name)


def read_fd_figshare(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted/FD_Dataset/YOLO"
    imgs = sorted(base.glob("*/images/*.jpg"))
    originals = {original_name(p.name) for p in imgs}
    groups = session_groups(
        [(o, stamp(o, r"photo_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", "%Y-%m-%d_%H-%M-%S")) for o in originals], "fd"
    )
    for img in imgs:
        w, h = image_size(img)
        boxes = yolo_boxes(img.parent.parent / "labels" / (img.stem + ".txt"), w, h)
        group = groups[original_name(img.name)]
        yield ImageRecord("fd_figshare", img, w, h, boxes, group=group,
                          force_split=FD_FORCED.get(group))


def yolo_boxes(label: Path, w: int, h: int) -> list[Box]:
    """YOLO label lines "class cx cy w h" (relative) → boxes in pixels; a missing file means no boxes."""
    boxes = []
    for line in label.read_text().splitlines() if label.exists() else []:
        parts = line.split()
        if len(parts) != 5:
            continue
        c, cx, cy, bw, bh = parts[0], *map(float, parts[1:])
        boxes.append(Box((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h, src_cls=c))
    return boxes


def read_fabric_stain(root: Path) -> Iterator[ImageRecord]:
    """Fabric Stain Dataset (University of Moratuwa; Kaggle priemshpathirana/fabric-stain-dataset, CC0): phone
    photos, YOLO labels with one class (stain). The Kaggle layout is images/<stain|defect_free>/N.jpg; both
    folders number from 1, so the build links them flat as <root>/flat/<folder>_N.<ext> (labels next to them as
    .txt) to keep file names unique. Consecutive numbers are often the same stain shot again: groups of
    FABRIC_STAIN_RUN."""
    for img in sorted((root / "flat").iterdir()):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        folder, num = img.stem.rsplit("_", 1)
        w, h = image_size(img)
        boxes = yolo_boxes(img.with_suffix(".txt"), w, h)
        if folder == "stain" and not boxes:
            continue  # a stain photo without labels would teach the stain as background
        n = int(num) if num.isdigit() else 0
        yield ImageRecord("fabric_stain", img, w, h, boxes, group=f"fabric_stain:{folder}:{n // FABRIC_STAIN_RUN}",
                          defect_free=folder == "defect_free")


FD_FORCED = {"fd:session1": "test", "fd:session6": "val"}
"""FD Dataset has 7 photo sessions, most bigger than a 10 % test share, so the balanced split gave test none
(and every oil photo went to train). Session 1 (125 photos: oil, cutting, crack) is test, session 6 (52) val."""
FABRIC_STAIN_RUN = 4


MORATUWA_MAX_BLOBS = 3
"""Some "_processed (3)" masks of line defects are noise (checked visually): images whose mask splits
into more blobs than this are left out."""
MORATUWA_LABELLED = ("hole", "horizontal", "Vertical")
"""Folders whose images come with masks ("<name>_processed (3).jpg"); "lines" and "stain" have none."""


def moratuwa_base(stem: str) -> str:
    return re.sub(r"(_processed)?\s*\(\d+\)$", "", stem).strip()


def read_moratuwa(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted/Fabric Defects Dataset/Fabric Defect Dataset"
    for folder in MORATUWA_LABELLED:
        files = sorted((base / folder).glob("*.*"))
        for img in files:
            if "_processed" in img.stem:
                continue
            mask_path = img.with_name(f"{img.stem}_processed (3){img.suffix}")
            if not mask_path.exists():
                continue  # no mask: no labels (see unlabelled())
            w, h = image_size(img)
            mask = np.asarray(Image.open(mask_path).convert("L").resize((w, h)))
            boxes = [Box(*b, src_cls=folder.lower()) for b in mask_boxes(np.where(mask > 127, 255, 0))]
            if not boxes or len(boxes) > MORATUWA_MAX_BLOBS:
                continue  # an empty or noisy mask (dozens of specks, the defect itself missed): unreliable
            yield ImageRecord("moratuwa", img, w, h, boxes, group=f"moratuwa:{folder}:{moratuwa_base(img.stem)}")
    yield from read_moratuwa_clean(root)


def read_moratuwa_clean(root: Path) -> Iterator[ImageRecord]:
    """The compilation's "defect free" folder (only downloaded on Kaggle; partly AITEX copies, which the
    near-duplicate step merges with the AITEX originals)."""
    clean = root / "extracted/Fabric Defects Dataset/Fabric Defect Dataset/defect free"
    for img in sorted(clean.rglob("*")):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
            continue
        w, h = image_size(img)
        yield ImageRecord("moratuwa", img, w, h, [], group=f"moratuwa:clean:{moratuwa_base(img.stem)}", defect_free=True)


def moratuwa_unlabelled(root: Path) -> dict[str, int]:
    """Images that would need labelling before they can train a detector."""
    base = root / "extracted/Fabric Defects Dataset/Fabric Defect Dataset"
    out = {}
    for folder in ("lines", "stain", *MORATUWA_LABELLED):
        files = [p for p in (base / folder).glob("*.*") if "_processed" not in p.stem]
        if folder in MORATUWA_LABELLED:
            files = [p for p in files if not p.with_name(f"{p.stem}_processed (3){p.suffix}").exists()]
        out[folder] = len(files)
    return out


ZJU_GROUP_SPAN = 50
"""ZJU-Leaper images are numbered in capture order per fabric pattern; neighbours may overlap, so runs of
this many ids form one group."""


def read_zju_leaper(root: Path) -> Iterator[ImageRecord]:
    """ZJU-Leaper (CC BY-NC-SA 4.0): one xml per image (pattern, group, defective 0/1, boxes where given)
    and a mask for defective images. Defect types are not labelled: every defect is ``defect``.
    The authors' own train/test lists are not used: their test lists hold most of the images, which would
    turn our test split into mostly ZJU (checked on the first Kaggle build); our group-aware split applies."""
    # On Kaggle the mirror is a read-only input linked in as <root>/ZJU-Leaper; Path.rglob does not follow symlinks.
    linked = root / "ZJU-Leaper"
    base = linked.resolve() if linked.is_symlink() else next(root.rglob("ImageSets")).parent
    masks = base / "Annotations/masks"
    for xml in sorted((base / "Annotations/xmls").glob("*.xml")):
        t = ET.parse(xml).getroot()
        img = base / "Images" / (t.findtext("filename") or f"{xml.stem}.jpg")
        defective = (t.findtext("defective") or "0").strip() == "1"
        size = t.find("size")
        if size is not None and size.findtext("width"):
            w, h = int(float(size.findtext("width"))), int(float(size.findtext("height")))
        else:
            w, h = image_size(img)
        boxes = [
            Box(float(b.findtext("xmin")), float(b.findtext("ymin")), float(b.findtext("xmax")), float(b.findtext("ymax")),
                src_cls="defect")
            for b in t.iter("bndbox")
        ]
        mask = masks / f"{xml.stem}.png"
        if defective and not boxes and mask.exists():
            m = np.asarray(Image.open(mask).convert("L"))
            boxes = [Box(*b, src_cls="defect") for b in mask_boxes(m)]
        if defective and not boxes:
            continue  # defective but no box or mask: unusable
        pattern = t.findtext("pattern_id") or "?"
        num = int(xml.stem) if xml.stem.isdigit() else 0
        yield ImageRecord("zju_leaper", img, w, h, boxes, group=f"zju:{pattern}:{num // ZJU_GROUP_SPAN}",
                          defect_free=not defective)


def read_raw_fabrid(root: Path) -> Iterator[ImageRecord]:
    """RAW-FABRID (CC BY 4.0): high-res line-scan images (4 px/mm) with COCO boxes; images without a box
    are defect-free. Captures of one roll are numbered in order: runs of 20 form one group."""
    ann = next(root.rglob("RAW_FABRID_HighRes_COCO.json"))

    def group_of(name: str) -> str:
        m = re.match(r"(Rollo[^_]+)_(\d+)_", name)
        return f"raw:{m.group(1)}:{int(m.group(2)) // 20}" if m else f"raw:{name}"

    for r in read_coco("raw_fabrid", [ann], group_of, image_dir_of=lambda a: a.parent / "images"):
        r.defect_free = not r.boxes
        yield r


def read_wfdd(root: Path) -> Iterator[ImageRecord]:
    """WFDD (woven fabric defect detection; Kaggle mirror, licence not stated): <fabric>/test/<defect>/NNN.png
    with masks in <fabric>/ground_truth/<defect>/NNN_mask.png; train/good and test/good are defect-free."""
    # On Kaggle WFDD is a read-only input linked in as <root>/WFDD; Path.rglob does not follow symlinks.
    base = (root / "WFDD").resolve() if (root / "WFDD").exists() else next(root.rglob("ground_truth")).parent.parent
    for fabric in sorted(p for p in base.iterdir() if p.is_dir()):
        for img in sorted((fabric / "test").glob("*/*.png")):
            defect = img.parent.name
            if defect == "good":
                continue
            mask_path = fabric / "ground_truth" / defect / f"{img.stem}_mask.png"
            if not mask_path.exists():
                continue
            boxes = [Box(*b, src_cls=defect) for b in mask_boxes(np.asarray(Image.open(mask_path).convert("L")))]
            if not boxes:
                continue
            w, h = image_size(img)
            num = int(img.stem) if img.stem.isdigit() else 0
            yield ImageRecord("wfdd", img, w, h, boxes, group=f"wfdd:{fabric.name}:{defect}:{num // 5}")
        for img in sorted(fabric.glob("*/good/*.png")):
            w, h = image_size(img)
            yield ImageRecord("wfdd", img, w, h, [], group=f"wfdd:{fabric.name}:good:{img.parent.parent.name}:{img.stem}",
                              defect_free=True)


def read_synth_nuisance(root: Path) -> Iterator[ImageRecord]:
    """ml/synth_nuisance.py output: each image keeps its base image's group (and forced split)."""
    groups = json.loads((root / "groups.json").read_text())
    for r in read_coco("synth_nuisance", [root / "annotations.json"], lambda n: groups[n]["group"],
                       image_dir_of=lambda ann: ann.parent / "images"):
        r.force_split = groups[r.path.name]["force_split"]
        yield r


READERS: dict[str, Callable[[Path], Iterator[ImageRecord]]] = {
    "aitex": read_aitex,
    "fabricspotdefect": read_fabricspotdefect,
    "moratuwa": read_moratuwa,
    "fd_figshare": read_fd_figshare,
    "garment_defects": read_garment_defects,
    "tianchi": read_tianchi,
    "zju_leaper": read_zju_leaper,
    "raw_fabrid": read_raw_fabrid,
    "wfdd": read_wfdd,
    "fabric_stain": read_fabric_stain,
    "synth_nuisance": read_synth_nuisance,
}
