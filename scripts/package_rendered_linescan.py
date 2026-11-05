"""Stage only source code/configuration for the private renderer-matched experiment."""

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stage = ROOT / "build/kaggle/round4"
code = stage / "code"
code.mkdir(parents=True, exist_ok=True)
files = list((ROOT / "ml").glob("linescan_*.py"))
files += list((ROOT / "ml/kaggle").glob("*linescan*.py"))
files += [
    p
    for folder in [ROOT / "ml/fabricdata", ROOT / "backend/threadeye"]
    for p in folder.rglob("*")
    if p.suffix in {".py", ".yaml"}
]
if (ROOT / "docs/model/round4/pilot-selection.json").is_file():
    files.append(ROOT / "docs/model/round4/pilot-selection.json")
files += [
    ROOT / "tools/simulator/make_roll_video.py",
    ROOT / "scripts/measure_impact.py",
    ROOT / "scripts/evaluate_roll_suite.py",
    ROOT / "docs/model/round3/preparation.json",
    ROOT / "docs/model/round3/frozen_videos-original.json",
    ROOT / "docs/model/round4/run.json",
    ROOT / "docs/model/round4/regression-hashes.json",
]
with zipfile.ZipFile(
    code / "round3_code.zip", "w", compression=zipfile.ZIP_DEFLATED
) as archive:
    for path in files:
        relative = path.relative_to(ROOT)
        if any(
            part.startswith(".") or "secret" in part or "db_url" in part
            for part in relative.parts
        ):
            raise ValueError("unsafe code input")
        archive.write(path, str(relative))
(code / "dataset-metadata.json").write_text(
    json.dumps(
        {
            "id": "shashwatanandi2004/threadeye-linescan-round4-code",
            "title": "threadeye-linescan-round4-code",
            "licenses": [{"name": "other"}],
        },
        indent=2,
    )
)
job = stage / "prepare-job"
job.mkdir(exist_ok=True)
shutil.copy(ROOT / "ml/kaggle/prepare_linescan_rendered.py", job / "run.py")
(job / "kernel-metadata.json").write_text(
    json.dumps(
        {
            "id": "shashwatanandi2004/threadeye-linescan-round4-prepare",
            "title": "threadeye-linescan-round4-prepare",
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": False,
            "enable_internet": True,
            "dataset_sources": [
                "shashwatanandi2004/threadeye-linescan-round4-code",
                "shashwatanandi2004/threadeye-linescan-domain-r2",
            ],
            "kernel_sources": ["shashwatanandi2004/threadeye-pack-dataset"],
        },
        indent=2,
    )
)
print("Private code/preparation staged", stage)
