# Training data inventory (model-training track, M4+)

Every external source the detector may learn from: where it comes from, its licence, what labels it has,
and whether it is downloaded. Raw files live in `data/external/<name>/raw/` (git-ignored, never
committed); `ml/scripts/` rebuilds everything from them. Nothing here is used by the running app.

Status: **downloaded** (on the team laptop), **cloud only** (too big for the laptop: download straight
into the Kaggle/Colab training notebook), **needs a person** (account, form or permission), **not usable**.

## Sources

| Name | Source | Licence | Labels | Size | Status |
|---|---|---|---|---|---|
| AITEX AFID | [aitex.es/afid](https://www.aitex.es/afid/) | No licence stated on AITEX's page; asks to cite the AFID paper (Dataset Ninja lists CC0 1.0). Confirm before any redistribution (PLAN Q2) | pixel masks, 12 classes; 245 greyscale 4096×256 images (105 defective) | 176 MB | downloaded |
| FabricSpotDefect (Independent University, Bangladesh) | [Mendeley 6574nhzm8x](https://data.mendeley.com/datasets/6574nhzm8x/1) | CC BY 4.0 | boxes + polygons, YOLOv8 and COCO; 1 class "spot" (stains, oil, rust, ink…); 1,014 raw colour images of cotton, denim, silk, prints… | 942 MB | downloaded |
| Moratuwa defect + stain sets (via the Mendeley "Fabric Defects Dataset" compilation) | [Mendeley 663j22s43c](https://data.mendeley.com/datasets/663j22s43c/3) | CC BY 4.0 | hole / horizontal / vertical / lines with masks; 398 stain images (1920×1080, colour) | 595 MB of 2.24 GB (defect folders only, fetched as one byte range; the rest repeats AITEX and defect-free images) | downloaded |
| FD Dataset (coloured fabrics) | [figshare 25546465](https://figshare.com/articles/dataset/FD_Dataset_7z/25546465) | CC BY 4.0 | detection; 720 images: oil, hole, cutting, crack | 191 MB | downloaded |
| Garment "Fabric Defect" | [Mendeley y62b4pfyz2](https://data.mendeley.com/datasets/y62b4pfyz2/1) | CC BY 4.0 | boxes (YOLO); 2,468 images incl. augmented copies: hole, colour defect, foreign yarn (+ button / sewing classes that are garment defects, not roll defects) | 322 MB | downloaded |
| ZJU-Leaper | [qaas.zju.edu.cn/zju-leaper](http://www.qaas.zju.edu.cn/zju-leaper/), Google Drive via bit.ly/zjuleaper | **not stated**: ask the authors | 98,777 images, 19 fabric patterns; masks, image labels and (setting 4) boxes | 6.26 GB (.7z) | cloud only; licence needs a person |
| RAW-FABRID | [Mendeley db6g85xsyg](https://data.mendeley.com/datasets/db6g85xsyg/1) | CC BY 4.0 | boxes + polygons (COCO); 709 high-res greyscale line-scan images, **known scale 4 px/mm** | 4.13 GB (zip inside a zip: no partial download) | cloud only |
| Tianchi Guangdong 2019 cloth flaw, round 1 (Alibaba) | official: [tianchi.aliyun.com/dataset/79336](https://tianchi.aliyun.com/dataset/79336) (download needs Chinese student verification); used: Roboflow mirror `project-fv1es/yuantianchi` **version 3** (raw: auto-orient only, no resize, no augmentation) | uploader lists CC BY 4.0; the original Tianchi terms could not be read; cite as "Tianchi 2019 Guangdong cloth flaw data, via a Roboflow mirror" | COCO boxes, 20 classes, 9,523 boxes; 5,913 images 2446×1000; 25 % of boxes < 32×32 px, 2,573 longer than 600 px | 2.59 GB | annotations checked locally; images: Kaggle (export link from the Roboflow API, key in `data/external/tianchi_roboflow/.secrets`, git-ignored) |
| TILDA | [Uni Freiburg](https://lmb.informatik.uni-freiburg.de/resources/datasets/tilda.en.html) | not stated | image-level class only (no boxes); 3,200 greyscale 768×512 | 1.2 GB | not usable for detection (clean-fabric negatives at most) |
| Chenab Textiles | in papers only | private | 7 classes | – | needs a person (ask the company) |
| DPFD-DET | in papers only | – | 4 classes | – | source not found |
| Kaggle set (3,077 images, 9 classes) | not identified | – | – | – | needs the link |
| ThreadEye simulator | `tools/simulator/` | ours | exact boxes for defects **and** non-defects (stickers, threads, wrinkles, hand, board) | unlimited | generated on demand |
| ThreadEye app labels | inspector decisions | ours (factory consent needed) | confirmed / rejected (with reason) / drawn missed defects, with frames | grows with use | collected by the app |

## What the downloaded sets really contain (checked 2026-10-18)

| Set | Images | Labels found | Usable for detection | Watch out |
|---|---|---|---|---|
| AITEX | 106 defective + 141 clean, greyscale 4096×256 | one mask per defective image; class code in the file name (`nnnn_CCC_FF`) | yes (mask → box) | 39 of 106 are code 019 (fuzzyball); several classes have 1 example; our sample roll is built from these images |
| FabricSpotDefect | 1,014 originals (+ an `Augmented` folder) | COCO boxes, 3,288 "spot" | yes | phone photos (mostly 4032×3024), not an inspection camera; one class only |
| Moratuwa hole / horizontal / vertical | ~143 originals + "_processed (1-3)" | `_processed (3)` is a clean mask | yes (mask → box) | mixed sizes (640×360 … 4608×3456) |
| Moratuwa lines | 157 | none (folder = class) | needs labelling | near-duplicate pairs (`…(1).jpg`) |
| Moratuwa stain | 398, 1984×1488 | none (folder = class) | needs labelling | |
| FD Dataset (figshare) | 720, resized to 640×640 by Roboflow | YOLO boxes, 781; classes `0..3` = oil, hole, cutting, crack (checked visually) | yes | many photos of the same physical defect: split by capture session, not by image |
| Garment defects | 2,468 = ~1,500 originals + Roboflow augmented copies (`_jpg.rf.<hash>`), 640×640 | COCO boxes | hole (613), colour defect (577), foreign yarn (344) only | button / sewing classes are garment defects: drop; group copies by original name |

## Tianchi class ids → ThreadEye taxonomy (draft: textile member to confirm)

Ids are the round-1 scoring categories; the names were checked against box shapes (warp defects are tall
and thin, weft defects wide and flat, bars span the width). In these images the roll runs top → bottom.

| id | Tianchi defect | boxes | median w×h px | ThreadEye class |
|---|---|---|---|---|
| 1 | 破洞 hole | 312 | 27×55 | hole |
| 2 | 水渍 / 油渍 / 污渍 water, oil, dirt stain | 401 | 102×164 | stain |
| 3 | 三丝 stray filaments | 1,055 | 16×86 | contamination |
| 4 | 结头 knot | 1,996 | 22×40 | knot |
| 5 | 花板跳 harness skip | 134 | 2426×176 | other_defect |
| 6 | 百脚 centipede (weave fault) | 161 | 2034×144 | other_defect |
| 7 | 毛粒 nep | 195 | 29×35 | slub |
| 8 | 粗经 thick end | 213 | 26×989 | slub |
| 9 | 松经 loose end | 396 | 35×941 | other_defect |
| 10 | 断经 broken end | 284 | 55×429 | broken_yarn |
| 11 | 吊经 tight end | 160 | 37×826 | other_defect |
| 12 | 粗维 thick pick | 915 | 80×22 | slub |
| 13 | 纬缩 weft curling | 452 | 130×24 | slub |
| 14 | 浆斑 starch mark | 336 | 1617×340 | stain |
| 15 | 整经结 warping knot | 473 | 25×66 | knot |
| 16 | 星跳 / 跳花 float | 302 | 27×456 | missing_yarn |
| 17 | 断氨纶 broken spandex | 546 | 31×27 | broken_yarn |
| 18 | 稀密档 / 浪纹档 / 色差档 density, wave, shade bar | 361 | 2384×215 | shade_bar |
| 19 | 磨痕 / 轧痕 / 修痕 / 烧毛痕 abrasion, crush, mend, singe marks | 470 | 57×989 | crease_mark |
| 20 | 死皱 / 云织 / 双纬 / 双经 / 跳纱 / 筘路 / 纬纱不良 misc weave faults | 361 | 42×767 | other_defect |

## Rules

- **Split by source image** (and by fabric where known): an image, its crops and any augmented copy
  stay in one split. The AITEX images used by `data/sample_roll` always go to `test`.
- **Duplicates across sources are removed** by perceptual hash before splitting (compilations re-upload
  AITEX and the Moratuwa sets).
- **Labels map to `backend/threadeye/data/taxonomy.yaml`**; classes that are not roll-inspection defects
  (buttons, sewing errors) are dropped, unknown ones become `other_defect`.
- Pre-augmented copies in a source are identified and kept in the same split as their original.
- Credit every CC BY source in PROVENANCE.md and in the model card.
