"""인크루트 Incruit: the mobile job list (the desktop host refuses many connections)."""

import re

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job

URL = "https://m.incruit.com/jobdb_list/searchjob.asp"
VIEW_URL = "https://job.incruit.com/jobdb_info/jobpost.asp?job={}"
PARAMS = {
    "rgn2": "11",  # 서울
    "crr": "1",  # 신입 (also returns 경력무관 postings)
    "jobty": "1",  # 정규직
    "sortfield": "reg",  # newest first
    "sortorder": "1",
}


class IncruitCollector(Collector):
    key = "incruit"

    def fetch_page(self, page: int) -> list[Job]:
        resp = self.http.get(URL, params={**PARAMS, "page": str(page)})
        # Served as EUC-KR; cp949 is its superset and decodes every Korean character.
        return parse(resp.content.decode("cp949", errors="replace"))


def parse(html: str) -> list[Job]:
    jobs = []
    for item in BeautifulSoup(html, "lxml").select("div.swiper-slide[jobno]"):
        job_no = item["jobno"]
        # "서울 강남구 외 | 신입/경력(1~5년) | 대졸(4년)↑"
        details = [part.strip() for part in text(item.select_one(".cCpSbCom")).split("|")]
        details += [""] * (3 - len(details))
        jobs.append(
            Job(
                source="incruit",
                source_id=job_no,
                title=text(item.select_one(".cTitle")),
                company=text(item.select_one(".cCpName")),
                url=VIEW_URL.format(job_no),
                location=details[0],
                experience=details[1],
                education=details[2],
                employment_type="정규직",
                posted_at=_posted(job_no),
                deadline=text(item.select_one(".cDate")),
            )
        )
    return jobs


def _posted(job_no: str):
    # Posting numbers start with the registration date: 2609260000087 -> 2026-09-26.
    m = re.match(r"(\d{2})(\d{2})(\d{2})\d{7}$", job_no)
    return parse_date(f"20{m[1]}-{m[2]}-{m[3]}") if m else None
