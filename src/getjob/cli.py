"""Command-line entry point: `getjob <command>` (or `python -m getjob <command>`)."""

import argparse
import sys
import traceback
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from getjob import __version__, clock, collect, notify
from getjob.apply import brief, drafter, pipeline
from getjob.apply.config import load_apply_profile, load_experience
from getjob.apply.tracker import ACTIVE, MANUAL, STATUSES, Tracker
from getjob.doctor import Doctor
from getjob.profile import load_profile
from getjob.settings import Settings
from getjob.sources import SOURCES
from getjob.store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getjob",
        description="Automated 신입 · 정규직 job search in Seoul, with application drafts.",
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
        "--all",
        action="store_true",
        help="read every posting on every site, past ones already seen (slow)",
    )
    run.add_argument(
        "--csv",
        nargs="?",
        const="auto",
        help="save new postings to a CSV file (default name: data/new_jobs_<time>.csv)",
    )
    run.add_argument("--show", type=int, default=50, help="new postings to print (default 50)")

    shortlist = sub.add_parser(
        "shortlist", help="show which collected postings would be picked, and why (no changes)"
    )
    shortlist.add_argument("--show", type=int, default=20, help="candidates to print")

    draft = sub.add_parser(
        "draft", help="pick postings within the weekly budget and draft 자기소개서 for them"
    )
    draft.add_argument(
        "--id", type=int, action="append", dest="ids", help="re-draft this application only"
    )
    draft.add_argument("--engine", choices=["auto", "template", "claude"], help="override")

    apps = sub.add_parser("apps", help="list applications (active ones unless --all)")
    apps.add_argument("--all", action="store_true", help="include finished and skipped ones")

    mark = sub.add_parser("mark", help="record what happened to an application")
    mark.add_argument("id", type=int)
    mark.add_argument(
        "status", choices=MANUAL, help=", ".join(f"{s}={STATUSES[s]}" for s in MANUAL)
    )
    mark.add_argument("--stage", help="e.g. 인적성, 1차 면접 (with status 'next')")
    mark.add_argument("--date", type=date.fromisoformat, help="date of that stage, YYYY-MM-DD")
    mark.add_argument("--note", help="free text")

    brief_cmd = sub.add_parser("brief", help="print (or send) the status message")
    brief_cmd.add_argument("--send", action="store_true", help="send to notify.channels")

    daily = sub.add_parser("run", help="collect + draft + brief: the command to schedule")
    daily.add_argument("--send", action="store_true", help="send the brief to notify.channels")
    daily.add_argument("--limit", type=int, help="newest postings to read per site")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    if args.command == "doctor":
        return Doctor(settings).run(offline=args.offline, all_sources=args.all_sources)
    try:
        return COMMANDS[args.command](args, settings)
    except (OSError, ValidationError, yaml.YAMLError) as e:
        print(f"getjob {args.command}: {e}", file=sys.stderr)
        return 1


def cmd_collect(args, settings: Settings) -> int:
    profile = load_profile(settings.profile_path)
    keys = args.source or profile.enabled_sources()
    limit = None if args.all else (args.limit or profile.limits.max_per_source)
    csv_path = None
    if args.csv == "auto":
        stamp = clock.now().strftime("%Y%m%d_%H%M")
        csv_path = settings.db_path.parent / f"new_jobs_{stamp}.csv"
    elif args.csv:
        csv_path = Path(args.csv)
    return collect.run(
        settings,
        profile,
        keys,
        limit,
        csv_path=csv_path,
        show=args.show,
        stop_at_known=not args.all,
    )


