"""Roll inspection report (PDF): verdict, per-yard points, roll map, every defect with its photo.

Honesty rules (PLAN.md §2): a simulated inspection carries the SIMULATED watermark and footer and the
detector's provider label on every page; the title never claims ASTM/AQL compliance.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from threadeye.api.schemas.inspection import DefectOut, InspectionSnapshot
from threadeye.core.taxonomy import load_default_taxonomy
from threadeye.reports.pdf import ThreadEyePDF

DHAKA = ZoneInfo("Asia/Dhaka")
VERDICT_COLOUR = {"PASS": (22, 128, 61), "BORDERLINE": (180, 110, 0), "FAIL": (190, 30, 30)}
STATUS_COLOUR = {"confirmed": (22, 128, 61), "rejected": (120, 120, 120), "pending": (190, 30, 30)}

TEXT = {
    "en": {
        "title": "Roll inspection report (4-point)",
        "roll": "Roll",
        "challan": "Challan",
        "mill": "Mill",
        "buyer": "Buyer",
        "fabric": "Fabric",
        "declared": "Declared",
        "rules": "Rules",
        "inspector": "Inspector",
        "inspected": "Inspected",
        "verdict": "System verdict",
        "decision": "Supervisor decision",
        "points": "Points",
        "per100": "per 100 sq yd",
        "threshold": "threshold",
        "yards": "Yards inspected",
        "perYard": "Points per yard (after the 4-point cap)",
        "map": "Roll map",
        "defects": "Defects",
        "ignored": "Shown but not scored (not defects)",
        "no": "No.",
        "type": "Type",
        "at": "At (yd)",
        "size": "Size (in)",
        "status": "Status",
        "pts": "Pts",
        "why": "Reason",
        "none": "No defects found.",
        "notFinal": "Verdict not computed yet: this is a provisional report.",
        "photo": "Evidence photos",
        "simNote": "SIMULATED: the video and the detections are simulated, not real AI. "
        "Scores follow the rule profile shown above.",
        "status_confirmed": "confirmed",
        "status_rejected": "rejected",
        "status_pending": "pending",
    },
    "bn": {
        "title": "রোল পরিদর্শন রিপোর্ট (৪-পয়েন্ট)",
        "roll": "রোল",
        "challan": "চালান",
        "mill": "মিল",
        "buyer": "ক্রেতা",
        "fabric": "কাপড়",
        "declared": "ঘোষিত",
        "rules": "নিয়ম",
        "inspector": "পরিদর্শক",
        "inspected": "পরিদর্শন",
        "verdict": "সিস্টেমের রায়",
        "decision": "সুপারভাইজারের সিদ্ধান্ত",
        "points": "পয়েন্ট",
        "per100": "প্রতি ১০০ বর্গগজে",
        "threshold": "সীমা",
        "yards": "পরিদর্শিত গজ",
        "perYard": "প্রতি গজে পয়েন্ট (৪-পয়েন্ট সীমার পরে)",
        "map": "রোলের মানচিত্র",
        "defects": "ত্রুটি",
        "ignored": "দেখানো হয়েছে, গোনা হয়নি (ত্রুটি নয়)",
        "no": "নং",
        "type": "ধরন",
        "at": "অবস্থান (গজ)",
        "size": "আকার (ইঞ্চি)",
        "status": "অবস্থা",
        "pts": "পয়েন্ট",
        "why": "কারণ",
        "none": "কোনো ত্রুটি পাওয়া যায়নি।",
        "notFinal": "রায় এখনো হিসাব হয়নি: এটি অস্থায়ী রিপোর্ট।",
        "photo": "প্রমাণের ছবি",
        "simNote": "সিমুলেটেড: ভিডিও ও শনাক্তকরণ সিমুলেটেড, বাস্তব AI নয়। পয়েন্ট উপরের নিয়ম অনুযায়ী হিসাব করা।",
        "status_confirmed": "নিশ্চিত",
        "status_rejected": "বাতিল",
        "status_pending": "বাকি",
    },
}


def _fmt_time(value: datetime | None) -> str:
    return value.astimezone(DHAKA).strftime("%d %b %Y %H:%M") if value else "-"


def build_roll_report(
    snap: InspectionSnapshot,
    defects: Sequence[DefectOut],
    crops: Mapping[str, bytes],
    *,
    lang: str = "en",
) -> bytes:
    t = TEXT.get(lang, TEXT["en"])
    tax = load_default_taxonomy()

    def label(cls: str) -> str:
        dc = tax.classes.get(cls)
        if dc is None:
            return cls
        return dc.label_bn if lang == "bn" else dc.label_en

    provider = f"{snap.provider.display_name} ({snap.provider.provider_id}@{snap.provider.version})"
    pdf = ThreadEyePDF(simulated=snap.is_simulated, provider_label=provider, title=t["title"])
    pdf.alias_nb_pages()
    pdf.add_page()

    # ---------------------------------------------------------------------------------- header
    pdf.use_font(18, bold=True)
    pdf.cell(0, 10, t["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.use_font(9)
    r = snap.roll
    rows = [
        (t["roll"], f"{r.roll_code}  (mill roll {r.mill_roll_no})"),
        (t["challan"], r.challan_no),
        (t["mill"], r.supplier),
        (t["buyer"], r.buyer),
        (t["fabric"], r.fabric_type),
        (t["declared"], f"{r.declared_length_yd:g} yd × {r.declared_width_in:g} in"),
        (t["rules"], f"{r.rule_profile} ({t['threshold']} {r.threshold_per_100:g})"),
        (t["inspector"], snap.inspector or "-"),
        (t["inspected"], f"{_fmt_time(snap.started_at)} → {_fmt_time(snap.completed_at)} (Asia/Dhaka)"),
    ]
    for k, v in rows:
        pdf.use_font(9, bold=True)
        pdf.cell(32, 5, k)
        pdf.use_font(9)
        pdf.cell(0, 5, v, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ---------------------------------------------------------------------------------- verdict
    verdict = snap.system_verdict
    score = snap.score
    if verdict:
        colour = VERDICT_COLOUR.get(verdict, (0, 0, 0))
        pdf.set_fill_color(*colour)
        pdf.set_text_color(255, 255, 255)
        pdf.use_font(16, bold=True)
        pdf.cell(60, 12, f"  {t['verdict']}: {verdict}", fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.use_font(11)
        pdf.cell(
            0,
            12,
            f"   {snap.points_total} {t['points']} · {snap.points_per_100} {t['per100']} "
            f"({t['threshold']} {r.threshold_per_100:g}) · {t['yards']}: {snap.yards_inspected}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        if snap.final_verdict:
            pdf.use_font(10, bold=True)
            pdf.cell(
                0,
                7,
                f"{t['decision']}: {snap.final_verdict} ({snap.decision_by}): {snap.decision_reason}",
                new_x="LMARGIN",
                new_y="NEXT",
            )
    else:
        pdf.set_text_color(190, 30, 30)
        pdf.use_font(11, bold=True)
        pdf.cell(0, 8, t["notFinal"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # ---------------------------------------------------------------------------------- per yard
    cells = {int(k): v for k, v in (score.cells if score else {}).items()}
    if cells:
        pdf.use_font(11, bold=True)
        pdf.cell(0, 7, t["perYard"], new_x="LMARGIN", new_y="NEXT")
        pdf.use_font(8)
        items = sorted(cells.items())
        per_row = 12
        for i in range(0, len(items), per_row):
            chunk = items[i : i + per_row]
            for yd, _ in chunk:
                pdf.cell(15, 5, f"yd {yd}", border=1, align="C")
            pdf.ln()
            for _, pts in chunk:
                pdf.cell(15, 5, str(pts), border=1, align="C")
            pdf.ln()
        pdf.ln(2)

    # ---------------------------------------------------------------------------------- roll map
    length = max((snap.yards_inspected or 0.0), max((d.end_yd for d in defects), default=0.0), 1.0)
    pdf.use_font(11, bold=True)
    pdf.cell(0, 7, t["map"], new_x="LMARGIN", new_y="NEXT")
    x0, y0 = pdf.l_margin, pdf.get_y() + 1
    w, h = pdf.w - pdf.l_margin - pdf.r_margin, 18.0
    width_cm = max((d.across_end_cm for d in defects), default=150.0)
    width_cm = max(width_cm, 150.0)
    pdf.set_draw_color(120, 120, 120)
    pdf.set_fill_color(245, 240, 230)
    pdf.rect(x0, y0, w, h, style="DF")
    pdf.use_font(6)
    step = max(1, round(length / 12))
    for yd in range(0, int(length) + 1, step):
        x = x0 + w * yd / length
        pdf.line(x, y0 + h, x, y0 + h + 1.5)
        pdf.text(x - 1.5, y0 + h + 4, f"{yd}")
    for d in defects:
        if d.kind != "defect":
            continue
        colour = STATUS_COLOUR.get(d.status, (0, 0, 0))
        pdf.set_fill_color(*colour)
        dx0 = x0 + w * d.start_yd / length
        dx1 = max(dx0 + 0.8, x0 + w * d.end_yd / length)
        dy0 = y0 + h * d.across_start_cm / width_cm
        dy1 = max(dy0 + 0.8, y0 + h * d.across_end_cm / width_cm)
        pdf.rect(dx0, dy0, dx1 - dx0, dy1 - dy0, style="F")
        pdf.set_text_color(*colour)
        pdf.text(dx0, max(y0 + 2, dy0 - 0.5), d.defect_no)
        pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + h + 7)

    # ---------------------------------------------------------------------------------- defects
    real = [d for d in defects if d.kind == "defect"]
    ignored = [d for d in defects if d.kind != "defect"]
    pdf.use_font(11, bold=True)
    pdf.cell(0, 7, f"{t['defects']} ({len(real)})", new_x="LMARGIN", new_y="NEXT")
    if not real:
        pdf.use_font(9)
        pdf.cell(0, 6, t["none"], new_x="LMARGIN", new_y="NEXT")
    else:
        widths = (14, 38, 18, 18, 22, 12, 68)
        heads = (t["no"], t["type"], t["at"], t["size"], t["status"], t["pts"], t["why"])
        pdf.use_font(8, bold=True)
        pdf.set_fill_color(230, 236, 245)
        for wd, hd in zip(widths, heads, strict=True):
            pdf.cell(wd, 6, hd, border=1, fill=True)
        pdf.ln()
        pdf.use_font(8)
        for d in real:
            why = d.excluded_reason if d.status != "confirmed" and d.excluded_reason else (d.points_reason or "")
            if d.status == "rejected" and d.reject_reason:
                why = f"rejected: {d.reject_reason.replace('_', ' ')}"
            if d.origin == "manual":
                why = f"added by inspector. {why}"
            values = (
                d.defect_no,
                label(d.current_cls),
                f"{d.center_yd:.2f}",
                f"{d.length_in:.2f}",
                t.get(f"status_{d.status}", d.status),
                "-" if d.points is None or d.status == "rejected" else str(d.points),
                why[:60],
            )
            for wd, val in zip(widths, values, strict=True):
                pdf.cell(wd, 5.5, val, border=1)
            pdf.ln()
    if ignored:
        pdf.ln(2)
        pdf.use_font(9, bold=True)
        pdf.cell(0, 6, f"{t['ignored']} ({len(ignored)})", new_x="LMARGIN", new_y="NEXT")
        pdf.use_font(8)
        counts: dict[str, int] = {}
        for d in ignored:
            key = label(d.nondefect_category or d.current_cls)
            counts[key] = counts.get(key, 0) + 1
        pdf.multi_cell(0, 5, ", ".join(f"{k}: {n}" for k, n in sorted(counts.items())))

    # ---------------------------------------------------------------------------------- photos
    with_photo = [d for d in real if d.defect_no in crops]
    if with_photo:
        pdf.ln(3)
        if pdf.get_y() > pdf.h - 70:
            pdf.add_page()
        pdf.use_font(11, bold=True)
        pdf.cell(0, 7, t["photo"], new_x="LMARGIN", new_y="NEXT")
        size, gap = 40.0, 5.0
        per_row = int((pdf.w - pdf.l_margin - pdf.r_margin + gap) // (size + gap))
        for i, d in enumerate(with_photo):
            col = i % per_row
            if col == 0:
                if i:
                    pdf.set_y(pdf.get_y() + size + 9)
                if pdf.get_y() + size + 9 > pdf.h - 20:
                    pdf.add_page()
            x = pdf.l_margin + col * (size + gap)
            y = pdf.get_y()
            pdf.image(io.BytesIO(crops[d.defect_no]), x=x, y=y, w=size, h=size)
            pdf.use_font(7)
            pdf.text(x, y + size + 3.5, f"{d.defect_no} · {label(d.current_cls)} · {d.center_yd:.2f} yd")
        pdf.set_y(pdf.get_y() + size + 9)

    if snap.is_simulated:
        pdf.ln(2)
        pdf.set_text_color(160, 90, 0)
        pdf.use_font(8, bold=True)
        pdf.multi_cell(0, 4.5, t["simNote"])
        pdf.set_text_color(0, 0, 0)
    pdf.use_font(7)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(
        0,
        5,
        f"Generated {datetime.now(UTC).astimezone(DHAKA).strftime('%d %b %Y %H:%M')} · inspection {snap.id}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    return bytes(pdf.output())
