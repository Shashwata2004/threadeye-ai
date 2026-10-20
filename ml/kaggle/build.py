"""Kaggle step 2: download the sources, lay them out like data/external/ on the laptop, and build the
dataset with ml/build_dataset.py (kept as this notebook's output, which the training notebook reads).

params.json "build" chooses what is built:
- {} — the full dataset into /kaggle/working/threadeye_v1 (every source, the non-defect tiles, hours);
- {"patch": ["fabricspotdefect", ...]} — only those sources again, on top of a full build attached as an input
  (notebook threadeye-patch-dataset), into /kaggle/working/threadeye_patch: minutes, for a fix in one source;
- "smoke": N — N images per source and kind, a few non-defect tiles: every step runs, each one's time is
  measured, before a long build.

Inputs: the private dataset "threadeye-ml-code" (ml/ and params.json with the Tianchi export link).
Internet on, no GPU needed.
"""

import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

CODE = next(Path("/kaggle/input").rglob("build_dataset.py")).parent  # .../ml
sys.path.insert(0, str(CODE / "kaggle"))
sys.path.insert(0, str(CODE))
import steplog  # time-stamped log with a heartbeat; every step has a time limit

from fabricdata.dedupe import COPY_PRONE

PARAMS = json.loads(next(Path("/kaggle/input").rglob("params.json")).read_text())
BUILD = PARAMS.get("build", {})
PATCH = sorted(BUILD.get("patch", []))
SMOKE = int(BUILD.get("smoke", 0))
EXT = Path("/kaggle/tmp/external")
OUT = Path("/kaggle/working/threadeye_patch" if PATCH else "/kaggle/working/threadeye_v1")
BASE = None
if PATCH:
    BASE = next((p.parent for p in Path("/kaggle/input").rglob("threadeye_v1/summary.json")), None)
    if BASE is None:
        raise SystemExit("patch build: attach a full build (threadeye-build-dataset) as an input")
    steplog.log(f"patch build of {PATCH} on top of {BASE}")
NEEDED = set(PATCH) | (COPY_PRONE if set(PATCH) & COPY_PRONE else set()) if PATCH else None
"""Sources a patch build reads: the patched ones and, for a copy-prone one, every source its copies may be in."""


def wanted(source: str) -> bool:
    return NEEDED is None or source in NEEDED


T0 = time.time()


def sh(cmd: str, name: str | None = None, limit_min: float = 20) -> None:
    steplog.step(name or cmd.split()[0], cmd, limit_min)


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sh(f"curl -sSL --retry 5 -A 'curl/8.5.0' -o '{dest}' '{url}'", f"download {dest.relative_to(EXT)}", 20)
    return dest


def unzip(zf: Path, to: Path, members_prefix: str | None = None) -> None:
    steplog.phase(f"unzip {zf.relative_to(EXT)}")
    to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zf) as z:
        names = [n for n in z.namelist() if members_prefix is None or n.startswith(members_prefix)]
        z.extractall(to, names)
    zf.unlink()


def un7z(f: Path, to: Path) -> None:
    sh(f"7z x -y -o'{to}' '{f}' > /dev/null", f"7z {f.name}", 20)
    f.unlink()


sh(f"{sys.executable} -m pip -q install gdown")

# AITEX: three .7z files
if wanted("aitex"):
    for part in ("Defect_images", "Mask_images", "NODefect_images"):
        un7z(fetch(f"https://www.aitex.es/wp-content/uploads/2019/07/{part}.7z", EXT / f"aitex/raw/{part}.7z"),
             EXT / "aitex/extracted")

# FabricSpotDefect (Mendeley)
if wanted("fabricspotdefect"):
    unzip(fetch("https://data.mendeley.com/public-api/zip/6574nhzm8x/download/1",
                EXT / "fabricspotdefect/raw.zip"), EXT / "fabricspotdefect/extracted")

# Moratuwa compilation (Mendeley): the defect folders and the defect-free folder
if wanted("moratuwa"):
    unzip(fetch("https://data.mendeley.com/public-api/zip/663j22s43c/download/3", EXT / "moratuwa/raw.zip"),
          EXT / "moratuwa/extracted", "Fabric Defects Dataset/Fabric Defect Dataset/")

# FD Dataset (figshare)
if wanted("fd_figshare"):
    un7z(fetch("https://ndownloader.figshare.com/files/45460297", EXT / "fd_figshare/raw/FD_Dataset.7z"),
         EXT / "fd_figshare/extracted")

# Garment defects (Mendeley): a Roboflow COCO zip inside the Mendeley zip
if wanted("garment_defects"):
    unzip(fetch("https://data.mendeley.com/public-api/zip/y62b4pfyz2/download/1",
                EXT / "garment_defects/raw.zip"), EXT / "garment_defects/extracted")
    inner = next((EXT / "garment_defects/extracted").rglob("*.zip"))
    unzip(inner, EXT / "garment_defects/extracted/inner")

# Tianchi 2019 Guangdong round 1 (Roboflow mirror, version 3 = raw images)
if wanted("tianchi"):
    unzip(fetch(PARAMS["tianchi_link"], EXT / "tianchi/raw.zip"), EXT / "tianchi/images")
    for ann in (EXT / "tianchi/images").glob("*/_annotations.coco.json"):
        dest = EXT / "tianchi/annotations" / ann.parent.name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(ann, dest / ann.name)

