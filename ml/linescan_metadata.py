"""Repair only expected-score serialization; video pixels and truth files stay frozen."""

import copy
import hashlib
import json
from pathlib import Path


def normalized_metadata(payload):
    meta = json.loads(payload)
    expected = meta["expected_score"]
    value = round(
        expected["total_points"]
        * 3600
        / (meta["roll_length_yd"] * meta["fabric_width_in"]),
        2,
    )
    verdict = "PASS" if value <= expected["threshold"] else "FAIL"
    if expected["points_per_100_sq_yd"] == value and expected["verdict"] == verdict:
        return payload, None
    before = copy.deepcopy(expected)
    expected["points_per_100_sq_yd"] = value
    expected["verdict"] = verdict
    updated = json.dumps(meta, indent=2).encode()
    return updated, {
        "reason": "expected score must use serialized roll length and width; no video, geometry or truth edits",
        "before": before,
        "after": copy.deepcopy(expected),
        "original_sha256": hashlib.sha256(payload).hexdigest(),
        "normalized_sha256": hashlib.sha256(updated).hexdigest(),
    }


def normalized_manifest(frozen, metadata):
    result = copy.deepcopy(frozen)
    for split, records in result.items():
        for n, record in enumerate(records):
            name = f"{split}_{n}"
            payload = metadata[name]
            assert (
                hashlib.sha256(payload).hexdigest() == record["files"]["roll_meta.json"]
            ), "original frozen metadata differs"
            updated, repair = normalized_metadata(payload)
            if repair:
                record["files"]["roll_meta.json"] = hashlib.sha256(updated).hexdigest()
                record["metadata_repair"] = repair
    return result


def stage_videos(prepared, destination):
    prepared, destination = Path(prepared), Path(destination)
    frozen = json.loads((prepared / "frozen_videos.json").read_text())
    metadata = {}
    for split, records in frozen.items():
        for n, _record in enumerate(records):
            name = f"{split}_{n}"
            source = prepared / "videos" / name
            folder = destination / name
            folder.mkdir(parents=True, exist_ok=True)
            metadata[name] = (source / "roll_meta.json").read_bytes()
            for p in source.iterdir():
                target = folder / p.name
                if p.name == "roll_meta.json":
                    target.write_bytes(normalized_metadata(metadata[name])[0])
                elif not target.exists():
                    target.symlink_to(p.resolve())
    manifest = normalized_manifest(frozen, metadata)
    (destination / "frozen_videos.json").write_text(json.dumps(manifest, indent=2))
    return destination, manifest
