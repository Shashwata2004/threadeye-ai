"""Kaggle step 2: download every source, lay it out like data/external/ on the laptop, and build the
dataset with ml/build_dataset.py into /kaggle/working/threadeye_v1 (kept as this notebook's output, which
the training notebook reads).

Inputs: the private dataset "threadeye-ml-code" (ml/ and params.json with the Tianchi export link).
Internet on, no GPU needed.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

CODE = next(Path("/kaggle/input").rglob("build_dataset.py")).parent  # .../ml
PARAMS = json.loads(next(Path("/kaggle/input").rglob("params.json")).read_text())
EXT = Path("/kaggle/tmp/external")
OUT = Path("/kaggle/working/threadeye_v1")
T0 = time.time()


def sh(cmd: str) -> None:
    print(f"[{time.time() - T0:6.0f}s] + {cmd[:160]}", flush=True)
    # Unbuffered, so the steps' own progress lines reach the live log (kernels logs -f) as they happen.
    subprocess.run(cmd, shell=True, check=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sh(f"curl -sSL --retry 5 -A 'curl/8.5.0' -o '{dest}' '{url}'")
    return dest


def unzip(zf: Path, to: Path, members_prefix: str | None = None) -> None:
    to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zf) as z:
        names = [n for n in z.namelist() if members_prefix is None or n.startswith(members_prefix)]
        z.extractall(to, names)
    zf.unlink()


def un7z(f: Path, to: Path) -> None:
    sh(f"7z x -y -o'{to}' '{f}' > /dev/null")
    f.unlink()


sh(f"{sys.executable} -m pip -q install gdown")

# AITEX: three .7z files
for part in ("Defect_images", "Mask_images", "NODefect_images"):
    un7z(fetch(f"https://www.aitex.es/wp-content/uploads/2019/07/{part}.7z", EXT / f"aitex/raw/{part}.7z"),
         EXT / "aitex/extracted")

# FabricSpotDefect (Mendeley)
unzip(fetch("https://data.mendeley.com/public-api/zip/6574nhzm8x/download/1", EXT / "fabricspotdefect/raw.zip"),
      EXT / "fabricspotdefect/extracted")

# Moratuwa compilation (Mendeley): the defect folders and the defect-free folder
unzip(fetch("https://data.mendeley.com/public-api/zip/663j22s43c/download/3", EXT / "moratuwa/raw.zip"),
      EXT / "moratuwa/extracted", "Fabric Defects Dataset/Fabric Defect Dataset/")

# FD Dataset (figshare)
un7z(fetch("https://ndownloader.figshare.com/files/45460297", EXT / "fd_figshare/raw/FD_Dataset.7z"),
     EXT / "fd_figshare/extracted")

# Garment defects (Mendeley): a Roboflow COCO zip inside the Mendeley zip
unzip(fetch("https://data.mendeley.com/public-api/zip/y62b4pfyz2/download/1", EXT / "garment_defects/raw.zip"),
      EXT / "garment_defects/extracted")
inner = next((EXT / "garment_defects/extracted").rglob("*.zip"))
unzip(inner, EXT / "garment_defects/extracted/inner")

# Tianchi 2019 Guangdong round 1 (Roboflow mirror, version 3 = raw images)
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
(EXT / "zju_leaper").mkdir(parents=True, exist_ok=True)
if zju_in is not None:
    (EXT / "zju_leaper" / "ZJU-Leaper").symlink_to(zju_in)
    print("ZJU-Leaper from the Kaggle mirror:", zju_in, flush=True)
else:
    zju = EXT / "zju_leaper/ZJU-Leaper.7z"
    try:
        sh(f"gdown --fuzzy 'https://drive.google.com/file/d/1zzoU3Aj21V62GWS8LBm217TsE5uFeMVB/view' -O '{zju}'")
        un7z(zju, EXT / "zju_leaper")
    except subprocess.CalledProcessError:
        print("!! ZJU-Leaper download refused by Google Drive: building without it", flush=True)
        shutil.rmtree(EXT / "zju_leaper", ignore_errors=True)

# RAW-FABRID (Mendeley): a zip inside the zip
outer = fetch("https://data.mendeley.com/public-api/zip/db6g85xsyg/download/1", EXT / "raw_fabrid/outer.zip")
unzip(outer, EXT / "raw_fabrid/outer")
unzip(next((EXT / "raw_fabrid/outer").rglob("*.zip")), EXT / "raw_fabrid")

# WFDD: a Kaggle dataset attached to this notebook (read-only input), linked into the external layout.
wfdd_in = next(Path("/kaggle/input").rglob("WFDD"), None)
if wfdd_in is not None:
    (EXT / "wfdd").mkdir(parents=True, exist_ok=True)
    (EXT / "wfdd" / "WFDD").symlink_to(wfdd_in)

# Fabric Stain Dataset: a Kaggle dataset attached to this notebook. Its two folders both number from 1, so the
# images (and their YOLO .txt labels) are linked flat as <folder>_<name> (fabricdata.sources.read_fabric_stain).
stain_in = next((p.parent for p in Path("/kaggle/input").rglob("images") if (p / "stain").is_dir()), None)
if stain_in is not None:
    flat = EXT / "fabric_stain/flat"
    flat.mkdir(parents=True, exist_ok=True)
    for folder in ("stain", "defect_free"):
        for img in sorted((stain_in / "images" / folder).iterdir()):
            (flat / f"{folder}_{img.name}").symlink_to(img)
            label = stain_in / "annotations" / folder / f"{img.stem}.txt"
            if label.exists():
                (flat / f"{folder}_{img.stem}.txt").symlink_to(label)
    print("Fabric Stain:", len(list(flat.glob("*.txt"))), "labels", flush=True)
else:
    print("!! Fabric Stain dataset not attached: building without it", flush=True)

# A look at the files whose details we have not seen yet (for the mapping notes).
if (EXT / "zju_leaper").exists():
    zju_base = zju_in or next((EXT / "zju_leaper").rglob("ImageSets")).parent
    defective = next(x for x in sorted((zju_base / "Annotations/xmls").glob("*.xml"))[::97]
                     if "<defective>1" in x.read_text())
    print("ZJU defective xml:", defective.read_text()[:800])
    print("ZJU statistic.csv:", (zju_base / "statistic.csv").read_text()[:1500])
raw_coco = json.loads(next((EXT / "raw_fabrid").rglob("RAW_FABRID_HighRes_COCO.json")).read_text())
print("RAW-FABRID categories:", raw_coco["categories"], "annotations:", len(raw_coco["annotations"]))
print("RAW-FABRID metadata:", next((EXT / "raw_fabrid").rglob("RAW_FABRID_HighRes_Metadata.csv")).read_text()[:800])
sh("df -h /kaggle/tmp /kaggle/working | cat")

# Non-defects (stickers, loose threads, wrinkles, hands) drawn on tiles of the sources above. Hands are cut
# out of EgoHands (CC BY 4.0), a Kaggle dataset attached to this notebook; without it they are cartoon only.
ego = next((p.parent for pat in ("*/_LABELLED_SAMPLES", "*/*/_LABELLED_SAMPLES", "*/*/*/_LABELLED_SAMPLES",
                                  "*/*/*/*/_LABELLED_SAMPLES") for p in Path("/kaggle/input").glob(pat)), None)
hands = EXT / "hand_cutouts"
if ego is not None:
    sh(f"{sys.executable} {CODE / 'scripts/egohands_cutouts.py'} '{ego}' '{hands}' --max 2000")
else:
    print("!! EgoHands not attached: cartoon hands only", flush=True)
sh(" ".join([sys.executable, str(CODE / "synth_nuisance.py"), "--external", str(EXT), "--n",
             str(PARAMS.get("synth_nuisance", 4000)), "--tianchi-images", str(EXT / "tianchi/images"),
             *(["--hands", str(hands)] if ego is not None else [])]))

caps = PARAMS.get("caps", [])
sh(" ".join([sys.executable, str(CODE / "build_dataset.py"), "--external", str(EXT), "--out", str(OUT),
             "--tianchi-images", str(EXT / "tianchi/images"), *[f"--cap {c}" for c in caps]]))
sh(f"du -sh {OUT} && ls {OUT}")
print(f"done in {(time.time() - T0) / 60:.1f} min")
