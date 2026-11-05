"""Private CPU preparation using existing packed data and full frozen AITEX training originals."""

import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

print("RENDERED_PREPARATION_BOOT", flush=True)
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
inputs = Path("/kaggle/input")
roots = (
    set(inputs.iterdir())
    | set(inputs.glob("datasets/*/*"))
    | set(inputs.glob("notebooks/*/*"))
)
code = Path("/kaggle/working/code")
bundles = [r / "round3_code.zip" for r in roots if (r / "round3_code.zip").is_file()]
if bundles:
    assert len(bundles) == 1
    with zipfile.ZipFile(bundles[0]) as archive:
        archive.extractall(code)
else:
    modules = [
        r / suffix
        for r in roots
        for suffix in ["ml/linescan_rendered.py", "round3_code/ml/linescan_rendered.py"]
        if (r / suffix).is_file()
    ]
    assert len(modules) == 1
    shutil.copytree(modules[0].parent.parent, code)
sys.path.insert(0, str(code / "ml"))
from linescan_targeted import prepare

packed = next(
    r / suffix
    for r in roots
    for suffix in ["", "threadeye_packed"]
    if (r / suffix / "PACKED").is_file()
)
sources = [
    r / "linescan_domain_sources.tar.gz"
    for r in roots
    if (r / "linescan_domain_sources.tar.gz").is_file()
]
full = Path("/kaggle/tmp/full_aitex")
if sources:
    assert len(sources) == 1
    full.mkdir(parents=True)
    subprocess.run(
        ["tar", "-xzf", str(sources[0]), "-C", str(full), "--no-same-owner"], check=True
    )
else:
    candidates = [
        r / suffix
        for r in roots
        for suffix in ["", "linescan_domain_sources"]
        if (r / suffix / "sources.json").is_file()
    ]
    assert len(candidates) == 1, "existing full AITEX training bundle missing"
    full = candidates[0]
old = json.loads((code / "docs/model/round3/preparation.json").read_text())
protocol = json.loads((code / "docs/model/round4/run.json").read_text())
assert (
    old["manifest_sha256"]
    == __import__("hashlib").sha256((packed / "manifest.csv").read_bytes()).hexdigest()
)
out = Path("/kaggle/working/prepared")
_, report = prepare(
    packed,
    out,
    seed=202611044,
    rendered=True,
    full_aitex=full,
    reserved_groups=old["reserved_groups"],
    train_count=protocol.get("train_images", 10000),
    val_count=protocol.get("validation_images", 1000),
)
shutil.copy(
    code / "docs/model/round3/frozen_videos-original.json", out / "frozen_videos.json"
)
for split in ["train", "val"]:
    with tarfile.open(out / f"{split}_prepared.tar", "w") as archive:
        for path in sorted((out / split).iterdir()):
            archive.add(path, arcname=path.name)
    shutil.rmtree(out / split)
shutil.rmtree(out / "original_tiles")
shutil.rmtree(out / "renderer_sources")
shutil.rmtree(code)
print("RENDERED_PREPARATION_COMPLETE", json.dumps(report["splits"]), flush=True)
