"""Verify the bundled demo videos and stable trained model, using only Python's standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "data/demo-assets.json").read_text())
    failed = False
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("asset path escapes project root")
        if not path.is_file():
            print(f"MISSING {item['path']}")
            failed = True
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if path.stat().st_size != item["bytes"] or digest.hexdigest() != item["sha256"]:
            print(f"MISMATCH {item['path']}")
            failed = True
        else:
            print(f"OK {item['path']}")
    if failed:
        print("Restore the bundled assets from the same Git revision, then run make assets-check again.")
    else:
        print("All bundled demo videos and the stable model are ready.")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
