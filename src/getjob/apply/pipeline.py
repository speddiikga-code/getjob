"""`getjob draft`: pick postings within the weekly budget, draft them, write the packages."""

import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TextIO

from getjob.apply import drafter
from getjob.apply.config import ApplyProfile, Experience
from getjob.apply.shortlist import Candidate, rank
from getjob.apply.tracker import Application, Tracker
from getjob.models import Job
from getjob.store import Store


@dataclass
class Outcome:
    app: Application
    folder: Path | None = None
    engine: str = ""
    warnings: list[str] | None = None
    error: str | None = None


def candidates(
    store: Store, tracker: Tracker, profile: ApplyProfile, today: date
) -> list[Candidate]:
    """Postings worth applying to that the tracker doesn't have yet, best first."""
    since = datetime.combine(today - timedelta(days=profile.target.lookback_days), time.min)
    return rank(store.recent(since), profile.target, today, tracker.fingerprints())


def plan(store: Store, tracker: Tracker, profile: ApplyProfile, today: date) -> list[int]:
    """Queue as many of the best candidates as this week's budget allows.

    Nothing is queued during a quiet period of the main pilot.
    """
    if profile.focus.quiet_period(today):
        return []
    room = tracker.capacity(profile.budget.max_per_week, today)
    if room <= 0:
        return []
    return [tracker.add(c) for c in candidates(store, tracker, profile, today)[:room]]


def draft_one(
    app: Application,
    store: Store,
    tracker: Tracker,
    profile: ApplyProfile,
    experience: Experience,
    engine: str,
    out_dir: Path,
    today: date,
    api_key: str | None = None,
    client=None,
    fallback: bool = False,
) -> Outcome:
    """Draft one application. With `fallback`, a failed Claude draft becomes a template draft."""
    job = store.get(app.job_key) or Job(
        app.source, app.job_key.split(":", 1)[-1], app.title, app.company, app.url
    )
    folder = Path(app.folder) if app.folder else out_dir / drafter.folder_name(app.id, app.company)
    questions_path = folder / drafter.QUESTIONS_FILE
    if questions_path.exists():
        try:
            questions = drafter.parse_questions(questions_path.read_text(encoding="utf-8"))
        except ValueError as e:  # e.g. a limit outside 10-5000 characters
            return Outcome(app, folder, engine, error=f"{questions_path}: {e}")
    else:
        questions = list(profile.questions)
    if not questions:
        return Outcome(app, folder, engine, error=f"no questions in {questions_path}")

    deadline = app.deadline
    try:
        if engine == "claude":
            draft = drafter.draft_with_claude(
                job, deadline, questions, experience, profile.drafting.model, client, api_key
            )
        else:
            draft = drafter.draft_with_template(job, questions, experience)
    except drafter.DraftError as e:
        if not fallback:
            return Outcome(app, folder, engine, error=str(e))
        draft = drafter.draft_with_template(job, questions, experience)
        draft.todo.insert(0, f"Claude 초안 실패로 템플릿 초안입니다 ({e})")

    others = [a.company for a in tracker.find() if a.id != app.id]
    warnings = draft.warnings(app.company, others)
    files = {
        drafter.DRAFT_FILE: drafter.render(
            app.id, job, deadline, app.score, app.reasons, draft, warnings, today
        ),
        drafter.PROMPT_FILE: drafter.prompt_markdown(job, deadline, questions, experience),
    }
    if not questions_path.exists():
        files[drafter.QUESTIONS_FILE] = drafter.format_questions(questions, app.id)
    previous = folder / drafter.DRAFT_FILE
    if previous.exists():  # keep your edits from the last version
        previous.replace(folder / drafter.PREVIOUS_DRAFT_FILE)
    drafter.write_package(folder, files)
    tracker.set_drafted(app.id, folder)
    return Outcome(app, folder, draft.engine, warnings)


def run(
    store: Store,
    tracker: Tracker,
    profile: ApplyProfile,
    experience: Experience,
    engine: str,
    out_dir: Path,
    today: date,
    ids: list[int] | None = None,
    api_key: str | None = None,
    client=None,
    fallback: bool = False,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    expired = tracker.expire(today)
    problems = False
    if ids:
        apps = [app for i in ids if (app := tracker.get(i))]
        missing = sorted(set(ids) - {a.id for a in apps})
        if missing:
            problems = True
            print(f"No application with id {', '.join(map(str, missing))}", file=err)
    else:
        quiet = profile.focus.quiet_period(today)
        queued = plan(store, tracker, profile, today)
        if quiet:
            print(f"집중 기간 ({quiet.reason}, ~{quiet.end}): 새 공고를 고르지 않습니다.", file=out)
        else:
            print(f"새로 고른 공고: {len(queued)}건", file=out)
        apps = tracker.find(("queued",))

    outcomes = [
        draft_one(
            app,
            store,
            tracker,
            profile,
            experience,
            engine,
            out_dir,
            today,
            api_key,
            client,
            fallback,
        )
        for app in apps
    ]
    for o in outcomes:
        head = f"  #{o.app.id} {o.app.company} — {o.app.title}"
        if o.error:
            print(f"  FAIL{head[1:]}: {o.error}", file=out)
            continue
        print(f"{head}\n      {o.folder}  ({o.engine})", file=out)
        for w in o.warnings or []:
            print(f"      - {w}", file=out)
    if expired:
        print(f"마감이 지난 초안 {len(expired)}건을 정리했습니다.", file=out)
    return 1 if problems or any(o.error for o in outcomes) else 0
