"""Source class names → ThreadEye taxonomy ids (backend/threadeye/data/taxonomy.yaml).

DRAFT mappings: the textile domain member confirms them (ml/DATASETS.md). ``None`` drops the box: the
object is not a roll-inspection defect (e.g. a broken button on a finished garment), so the image is kept
and that region counts as background.
"""

from __future__ import annotations

# The detector's classes, in a fixed order (COCO category ids are index + 1). A subset of the taxonomy:
#  - oil_stain is learned as stain: the 4-point score depends on size, not on what made the stain, and the
#    public data has one small source of oil stains (FD Dataset) — too few to tell them apart reliably.
#  - selvage_defect is placed, not detected: the app turns a yarn fault inside the selvage band into a
#    selvage defect (backend/threadeye/core/nondefect.py). Public data has 9 selvage examples (AITEX).
DEFECT_CLASSES = (
    "hole",
    "stain",
    "slub",
    "broken_yarn",
    "missing_yarn",
    "knot",
    "crease_mark",
    "contamination",
    "shade_bar",
    "other_defect",
)
NUISANCE_CLASSES = ("sticker", "loose_thread", "wrinkle", "hand")
"""Non-defects the detector also learns (synth_nuisance.py): the app shows them grey and never scores them."""
DETECTOR_CLASSES = DEFECT_CLASSES + NUISANCE_CLASSES

SOURCE_CLASS_MAP: dict[str, dict[str, str | None]] = {
    # Sources without defect types: every defect is other_defect ("*" matches any name).
    "zju_leaper": {"*": "other_defect"},
    "raw_fabrid": {"*": "other_defect"},
    # WFDD: typed only for grey_cloth; the other fabrics say just "defect".
    "wfdd": {"contaminated": "contamination", "flecked": "stain", "line": "broken_yarn", "string": "contamination",
             "defect": "other_defect"},
    # AITEX: three-digit code in the file name (tools/simulator/make_roll_video.py AITEX_CODES).
    "aitex": {
        "002": "broken_yarn",  # broken end
        "006": "broken_yarn",
        "010": "broken_yarn",  # broken pick
        "016": "slub",  # weft curling
        "019": "slub",  # fuzzyball
        "022": "other_defect",  # cut selvage (placed as selvage_defect by the app)
        "023": "crease_mark",
        "025": "slub",  # warp ball
        "027": "knot",
        "029": "contamination",
        "030": "slub",  # nep
        "036": "missing_yarn",  # weft crack
    },
    "aitex_paste": {},  # set below: the same codes as AITEX (ml/aitex_paste.py)
    "fabricspotdefect": {"spot": "stain"},
    "fabric_stain": {"0": "stain"},
    # Already ThreadEye names (defects of the base tile + the nuisances drawn on it).
    "synth_nuisance": {c: c for c in DEFECT_CLASSES + NUISANCE_CLASSES},
    "moratuwa": {"hole": "hole", "horizontal": "broken_yarn", "vertical": "broken_yarn"},
    # FD Dataset: Roboflow ids 0..3, checked visually: oil, hole, cutting, crack.
    "fd_figshare": {"0": "stain", "1": "hole", "2": "hole", "3": "hole"},
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
SOURCE_CLASS_MAP["aitex_paste"] = SOURCE_CLASS_MAP["aitex"]


class UnmappedClass(KeyError):
    pass


def map_class(source: str, src_cls: str) -> str | None:
    table = SOURCE_CLASS_MAP.get(source)
    if table is not None and src_cls not in table and "*" in table:
        src_cls = "*"
    if table is None or src_cls not in table:
        raise UnmappedClass(f"{source}: class {src_cls!r} has no mapping (add it to SOURCE_CLASS_MAP)")
    cls = table[src_cls]
    if cls is not None and cls not in DETECTOR_CLASSES:
        raise UnmappedClass(f"{source}: {src_cls!r} maps to unknown class {cls!r}")
    return cls
