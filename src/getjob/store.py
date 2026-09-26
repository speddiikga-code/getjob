"""SQLite database of every posting seen, so each run reports only new ones."""

import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from getjob.models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key             TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    fingerprint     TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    url             TEXT NOT NULL,
    location        TEXT,
    experience      TEXT,
    education       TEXT,
    employment_type TEXT,
    salary          TEXT,
    posted_at       TEXT,
    deadline        TEXT,
    tags            TEXT,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs (fingerprint);
"""
COLUMNS = [
    "key", "source", "source_id", "fingerprint", "title", "company", "url", "location",
    "experience", "education", "employment_type", "salary", "posted_at", "deadline", "tags",
    "first_seen", "last_seen",
]  # fmt: skip


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def known_keys(self) -> set[str]:
        return {row[0] for row in self.db.execute("SELECT key FROM jobs")}

    def add(self, jobs: list[Job]) -> list[Job]:
        """Save `jobs`; return the ones never seen before on any site.

        A posting already stored from another site (same company and title) is saved
        but not returned again, so the same job listed on 사람인 and 고용24 is reported once.
        """
        now = datetime.now().isoformat(timespec="seconds")
        fingerprints = {row[0] for row in self.db.execute("SELECT fingerprint FROM jobs")}
        new: list[Job] = []
        with self.db:
            for job in jobs:
                cur = self.db.execute("UPDATE jobs SET last_seen = ? WHERE key = ?", (now, job.key))
                if cur.rowcount:
                    continue
                row = {
                    **asdict(job),
                    "key": job.key,
                    "fingerprint": job.fingerprint,
                    "posted_at": job.posted_at.isoformat() if job.posted_at else None,
                    "tags": ", ".join(job.tags),
                    "first_seen": now,
                    "last_seen": now,
                }
                self.db.execute(
                    f"INSERT INTO jobs ({', '.join(COLUMNS)}) "
                    f"VALUES ({', '.join(':' + c for c in COLUMNS)})",
                    row,
                )
                if job.fingerprint not in fingerprints:
                    fingerprints.add(job.fingerprint)
                    new.append(job)
        return new

    def close(self) -> None:
        self.db.close()
