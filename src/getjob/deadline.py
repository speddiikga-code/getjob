"""Turn the many ways sites write an application deadline into a date.

Examples seen on the supported sites: `~ 10/11(일)` (사람인), `2026-10-26` (잡코리아, 고용24),
`~10.26` (인크루트), `10.26` (피플앤잡), `26.10.07` (잡알리오), `오늘마감`, `D-3`,
`상시채용`, `채용시까지`.
"""

import datetime as dt
import re
from dataclasses import dataclass
from datetime import timedelta

from getjob import clock
from getjob.collectors.base import parse_date

_ROLLING = ("상시", "채용시", "수시", "충원시", "마감시")
_D_DAY = re.compile(r"D\s*-\s*(\d+)|D-?day", re.IGNORECASE)
_YY_MM_DD = re.compile(r"(?<!\d)(\d{2})\.(\d{1,2})\.(\d{1,2})(?!\d)")
_MM_DD = re.compile(r"(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?!\d)")
# A month/day more than this far in the past is read as next year's date.
_PAST_TOLERANCE = timedelta(days=60)


@dataclass(frozen=True)
class Deadline:
    raw: str
    date: dt.date | None = None
    rolling: bool = False  # 상시채용 / 채용시까지: open until filled

    def days_left(self, today: dt.date) -> int | None:
        return (self.date - today).days if self.date else None

    def label(self, today: dt.date) -> str:
        """`10/07(수) D-9`, `상시`, or `마감일 미상`."""
        if self.date:
            left = (self.date - today).days
            weekday = "월화수목금토일"[self.date.weekday()]
            when = f"D-{left}" if left > 0 else ("D-day" if left == 0 else "마감")
            return f"{self.date.month:02d}/{self.date.day:02d}({weekday}) {when}"
        return "상시" if self.rolling else "마감일 미상"


def parse_deadline(raw: str | None, today: dt.date | None = None) -> Deadline:
    today = today or clock.today()
    raw = (raw or "").strip()
    if not raw:
        return Deadline(raw)
    if "오늘" in raw:
        return Deadline(raw, today)
    if "내일" in raw:
        return Deadline(raw, today + timedelta(days=1))
    if m := _D_DAY.search(raw):
        return Deadline(raw, today + timedelta(days=int(m[1] or 0)))
    if full := parse_date(raw.lstrip("~ ")):
        # 고용24 and others use 2099-12-31 / 9999-12-31 for "until filled".
        return Deadline(raw, rolling=True) if full.year >= 2099 else Deadline(raw, full)
    if m := _YY_MM_DD.search(raw):
        return Deadline(raw, _safe_date(2000 + int(m[1]), int(m[2]), int(m[3])))
    if m := _MM_DD.search(raw):
        return Deadline(raw, _upcoming(int(m[1]), int(m[2]), today))
    if any(word in raw for word in _ROLLING):
        return Deadline(raw, rolling=True)
    return Deadline(raw)


def _upcoming(month: int, day: int, today: dt.date) -> dt.date | None:
    """A deadline written without a year: the earliest such date not long past.

    `~12/28` read on 1/5 is last December's (closed); `~01/05` read on 12/20 is next January's.
    """
    candidates = (_safe_date(today.year + i, month, day) for i in (-1, 0, 1))
    return next((d for d in candidates if d and d >= today - _PAST_TOLERANCE), None)


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None
