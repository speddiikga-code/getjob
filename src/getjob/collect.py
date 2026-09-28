"""`getjob collect`: run every enabled collector, filter, store, and report new postings."""

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import httpx

from getjob.collectors import build_collector
from getjob.models import Job
from getjob.profile import SearchProfile
from getjob.settings import Settings
from getjob.sources import SOURCES
from getjob.store import Store
from getjob.web import Http

CSV_COLUMNS = [
    "source", "company", "title", "location", "experience", "education",
    "employment_type", "salary", "posted_at", "deadline", "url",
]  # fmt: skip


@dataclass
class SourceResult:
    key: str
    fetched: int = 0
    matched: list[Job] = field(default_factory=list)
    new: int = 0
    error: str | None = None
    seconds: float = 0.0


def run(
    settings: Settings,
    profile: SearchProfile,
    keys: list[str],
    limit: int | None,
    csv_path: Path | None = None,
    show: int = 50,
    out: TextIO = sys.stdout,
    stop_at_known: bool = True,
) -> int:
    store = Store(settings.db_path)
    try:
        # Without stopping at known postings, a deep run reads past what was already seen.
        known = store.known_keys() if stop_at_known else set()
        with Http(settings) as http, ThreadPoolExecutor(max_workers=len(keys) or 1) as pool:
            results = list(
                pool.map(lambda key: _collect_one(key, http, settings, profile, limit, known), keys)
            )
        new_jobs: list[Job] = []
        for result in results:
            fresh = store.add(result.matched)
            result.new = len(fresh)
            new_jobs.extend(fresh)
    finally:
        store.close()

    _print_summary(results, out)
    _print_jobs(new_jobs, show, out)
    if csv_path and new_jobs:
        write_csv(new_jobs, csv_path)
        print(f"\nSaved {len(new_jobs)} new postings to {csv_path}", file=out)
    return 0 if any(r.error is None for r in results) else 1


def _collect_one(
    key: str,
    http: Http,
    settings: Settings,
    profile: SearchProfile,
    limit: int | None,
    known: set[str],
) -> SourceResult:
    result = SourceResult(key)
    started = time.monotonic()
    try:
        jobs = build_collector(key, http, settings).collect(limit, known.__contains__)
    except Exception as e:  # one broken site must not stop the others
        result.error = _describe(e)
    else:
        result.fetched = len(jobs)
        result.matched = [job for job in jobs if profile.accepts(job)]
    result.seconds = time.monotonic() - started
    return result


def _describe(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    return f"{type(error).__name__}: {error}"[:120]


def _print_summary(results: list[SourceResult], out: TextIO) -> None:
    print("\n[Sites]", file=out)
    for r in results:
        name = SOURCES[r.key].name
        if r.error:
            print(f"  FAIL  {name}: {r.error}", file=out)
        else:
            print(
                f"  OK    {name}: {r.fetched} fetched, {len(r.matched)} matched, "
                f"{r.new} new ({r.seconds:.0f}s)",
                file=out,
            )


def _print_jobs(jobs: list[Job], show: int, out: TextIO) -> None:
    print(f"\n[New postings: {len(jobs)}]", file=out)
    for job in jobs[:show]:
        details = " · ".join(
            filter(None, [job.location, job.experience, job.education, job.salary, job.deadline])
        )
        print(f"  [{SOURCES[job.source].name}] {job.company} — {job.title}", file=out)
        if details:
            print(f"      {details}", file=out)
        print(f"      {job.url}", file=out)
    if len(jobs) > show:
        print(f"  ... and {len(jobs) - show} more (use --csv to save them all)", file=out)


def write_csv(jobs: list[Job], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows Korean correctly
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for job in jobs:
            row = {**job.__dict__, "source": SOURCES[job.source].name}
            writer.writerow([row[c] if row[c] is not None else "" for c in CSV_COLUMNS])
