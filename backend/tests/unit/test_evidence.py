"""Evidence must show the detected location even when legacy image metadata is stale."""

import io

from PIL import Image, ImageDraw

from threadeye.services.evidence import crop


def test_crop_uses_actual_image_scale_for_legacy_overwritten_capture() -> None:
    image = Image.new("RGB", (960, 62), "gray")
    draw = ImageDraw.Draw(image)
    # A blue marker at camera-view coordinates (1660, 200), actual scale 0.25.
    draw.rectangle((414, 49, 419, 54), fill="blue")
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=95)
    result = crop(buf.getvalue(), (1660, 200, 1668, 208), 0.5, size=240, view_width=3840)
    with Image.open(io.BytesIO(result)) as photo:
        pixels = list(photo.getdata())
        assert any(b > r + 60 and b > g + 60 for r, g, b in pixels)
        assert any(r > g + 100 and r > b + 100 for r, g, b in pixels)


def test_crop_keeps_box_visible_near_camera_edge() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (960, 62), "gray").save(buf, "JPEG")
    result = crop(buf.getvalue(), (3780, 225, 3820, 245), 0.25, size=240, view_width=3840)
    with Image.open(io.BytesIO(result)) as photo:
        assert any(r > g + 100 and r > b + 100 for r, g, b in photo.getdata())
