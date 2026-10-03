from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from threadeye.api.schemas.common import ApiModel
from threadeye.security.rbac import Role

Locale = Literal["bn", "en"]
DigitStyle = Literal["latin", "bengali"]


class LoginIn(ApiModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class MeOut(ApiModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    locale: Locale
    digit_style: DigitStyle
    permissions: list[str]


class MePatch(ApiModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    locale: Locale | None = None
    digit_style: DigitStyle | None = None


class UserOut(ApiModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    locale: Locale
    digit_style: DigitStyle
    active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    role: Role
    password: str = Field(min_length=10, max_length=256)
    locale: Locale | None = None


class UserPatch(ApiModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: Role | None = None
    active: bool | None = None
    locale: Locale | None = None
