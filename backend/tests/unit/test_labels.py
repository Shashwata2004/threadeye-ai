"""QR roll labels must be scannable (regression: segno.make picked an unreadable Micro QR)."""

from __future__ import annotations

import pytest

from threadeye.reports.labels import LabelData, _qr_png, build_labels_pdf


def label(code: str) -> LabelData:
    return LabelData(code, "R1", "CH-1", "Mill (fictional)", "Buyer (fictional)", "Twill", 100.0, 58.0, None, True)


def test_one_page_per_roll() -> None:
    pdf = build_labels_pdf([label("TE-000001"), label("TE-000002")])
    assert pdf.startswith(b"%PDF-")
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 2
    with pytest.raises(ValueError):
        build_labels_pdf([])


@pytest.mark.parametrize("code", ["TE-000001", "TE-123456", "TE-999999"])
def test_qr_is_a_standard_qr_that_decodes_to_the_roll_code(code: str) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = cv2.imdecode(np.frombuffer(_qr_png(code).getvalue(), np.uint8), cv2.IMREAD_GRAYSCALE)
    decoded, _points, _ = cv2.QRCodeDetectorAruco().detectAndDecode(img)
    assert decoded == code
