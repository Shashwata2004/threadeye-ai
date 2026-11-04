"""Bundle existing frozen AITEX training originals/masks and the round-two configuration."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = ROOT / "build/kaggle/existing/packed-metadata/threadeye_packed/manifest.csv"
    staging = ROOT / "build/kaggle/round2"
    raw = staging / "raw"
    code = staging / "code"
    if code.exists():
        raise SystemExit("round-two staging already exists; refusing to overwrite")
    code.mkdir(parents=True)
    raw.mkdir()
    memberships: dict[str, set[str]] = {}
    for row in csv.DictReader(manifest.open()):
        if row["source"] == "aitex":
            memberships.setdefault(row["original"], set()).add(row["split"])
    records = []
    for original, splits in sorted(memberships.items()):
        if splits != {"train"}:
            continue
        source = ROOT / "data/external" / original
        kind = "defect" if "/Defect_images/" in original else "clean"
        relative = Path(kind) / source.name
        dest = raw / relative
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(source, dest)
        record = {"original": original, "kind": kind, "path": str(relative), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "masks": []}
        if kind == "defect":
            for mask in (ROOT / "data/external/aitex/extracted/Mask_images").glob(source.stem + "_mask*"):
                m = raw / "masks" / mask.name
                m.parent.mkdir(exist_ok=True)
                shutil.copy2(mask, m)
                record["masks"].append({"path": str(m.relative_to(raw)), "sha256": hashlib.sha256(m.read_bytes()).hexdigest()})
        records.append(record)
    (raw / "sources.json").write_text(json.dumps(records, indent=2))
    shutil.copy2(manifest, raw / "frozen_manifest.csv")
    with tarfile.open(code / "linescan_domain_sources.tar.gz", "w:gz", compresslevel=1) as archive:
        for path in raw.rglob("*"):
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(raw)))
    files = {"train.py": "ml/kaggle/train.py", "linescan_domain.py": "ml/linescan_domain.py",
             "make_roll_video.py": "tools/simulator/make_roll_video.py", "evaluate_rolls.py": "ml/kaggle/evaluate_rolls.py"}
    for target, source in files.items():
        shutil.copy2(ROOT / source, code / target)
    baseline = json.loads((ROOT / "build/kaggle/baseline-model/model_info.json").read_text())
    config = {"train": {"model": "s", "epochs": 8, "batch": 16, "train_budget_h": 4.0, "resume": False,
                        "init_from_previous": True, "checkpoint_name": "latest_ckpt.pth", "lr_scale": 0.1,
                        "yolox_commit": baseline["yolox_commit"], "domain_augment": 8000, "augmentation_seed": 202611042,
                        "mosaic_prob": 0, "mosaic_scale": [1, 1], "random_size": [20, 20], "degrees": 0, "hsv_prob": 0.2,
                        "baseline_threshold_guard": baseline["thresholds"],
                        "checkpoint_prefix": "models/training/yolox_s_linescan_round2_20261104",
                        "frozen_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}}
    (code / "targeted_params.json").write_text(json.dumps(config, indent=2))
    (code / "dataset-metadata.json").write_text(json.dumps({"id": "shashwatanandi2004/threadeye-linescan-domain-r2", "title": "threadeye-linescan-domain-r2", "licenses": [{"name": "other"}]}, indent=2))
    print("Frozen train originals:", len(records), "clean:", sum(r["kind"] == "clean" for r in records))
    print("Source bundle MB:", round((code / "linescan_domain_sources.tar.gz").stat().st_size / 1e6, 1))


if __name__ == "__main__":
    main()