def cmd_shortlist(args, settings: Settings) -> int:
    profile = load_apply_profile(settings.apply_path)
    today = clock.today()
    store, tracker = Store(settings.db_path), Tracker(settings.db_path)
    try:
        found = pipeline.candidates(store, tracker, profile, today)
        room = tracker.capacity(profile.budget.max_per_week, today)
    finally:
        store.close()
        tracker.close()
    quiet = profile.focus.quiet_period(today)
    print(f"[Candidates: {len(found)}] room this week: {0 if quiet else room}")
    if quiet:
        print(f"  집중 기간 ~{quiet.end} ({quiet.reason}): 새 초안을 만들지 않습니다.")
    for c in found[: args.show]:
        print(f"  {c.score:>3}  {c.job.company} — {c.job.title}")
        print(f"       {c.deadline.label(today)} · {', '.join(c.reasons)} · {c.job.url}")
    return 0


def cmd_draft(args, settings: Settings) -> int:
    profile = load_apply_profile(settings.apply_path)
    experience = load_experience(settings.experience_path)
    choice = args.engine or profile.drafting.engine
    engine = drafter.resolve_engine(choice, settings.anthropic_key)
    if engine is None:
        print(
            "The Claude engine needs ANTHROPIC_API_KEY in .env and: pip install 'getjob[ai]'",
            file=sys.stderr,
        )
        return 1
    store, tracker = Store(settings.db_path), Tracker(settings.db_path)
    try:
        return pipeline.run(
            store,
            tracker,
            profile,
            experience,
            engine,
            settings.applications_dir,
            clock.today(),
            ids=args.ids,
            api_key=settings.anthropic_key,
            fallback=choice == "auto",  # a failed Claude draft becomes a template draft
        )
    finally:
        store.close()
        tracker.close()


def cmd_apps(args, settings: Settings) -> int:
    today = clock.today()
    tracker = Tracker(settings.db_path)
    try:
        apps = tracker.find(None if args.all else ACTIVE)
    finally:
        tracker.close()
    print(f"[Applications: {len(apps)}]")
    for app in apps:
        extra = app.deadline.label(today)
        if app.status == "next":
            extra = f"{app.stage} {app.next_date or ''}".strip()
        print(f"  #{app.id:<4} {STATUSES[app.status]:<8} {app.company} — {app.title[:40]}  {extra}")
        if app.folder and app.status in ("queued", "drafted"):
            print(f"         {app.folder}")
    return 0


def cmd_mark(args, settings: Settings) -> int:
    tracker = Tracker(settings.db_path)
    try:
        app = tracker.get(args.id)
        if app is None:
            print(f"No application with id {args.id}", file=sys.stderr)
            return 1
        tracker.mark(args.id, args.status, stage=args.stage, next_date=args.date, note=args.note)
    finally:
        tracker.close()
    print(f"#{app.id} {app.company}: {STATUSES[args.status]}")
    return 0


def cmd_brief(args, settings: Settings) -> int:
    return _brief(settings, args.send)


def cmd_run(args, settings: Settings) -> int:
    profile = load_profile(settings.profile_path)
    limit = args.limit or profile.limits.max_per_source
    codes = [collect.run(settings, profile, profile.enabled_sources(), limit, show=10)]
    print("\n[Drafts]")
    try:
        codes.append(cmd_draft(argparse.Namespace(ids=None, engine=None), settings))
    except Exception as e:  # the brief must go out even when drafting breaks
        print(f"  FAIL  drafting stopped: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        codes.append(1)
    print("\n[Brief]")
    codes.append(_brief(settings, args.send))
    return max(codes)


def _brief(settings: Settings, send: bool) -> int:
    profile = load_apply_profile(settings.apply_path)
    tracker = Tracker(settings.db_path)
    try:
        subject, text = brief.build(tracker, profile, clock.today())
    finally:
        tracker.close()
    print(f"{subject}\n\n{text}")
    if not send:
        return 0
    channels = load_profile(settings.profile_path).notify.channels
    problems = notify.send(settings, channels, subject, text)
    for p in problems:
        print(f"  WARN  {p}", file=sys.stderr)
    return 1 if problems and len(problems) == len(channels) else 0


COMMANDS = {
    "collect": cmd_collect,
    "shortlist": cmd_shortlist,
    "draft": cmd_draft,
    "apps": cmd_apps,
    "mark": cmd_mark,
    "brief": cmd_brief,
    "run": cmd_run,
}
