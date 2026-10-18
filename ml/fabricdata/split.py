"""Group-aware, per-source split: a group (see records.ImageRecord.group) lands in one split only.

Deterministic: groups are visited in an order fixed by a hash of (seed, group) and each goes to the split
furthest below its target share of that source's images. A group with any forced member (the AITEX demo
fabric → test) goes where it is forced.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Sequence

from fabricdata.records import ImageRecord

SPLITS = ("train", "val", "test")
DEFAULT_RATIOS = {"train": 0.8, "val": 0.1, "test": 0.1}


def _order(seed: int, group: str) -> str:
    return hashlib.sha1(f"{seed}:{group}".encode()).hexdigest()


def assign_splits(
    records: Sequence[ImageRecord], *, seed: int = 0, ratios: dict[str, float] | None = None
) -> dict[str, str]:
    """record.key → split."""
    ratios = ratios or DEFAULT_RATIOS
    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    for r in records:
        groups[r.group].append(r)
    by_source: dict[str, list[str]] = defaultdict(list)
    for g, members in groups.items():
        source = Counter(m.source for m in members).most_common(1)[0][0]
        by_source[source].append(g)

    out: dict[str, str] = {}
    for source, gs in by_source.items():
        total = sum(len(groups[g]) for g in gs)
        counts = dict.fromkeys(SPLITS, 0)
        forced = [g for g in gs if any(m.force_split for m in groups[g])]
        free = sorted((g for g in gs if g not in forced), key=lambda g: _order(seed, g))
        for g in forced:
            split = next(m.force_split for m in groups[g] if m.force_split)
            assert split in SPLITS, split
            counts[split] += len(groups[g])
            for m in groups[g]:
                out[m.key] = split
        for g in free:
            split = max(SPLITS, key=lambda s: ratios[s] * total - counts[s])
            counts[split] += len(groups[g])
            for m in groups[g]:
                out[m.key] = split
    return out
