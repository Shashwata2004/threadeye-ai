"""``threadeye`` command-line tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _export_openapi(args: argparse.Namespace) -> int:
    from threadeye.api.app import create_app

    spec = create_app().openapi()
    text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({len(spec.get('paths', {}))} paths)")
    return 0


def _validate_dataset(args: argparse.Namespace) -> int:
    from threadeye.datasets.contracts import format_report, validate_dataset

    report, _ = validate_dataset(args.directory, require_media=not args.no_media)
    format_report(report)
    return 0 if report.ok else 1


def _migrate(args: argparse.Namespace) -> int:
    from alembic import command

    from threadeye.db.migrate import alembic_config

    # sql=True prints the statements instead of connecting, so the schema can be created
    # through Supabase's Management API (`supabase db query`), which needs no DB password.
    command.upgrade(alembic_config(), "head", sql=args.sql)
    return 0


def _seed_demo_users(args: argparse.Namespace) -> int:
    from threadeye.security.seed import seed_demo_users, seed_demo_users_sql
    from threadeye.settings import get_settings

    password = get_settings().demo_password
    if not password:
        print("THREADEYE_DEMO_PASSWORD is not set; skipping demo users", file=sys.stderr)
        return 1
    if args.sql:
        print(seed_demo_users_sql(password))
        return 0

    from threadeye.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        created = seed_demo_users(db, password)
    print(f"demo users created: {', '.join(created) if created else 'none (already present)'}")
    return 0


def _cloud_check(_: argparse.Namespace) -> int:
    from threadeye.db.cloud_check import run_cloud_check

    report = run_cloud_check()
    print(report.render())
    return 0 if report.ok else 1


def _spike_pdf(args: argparse.Namespace) -> int:
    from threadeye.reports.spike import build_spike_pdf

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_spike_pdf())
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="threadeye", description="ThreadEye AI tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export-openapi", help="write the OpenAPI contract")
    p.add_argument("output", nargs="?", default="-")
    p.set_defaults(fn=_export_openapi)

    p = sub.add_parser("validate-dataset", help="check a simulator dataset against the data contracts")
    p.add_argument("directory")
    p.add_argument("--no-media", action="store_true", help="allow missing video/preview (CSV fixtures)")
    p.set_defaults(fn=_validate_dataset)

    p = sub.add_parser("migrate", help="apply database migrations (alembic upgrade head)")
    p.add_argument("--sql", action="store_true", help="print the SQL instead of connecting")
    p.set_defaults(fn=_migrate)

    p = sub.add_parser("seed-demo-users", help="create one demo account per role (password from env)")
    p.add_argument("--sql", action="store_true", help="print the SQL instead of connecting")
    p.set_defaults(fn=_seed_demo_users)

    p = sub.add_parser("cloud-check", help="verify a cloud database: schema, guards, audit chain")
    p.set_defaults(fn=_cloud_check)

    p = sub.add_parser("spike-pdf", help="render the Bangla shaping spike PDF")
    p.add_argument("output", nargs="?", default="out/spike_bangla.pdf")
    p.set_defaults(fn=_spike_pdf)

    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
