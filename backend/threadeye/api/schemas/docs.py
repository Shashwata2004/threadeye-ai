"""Bounded public documentation content; no executable markup or remote images."""

from __future__ import annotations

import base64
import binascii
import io
import re
from typing import Literal, Self
from urllib.parse import parse_qs, urlsplit

from PIL import Image, UnidentifiedImageError
from pydantic import AwareDatetime, Field, field_validator, model_validator

from threadeye.api.schemas.common import ApiModel


class DocsText(ApiModel):
    en: str = Field(min_length=1, max_length=6000)
    bn: str = Field(min_length=1, max_length=6000)


class DocsSection(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    title: DocsText
    body: DocsText
    visible: bool = True
    diagram: Literal["architecture", "inspection"] | None = None
    steps: list[DocsText] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def diagram_steps(self) -> Self:
        if self.diagram == "architecture" and len(self.steps) != 4:
            raise ValueError("architecture diagrams require four node labels")
        if self.diagram == "inspection" and len(self.steps) < 2:
            raise ValueError("inspection diagrams require at least two steps")
        return self


def safe_https(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("use a public HTTPS URL without embedded credentials")
    return value


def resize_portrait(value: str | None) -> str | None:
    if not value:
        return None
    if not re.fullmatch(r"data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+", value):
        raise ValueError("portrait must be a base64 JPEG, PNG or WebP image")
    try:
        raw = base64.b64decode(value.split(",", 1)[1], validate=True)
        if len(raw) > 60_000:
            raise ValueError("portrait upload must be at most 60 KB after browser resizing")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or max(image.size) > 1024:
                raise ValueError("portrait dimensions must be at most 1024 pixels")
            image.load()
            image.thumbnail((256, 256))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (OSError, UnidentifiedImageError, binascii.Error, Image.DecompressionBombError) as exc:
        raise ValueError("portrait could not be decoded") from exc


class DocsMember(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    role: DocsText
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    image_data: str | None = Field(default=None, max_length=85_000)
    github_username: str | None = Field(default=None, max_length=39, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")

    @field_validator("image_data")
    @classmethod
    def portrait(cls, value: str | None) -> str | None:
        return resize_portrait(value)


class DocsConfig(ApiModel):
    revision: int = Field(default=0, ge=0)
    enabled: bool = False
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    project_name: str = Field(default="ThreadEye AI", min_length=1, max_length=100)
    team_name: str = Field(default="DU_Synapse", min_length=1, max_length=100)
    tagline: DocsText
    repository_url: str = Field(max_length=500)
    app_url: str = Field(max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    show_live: bool = True
    show_apis: bool = True
    show_team: bool = True
    sections: list[DocsSection] = Field(min_length=1, max_length=20)
    members: list[DocsMember] = Field(default_factory=list, max_length=12)

    @field_validator("repository_url", "app_url")
    @classmethod
    def https_link(cls, value: str) -> str:
        return safe_https(value)

    @field_validator("video_url")
    @classmethod
    def youtube_link(cls, value: str | None) -> str | None:
        if not value:
            return None
        safe_https(value)
        parts = urlsplit(value)
        if parts.hostname == "youtu.be":
            video_id = parts.path.strip("/")
        elif parts.hostname in {"youtube.com", "www.youtube.com"} and parts.path == "/watch":
            video_id = parse_qs(parts.query).get("v", [""])[0]
        else:
            raise ValueError("use a YouTube watch URL or youtu.be link")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError("invalid YouTube video ID")
        return f"https://www.youtube.com/watch?v={video_id}"

    @model_validator(mode="after")
    def unique_ids_and_window(self) -> Self:
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValueError("availability end must be later than start")
        for values in (self.sections, self.members):
            ids = [value.id for value in values]
            if len(ids) != len(set(ids)):
                raise ValueError("section and member IDs must be unique")
        return self


class DocsApiEntry(ApiModel):
    path: str
    methods: list[str]
    access: str


class DocsLive(ApiModel):
    generated_at: AwareDatetime
    version: str
    profile: str
    database: Literal["ok"] = "ok"
    worker_alive: bool
    active_provider: str
    detector_is_simulated: bool
    registered_rolls: int
    inspections: int
    finalized_inspections: int
    simulated_video_inspections: int
    active_users: int
    audit_events: int
    verdicts: dict[str, int]
    runtime: dict[str, str]
    evaluation: dict[str, float | int | str | None] | None = None


class DocsDocument(ApiModel):
    content: DocsConfig
    live: DocsLive | None = None
    apis: list[DocsApiEntry] = Field(default_factory=list)
