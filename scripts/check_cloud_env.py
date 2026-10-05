#!/usr/bin/env python3
"""Check .env.cloud before any cloud command, and say exactly what is wrong. Never prints secrets.

    python3 scripts/check_cloud_env.py [.env.cloud]

Without this, a missing or broken database URL makes the app fall back to a local database
(127.0.0.1:5432) and fail with a long, confusing "connection refused" traceback.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = {
    "THREADEYE_DATABASE_URL": ":6543/",  # transaction pooler
    "THREADEYE_MIGRATION_DATABASE_URL": ":5432/",  # session pooler
}
FIX = "Fix: run `make cloud-env` and paste the Supabase connection string (or get a working .env.cloud from the owner)."


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env.cloud")
    if not path.is_file():
        print(f"{path} is missing. {FIX}", file=sys.stderr)
        return 1
    raw = path.read_bytes()
    problems = []
    if b"\r" in raw:
        problems.append("the file has Windows line endings (CRLF); save it with Unix (LF) line endings")
    values: dict[str, str] = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        m = re.match(r"^\s*([A-Z_]+)\s*=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2).strip().strip("\r")
    if values.get("THREADEYE_DEPLOY_PROFILE") != "cloud_demo":
        problems.append("THREADEYE_DEPLOY_PROFILE must be cloud_demo")
    for name, port in REQUIRED.items():
        v = values.get(name, "")
        if not v:
            problems.append(f"{name} is missing or empty")
            continue
        if v[0] in "\"'":
            problems.append(f"{name} must not be in quotes")
        if not v.startswith("postgresql+psycopg://"):
            problems.append(f"{name} must start with postgresql+psycopg://")
        if "<" in v or "[YOUR-PASSWORD]" in v:
            problems.append(f"{name} still has a placeholder (<...> or [YOUR-PASSWORD])")
        if "localhost" in v or "127.0.0.1" in v:
            problems.append(f"{name} points at this computer, not Supabase")
        if port not in v:
            problems.append(f"{name} should use port {port.strip(':/')}")
        # In a shell-sourced file these characters break the value (the password must be URL-encoded).
        bad = sorted({c for c in v if c in " &;|$`\\'\"()<>"} - {"<", ">"})
        if bad:
            problems.append(f"{name} contains {' '.join(bad)}: the password must be URL-encoded (make cloud-env does it)")
    if not values.get("THREADEYE_DEMO_PASSWORD"):
        problems.append("THREADEYE_DEMO_PASSWORD is missing (the password of the demo logins)")
    if problems:
        print(f"{path} has problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(FIX, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
