"""Check/promote a gate-passing local candidate, or restore its complete model-directory backup.

Stop the demo before --activate or --rollback. Dry-run checking is the default. No cloud model,
business decision or historical inspection is modified by this command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "ml")]
from linescan_release import release_reasons
from threadeye.services.model_activation import (
    ACTIVATION,
    MODEL_FILES,
    validated_local_model,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offline():
    for port in (3000, 8099):
        with socket.socket() as connection:
            connection.settimeout(0.2)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise ValueError("stop the demo before changing its model")


def replace(directory, prepared):
    previous = directory.with_name(directory.name + ".swap-" + uuid.uuid4().hex)
    directory.rename(previous)
    try:
        prepared.rename(directory)
    except BaseException:
        previous.rename(directory)
        raise
    shutil.rmtree(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path)
    parser.add_argument(
        "--result", type=Path, default=ROOT / "docs/model/round3/result.json"
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "data/model")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    if args.rollback:
        offline()
        source = args.rollback
        hashes = json.loads((source / "backup-hashes.json").read_text())
        for name, expected in hashes.items():
            if sha(source / name) != expected:
                raise ValueError("backup hash differs: " + name)
        prepared = args.directory.with_name(
            args.directory.name + ".restore-" + uuid.uuid4().hex
        )
        shutil.copytree(source, prepared)
        (prepared / "backup-hashes.json").unlink()
        replace(args.directory, prepared)
        print("Restored previous model", sha(args.directory / "threadeye_s.onnx"))
        return
    if args.model is None:
        parser.error("--model is required unless rolling back")
    result = json.loads(args.result.read_text())
    reasons = release_reasons(
        result["regression"]["rolls"],
        result["validation"]["metrics"],
        result["final_test"]["metrics"],
        [
            r["cpu_ratio"]
            for group in ["regression", "validation", "final_test"]
            for r in result[group].get("rolls", [])
        ],
        native_validation=result["native_validation"],
    )
    if reasons or not result["release_passed"]:
        raise ValueError("candidate did not pass release gates: " + str(reasons))
    if (
        sha(args.model) != result["model_sha256"]
        or sha(args.model.with_name("model_info.json")) != result["card_sha256"]
    ):
        raise ValueError("candidate differs from the evaluated model/card")
    for name in MODEL_FILES:
        if not args.model.with_name(name).is_file():
            raise ValueError("candidate artifact missing: " + name)
    print("Release gates and candidate identity verified")
    if not args.activate:
        return
    offline()
    backup = (
        ROOT
        / "build/kaggle/round3/model-backups"
        / sha(args.directory / "threadeye_s.onnx")
    )
    if not backup.exists():
        shutil.copytree(args.directory, backup)
        (backup / "backup-hashes.json").write_text(
            json.dumps(
                {
                    str(p.relative_to(backup)): sha(p)
                    for p in backup.rglob("*")
                    if p.is_file()
                },
                indent=2,
            )
        )
    prepared = args.directory.with_name(
        args.directory.name + ".next-" + uuid.uuid4().hex
    )
    prepared.mkdir()
    for name in MODEL_FILES:
        shutil.copy(args.model.with_name(name), prepared / name)
    marker = {
        "release_passed": True,
        "at_utc": datetime.now(UTC).isoformat(),
        "report_sha256": sha(args.result),
        "sha256": {name: sha(prepared / name) for name in MODEL_FILES},
        "backup": str(backup),
    }
    (prepared / ACTIVATION).write_text(json.dumps(marker, indent=2))
    validated_local_model(prepared)
    replace(args.directory, prepared)
    (ROOT / "docs/model/round3/activation.json").write_text(
        json.dumps(marker, indent=2)
    )
    print("Activated local candidate; restart make demo. Backup:", backup)


if __name__ == "__main__":
    main()
