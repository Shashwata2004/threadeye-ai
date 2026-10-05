"""M0 spike: Bangla PDF generation works and every report is labelled with its provider."""

import shutil
import subprocess
from pathlib import Path

import pytest

from threadeye.reports.spike import build_spike_pdf


def test_spike_pdf_embeds_both_fonts() -> None:
    data = build_spike_pdf()
    assert data.startswith(b"%PDF-")
    assert b"NotoSansBengali" in data
    assert b"NotoSans-" in data or b"NotoSans" in data


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler-utils not installed")
def test_spike_pdf_carries_simulated_labels(tmp_path: Path) -> None:
    pdf = tmp_path / "spike.pdf"
    pdf.write_bytes(build_spike_pdf())
    exe = shutil.which("pdftotext")
    assert exe
    text = subprocess.run([exe, str(pdf), "-"], check=True, capture_output=True, text=True).stdout  # noqa: S603
    assert "SIMULATED DETECTIONS (not real AI)" in text
    assert "provider: simulated@0.1.0" in text
    assert "4-point inspection report" in text


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler-utils not installed")
def test_latin_line_after_a_bangla_line_keeps_its_glyphs(tmp_path: Path) -> None:
    """fpdf2 2.8.9 wrote wrong glyphs for a line that followed a Bangla line in the same font."""
    from threadeye.reports.pdf import ThreadEyePDF

    pdf = ThreadEyePDF(simulated=False, provider_label="x", title="t")
    pdf.add_page()
    pdf.use_font(16, bold=True)
    pdf.cell(80, 12, "  সিস্টেমের রায়: সীমার কাছাকাছি  ", new_x="LMARGIN", new_y="NEXT")
    pdf.use_font(10, bold=True)
    pdf.cell(0, 6, "সুপারভাইজারের সিদ্ধান্ত", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "ends from the mill", new_x="LMARGIN", new_y="NEXT")
    out = tmp_path / "t.pdf"
    pdf.output(str(out))
    exe = shutil.which("pdftotext")
    assert exe
    text = subprocess.run([exe, str(out), "-"], capture_output=True, text=True, check=True).stdout  # noqa: S603
    assert "ends from the mill" in text
