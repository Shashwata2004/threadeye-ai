"""QR roll labels: one 100 × 50 mm label per roll (thermal label printers), as one PDF.

The QR encodes only the roll code (e.g. ``TE-000123``), so any USB scanner can type it into the
"load roll" field. Labels of sample/fictional lots say SAMPLE DATA.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

import segno
from fpdf import FPDF

from threadeye.reports.pdf import BENGALI, FONT_DIR, LATIN

LABEL_W_MM, LABEL_H_MM = 100.0, 50.0


@dataclass(frozen=True)
class LabelData:
    roll_code: str
    mill_roll_no: str
    challan_no: str
    supplier: str
    buyer: str
    fabric_type: str
    declared_length_yd: float
    declared_width_in: float
    dye_lot: str | None
    is_sample_data: bool


def _qr_png(text: str) -> io.BytesIO:
    # make_qr, not make: for short text segno would pick a Micro QR, which most scanners cannot read.
    # A 4-module quiet zone is what the QR standard asks for.
    buf = io.BytesIO()
    segno.make_qr(text, error="m").save(buf, kind="png", scale=12, border=4)
    buf.seek(0)
    return buf


def build_labels_pdf(labels: Sequence[LabelData]) -> bytes:
    if not labels:
        raise ValueError("no rolls to label")
    pdf = FPDF(orientation="L", unit="mm", format=(LABEL_H_MM, LABEL_W_MM))
    pdf.set_auto_page_break(False)
    pdf.set_margins(3, 3, 3)
    for family, stem in ((LATIN, "NotoSans"), (BENGALI, "NotoSansBengali")):
        pdf.add_font(family, "", str(FONT_DIR / f"{stem}-Regular.ttf"))
        pdf.add_font(family, "B", str(FONT_DIR / f"{stem}-Bold.ttf"))
    pdf.set_fallback_fonts([BENGALI], exact_match=False)
    pdf.set_text_shaping(use_shaping_engine=True)
    pdf.set_title("ThreadEye roll labels")
    pdf.set_creator("ThreadEye AI")

    for lab in labels:
        pdf.add_page()
        pdf.image(_qr_png(lab.roll_code), x=3, y=3, w=40, h=40)
        pdf.set_xy(3, 44)
        pdf.set_font(LATIN, "B", 9)
        pdf.cell(40, 4, lab.roll_code, align="C")

        x = 46.0
        pdf.set_xy(x, 4)
        pdf.set_font(LATIN, "B", 16)
        pdf.cell(0, 8, lab.roll_code, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(LATIN, "", 8)
        rows = [
            ("Mill roll", lab.mill_roll_no),
            ("Challan", lab.challan_no),
            ("Mill", lab.supplier),
            ("Buyer", lab.buyer),
            ("Fabric", lab.fabric_type),
            ("Declared", f"{lab.declared_length_yd:g} yd × {lab.declared_width_in:g} in"),
        ]
        if lab.dye_lot:
            rows.append(("Dye lot", lab.dye_lot))
        y = 13.0
        for key, value in rows:
            pdf.set_xy(x, y)
            pdf.set_font(LATIN, "B", 7)
            pdf.cell(14, 4, key)
            pdf.set_font(LATIN, "", 7)
            pdf.cell(0, 4, value[:42])
            y += 4.2
        if lab.is_sample_data:
            pdf.set_xy(x, 44)
            pdf.set_font(LATIN, "B", 8)
            pdf.set_text_color(160, 90, 0)
            pdf.cell(0, 4, "SAMPLE DATA · নমুনা তথ্য")
            pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())
