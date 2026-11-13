"""Local-only browser boundary, bounded sessions, and CSRF state."""

from __future__ import annotations

import hmac
import secrets
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable


SESSION_COOKIE = "threadeye_ui_session"
PREAUTH_COOKIE = "threadeye_ui_preauth"
MAX_ACCESS_CODE_CHARS = 128
MIN_ACCESS_CODE_CHARS = 12


@dataclass
class BrowserSession:
    csrf_token: str
    created_at: float
    last_seen: float


@dataclass
class PreauthSession:
    csrf_token: str
    expires_at: float


class SessionStore:
    """Small process-local store suitable only for a single localhost demo."""

    def __init__(
        self,
        access_code: str,
        *,
        idle_seconds: int = 900,
        absolute_seconds: int = 1_800,
        preauth_seconds: int = 300,
        max_sessions: int = 16,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(access_code, str) or not MIN_ACCESS_CODE_CHARS <= len(access_code) <= MAX_ACCESS_CODE_CHARS:
            raise ValueError("local UI access code must contain 12 through 128 characters")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in access_code):
            raise ValueError("local UI access code cannot contain control characters")
        self._access_code = access_code
        self.idle_seconds = idle_seconds
        self.absolute_seconds = absolute_seconds
        self.preauth_seconds = preauth_seconds
        self.max_sessions = max_sessions
        self.clock = clock
        self._preauth: OrderedDict[str, PreauthSession] = OrderedDict()
        self._sessions: OrderedDict[str, BrowserSession] = OrderedDict()
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()

    def _cleanup(self) -> None:
        now = self.clock()
        for identifier, state in list(self._preauth.items()):
            if state.expires_at <= now:
                del self._preauth[identifier]
        for identifier, state in list(self._sessions.items()):
            if now - state.last_seen >= self.idle_seconds or now - state.created_at >= self.absolute_seconds:
                del self._sessions[identifier]
        for key, events in list(self._attempts.items()):
            while events and events[0] <= now - 60:
                events.popleft()
            if not events:
                del self._attempts[key]

    def new_preauth(self) -> tuple[str, str]:
        self._cleanup()
        identifier = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        self._preauth[identifier] = PreauthSession(csrf, self.clock() + self.preauth_seconds)
        while len(self._preauth) > self.max_sessions * 2:
            self._preauth.popitem(last=False)
        return identifier, csrf

    def login(self, preauth_id: str, csrf_token: str, access_code: str, client_key: str) -> tuple[str, BrowserSession] | None:
        self._cleanup()
        attempts = self._attempts.setdefault(client_key, deque())
        self._attempts.move_to_end(client_key)
        if len(attempts) >= 5:
            return None
        attempts.append(self.clock())
        state = self._preauth.pop(preauth_id, None)
        csrf_ok = state is not None and hmac.compare_digest(state.csrf_token, csrf_token)
        code_ok = isinstance(access_code, str) and hmac.compare_digest(self._access_code, access_code)
        if not csrf_ok or not code_ok:
            return None
        identifier = secrets.token_urlsafe(32)
        now = self.clock()
        session = BrowserSession(secrets.token_urlsafe(32), now, now)
        self._sessions[identifier] = session
        while len(self._sessions) > self.max_sessions:
            self._sessions.popitem(last=False)
        return identifier, session

    def get(self, identifier: str | None) -> BrowserSession | None:
        self._cleanup()
        if not identifier:
            return None
        state = self._sessions.get(identifier)
        if state is None:
            return None
        state.last_seen = self.clock()
        self._sessions.move_to_end(identifier)
        return state

    def csrf_valid(self, identifier: str | None, supplied: str | None) -> bool:
        state = self.get(identifier)
        return bool(state and supplied and hmac.compare_digest(state.csrf_token, supplied))

    def revoke(self, identifier: str | None) -> None:
        if identifier:
            self._sessions.pop(identifier, None)

    @property
    def active_sessions(self) -> int:
        self._cleanup()
        return len(self._sessions)
