"""Cut large images into overlapping tiles so small defects keep their pixels.

A quarter of the Tianchi defects are smaller than 32×32 px in a 2446×1000 image; shrinking the whole image
to the detector's input would erase them. Tiles are ``size`` px with ``overlap``; an image already
smaller than a tile is one tile. Boxes are clipped to each tile and kept when enough of the defect is
inside it, or when the visible part of a long (running) defect is still a clear stretch of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fabricdata.records import Box


@dataclass(frozen=True)
class Window:
    x0: int
    y0: int
    x1: int
    y1: int


def positions(length: int, size: int, overlap: float) -> list[tuple[int, int]]:
    if length <= size:
        return [(0, length)]
    step = size * (1 - overlap)
    n = math.ceil((length - size) / step) + 1
    stride = (length - size) / (n - 1)
    return [(round(i * stride), round(i * stride) + size) for i in range(n)]


def windows(width: int, height: int, size: int = 640, overlap: float = 0.2) -> list[Window]:
    return [Window(x0, y0, x1, y1) for y0, y1 in positions(height, size, overlap) for x0, x1 in positions(width, size, overlap)]


def clip(boxes: list[Box], win: Window, *, min_fraction: float = 0.4, long_px: float = 32, min_side: float = 3) -> list[Box]:
    """Boxes visible in ``win``, in the window's coordinates."""
    out = []
    for b in boxes:
        x0, y0 = max(b.x0, win.x0), max(b.y0, win.y0)
        x1, y1 = min(b.x1, win.x1), min(b.y1, win.y1)
        iw, ih = x1 - x0, y1 - y0
        if iw <= 0 or ih <= 0:
            continue
        area = max(b.w * b.h, 1e-6)
        visible = iw * ih / area
        running = max(iw, ih) >= long_px and min(iw, ih) >= min_side
        if visible >= min_fraction or running:
            out.append(Box(x0 - win.x0, y0 - win.y0, x1 - win.x0, y1 - win.y0, b.src_cls, b.cls))
    return out


def scaled(boxes: list[Box], s: float) -> list[Box]:
    return [Box(b.x0 * s, b.y0 * s, b.x1 * s, b.y1 * s, b.src_cls, b.cls) for b in boxes]
