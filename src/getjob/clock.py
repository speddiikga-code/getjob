"""Korean time for every date getjob reasons about: deadlines, budget weeks, D-days.

Servers and Docker images usually run in UTC, where an 08:00 KST run is still yesterday.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    """Current time in Seoul, without tzinfo so stored timestamps compare as plain text."""
    return datetime.now(KST).replace(tzinfo=None)


def today() -> date:
    return now().date()
