"""Verify a clean source snapshot without local environments, dependencies or credentials.

Uses a separate Docker project/database and only the generated synthetic CI roll. The snapshot
includes uncommitted implementation, so this is not a claim about the unmodified remote HEAD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise RuntimeError(f"missing executable: {arguments[0]}")
    return subprocess.run([executable, *arguments[1:]], **options)  # noqa: S603 -- fixed commands, no shell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    target = ROOT / "build" / f"fresh-source-{os.getpid()}"
    target.mkdir(parents=True)
    listing = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    hashes = {}
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        relative = Path(os.fsdecode(entry))
        if relative.name.startswith(".env") and relative.name not in {".env.example", ".env.cloud.example"}:
            raise ValueError("refusing to copy a private environment file")
        source = ROOT / relative
        if not source.is_file():
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        shutil.copymode(source, destination)
        hashes[str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
    fixture = target / "data/ci_roll"
    fixture.mkdir(parents=True)
    for name in (
        "roll_meta.json",
        "frames.csv",
        "ground_truth.csv",
        "nuisance.csv",
        "roll_video.mp4",
        "evaluation_manifest.json",
    ):
        shutil.copyfile(ROOT / "data/ci_roll" / name, fixture / name)
    (target / "SOURCE_SNAPSHOT.json").write_text(
        json.dumps(
            {
                "code_sha256": hashes,
                "assets": "Only synthetic CI assets injected; no private settings, dependencies or model weights.",
            },
            indent=2,
        )
    )
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("THREADEYE_") and key not in {"POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_DB"}
    }
    env = {
        **clean_env,
        "THREADEYE_ENV_FILE": ".env.example",
        "THREADEYE_IMAGE_TAG": "operations-fresh",
        "THREADEYE_HTTP_PORT": "8188",
        "COMPOSE_PROJECT_NAME": f"threadeye-fresh-{os.getpid()}",
    }
    command = ["docker", "compose", "--env-file", ".env.example"]
    log_path = ROOT / "build/fresh-source-check.log"
    try:
        with log_path.open("w") as log:
            run(
                [*command, "build", "api", "web"],
                cwd=target,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=600,
            )
            run(
                [*command, "up", "-d", "--no-build", "--wait"],
                cwd=target,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=120,
            )
            run(
                ["bash", "scripts/verify_offline.sh"],
                cwd=target,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=60,
            )
            if args.browser:
                run(
                    ["pnpm", "exec", "playwright", "test", "golden-path.spec.ts", "operations.spec.ts", "--workers=1"],
                    cwd=ROOT / "frontend",
                    env={**env, "E2E_BASE_URL": "http://localhost:8188", "E2E_DATASET": "ci_roll"},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=600,
                )
        summary = {
            "passed": True,
            "seconds": round(time.monotonic() - started, 2),
            "source_snapshot": str(target.relative_to(ROOT)),
            "source_files": len(hashes),
            "browser_checked": args.browser,
            "network": "app containers internal-only",
        }
        (ROOT / "build/fresh-source-check.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
    finally:
        run([*command, "down", "-v"], cwd=target, env=env, capture_output=True, timeout=60)


if __name__ == "__main__":
    main()
