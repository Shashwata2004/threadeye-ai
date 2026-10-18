"""Near-duplicate images across all sources (compilations re-upload AITEX, Moratuwa…): one group each.

A 64-bit difference hash per image; images within ``max_bits`` of each other are merged into one group, so
they can never be split between train and test. Candidate pairs come from 16-bit chunk buckets: with
max_bits ≤ 3, two near-identical hashes always share at least one chunk exactly (pigeonhole), so the
search stays fast for 100k images.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from fabricdata.records import ImageRecord


def dhash(path: Path) -> int:
    with Image.open(path) as im:
        px = np.asarray(im.convert("L").resize((9, 8), Image.Resampling.BILINEAR), dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    return int(sum(1 << i for i, b in enumerate(bits) if b))


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


def merge_near_duplicates(records: Sequence[ImageRecord], hashes: Sequence[int], max_bits: int = 3) -> int:
    """Rewrite ``record.group`` so near-duplicates share one group. Returns the number of merges."""
    if max_bits > 3:
        raise ValueError("chunk buckets only guarantee recall for max_bits <= 3")
    uf = _UnionFind()
    for r in records:
        uf.find(r.group)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, h in enumerate(hashes):
        for c in range(4):
            buckets[(c, (h >> (16 * c)) & 0xFFFF)].append(i)
    merges = 0
    seen: set[tuple[int, int]] = set()
    for members in buckets.values():
        for a_i, a in enumerate(members):
            for b in members[a_i + 1 :]:
                pair = (a, b)
                if pair in seen:
                    continue
                seen.add(pair)
                if (hashes[a] ^ hashes[b]).bit_count() <= max_bits and uf.find(records[a].group) != uf.find(
                    records[b].group
                ):
                    uf.union(records[a].group, records[b].group)
                    merges += 1
    for r in records:
        r.group = uf.find(r.group)
    return merges
