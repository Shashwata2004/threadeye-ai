import base64
import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from pydantic import ValidationError

from threadeye.api.routers.docs import visible
from threadeye.api.schemas.docs import DocsConfig, resize_portrait
from threadeye.services.docs_content import default_config


def test_portrait_is_resized_and_reencoded() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 300), "green").save(buffer, format="PNG")
    result = resize_portrait("data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode())
    assert result and result.startswith("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.b64decode(result.split(",")[1]))) as image:
        assert image.size == (256, 128)
        assert not image.getexif()


def test_schedule_timezone_and_boundaries() -> None:
    values = default_config().model_dump(mode="json")
    values.update(enabled=True, starts_at="2026-11-21T12:00:00+06:00", ends_at="2026-11-21T13:00:00+06:00")
    c = DocsConfig.model_validate(values)
    assert visible(c, datetime(2026, 11, 21, 6, tzinfo=UTC))
    assert not visible(c, datetime(2026, 11, 21, 7, tzinfo=UTC))
    values["starts_at"] = "2026-11-21T12:00:00"
    with pytest.raises(ValidationError):
        DocsConfig.model_validate(values)


def test_github_profile_is_an_optional_username() -> None:
    values = default_config().model_dump(mode="json")
    assert values["members"][0]["github_username"] == "Shashwata2004"
    values["members"][0]["github_username"] = "https://github.com/example"
    with pytest.raises(ValidationError):
        DocsConfig.model_validate(values)
    values["members"][0].pop("github_username")
    assert DocsConfig.model_validate(values).members[0].github_username is None
