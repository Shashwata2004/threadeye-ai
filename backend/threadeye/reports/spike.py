"""M0 spike: prove Bangla shaping in PDFs (PLAN.md §2 default 4, M0 acceptance).

``threadeye spike-pdf out/spike_bangla.pdf``, then open the PDF (or ``pdftoppm -png``) and check that
conjuncts (ক্ষ, স্ক্র, দ্রু, ন্ত) and vowel signs (ি, ে, ো) are positioned correctly, including
in lines that mix Bangla and English.
"""

from __future__ import annotations

from threadeye.reports.pdf import ThreadEyePDF

LINES = [
    ("Verdict line", "রোলের রায়: বাতিল"),
    ("Score line", "প্রতি ১০০ বর্গগজে পয়েন্ট: 46.45 (সীমা 40)"),
    ("Tagline", "কাপড় পরীক্ষার স্মার্ট সহকারী"),
    ("Conjuncts", "ক্ষতিপূরণ দাবি · স্ক্র্যাপ · দ্রুত · চলন্ত · শ্রেণি · স্ত্রী"),
    ("Vowel signs", "কি কী কু কূ কে কৈ কো কৌ · কিনারার পিনের ছিদ্র"),
    ("Mixed Bangla + English", "4-point inspection report — ৪-পয়েন্ট পরিদর্শন রিপোর্ট, roll R-101"),
    ("Non-defect vs defect", "নাড়াচাড়ার ভাঁজ (ত্রুটি নয়) · ভাঁজের দাগ (ত্রুটি)"),
    ("Simulated label", "সিমুলেশন মোড — ভিডিও ও শনাক্তকরণ সিমুলেটেড, বাস্তব AI নয়"),
]


def build_spike_pdf() -> bytes:
    pdf = ThreadEyePDF(simulated=True, provider_label="simulated@0.1.0", title="Bangla shaping spike (M0)")
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.use_font(16, bold=True)
    pdf.cell(0, 10, "ThreadEye AI: Bangla text shaping check", new_x="LMARGIN", new_y="NEXT")
    pdf.use_font(10)
    pdf.multi_cell(
        0,
        5,
        "Each line below must render with correct conjuncts and vowel-sign placement. "
        "Fonts: Noto Sans + Noto Sans Bengali fallback (OFL 1.1). Engine: fpdf2 + HarfBuzz.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    for label, text in LINES:
        pdf.use_font(9, bold=True)
        pdf.cell(0, 6, label, new_x="LMARGIN", new_y="NEXT")
        pdf.use_font(15)
        pdf.multi_cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.use_font(20, bold=True)
    pdf.cell(0, 14, "রোলের রায়: বাতিল (FAIL)", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
