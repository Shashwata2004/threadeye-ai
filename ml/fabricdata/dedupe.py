"""Copies of the same image in different sources (compilations re-upload AITEX, Moratuwa…): one group each.

Only pairs from *different* sources are compared: copies inside one source are grouped by its reader
(Roboflow augmentations, photo sessions). Comparing plain fabrics within a source would merge different
images that merely look alike (a 64-bit hash of a uniform weave is almost noise).

Two images are copies when their aspect ratios agree (re-uploads keep the shape), their 64-bit difference
hashes are within 3 bits and their 256-bit hashes within 12 bits. Candidates come from 16-bit chunk
buckets of the 64-bit hash: within 3 bits, two hashes always share a chunk (pigeonhole).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from fabricdata.records import ImageRecord

COPY_PRONE = {"aitex", "moratuwa", "fabricspotdefect", "fd_figshare", "garment_defects", "tianchi"}
"""Sources that compilations re-upload. ZJU-Leaper, RAW-FABRID and WFDD are not in any compilation, and
their tens of thousands of plain-weave images share near-identical hashes: comparing them made the first
full build run for hours (buckets of thousands of members, all pairs compared)."""
MAX_BUCKET = 5000
"""A bucket bigger than this is a degenerate hash value (flat images), not a set of copies: skipped."""


@dataclass(frozen=True)
class Fingerprint:
    aspect: float
    h64: int
    h256: int


def _dhash(gray: Image.Image, side: int) -> int:
    px = np.asarray(gray.resize((side + 1, side), Image.Resampling.BILINEAR), dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    return int(sum(1 << i for i, b in enumerate(bits) if b))


def fingerprint(path: Path) -> Fingerprint:
    with Image.open(path) as im:
        gray = im.convert("L")
        return Fingerprint(im.width / max(im.height, 1), _dhash(gray, 8), _dhash(gray, 16))


def dhash(path: Path) -> int:
    return fingerprint(path).h64


def same_image(a: Fingerprint, b: Fingerprint) -> bool:
    return (
        abs(a.aspect - b.aspect) <= 0.03 * max(a.aspect, b.aspect)
        and (a.h64 ^ b.h64).bit_count() <= 3
        and (a.h256 ^ b.h256).bit_count() <= 12
    )


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def merge_near_duplicates(records: Sequence[ImageRecord], prints: Sequence[Fingerprint]) -> int:
    """Rewrite ``record.group`` so cross-source copies share one group. Returns the number of merges."""
    uf = _UnionFind()
    for r in records:
        uf.find(r.group)
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for i, fp in enumerate(prints):
        if records[i].source not in COPY_PRONE:
            continue
        shape = round(fp.aspect * 20)  # re-uploads keep the aspect ratio
        for c in range(4):
            buckets[(shape, c, (fp.h64 >> (16 * c)) & 0xFFFF)].append(i)
    merges = 0
    seen: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) > MAX_BUCKET:
            continue
        for a_i, a in enumerate(members):
            for b in members[a_i + 1 :]:
                if records[a].source == records[b].source or (a, b) in seen:
                    continue
                seen.add((a, b))
                if same_image(prints[a], prints[b]) and uf.find(records[a].group) != uf.find(records[b].group):
                    uf.union(records[a].group, records[b].group)
                    merges += 1
    for r in records:
        r.group = uf.find(r.group)
    return merges
