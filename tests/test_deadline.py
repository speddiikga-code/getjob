"""Deadline strings as the supported sites write them."""

from datetime import date

import pytest

from getjob.deadline import parse_deadline

TODAY = date(2026, 9, 27)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("~ 10/11(일)", date(2026, 10, 11)),  # 사람인
        ("2026-10-26", date(2026, 10, 26)),  # 잡코리아, 고용24
        ("~10.26", date(2026, 10, 26)),  # 인크루트
        ("10.26", date(2026, 10, 26)),  # 피플앤잡
        ("26.10.07", date(2026, 10, 7)),  # 잡알리오
        ("2026.10.26 23:59", date(2026, 10, 26)),
        ("오늘마감", TODAY),
        ("내일마감", date(2026, 9, 28)),
        ("D-3", date(2026, 9, 30)),
        ("D-day", TODAY),
    ],
)
def test_dates(raw, expected):
    deadline = parse_deadline(raw, TODAY)
    assert deadline.date == expected
    assert not deadline.rolling


@pytest.mark.parametrize("raw", ["상시채용", "채용시", "채용시까지", "수시채용", "9999-12-31"])
def test_open_until_filled(raw):
    deadline = parse_deadline(raw, TODAY)
    assert deadline.rolling and deadline.date is None
    assert deadline.label(TODAY) == "상시"


@pytest.mark.parametrize("raw", ["", None, "협의", "02/30"])
def test_unknown(raw):
    deadline = parse_deadline(raw, TODAY)
    assert deadline.date is None and not deadline.rolling
    assert deadline.label(TODAY) == "마감일 미상"


def test_month_day_without_a_year_rolls_over_only_when_long_past():
    december = date(2026, 12, 20)
    assert parse_deadline("~01/05", december).date == date(2027, 1, 5)
    # A deadline that passed recently stays in the past, so it can expire.
    assert parse_deadline("~12/10", december).date == date(2026, 12, 10)


def test_label():
    assert parse_deadline("~ 10/07(수)", TODAY).label(TODAY) == "10/07(수) D-10"
    assert parse_deadline("오늘마감", TODAY).label(TODAY) == "09/27(일) D-day"
    assert parse_deadline("2026-09-20", TODAY).label(TODAY) == "09/20(일) 마감"
    assert parse_deadline("2026-09-20", TODAY).days_left(TODAY) == -7


def test_a_december_deadline_read_in_january_is_last_december():
    assert parse_deadline("~12/28", date(2027, 1, 5)).date == date(2026, 12, 28)


def test_clock_is_korean_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from getjob import clock

    assert abs(clock.now() - datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)).seconds < 5
