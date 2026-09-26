"""LinkedIn public (guest) job search. No login; only listings anyone can see."""

import re

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job

URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10
PARAMS = {
    "geoId": "103588929",  # Seoul, South Korea
    "f_E": "2",  # experience level: Entry level
    "f_JT": "F",  # job type: Full-time
    "f_TPR": "r604800",  # posted in the past week (results can't be sorted by date)
}


class LinkedInCollector(Collector):
    key = "linkedin"
    newest_first = False

    def fetch_page(self, page: int) -> list[Job]:
        params = {**PARAMS, "start": str((page - 1) * PAGE_SIZE)}
        resp = self.http.get(URL, params=params)
        return parse(resp.text)

    def keep(self, job: Job) -> bool:
        # The geo filter also lets in nearby cities; keep Seoul only (Korean or English names).
        return "서울" in job.location or "seoul" in job.location.lower()


def parse(html: str) -> list[Job]:
    jobs = []
    for card in BeautifulSoup(html, "lxml").select("div.base-card[data-entity-urn]"):
        m = re.search(r"jobPosting:(\d+)", card["data-entity-urn"])
        if not m:
            continue
        posted = card.select_one("time")
        jobs.append(
            Job(
                source="linkedin",
                source_id=m[1],
                title=text(card.select_one(".base-search-card__title")),
                company=text(card.select_one(".base-search-card__subtitle")),
                url=f"https://www.linkedin.com/jobs/view/{m[1]}",
                location=text(card.select_one(".job-search-card__location")),
                experience="Entry level",
                employment_type="Full-time",
                posted_at=parse_date(posted.get("datetime") if posted else None),
            )
        )
    return jobs
