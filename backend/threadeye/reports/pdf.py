"""PDF base for every ThreadEye report: fpdf2 + HarfBuzz text shaping for correct Bangla.

fpdf2 and uharfbuzz are pure wheels, so the same code runs in Docker (edge) and on Vercel (cloud).
Noto Sans renders Latin text and Noto Sans Bengali is the per-glyph fallback for Bangla.
Every report carries the provider label and, when simulated, a SIMULATED watermark and footer.

RULE (found in the M0 spike): always select the LATIN family via ``use_font``, including for Bangla
text. The Bengali fallback picks up Bangla runs and shapes them correctly. Selecting NotoSansBengali
as the primary font drops Latin glyphs and breaks shaping in mixed lines ("পরিদর্শন" → "পরদির্শন").

FOUND IN M2 (fpdf2 2.8.9): after a cell that used the Bengali fallback, the next cell with the very
same font settings can be written with wrong glyphs ("ends from the mill" → "RBCfi wo").
``cell`` below re-selects the font after any Bangla cell, which avoids it. Regression test:
tests/unit/test_pdf_spike.py.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from fpdf import FPDF

FONT_DIR = Path(str(resources.files("threadeye.reports").joinpath("fonts")))
LATIN = "NotoSans"
BENGALI = "NotoSansBengali"


class ThreadEyePDF(FPDF):
    def __init__(
        self, *, simulated: bool, provider_label: str, title: str, detections_simulated: bool | None = None
    ) -> None:
        """``simulated``: the roll video is simulated (watermark). ``detections_simulated``: the detector is the
        simulated one too (default: as ``simulated``); with our trained model only the video is."""
        super().__init__(orientation="P", unit="mm", format="A4")
        self.simulated = simulated
        self.detections_simulated = simulated if detections_simulated is None else detections_simulated
        self.provider_label = provider_label
        self.report_title = title
        self.set_title(title)
        self.set_author("ThreadEye AI")
        self.set_creator("ThreadEye AI (fpdf2)")
        for family, stem in ((LATIN, "NotoSans"), (BENGALI, "NotoSansBengali")):
            self.add_font(family, "", str(FONT_DIR / f"{stem}-Regular.ttf"))
            self.add_font(family, "B", str(FONT_DIR / f"{stem}-Bold.ttf"))
        self.set_fallback_fonts([BENGALI], exact_match=False)
        self.set_text_shaping(use_shaping_engine=True)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_font(LATIN, size=11)
        self._after_bangla = False

    def cell(self, *args: Any, **kwargs: Any) -> Any:
        if self._after_bangla:
            family, style, size = self.font_family, self.font_style, self.font_size_pt
            super().set_font(family, style, size + 1)
            super().set_font(family, style, size)
        text = kwargs.get("text", args[2] if len(args) > 2 else "")
        self._after_bangla = any("\u0980" <= ch <= "\u09ff" for ch in str(text or ""))
        return super().cell(*args, **kwargs)

    def use_font(self, size: float, bold: bool = False) -> None:
        """The only way report code should pick a font (see module docstring)."""
        self.set_font(LATIN, "B" if bold else "", size)

    def header(self) -> None:
        if self.simulated:
            self._watermark()
        self.set_font(LATIN, "B", 9)
        self.set_text_color(90, 90, 90)
        self.cell(0, 6, f"ThreadEye AI · {self.report_title}", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font(LATIN, size=8)
        self.set_text_color(90, 90, 90)
        if self.detections_simulated:
            mode = "SIMULATED DETECTIONS (not real AI)"
        elif self.simulated:
            mode = "SIMULATED VIDEO · detections by the trained model"
        else:
            mode = "Detections"
        self.cell(0, 5, f"{mode} · provider: {self.provider_label}", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, f"Page {self.page_no()}/{{nb}}", align="R")
        self.set_text_color(0, 0, 0)

    def _watermark(self) -> None:
        with self.local_context():
            self.set_font(LATIN, "B", 64)
            self.set_text_color(235, 200, 200)
            with self.rotation(angle=35, x=self.w / 2, y=self.h / 2):
                self.text(x=self.w / 2 - 75, y=self.h / 2 + 10, text="SIMULATED")
