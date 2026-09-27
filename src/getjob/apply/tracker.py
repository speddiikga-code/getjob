"""Every application the pipeline has taken on, from 초안 대기 to 최종 결과."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from getjob.apply.shortlist import Candidate
from getjob.deadline import Deadline, parse_deadline

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY,
    job_key      TEXT NOT NULL UNIQUE,
    fingerprint  TEXT NOT NULL UNIQUE,
    source       TEXT NOT NULL,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    deadline_raw TEXT NOT NULL DEFAULT '',
    deadline     TEXT,          -- resolved when added, so '~10/11' can't drift to next year
    score        INTEGER NOT NULL DEFAULT 0,
    reasons      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,
    stage        TEXT NOT NULL DEFAULT '',
    next_date    TEXT,
    folder       TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    drafted_at   TEXT,
    submitted_at TEXT,
    updated_at   TEXT NOT NULL
);
"""

# status -> label shown in `getjob apps` and the brief
STATUSES = {
    "queued": "초안 대기",
    "drafted": "검토·제출 대기",
    "submitted": "제출함",
    "next": "다음 전형",
    "offer": "최종 합격",
    "rejected": "불합격",
    "skipped": "건너뜀",
    "expired": "마감 지남",
}
ACTIVE = ("queued", "drafted", "submitted", "next")
# Statuses you set by hand with `getjob mark`.
MANUAL = ("submitted", "next", "offer", "rejected", "skipped", "drafted")  # drafted = un-skip


@dataclass
class Application:
    id: int
    job_key: str
    fingerprint: str
    source: str
    company: str
    title: str
    url: str
    deadline_raw: str
    deadline_date: date | None
    score: int
    reasons: str
    status: str
    stage: str
    next_date: date | None
    folder: str
    note: str
    created_at: str
    drafted_at: str | None
    submitted_at: str | None

    @property
    def deadline(self) -> Deadline:
        if self.deadline_date:
            return Deadline(self.deadline_raw, self.deadline_date)
        return parse_deadline(self.deadline_raw)  # only 상시 / unknown get here


COLUMNS = (
    "id, job_key, fingerprint, source, company, title, url, deadline_raw, deadline, score, "
    "reasons, status, stage, next_date, folder, note, created_at, drafted_at, submitted_at"
)


class Tracker:
    def __init__(self, path: Path, clock: Callable[[], datetime] = datetime.now) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.clock = clock

    def close(self) -> None:
        self.db.close()

    def _now(self) -> str:
        return self.clock().isoformat(timespec="seconds")

    # --- reading --------------------------------------------------------------

    def get(self, app_id: int) -> Application | None:
        row = self.db.execute(
            f"SELECT {COLUMNS} FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        return _application(row) if row else None

    def find(self, statuses: tuple[str, ...] | None = None) -> list[Application]:
        query = f"SELECT {COLUMNS} FROM applications"
        params: tuple = ()
        if statuses:
            query += f" WHERE status IN ({', '.join('?' * len(statuses))})"
            params = statuses
        return [_application(row) for row in self.db.execute(query + " ORDER BY id", params)]

    def fingerprints(self) -> set[str]:
        return {row[0] for row in self.db.execute("SELECT fingerprint FROM applications")}

    def drafted_since(self, since: date) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM applications WHERE drafted_at >= ?", (since.isoformat(),)
        ).fetchone()
        return row[0]

    def submitted_since(self, since: date) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM applications WHERE submitted_at >= ?", (since.isoformat(),)
        ).fetchone()
        return row[0]

    def capacity(self, max_per_week: int, today: date) -> int:
        """How many more postings may be drafted now.

        Limited by this week's budget and by the unreviewed backlog, so drafts never
        pile up faster than you review them.
        """
        monday = today - timedelta(days=today.weekday())
        backlog = len(self.find(("queued", "drafted")))
        return max(0, min(max_per_week - self.drafted_since(monday), max_per_week - backlog))

    # --- writing --------------------------------------------------------------

    def add(self, candidate: Candidate) -> int:
        job, now = candidate.job, self._now()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO applications (job_key, fingerprint, source, company, title, url, "
                "deadline_raw, deadline, score, reasons, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)",
                (
                    job.key,
                    job.fingerprint,
                    job.source,
                    job.company,
                    job.title,
                    job.url,
                    job.deadline,
                    deadline.isoformat() if (deadline := candidate.deadline.date) else None,
                    candidate.score,
                    ", ".join(candidate.reasons),
                    now,
                    now,
                ),
            )
        return cur.lastrowid

    def set_drafted(self, app_id: int, folder: Path) -> None:
        now = self._now()
        with self.db:
            self.db.execute(
                "UPDATE applications SET status = 'drafted', folder = ?, "
                "drafted_at = COALESCE(drafted_at, ?), updated_at = ? WHERE id = ?",
                (str(folder), now, now, app_id),
            )

    def mark(
        self,
        app_id: int,
        status: str,
        stage: str | None = None,
        next_date: date | None = None,
        note: str | None = None,
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}; use one of: {', '.join(STATUSES)}")
        now = self._now()
        with self.db:
            self.db.execute(
                "UPDATE applications SET status = ?, stage = COALESCE(?, stage), "
                "next_date = ?, note = COALESCE(?, note), updated_at = ?, "
                "submitted_at = CASE WHEN ? IN ('submitted', 'next') "
                "THEN COALESCE(submitted_at, ?) ELSE submitted_at END WHERE id = ?",
                (
                    status,
                    stage,
                    next_date.isoformat() if next_date else None,
                    note,
                    now,
                    status,
                    now,
                    app_id,
                ),
            )

    def expire(self, today: date) -> list[Application]:
        """Move 초안 대기 / 검토·제출 대기 applications whose deadline passed to `expired`."""
        expired = [
            app
            for app in self.find(("queued", "drafted"))
            if (left := app.deadline.days_left(today)) is not None and left < 0
        ]
        for app in expired:
            self.mark(app.id, "expired")
        return expired


def _application(row: tuple) -> Application:
    values = list(row)
    for i in (8, 13):  # deadline, next_date
        values[i] = date.fromisoformat(values[i]) if values[i] else None
    return Application(*values)
