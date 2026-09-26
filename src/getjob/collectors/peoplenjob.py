"""피플앤잡 PeopleNJob (외국계 기업): the job list page."""

import re

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, past_month_day, text
from getjob.models import Job

URL = "https://www.peoplenjob.com/jobs"
PARAMS = {
    "career_level": "1",  # 인턴.신입.2년이내
    "field": "scope.workLocationTag",
    "q": "서울",
}


class PeopleNJobCollector(Collector):
    key = "peoplenjob"

    def fetch_page(self, page: int) -> list[Job]:
        return parse(self.http.get(URL, params={**PARAMS, "page": str(page)}).text)


def parse(html: str) -> list[Job]:
    jobs = []
    for card in BeautifulSoup(html, "lxml").select("div.jd-card"):
        link = card.select_one("h5 a[href]")
        m = re.search(r"/jobs/(\d+)", link["href"]) if link else None
        if not m:
            continue
        # "09.26 ~ 10.26" or "09.26 ~ 채용시"
        period = text(card.select_one(".jd-card-meta-static")).split("~")
        start = re.match(r"\s*(\d{1,2})\.(\d{1,2})", period[0])
        jobs.append(
            Job(
                source="peoplenjob",
                source_id=m[1],
                title=text(link),
                company=text(card.select_one(".jd-card-company")),
                url=f"https://www.peoplenjob.com/jobs/{m[1]}",
                location=text(card.select_one(".jd-card-meta-location-text")),
                experience=text(card.select_one(".jd-card-meta-career-text")),
                posted_at=past_month_day(int(start[1]), int(start[2])) if start else None,
                deadline=period[1].strip() if len(period) > 1 else "",
            )
        )
    return jobs
