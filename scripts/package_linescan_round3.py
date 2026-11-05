"""Stage a secret-free private Kaggle code input and CPU preparation notebook."""

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stage = ROOT / "build/kaggle/round3"
code = stage / "code"
code.mkdir(parents=True, exist_ok=True)
files = [
    ROOT / "ml/linescan_targeted.py",
    ROOT / "tools/simulator/make_roll_video.py",
    ROOT / "scripts/measure_impact.py",
    ROOT / "scripts/evaluate_roll_suite.py",
]
files += [
    p for p in (ROOT / "ml/fabricdata").rglob("*") if p.suffix in {".py", ".yaml"}
]
files += [
    p for p in (ROOT / "backend/threadeye").rglob("*") if p.suffix in {".py", ".yaml"}
]
files += list((ROOT / "ml/kaggle").glob("*linescan*.py"))
files += list((ROOT / "ml").glob("linescan_release*.py"))
files += [ROOT / "ml/linescan_metadata.py", ROOT / "ml/linescan_training.py"]
if (ROOT / "docs/model/round3/pilots-recovery.json").is_file():
    files.append(ROOT / "docs/model/round3/pilots-recovery.json")
with zipfile.ZipFile(
    code / "round3_code.zip", "w", compression=zipfile.ZIP_DEFLATED
) as archive:
    for p in files:
        relative = p.relative_to(ROOT)
        if any(
            x.startswith(".") or "secret" in x or "db_url" in x for x in relative.parts
        ):
            raise ValueError("unsafe code input")
        archive.write(p, str(relative))
(code / "dataset-metadata.json").write_text(
    json.dumps(
        {
            "id": "shashwatanandi2004/threadeye-linescan-round3-code",
            "title": "threadeye-linescan-round3-code",
            "licenses": [{"name": "other"}],
        },
        indent=2,
    )
)
job = stage / "prepare-job"
job.mkdir(exist_ok=True)
shutil.copy(ROOT / "ml/kaggle/prepare_linescan.py", job / "run.py")
(job / "kernel-metadata.json").write_text(
    json.dumps(
        {
            "id": "shashwatanandi2004/threadeye-linescan-round3-prepare",
            "title": "threadeye-linescan-round3-prepare",
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": False,
            "enable_internet": True,
            "dataset_sources": ["shashwatanandi2004/threadeye-linescan-round3-code"],
            "kernel_sources": ["shashwatanandi2004/threadeye-pack-dataset"],
        },
        indent=2,
    )
)
print("Staged private code:", code, "preparation:", job)
