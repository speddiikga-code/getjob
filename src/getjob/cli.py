"""Command-line entry point: `getjob <command>` (or `python -m getjob <command>`)."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from getjob import __version__, collect
from getjob.doctor import Doctor
from getjob.profile import load_profile
from getjob.settings import Settings
from getjob.sources import SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getjob",
        description="Automated 신입 · 정규직 job search in Seoul.",
    )
    parser.add_argument("--version", action="version", version=f"getjob {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check config, secrets and site reachability")
    doctor.add_argument("--offline", action="store_true", help="skip network checks")
    doctor.add_argument(
        "--all-sources", action="store_true", help="probe every supported site, not just enabled"
    )

    run = sub.add_parser("collect", help="search every enabled site and report new postings")
    run.add_argument(
        "--source",
        action="append",
        choices=list(SOURCES),
        help="only this site (repeatable); default: every site enabled in the profile",
    )
    size = run.add_mutually_exclusive_group()
    size.add_argument("--limit", type=int, help="newest postings to read per site")
    size.add_argument(
        "--all", action="store_true", help="read every posting on every site (slow; first run)"
    )
    run.add_argument(
        "--csv",
        nargs="?",
        const="auto",
        help="save new postings to a CSV file (default name: data/new_jobs_<time>.csv)",
    )
    run.add_argument("--show", type=int, default=50, help="new postings to print (default 50)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    if args.command == "doctor":
        return Doctor(settings).run(offline=args.offline, all_sources=args.all_sources)

    try:
        profile = load_profile(settings.profile_path)
    except (OSError, ValidationError) as e:
        print(f"Cannot load {settings.profile_path}: {e}", file=sys.stderr)
        return 1
    keys = args.source or profile.enabled_sources()
    limit = None if args.all else (args.limit or profile.limits.max_per_source)
    csv_path = None
    if args.csv == "auto":
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        csv_path = settings.db_path.parent / f"new_jobs_{stamp}.csv"
    elif args.csv:
        csv_path = Path(args.csv)
    return collect.run(settings, profile, keys, limit, csv_path=csv_path, show=args.show)
