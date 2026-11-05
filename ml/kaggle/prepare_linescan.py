"""Private CPU data preparation; no training and no production database access."""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

print("ROUND3_PREPARATION_BOOT", flush=True)
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "-q",
        "install",
        "numpy",
        "pillow",
        "scipy",
        "opencv-python-headless",
        "pyyaml",
    ],
    check=True,
)
import shutil
import zipfile

root = Path("/kaggle/working/round3_code")
inputs = Path("/kaggle/input")
roots = (
    set(inputs.iterdir())
    | set(inputs.glob("datasets/*/*"))
    | set(inputs.glob("notebooks/*/*"))
)
bundles = list(
    {r / "round3_code.zip" for r in roots if (r / "round3_code.zip").is_file()}
)
if bundles:
    with zipfile.ZipFile(bundles[0]) as archive:
        archive.extractall(root)
else:
    modules = list(
        {
            r / suffix
            for r in roots
            for suffix in [
                "ml/linescan_targeted.py",
                "round3_code/ml/linescan_targeted.py",
            ]
            if (r / suffix).is_file()
        }
    )
    assert len(modules) == 1, "round3 code input missing or ambiguous"
    shutil.copytree(modules[0].parent.parent, root)
sys.path.insert(0, str(root / "ml"))
from linescan_targeted import prepare, prepare_videos

packed = next(
    r / suffix
    for r in roots
    for suffix in ["", "threadeye_packed"]
    if (r / suffix / "PACKED").is_file()
)
print("INPUTS_READY", packed, flush=True)
out = Path("/kaggle/working/prepared")
pools, report = prepare(packed, out)
prepare_videos(packed, out, pools, report["seed"])
for split in ["train", "val"]:
    with tarfile.open(out / f"{split}_prepared.tar", "w") as archive:
        for p in sorted((out / split).iterdir()):
            archive.add(p, arcname=p.name)
    # Keep only portable archives after freezing all video source pools.
for folder in ["train", "val", "original_tiles", "video_raw", "video_sources"]:
    shutil.rmtree(out / folder, ignore_errors=True)
shutil.rmtree(root)
print("PREPARATION_COMPLETE", json.dumps(report["splits"]), flush=True)
