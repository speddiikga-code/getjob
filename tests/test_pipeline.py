"""Paging, filtering, de-duplication and the `collect` command, without the network."""

import csv
import io

from getjob import collect
from getjob.collectors.base import Collector
from getjob.models import Job
from getjob.profile import SearchProfile
from getjob.settings import Settings
from getjob.store import Store


def job(source="saramin", source_id="1", title="백엔드 개발자", company="(주)테스트", **kw):
    url = f"https://example.com/{source}/{source_id}"
    return Job(source, source_id, title, company, url, location="서울 강남구", **kw)


class FakeCollector(Collector):
    key = "saramin"

    def __init__(self, pages: list[list[Job]], newest_first: bool = True) -> None:
        super().__init__(http=None)
        self.pages = pages
        self.newest_first = newest_first
        self.requested: list[int] = []

    def fetch_page(self, page: int) -> list[Job]:
        self.requested.append(page)
        return self.pages[page - 1] if page <= len(self.pages) else []


def pages(*sizes: int) -> list[list[Job]]:
    out, n = [], 0
    for size in sizes:
        out.append([job(source_id=str(n + i), title=f"개발자 {n + i}") for i in range(size)])
        n += size
    return out


def test_collect_reads_until_the_end():
    c = FakeCollector(pages(3, 3, 1))
    assert len(c.collect(None, lambda key: False)) == 7
    assert c.requested == [1, 2, 3, 4]


def test_collect_stops_at_limit():
    c = FakeCollector(pages(3, 3, 3))
    assert [j.source_id for j in c.collect(4, lambda key: False)] == ["0", "1", "2", "3"]
    assert c.requested == [1, 2]


def test_collect_stops_after_a_page_of_already_seen_postings():
    c = FakeCollector(pages(3, 3, 3))
    known = {"saramin:3", "saramin:4", "saramin:5"}
    assert len(c.collect(None, known.__contains__)) == 6
    assert c.requested == [1, 2]


def test_collect_keeps_paging_when_results_are_not_sorted_by_date():
    c = FakeCollector(pages(3, 3, 3), newest_first=False)
    assert len(c.collect(None, lambda key: True)) == 9


def test_collect_stops_when_a_site_repeats_the_same_page():
    same = pages(3)[0]
    c = FakeCollector([same, same, same])
    assert len(c.collect(None, lambda key: False)) == 3
    assert c.requested == [1, 2]


def test_store_reports_each_posting_once_across_runs_and_sites(tmp_path):
    store = Store(tmp_path / "jobs.db")
    first = store.add([job(source_id="1"), job(source_id="2", title="마케터")])
    assert len(first) == 2
    # Same saramin posting again, plus the same job re-listed on 고용24 with a
    # differently written company name: neither is new.
    again = store.add([job(source_id="1"), job(source="work24", company="주식회사 테스트")])
    assert again == []
    assert store.known_keys() == {"saramin:1", "saramin:2", "work24:1"}
    store.close()


def test_profile_filters():
    profile = SearchProfile(
        keywords=["백엔드", "backend"],
        exclude_keywords=["계약직"],
        exclude_companies=["블랙"],
        location={"districts": ["강남구"]},
    )
    assert profile.accepts(job())
    assert profile.accepts(job(title="Java Engineer", tags=["Backend"]))
    assert not profile.accepts(job(title="마케터"))
    assert not profile.accepts(job(title="백엔드 계약직"))
    assert not profile.accepts(job(company="(주)블랙기업"))
    other = job()
    other.location = "서울 마포구"
    assert not profile.accepts(other)
    other.location = "서울 외"
    assert profile.accepts(other)


def test_empty_keywords_keep_everything():
    assert SearchProfile().accepts(job(title="무엇이든"))


def test_collect_run_saves_prints_and_exports(tmp_path, monkeypatch):
    postings = [job(source_id="1"), job(source_id="2", title="단기 알바")]
    monkeypatch.setattr(
        collect, "build_collector", lambda key, http, settings: FakeCollector([postings])
    )
    settings = Settings(_env_file=None, db_path=tmp_path / "jobs.db")
    profile = SearchProfile(exclude_keywords=["알바"])
    out = io.StringIO()

    code = collect.run(settings, profile, ["saramin"], 100, csv_path=tmp_path / "new.csv", out=out)

    assert code == 0
    assert "2 fetched, 1 matched, 1 new" in out.getvalue()
    assert "(주)테스트 — 백엔드 개발자" in out.getvalue()
    rows = list(csv.DictReader((tmp_path / "new.csv").open(encoding="utf-8-sig")))
    assert [r["title"] for r in rows] == ["백엔드 개발자"]
    assert rows[0]["source"] == "사람인 Saramin"

    # A second run finds nothing new.
    out = io.StringIO()
    collect.run(settings, profile, ["saramin"], 100, out=out)
    assert "[New postings: 0]" in out.getvalue()


def test_collect_run_reports_a_failing_site_and_continues(tmp_path, monkeypatch):
    class Broken(FakeCollector):
        def fetch_page(self, page):
            raise RuntimeError("layout changed")

    monkeypatch.setattr(
        collect,
        "build_collector",
        lambda key, http, settings: Broken([]) if key == "wanted" else FakeCollector(pages(2)),
    )
    settings = Settings(_env_file=None, db_path=tmp_path / "jobs.db")
    out = io.StringIO()
    code = collect.run(settings, SearchProfile(), ["saramin", "wanted"], 10, out=out)
    assert code == 0
    assert "FAIL  원티드 Wanted: RuntimeError: layout changed" in out.getvalue()
    assert "[New postings: 2]" in out.getvalue()