# ZJU-Leaper: preferably the unpacked Kaggle mirror attached to this notebook (bnhphan/zju-dataset), linked in.
# Otherwise Google Drive, which refuses a file that was fetched many times in a day ("many accesses"): then
# the build goes on without ZJU-Leaper rather than failing.
zju_in = next((p.parent for pat in ("*/ImageSets", "*/*/ImageSets", "*/*/*/ImageSets", "*/*/*/*/ImageSets")
               for p in Path("/kaggle/input").glob(pat)
               if (p.parent / "Images").is_dir() and (p.parent / "Annotations/xmls").is_dir()), None)
if not wanted("zju_leaper"):
    pass
elif zju_in is not None:
    (EXT / "zju_leaper").mkdir(parents=True, exist_ok=True)
    (EXT / "zju_leaper" / "ZJU-Leaper").symlink_to(zju_in)
    print("ZJU-Leaper from the Kaggle mirror:", zju_in, flush=True)
else:
    (EXT / "zju_leaper").mkdir(parents=True, exist_ok=True)
    zju = EXT / "zju_leaper/ZJU-Leaper.7z"
    try:
        sh(f"gdown --fuzzy 'https://drive.google.com/file/d/1zzoU3Aj21V62GWS8LBm217TsE5uFeMVB/view' -O '{zju}'")
        un7z(zju, EXT / "zju_leaper")
    except subprocess.CalledProcessError:
        print("!! ZJU-Leaper download refused by Google Drive: building without it", flush=True)
        shutil.rmtree(EXT / "zju_leaper", ignore_errors=True)

# RAW-FABRID (Mendeley): a zip inside the zip
if wanted("raw_fabrid"):
    outer = fetch("https://data.mendeley.com/public-api/zip/db6g85xsyg/download/1", EXT / "raw_fabrid/outer.zip")
    unzip(outer, EXT / "raw_fabrid/outer")
    unzip(next((EXT / "raw_fabrid/outer").rglob("*.zip")), EXT / "raw_fabrid")

# WFDD: a Kaggle dataset attached to this notebook (read-only input), linked into the external layout.
wfdd_in = next(Path("/kaggle/input").rglob("WFDD"), None)
if wfdd_in is not None and wanted("wfdd"):
    (EXT / "wfdd").mkdir(parents=True, exist_ok=True)
    (EXT / "wfdd" / "WFDD").symlink_to(wfdd_in)

# Fabric Stain Dataset: a Kaggle dataset attached to this notebook. Its two folders both number from 1, so the
# images (and their YOLO .txt labels) are linked flat as <folder>_<name> (fabricdata.sources.read_fabric_stain).
stain_in = next((p.parent for p in Path("/kaggle/input").rglob("images") if (p / "stain").is_dir()), None)
if stain_in is not None and wanted("fabric_stain"):
    flat = EXT / "fabric_stain/flat"
    flat.mkdir(parents=True, exist_ok=True)
    for folder in ("stain", "defect_free"):
        for img in sorted((stain_in / "images" / folder).iterdir()):
            (flat / f"{folder}_{img.name}").symlink_to(img)
            label = stain_in / "annotations" / folder / f"{img.stem}.txt"
            if label.exists():
                (flat / f"{folder}_{img.stem}.txt").symlink_to(label)
    print("Fabric Stain:", len(list(flat.glob("*.txt"))), "labels", flush=True)
elif wanted("fabric_stain"):
    print("!! Fabric Stain dataset not attached: building without it", flush=True)

sh("df -h /kaggle/tmp /kaggle/working | cat")
caps = PARAMS.get("caps", [])
smoke = [f"--smoke {SMOKE}"] if SMOKE else []
tianchi = ["--tianchi-images", str(EXT / "tianchi/images")]
if PATCH:
    sh(" ".join([sys.executable, str(CODE / "build_dataset.py"), "--external", str(EXT), "--out", str(OUT), *tianchi,
                 *[f"--cap {c}" for c in caps], *smoke, "--patch-base", str(BASE), "--patch", *PATCH]),
       "patch tiles", 60)
    sh(f"du -sh {OUT} && ls {OUT}")
    steplog.log(f"done in {(time.time() - T0) / 60:.1f} min")
    raise SystemExit(0)

# Non-defects (stickers, loose threads, wrinkles, hands) drawn on tiles of the sources above. Hands are cut
# out of EgoHands (CC BY 4.0), a Kaggle dataset attached to this notebook; without it they are cartoon only.
ego = next((p.parent for pat in ("*/_LABELLED_SAMPLES", "*/*/_LABELLED_SAMPLES", "*/*/*/_LABELLED_SAMPLES",
                                  "*/*/*/*/_LABELLED_SAMPLES") for p in Path("/kaggle/input").glob(pat)), None)
hands = EXT / "hand_cutouts"
if ego is not None:
    sh(f"{sys.executable} {CODE / 'scripts/egohands_cutouts.py'} '{ego}' '{hands}' --max {100 if SMOKE else 2000}",
       "hand cut-outs", 45)
else:
    print("!! EgoHands not attached: cartoon hands only", flush=True)
sh(" ".join([sys.executable, str(CODE / "synth_nuisance.py"), "--external", str(EXT), "--n",
             str(100 if SMOKE else PARAMS.get("synth_nuisance", 4000)), *tianchi,
             *(["--hands", str(hands)] if ego is not None else [])]), "non-defect tiles", 60)

sh(" ".join([sys.executable, str(CODE / "build_dataset.py"), "--external", str(EXT), "--out", str(OUT), *tianchi,
             *[f"--cap {c}" for c in caps], *smoke]), "dataset tiles", 150)
sh(f"du -sh {OUT} && ls {OUT}")
steplog.log(f"done in {(time.time() - T0) / 60:.1f} min")
