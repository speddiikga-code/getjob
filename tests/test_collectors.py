"""Parser tests against trimmed real responses saved in tests/fixtures/."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from getjob.collectors import (
    COLLECTORS,
    alio,
    incruit,
    jobkorea,
    jumpit,
    linkedin,
    peoplenjob,
    remember,
    saramin,
    wanted,
    work24,
)
from getjob.collectors.base import past_month_day
from getjob.sources import SOURCES

FIXTURES = Path(__file__).parent / "fixtures"


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def data(name: str) -> dict:
    return json.loads(html(name))


PARSED = {
    "linkedin": lambda: linkedin.parse(html("linkedin.html")),
    "saramin": lambda: saramin.parse_search(html("saramin.html")),
    "jobkorea": lambda: jobkorea.parse(html("jobkorea.html")),
    "wanted": lambda: wanted.parse(data("wanted.json")),
    "incruit": lambda: incruit.parse(html("incruit.html")),
    "work24": lambda: work24.parse(html("work24.html")),
    "remember": lambda: remember.parse(data("remember.json")),
    "jumpit": lambda: jumpit.parse(data("jumpit.json")),
    "peoplenjob": lambda: peoplenjob.parse(html("peoplenjob.html")),
    "alio": lambda: alio.parse(html("alio.html")),
}


def test_every_site_has_a_collector_and_a_fixture():
    assert set(COLLECTORS) == set(SOURCES) == set(PARSED)


@pytest.mark.parametrize("key", sorted(PARSED))
def test_parser_extracts_complete_postings(key):
    jobs = PARSED[key]()
    assert len(jobs) == 3
    assert len({job.source_id for job in jobs}) == 3
    for job in jobs:
        assert job.source == key
        assert job.source_id and job.title and job.company
        assert job.url.startswith("https://")
        assert job.source_id in job.url
        # Multi-location postings show one place plus "외"/"등" (and more, incl. Seoul).
        assert "서울" in job.location or re.search(r"(외|등)( \d+)?$", job.location)


def test_linkedin():
    job = PARSED["linkedin"]()[0]
    assert job.source_id == "4468700731"
    assert job.url == "https://www.linkedin.com/jobs/view/4468700731"
    assert job.company == "Harper"
    assert job.posted_at == date(2026, 9, 23)


def test_saramin():
    job = PARSED["saramin"]()[0]
    assert job.source_id == "55121922"
    assert job.title == "[외국계 강소기업] BD or BD Associate"
    assert job.company == "(주)에임즈인터내셔널코리아"
    assert (job.location, job.experience, job.education, job.employment_type) == (
        "서울 종로구",
        "신입·경력",
        "대졸↑",
        "정규직",
    )
    assert job.posted_at == date(2026, 9, 26)
    assert job.deadline == "~ 10/11(일)"
    assert "임상시험" in job.tags


def test_jobkorea():
    job = PARSED["jobkorea"]()[0]
    assert job.source_id == "50052681"
    assert job.company == "아루"
    assert (job.location, job.experience, job.employment_type) == (
        "서울 강남구",
        "신입·경력",
        "정규직",
    )
    assert job.salary == "3,600~4,800만원"
    assert (job.posted_at, job.deadline) == (date(2026, 9, 26), "2026-10-26")


def test_wanted_keeps_only_regular_jobs():
    jobs = PARSED["wanted"]()
    collector = wanted.WantedCollector(http=None)
    assert [collector.keep(job) for job in jobs] == [True, True, False]
    assert jobs[0].experience == "신입~10년"
    assert jobs[0].url == "https://www.wanted.co.kr/wd/369219"


def test_incruit_reads_posted_date_from_job_number():
    job = PARSED["incruit"]()[0]
    assert job.source_id == "2609260000087"
    assert job.posted_at == date(2026, 9, 26)
    assert (job.experience, job.education) == ("경력무관", "학력무관")


def test_work24():
    job = PARSED["work24"]()[0]
    assert job.source_id == "54600039"
    assert job.company == "디씨에스아이(주)"
    assert job.salary == "회사내규에 따름"
    assert (job.posted_at, job.deadline) == (date(2026, 9, 26), "채용시까지")


def test_remember():
    job = PARSED["remember"]()[0]
    assert job.url == "https://career.rememberapp.co.kr/job/posting/328112"
    assert job.location == "서울특별시 구로구"
    assert job.experience == "0~1년"


def test_jumpit():
    job = PARSED["jumpit"]()[0]
    assert job.url == "https://jumpit.saramin.co.kr/position/55090664"
    assert job.experience == "신입"
    assert "Kotlin" in job.tags


def test_peoplenjob():
    job = PARSED["peoplenjob"]()[0]
    assert job.url == "https://www.peoplenjob.com/jobs/6288113"
    assert (job.posted_at.month, job.posted_at.day) == (9, 26)
    assert job.deadline == "10.26"


def test_alio():
    job = PARSED["alio"]()[0]
    assert job.company == "국가철도공단"
    assert job.posted_at == date(2026, 9, 23)
    assert job.deadline == "26.10.07"


def test_past_month_day_uses_last_year_for_future_dates():
    today = date(2026, 1, 5)
    assert past_month_day(1, 3, today) == date(2026, 1, 3)
    assert past_month_day(12, 30, today) == date(2025, 12, 30)
    assert past_month_day(2, 30, today) is None
