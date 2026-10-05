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


def _seed_sample_data(_: argparse.Namespace) -> int:
    from threadeye.db.session import get_sessionmaker
    from threadeye.services.receiving import seed_sample_data

    with get_sessionmaker()() as db:
        created = seed_sample_data(db)
    print(f"sample data created: {', '.join(created) if created else 'none (already present)'}")
    return 0


def _run_sample(args: argparse.Namespace) -> int:
    import json as _json

    from threadeye.core.scoring.profile import default_profile, simulator_parity_profile
    from threadeye.services.benchmark import run_roll

    profile = simulator_parity_profile() if args.profile == "parity" else default_profile()
    run = run_roll(args.directory, preset=args.preset, profile=profile, use_video=args.video)
    s, e, ev = run.score, run.expected, run.evaluation
    if args.json:
        print(
            _json.dumps(
                {
                    "dataset": run.dataset,
                    "provider": run.provider_label,
                    "simulated": True,
                    "preset": dict(run.preset),
                    "profile": run.profile_name,
                    "frames": run.frames,
                    "frames_sampled": run.frames_sampled,
                    "coverage_pct": run.coverage_pct,
                    "score": {"points": s.total_points, "per_100": round(s.per_100, 2), "verdict": s.verdict},
                    "expected": e,
                    "matches_expected": run.matches_expected,
                    "evaluation": ev.as_dict(),
                    "defects": run.defects,
                },
                indent=2,
            )
        )
    else:
        print(
            f"SIMULATED DETECTIONS ({run.provider_label}, not AI) · dataset {run.dataset} · profile {run.profile_name}"
        )
        print(
            f"frames {run.frames}, sampled {run.frames_sampled} "
            f"({run.frames_sampled / max(run.frames, 1):.1%}), roll coverage {run.coverage_pct}%"
        )
        print(f"\n{'defect':<7}{'kind':<14}{'class':<14}{'yd':>8}{'len in':>8}{'pts':>5}  explanation")
        for d in run.defects:
            kind = d["nondefect_category"] or "defect"
            print(
                f"{d['defect_no']:<7}{kind:<14}{d['current_cls']:<14}{d['center_yd']:>8.3f}"
                f"{d['length_in']:>8.2f}{d['points'] or 0:>5}  {d['explanation']}"
            )
        print("\nper yard: " + ", ".join(f"yd{c}={p}" for c, p in s.cells.items()))
        for line in s.explanation[-1:]:
            print(line)
        print(
            f"expected (roll_meta): {e['total_points']} points, {e['points_per_100_sq_yd']} → {e['verdict']}"
            f"   {'MATCH' if run.matches_expected else 'MISMATCH'}"
        )
        print(
            f"detection vs answer key: precision {ev.precision:.2f}, recall {ev.recall:.2f}, F1 {ev.f1:.2f}, "
            f"FP {ev.fp} {ev.fp_by_type or ''}, missed {ev.missed or 'none'}"
        )
        if ev.nondefects_ignored:
            print(f"non-defects shown but not scored: {ev.nondefects_ignored}")
    return 1 if args.expect and not run.matches_expected else 0


def _cloud_check(_: argparse.Namespace) -> int:
    from threadeye.db.cloud_check import run_cloud_check

    report = run_cloud_check()
    print(report.render())
    return 0 if report.ok else 1


def _upload_video(args: argparse.Namespace) -> int:
    """Cloud profile: keep a simulated roll's video in the shared database, for hosts without local files."""
    from sqlalchemy import delete, text

    from threadeye.db.models import Blob
    from threadeye.db.session import get_sessionmaker
    from threadeye.services import storage
    from threadeye.settings import get_settings

    if not get_settings().is_cloud:
        print("upload-video is for the cloud profile: run `make cloud-upload-video`")
        return 1
    directory = Path(args.directory)
    video = directory / "roll_video.mp4"
    if not video.is_file():
        print(f"{video} not found")
        return 1
    data = video.read_bytes()
    key = storage.video_key(directory.name)
    with get_sessionmaker()() as db:
        # One large statement: lift Supabase's per-statement time limit for this transaction only,
        # and send the bytes once (delete + insert, not an upsert that repeats them).
        db.execute(text("SET LOCAL statement_timeout = '15min'"))
        db.execute(delete(Blob).where(Blob.key == key))
        sha = storage.put(db, key, data, content_type="video/mp4")
        db.commit()
    print(f"uploaded {video} ({len(data) / 1e6:.1f} MB, sha256 {sha[:16]}) as {key}")
    return 0


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

    p = sub.add_parser("seed-sample-data", help="rule profiles, a machine, fictional mills and a buyer (SAMPLE DATA)")
    p.set_defaults(fn=_seed_sample_data)

    p = sub.add_parser("run-sample", help="run a simulated roll headless and score it (SIMULATED, not AI)")
    p.add_argument("directory")
    p.add_argument("--preset", choices=["perfect", "realistic"], default="perfect")
    p.add_argument("--profile", choices=["parity", "default"], default="parity")
    p.add_argument("--video", action="store_true", help="decode roll_video.mp4 (needs the vision extra)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--expect", action="store_true", help="exit 1 unless the score equals roll_meta.expected_score")
    p.set_defaults(fn=_run_sample)

    p = sub.add_parser("cloud-check", help="verify a cloud database: schema, guards, audit chain")
    p.set_defaults(fn=_cloud_check)

    p = sub.add_parser("upload-video", help="cloud: store a simulated roll's video in Supabase")
    p.add_argument("directory")
    p.set_defaults(fn=_upload_video)

    p = sub.add_parser("spike-pdf", help="render the Bangla shaping spike PDF")
    p.add_argument("output", nargs="?", default="out/spike_bangla.pdf")
    p.set_defaults(fn=_spike_pdf)

    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
