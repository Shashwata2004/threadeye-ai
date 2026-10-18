"""Kaggle step 1: download the two big sources whose layout we have not seen yet (ZJU-Leaper, RAW-FABRID)
and write their folder structure to /kaggle/working/layout.txt, so their readers can be written.

Runs on Kaggle with internet on. Raw files go to /kaggle/tmp (large, not saved); only the report is kept.
"""

import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

TMP = Path("/kaggle/tmp")
OUT = Path("/kaggle/working")
TMP.mkdir(parents=True, exist_ok=True)
report: list[str] = []


def sh(cmd: str) -> None:
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


def log(line: str) -> None:
    print(line, flush=True)
    report.append(line)


def layout(root: Path, depth: int = 4, samples: int = 4) -> None:
    for d in sorted({p.parent for p in root.rglob("*") if p.is_file()}):
        rel = d.relative_to(root)
        if len(rel.parts) > depth:
            continue
        files = sorted(p for p in d.iterdir() if p.is_file())
        exts = Counter(p.suffix.lower() for p in files)
        size = sum(p.stat().st_size for p in files) / 1e6
        log(f"  {rel}/  {len(files)} files {size:.0f} MB {dict(exts)}  e.g. {[p.name for p in files[:samples]]}")
        for p in files:
            if p.suffix.lower() in {".json", ".txt", ".csv", ".yaml", ".xml"} and p.stat().st_size < 50_000_000:
                head = p.read_text(errors="replace")[:600].replace("\n", " | ")
                log(f"    {p.name}: {head}")
                break


def disk() -> None:
    st = os.statvfs("/kaggle/tmp")
    log(f"disk free: {st.f_bavail * st.f_frsize / 1e9:.1f} GB")


disk()
sh(f"{sys.executable} -m pip -q install gdown py7zr")

# ZJU-Leaper: one .7z on Google Drive (bit.ly/zjuleaper)
zju = TMP / "ZJU-Leaper.7z"
sh(f"gdown --fuzzy 'https://drive.google.com/file/d/1zzoU3Aj21V62GWS8LBm217TsE5uFeMVB/view' -O {zju}")
sh(f"7z x -y -o{TMP / 'zju'} {zju} > /dev/null || {sys.executable} -c \"import py7zr; py7zr.SevenZipFile('{zju}').extractall('{TMP / 'zju'}')\"")
zju.unlink()
log("## ZJU-Leaper")
layout(TMP / "zju")
disk()

# RAW-FABRID: a zip inside the Mendeley "download all" zip
raw = TMP / "rawfabrid_outer.zip"
sh(f"curl -sSL -A 'curl/8.5.0' -o {raw} 'https://data.mendeley.com/public-api/zip/db6g85xsyg/download/1'")
with zipfile.ZipFile(raw) as z:
    inner = [n for n in z.namelist() if n.lower().endswith(".zip")][0]
    z.extract(inner, TMP / "rawfabrid_inner")
raw.unlink()
inner_path = next((TMP / "rawfabrid_inner").rglob("*.zip"))
with zipfile.ZipFile(inner_path) as z:
    z.extractall(TMP / "rawfabrid")
inner_path.unlink()
log("## RAW-FABRID")
layout(TMP / "rawfabrid")
disk()

(OUT / "layout.txt").write_text("\n".join(report))
print(json.dumps({"lines": len(report)}))
