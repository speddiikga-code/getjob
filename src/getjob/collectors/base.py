"""Base class for site collectors."""

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date
from typing import ClassVar

from getjob import clock
from getjob.models import Job
from getjob.web import Http

# Safety net in case a site ignores the page parameter and keeps returning results.
MAX_PAGES = 500


class Collector(ABC):
    """Fetches 서울 · 신입(incl. 경력무관) · 정규직 postings from one site, newest first."""

    key: ClassVar[str]
    # False when the site cannot sort newest-first; then paging never stops early.
    newest_first: ClassVar[bool] = True

    def __init__(self, http: Http) -> None:
        self.http = http

    @abstractmethod
    def fetch_page(self, page: int) -> list[Job]:
        """Return the postings on result page `page` (1-based); empty when past the end."""

    def keep(self, job: Job) -> bool:
        """Drop postings the site's own search filters can't exclude."""
        return True

    def collect(self, limit: int | None, is_known: Callable[[str], bool]) -> list[Job]:
        """Page through results until `limit` postings, the end, or already-seen postings.

        `limit=None` means no limit. When results are sorted newest-first, a page made
        only of postings seen on a previous run means everything after it is old too.
        """
        jobs: list[Job] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            batch = [job for job in self.fetch_page(page) if job.source_id not in seen]
            if not batch:
                break
            seen.update(job.source_id for job in batch)
            jobs.extend(job for job in batch if self.keep(job))
            if limit is not None and len(jobs) >= limit:
                return jobs[:limit]
            if self.newest_first and all(is_known(job.key) for job in batch):
                break
        return jobs


def text(node) -> str:
    """Whitespace-collapsed text of a BeautifulSoup node (or '' for None)."""
    return " ".join(node.get_text(" ", strip=True).split()) if node is not None else ""


def past_month_day(month: int, day: int, today: date | None = None) -> date | None:
    """Date of a past 'MM.DD' (no year given): this year, or last year if still ahead."""
    today = today or clock.today()
    year = today.year if (month, day) <= (today.month, today.day) else today.year - 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    """Parse the start of '2026-09-26', '2026.09.26' or '2026-09-26T00:00:00+09:00'."""
    if not value:
        return None
    m = re.match(r"\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})", value)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
