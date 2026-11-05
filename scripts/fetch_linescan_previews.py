"""Read only metadata and selected labelled examples from private prepared TAR streams.

Avoids downloading the entire training corpus onto a space-constrained laptop. Signed download
URLs stay in memory and never enter logs or artifacts. Run with the existing Kaggle CLI environment.
"""

import argparse
import json
import tarfile
from pathlib import Path

import requests
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (
    ApiListKernelSessionOutputRequest,
)


def select_examples(data, provenance):
    anns = {}
    prov = {p["file"]: p for p in provenance}
    for a in data["annotations"]:
        anns.setdefault(a["image_id"], []).append(a)
    selected = []
    seen = set()
    for cls in [4, 5, 7, 3]:
        count = 0
        for im in data["images"]:
            p = prov[im["file_name"]]
            if p["kind"] != "target" or p["original"] in seen:
                continue
            if any(a["category_id"] == cls for a in anns.get(im["id"], [])):
                selected.append(im["file_name"])
                seen.add(p["original"])
                count += 1
                if count == 4:
                    break
    selected += [
        im["file_name"]
        for im in data["images"]
        if prov[im["file_name"]]["kind"] == "clean"
    ][:4]
    thin_originals = set()
    for im in data["images"]:
        p = prov[im["file_name"]]
        if (
            p["kind"] == "target"
            and p["original"] not in thin_originals
            and any(
                a["category_id"] == 4
                and a["bbox"][2] <= 16
                and a["bbox"][3] >= max(64, 4 * a["bbox"][2])
                for a in anns.get(im["id"], [])
            )
        ):
            selected.append(im["file_name"])
            thin_originals.add(p["original"])
            if len(thin_originals) == 20:
                break
    for source in ("aitex/extracted/Defect_images/0081_006_04.png", "moratuwa"):
        extra = [
            im["file_name"]
            for im in data["images"]
            if source.lower() in prov[im["file_name"]]["original"].lower()
            and any(a["category_id"] == 4 for a in anns.get(im["id"], []))
        ]
        selected += extra[:2]
    return set(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    api = KaggleApi()
    api.authenticate()
    parts = args.ref.split("/")
    owner, slug = parts[:2]
    files = {}
    token = None
    with api.build_kaggle_client() as client:
        while True:
            request = ApiListKernelSessionOutputRequest()
            request.user_name = owner
            request.kernel_slug = slug
            if len(parts) == 3:
                request.version_label = parts[2]
            request.page_size = 100
            if token:
                request.page_token = token
            response = client.kernels.kernels_api_client.list_kernel_session_output(
                request
            )
            files.update({Path(f.file_name).name: f.url for f in response.files})
            token = response.next_page_token
            if not token:
                break
    for split in ["train", "val"]:
        destination = args.out / split
        destination.mkdir(parents=True, exist_ok=True)
        response = requests.get(
            files[f"{split}_prepared.tar"], stream=True, timeout=(30, 180)
        )
        if response.status_code != 200:
            raise RuntimeError(f"prepared stream returned HTTP {response.status_code}")
        data = None
        provenance = None
        wanted = None
        saved = set()
        try:
            with tarfile.open(fileobj=response.raw, mode="r|") as archive:
                for member in archive:
                    name = Path(member.name).name
                    if name in ["annotations.json", "provenance.json"]:
                        payload = archive.extractfile(member).read()
                        (destination / name).write_bytes(payload)
                        if name == "annotations.json":
                            data = json.loads(payload)
                        else:
                            provenance = json.loads(payload)
                    if data is not None and provenance is not None and wanted is None:
                        wanted = (
                            select_examples(data, provenance)
                            if split == "train"
                            else set()
                        )
                    if name.endswith(".jpg"):
                        if wanted is None:
                            raise ValueError("metadata must precede training images")
                        if name in wanted:
                            (destination / name).write_bytes(
                                archive.extractfile(member).read()
                            )
                            saved.add(name)
                    if wanted is not None and saved == wanted:
                        break
        finally:
            response.close()
        if data is None or provenance is None or wanted != saved:
            raise ValueError("incomplete prepared preview stream")
        print(
            split,
            "metadata",
            len(data["images"]),
            "images; preview examples",
            len(saved),
            flush=True,
        )


if __name__ == "__main__":
    main()
