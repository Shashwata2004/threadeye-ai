"""Source class names → ThreadEye taxonomy ids (backend/threadeye/data/taxonomy.yaml).

DRAFT mappings: the textile domain member confirms them (ml/DATASETS.md). ``None`` drops the box: the
object is not a roll-inspection defect (e.g. a broken button on a finished garment), so the image is kept
and that region counts as background.
"""

from __future__ import annotations

# The detector's classes, in a fixed order (COCO category ids are index + 1).
DEFECT_CLASSES = (
    "hole",
    "stain",
    "oil_stain",
    "slub",
    "broken_yarn",
    "missing_yarn",
    "knot",
    "crease_mark",
    "contamination",
    "shade_bar",
    "selvage_defect",
    "other_defect",
)

SOURCE_CLASS_MAP: dict[str, dict[str, str | None]] = {
    # AITEX: three-digit code in the file name (tools/simulator/make_roll_video.py AITEX_CODES).
    "aitex": {
        "002": "broken_yarn",  # broken end
        "006": "broken_yarn",
        "010": "broken_yarn",  # broken pick
        "016": "slub",  # weft curling
        "019": "slub",  # fuzzyball
        "022": "selvage_defect",  # cut selvage
        "023": "crease_mark",
        "025": "slub",  # warp ball
        "027": "knot",
        "029": "contamination",
        "030": "slub",  # nep
        "036": "missing_yarn",  # weft crack
    },
    "fabricspotdefect": {"spot": "stain"},
    "moratuwa": {"hole": "hole", "horizontal": "broken_yarn", "vertical": "broken_yarn"},
    # FD Dataset: Roboflow ids 0..3, checked visually: oil, hole, cutting, crack.
    "fd_figshare": {"0": "oil_stain", "1": "hole", "2": "hole", "3": "hole"},
    "garment_defects": {
        "Hole": "hole",
        "Color_defect": "stain",
        "Foreign_yarn": "contamination",
        "Broken_button": None,
        "Button_hike": None,
        "Sewing_error": None,
    },
    # Tianchi 2019 Guangdong round 1 scoring categories (names checked against box shapes).
    "tianchi": {
        "1": "hole",
        "2": "stain",
        "3": "contamination",
        "4": "knot",
        "5": "other_defect",
        "6": "other_defect",
        "7": "slub",
        "8": "slub",
        "9": "other_defect",
        "10": "broken_yarn",
        "11": "other_defect",
        "12": "slub",
        "13": "slub",
        "14": "stain",
        "15": "knot",
        "16": "missing_yarn",
        "17": "broken_yarn",
        "18": "shade_bar",
        "19": "crease_mark",
        "20": "other_defect",
    },
}


class UnmappedClass(KeyError):
    pass


def map_class(source: str, src_cls: str) -> str | None:
    table = SOURCE_CLASS_MAP.get(source)
    if table is None or src_cls not in table:
        raise UnmappedClass(f"{source}: class {src_cls!r} has no mapping (add it to SOURCE_CLASS_MAP)")
    cls = table[src_cls]
    if cls is not None and cls not in DEFECT_CLASSES:
        raise UnmappedClass(f"{source}: {src_cls!r} maps to unknown class {cls!r}")
    return cls
