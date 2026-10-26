"""Roll inspection report (PDF): verdict, per-yard points, every defect with its photo.

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
        "simVideoNote": "SIMULATED VIDEO: the roll video is simulated from a public fabric dataset; the defects "
        "were found by our trained model ({provider}). Scores follow the rule profile shown above.",
        "status_confirmed": "confirmed",
        "status_rejected": "rejected",
        "status_pending": "pending",
        "status_unreviewed": "not reviewed",
        "unreviewed": "{n} defect(s) were not reviewed: they cannot change the verdict "
        "({low} points if all are false alarms, {high} if all are real).",
        "PASS": "PASS",
        "BORDERLINE": "BORDERLINE",
        "FAIL": "FAIL",
        "ACCEPT": "Accept",
        "ACCEPT_WITH_CLAIM": "Accept with a claim",
        "REJECT": "Reject (return to mill)",
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
        "simVideoNote": "সিমুলেটেড ভিডিও: রোলের ভিডিও একটি পাবলিক কাপড়ের ডেটাসেট থেকে সিমুলেট করা; ত্রুটিগুলো খুঁজেছে "
        "আমাদের প্রশিক্ষিত মডেল ({provider})। পয়েন্ট উপরের নিয়ম অনুযায়ী হিসাব করা।",
        "status_confirmed": "নিশ্চিত",
        "status_rejected": "বাতিল",
        "status_pending": "বাকি",
        "status_unreviewed": "পর্যালোচনা হয়নি",
        "unreviewed": "{n}টি ত্রুটি পর্যালোচনা হয়নি: এগুলো রায় বদলাতে পারে না "
        "(সব ভুল সতর্কতা হলে {low} পয়েন্ট, সব সত্যি হলে {high} পয়েন্ট)।",
        "PASS": "পাস",
        "BORDERLINE": "সীমার কাছাকাছি",
        "FAIL": "বাতিল",
        "ACCEPT": "গ্রহণ",
        "ACCEPT_WITH_CLAIM": "দাবি সহ গ্রহণ",
        "REJECT": "ফেরত (মিলে পাঠানো)",
    },
}


def _fmt_time(value: datetime | None) -> str:
    return value.astimezone(DHAKA).strftime("%d %b %Y %H:%M") if value else "-"


def _wrapped(pdf: ThreadEyePDF, text: str, h: float) -> None:
    """Word-wrap with one cell per line (multi_cell loses the Bangla fallback shaping on wrapped lines).

    Lines are broken by an estimated character width: measuring Bangla with the Latin primary font
    only logs missing-glyph warnings, and shaped Bangla clusters are narrower than the estimate.
    """
    width_mm = pdf.w - pdf.l_margin - pdf.r_margin
    per_line = max(20, int(width_mm / (pdf.font_size * 0.52)))
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > per_line:
            pdf.cell(0, h, line, new_x="LMARGIN", new_y="NEXT")
            line = word
        else:
            line = candidate
    if line:
        pdf.cell(0, h, line, new_x="LMARGIN", new_y="NEXT")


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
    pdf = ThreadEyePDF(
        simulated=snap.is_simulated,
        provider_label=provider,
        title=t["title"],
        detections_simulated=snap.provider.is_simulated,
    )
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
        (t["inspected"], f"{_fmt_time(snap.started_at)} - {_fmt_time(snap.completed_at)} (Asia/Dhaka)"),
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
        badge = f"  {t['verdict']}: {t.get(verdict, verdict)}  "
        pdf.cell(pdf.get_string_width(badge) + 2, 12, badge, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.use_font(11)
        pdf.cell(
            0,
            12,
            f"  {snap.points_total} {t['points']} · {snap.points_per_100} {t['per100']} "
            f"({t['threshold']} {r.threshold_per_100:g}) · {t['yards']}: {snap.yards_inspected}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        if snap.unreviewed:
            pdf.use_font(9)
            note = t["unreviewed"].format(n=snap.unreviewed, low=snap.points_total, high=snap.points_if_all_confirmed)
            _wrapped(pdf, note, 5)
        if snap.final_verdict:
            pdf.use_font(10, bold=True)
            decision = t.get(snap.final_verdict, snap.final_verdict)
            _wrapped(pdf, f"{t['decision']}: {decision} ({snap.decision_by}): {snap.decision_reason}", 5.5)
    else:
        pdf.set_text_color(190, 30, 30)
        pdf.use_font(11, bold=True)
        pdf.cell(0, 8, t["notFinal"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # ---------------------------------------------------------------------------------- per yard
    # After the verdict: its own per-yard points (confirmed defects only); before it, the live score.
    raw_cells = snap.verdict_cells if snap.verdict_cells is not None else (score.cells if score else {})
    cells = {int(k): v for k, v in raw_cells.items()}
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
                t["status_unreviewed"] if d.status == "pending" and verdict else t.get(f"status_{d.status}", d.status),
                "-" if d.points is None or d.status == "rejected" else str(d.points),
                why.replace("→", "=")[:60],  # the PDF font has no arrow glyph
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
        _wrapped(pdf, ", ".join(f"{k}: {n}" for k, n in sorted(counts.items())), 5)

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
            # cell(), not text(): text() skips Bangla shaping.
            pdf.set_xy(x, y + size + 0.5)
            pdf.cell(size, 4, f"{d.defect_no} · {label(d.current_cls)} · {d.center_yd:.2f} yd")
            pdf.set_y(y)
        pdf.set_y(pdf.get_y() + size + 9)

    if snap.is_simulated:
        pdf.ln(2)
        pdf.set_text_color(160, 90, 0)
        pdf.use_font(8, bold=True)
        note = t["simNote"] if snap.provider.is_simulated else t["simVideoNote"].format(provider=provider)
        _wrapped(pdf, note, 4.5)
        pdf.set_text_color(0, 0, 0)
    pdf.use_font(7)
    pdf.set_text_color(110, 110, 110)
    pdf.set_x(pdf.l_margin)
    pdf.cell(
        0,
        5,
        f"Generated {datetime.now(UTC).astimezone(DHAKA).strftime('%d %b %Y %H:%M')} · inspection {snap.id}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    return bytes(pdf.output())
