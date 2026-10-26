"""Claim letter (PDF, English) to the mill for the failed rolls of one delivery (M5 claim pack).

It states what was received, how it was inspected (4-point, the rule profile and its threshold), which rolls
failed with their points, the main defects, the decision and the request, and points to the evidence in the
pack (each roll's report with photos, every file's SHA-256 in SHA256SUMS.txt). Honesty rules as for every
report: the SIMULATED watermark and notes when the video or the detections are simulated; no money amounts
(the purchase terms set them).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from threadeye.core.taxonomy import load_default_taxonomy
from threadeye.reports.pdf import ThreadEyePDF

DHAKA = ZoneInfo("Asia/Dhaka")
DECISION_TEXT = {
    "REJECT": "Rejected: return to mill",
    "ACCEPT_WITH_CLAIM": "Accepted with a claim",
    "ACCEPT": "Accepted",
    None: "Failed (no decision yet)",
}
LOT_DECISION_TEXT = {
    "ACCEPT": "accept the delivery",
    "ACCEPT_WITH_REJECTS": "accept the delivery and return the failed rolls",
    "REJECT": "reject the whole delivery",
    "INSPECT_ALL": "inspect every roll of the delivery before deciding",
}


@dataclass(frozen=True)
class ClaimRoll:
    roll_code: str
    mill_roll_no: str
    declared_length_yd: float
    yards_inspected: float | None
    points_total: int | None
    points_per_100: float | None
    final_verdict: str | None
    decision_reason: str | None
    defects: dict[str, int]
    """Confirmed defects by class."""


@dataclass(frozen=True)
class ClaimData:
    challan: str
    order_ref: str | None
    fabric: str
    colour: str | None
    received: date
    declared_rolls: int
    mill: str
    mill_country: str | None
    buyer: str
    profile: str
    threshold_per_100: float
    inspected: int
    rolls: Sequence[ClaimRoll]
    lot_decision: str | None
    lot_decision_reason: str | None
    signed_by: str
    generated_at: datetime
    simulated_video: bool
    simulated_detections: bool
    provider_label: str
    demo_data: bool = False
    """The mill, buyer and delivery are the app's sample data."""
    files: Sequence[str] = field(default_factory=tuple)


def _para(pdf: ThreadEyePDF, text: str, size: float = 10.5, bold: bool = False, h: float = 5.2) -> None:
    pdf.use_font(size, bold=bold)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, h, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def build_claim_letter(c: ClaimData) -> bytes:
    taxonomy = load_default_taxonomy()

    def label(cls: str) -> str:
        info = taxonomy.classes.get(cls)
        return info.label_en if info else cls.replace("_", " ")

    pdf = ThreadEyePDF(
        simulated=c.simulated_video,
        provider_label=c.provider_label,
        title="Quality claim",
        detections_simulated=c.simulated_detections,
    )
    pdf.alias_nb_pages()
    pdf.add_page()
    today = c.generated_at.astimezone(DHAKA)

    pdf.use_font(9)
    pdf.cell(0, 5, today.strftime("%d %B %Y"), new_x="LMARGIN", new_y="NEXT", align="R")
    _para(pdf, f"To: Quality department, {c.mill}" + (f" ({c.mill_country})" if c.mill_country else ""), 10.5)
    order = f", order {c.order_ref}" if c.order_ref else ""
    _para(pdf, f"Subject: Quality claim for challan {c.challan}{order}: {c.fabric}", 12, bold=True)
    _para(pdf, "Dear Sir or Madam,")
    colour = f", {c.colour}" if c.colour else ""
    _para(
        pdf,
        f"On {c.received:%d %B %Y} we received {c.declared_rolls} roll(s) of {c.fabric}{colour} under challan "
        f"{c.challan}{order}. We inspected {c.inspected} of them with the 4-point system under the rule profile "
        f"“{c.profile}” (a roll fails above {c.threshold_per_100:g} points per 100 square yards). "
        f"{len(c.rolls)} roll(s) did not meet the standard:",
    )

    widths = (24, 26, 22, 22, 22, 0)
    head = ("Roll", "Mill roll no.", "Length (yd)", "Points", "Per 100 sq yd", "Decision")
    pdf.use_font(9, bold=True)
    pdf.set_fill_color(235, 238, 242)
    for w, t in zip(widths, head, strict=True):
        pdf.cell(w, 6, t, border=1, fill=True, new_x="RIGHT", new_y="TOP")
    pdf.ln(6)
    pdf.use_font(9)
    for r in c.rolls:
        length = f"{r.declared_length_yd:g}"
        if r.yards_inspected is not None:
            length = f"{r.yards_inspected:.1f}/{length}"
        cells = (
            r.roll_code,
            r.mill_roll_no,
            length,
            "" if r.points_total is None else str(r.points_total),
            "" if r.points_per_100 is None else f"{r.points_per_100:.2f}",
            DECISION_TEXT.get(r.final_verdict, r.final_verdict or ""),
        )
        for w, t in zip(widths, cells, strict=True):
            pdf.cell(w, 6, t, border=1, new_x="RIGHT", new_y="TOP")
        pdf.ln(6)
    pdf.use_font(7.5)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 4, "Length: yards inspected / yards declared on the challan.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    totals: dict[str, int] = {}
    for r in c.rolls:
        for cls, n in r.defects.items():
            totals[cls] = totals.get(cls, 0) + n
    if totals:
        mix = ", ".join(f"{label(cls).lower()} ({n})" for cls, n in sorted(totals.items(), key=lambda x: -x[1]))
        _para(pdf, f"The defects confirmed by our inspectors in these rolls: {mix}.")
    reasons = [f"{r.roll_code}: {r.decision_reason}" for r in c.rolls if r.decision_reason]
    if reasons:
        _para(pdf, "Notes from the supervisor: " + "; ".join(reasons) + ".")
    if c.lot_decision:
        why = f" ({c.lot_decision_reason})" if c.lot_decision_reason else ""
        _para(pdf, f"Our decision on this delivery is to {LOT_DECISION_TEXT.get(c.lot_decision, c.lot_decision)}{why}.")

    _para(
        pdf,
        "We request a replacement or full credit for the rolls returned to you, and a price allowance under the "
        "purchase terms for the rolls we accept with a claim. Please reply within 7 days.",
    )
    _para(
        pdf,
        "The enclosed inspection reports show every defect with its position (yard along the roll, centimetres "
        "from the edge), its size, its points and a photo. Every file in this pack is listed with its SHA-256 "
        "checksum in SHA256SUMS.txt, so you can check that nothing was changed after the inspection.",
    )
    if c.files:
        _para(pdf, "Enclosed: " + "; ".join(c.files) + ".", 8.5, h=4.2)
    _para(pdf, "Sincerely,")
    _para(pdf, f"{c.signed_by}\nQuality control (receiving), {c.buyer}", bold=True)

    if c.simulated_video or c.simulated_detections:
        pdf.ln(2)
        pdf.set_text_color(160, 90, 0)
        note = (
            "SIMULATED: the roll video and the detections are simulated, not real AI."
            if c.simulated_detections
            else "SIMULATED VIDEO: the roll video is simulated from a public fabric dataset; the defects were found "
            f"by our trained model ({c.provider_label})."
        )
        _para(pdf, note + (" Mill, buyer and challan are demo data." if c.demo_data else ""), 8, bold=True, h=4.2)
        pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())
