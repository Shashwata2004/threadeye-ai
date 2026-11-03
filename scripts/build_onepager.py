"""Render the local M9 handout; this does not publish or submit anything."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from threadeye.reports.pdf import ThreadEyePDF  # noqa: E402

pdf = ThreadEyePDF(simulated=True, provider_label="YOLOX-S / simulated baseline", title="ThreadEye AI · handout")
pdf.add_page()
for paragraph in (ROOT / "docs/congress/one-pager.md").read_text().split("\n\n"):
    heading = paragraph.startswith("# ")
    text = paragraph.removeprefix("# ").replace("**", "").replace("\n", " ")
    pdf.use_font(16 if heading else 10, bold=heading)
    pdf.multi_cell(0, 5.5 if not heading else 9, text=text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
output = ROOT / "docs/congress/one-pager.pdf"
output.write_bytes(bytes(pdf.output()))
print(output.relative_to(ROOT))
