"""Command-line entry point: `getjob <command>` (or `python -m getjob <command>`)."""

import argparse

from getjob import __version__
from getjob.doctor import Doctor
from getjob.settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getjob",
        description="Automated regular-job (정규직) search in Seoul.",
    )
    parser.add_argument("--version", action="version", version=f"getjob {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check config, secrets and site reachability")
    doctor.add_argument("--offline", action="store_true", help="skip network checks")
    doctor.add_argument(
        "--all-sources", action="store_true", help="probe every supported site, not just enabled"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return Doctor(Settings()).run(offline=args.offline, all_sources=args.all_sources)
    return 2
