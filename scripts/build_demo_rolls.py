"""Build additional demo rolls using ONLY the existing Kaggle test-source manifest.

Existing rolls are never overwritten. Outputs are simulated regression scenarios,
not new independent fabrics or evidence of factory performance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    {"id": "demo_basic_roll", "fabric": "02", "partition": 0, "seed": 101, "density": 2.5, "noise": 0.8, "vignette": 0.08, "speed": 20},
    {"id": "demo_mixed_roll", "fabric": "02", "partition": 1, "seed": 203, "density": 6, "noise": 2, "vignette": 0.12, "speed": 20},
    {"id": "demo_challenge_roll", "fabric": "03", "partition": None, "seed": 307, "density": 8, "noise": 3.5, "vignette": 0.18, "speed": 25, "trim_left": 0.30},
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--external", type=Path, default=ROOT / "data/external")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    parser.add_argument("--sources", type=Path, default=ROOT / "build/demo_sources")
    parser.add_argument("--only", choices=[s["id"] for s in SCENARIOS])
    args = parser.parse_args()
    rows = [r for r in csv.DictReader(args.manifest.open()) if r["source"] == "aitex"]
    memberships: dict[str, set[str]] = {}
    for row in rows:
        memberships.setdefault(row["original"], set()).add(row["split"])
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    for scenario in SCENARIOS:
        if args.only and scenario["id"] != args.only:
            continue
        out = args.out / scenario["id"]
        if out.exists():
            raise SystemExit(f"refusing to overwrite {out}")
        source = args.sources / scenario["id"]
        if source.exists():
            raise SystemExit(f"source staging already exists: {source}")
        selected = []
        for original, splits in sorted(memberships.items()):
            path = args.external / original
            if splits != {"test"} or path.stem.split("_")[2] != scenario["fabric"]:
                continue
            if scenario["partition"] is not None and int(hashlib.sha256(path.name.encode()).hexdigest(), 16) % 2 != scenario["partition"]:
                continue
            if not path.is_file():
                raise SystemExit(f"source file missing: {path}")
            folder = "Defect_images" if "/Defect_images/" in original else "NODefect_images"
            target = source / folder / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(path.resolve())
            selected.append({"original": original, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            if folder == "Defect_images":
                for mask in (args.external / "aitex/extracted/Mask_images").glob(path.stem + "_mask*"):
                    dest = source / "Mask_images" / mask.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.symlink_to(mask.resolve())
        if not (source / "Defect_images").is_dir() or not (source / "NODefect_images").is_dir():
            raise SystemExit(f"not enough held-out sources for {scenario['id']}")
        cmd = [sys.executable, str(ROOT / "tools/simulator/make_roll_video.py"), "--source", "aitex",
               "--dataset", str(source), "--out", str(out), "--fabric-id", scenario["fabric"],
               "--linescan", "--seam-cut", "--frame-width", "3840", "--roll-length-m", "12",
               "--seed", str(scenario["seed"]), "--defects-per-10m", str(scenario["density"]),
               "--noise", str(scenario["noise"]), "--vignette", str(scenario["vignette"]),
               "--speed-m-min", str(scenario["speed"])]
        if "trim_left" in scenario:
            cmd += ["--trim-left", str(scenario["trim_left"])]
        subprocess.run(cmd, check=True)
        (out / "evaluation_manifest.json").write_text(json.dumps({
            "split": "test", "training_excluded": True, "source_groups": [f"aitex:fabric-{scenario['fabric']}"],
            "basis": "Original source paths occur only in test in the existing Kaggle packed manifest",
            "packed_manifest_sha256": manifest_hash, "scenario": scenario, "source_images": selected,
            "limitation": "New simulated arrangement of existing held-out images; not a new independent fabric or blind test",
        }, indent=2))
        meta_path = out / "roll_meta.json"
        meta = json.loads(meta_path.read_text())
        meta["fixture_note"] = f"{scenario['id']}: simulated AITEX test-source roll; not factory footage"
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"Ready: {out.name} ({meta['defect_count']} defects, {meta['frames']} frames)", flush=True)


if __name__ == "__main__":
    main()
