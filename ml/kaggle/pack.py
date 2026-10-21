"""Kaggle (CPU): pack the training dataset into one tar per split, so training attaches a few files.

Attaching the full build's 65,000 tile files to a notebook stalled the start of training for 45 minutes and
more (2026-10-21: notebooks without inputs started at once, the same notebook with the tiles did not). This
notebook reads the full build (threadeye_v1) and, if attached, a patch build (threadeye_patch, whose
annotations describe the whole dataset), and writes /kaggle/working/threadeye_packed/:
  {train,val,test}.tar         the tiles the annotations name, patch tiles over the full build's
  {train,val,test}/annotations.json, summary.json, manifest.csv, PACKED
Training (train.py) unpacks the tars onto the machine's local disk before it starts.
"""

import io
import json
import os
import shutil
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

print("pack.py started", flush=True)


INPUT = Path(os.environ.get("PACK_INPUT", "/kaggle/input"))  # the environment variables: for a local test
OUT = Path(os.environ.get("PACK_OUT", "/kaggle/working/threadeye_packed"))


def find_inputs(name: str, max_depth: int) -> list[Path]:
    """Matches of ``name`` at most ``max_depth`` folders below the inputs (never a walk through the tiles)."""
    return [p for d in range(max_depth + 1) for p in sorted(INPUT.glob("*/" * d + name))]


sys.path.insert(0, str(find_inputs("kaggle/steplog.py", 4)[0].parent))
import steplog  # time-stamped log with a heartbeat

DATA = find_inputs("threadeye_v1/summary.json", 3)[0].parent
PATCH = next((p.parent for p in find_inputs("threadeye_patch/PATCH", 3)), None)
ANN = PATCH or DATA
OUT.mkdir(parents=True, exist_ok=True)
steplog.log(f"full build {DATA}; patch {PATCH}")


def read(src: Path) -> bytes:
    return src.read_bytes()


for split in ("train", "val", "test"):
    steplog.phase(f"pack {split}")
    names = [im["file_name"] for im in json.loads((ANN / split / "annotations.json").read_text())["images"]]
    own = {f.name for f in (PATCH / split / "images").iterdir()} if PATCH and (PATCH / split / "images").exists() else set()
    srcs = [((PATCH if n in own else DATA) / split / "images" / n) for n in names]
    t = time.time()
    with tarfile.open(OUT / f"{split}.tar", "w") as tar, ThreadPoolExecutor(32) as ex:
        # Opening files on the input disk waits on the disk: read from 32 threads, write in order.
        for i, (n, data) in enumerate(zip(names, ex.map(read, srcs), strict=True)):
            info = tarfile.TarInfo(n)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            if (i + 1) % 5000 == 0:
                steplog.log(f"   {split}: {i + 1}/{len(names)} tiles, {(i + 1) / (time.time() - t):.0f}/s")
    (OUT / split).mkdir(exist_ok=True)
    shutil.copy(ANN / split / "annotations.json", OUT / split / "annotations.json")
    steplog.log(f"{split}: {len(names)} tiles ({len(own)} from the patch) in {(time.time() - t) / 60:.1f} min, "
                f"{(OUT / f'{split}.tar').stat().st_size / 1e9:.2f} GB")
for f in ("summary.json", "manifest.csv"):
    shutil.copy(ANN / f, OUT / f)
(OUT / "PACKED").write_text(f"full build {DATA}\npatch {PATCH}\n")
steplog.log(f"done in {(time.time() - steplog.T0) / 60:.1f} min")
