"""사람인 Saramin: official Open API when SARAMIN_API_KEY is set, otherwise the search page."""

import re
from datetime import date

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job
from getjob.web import Http

SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
API_URL = "https://oapi.saramin.co.kr/job-search"
VIEW_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={}"
SEOUL = "101000"
REGULAR = "1"  # 정규직
NEWCOMER = "1"  # 신입 (also returns 신입·경력 and 경력무관 postings)


class SaraminCollector(Collector):
    key = "saramin"

    def __init__(self, http: Http, api_key: str | None = None) -> None:
        super().__init__(http)
        self.api_key = api_key

    def fetch_page(self, page: int) -> list[Job]:
        if self.api_key:
            return self._fetch_api(page)
        params = {
            "searchType": "search",
            "loc_mcd": SEOUL,
            "exp_cd": NEWCOMER,
            "job_type": REGULAR,
            "recruitPage": str(page),
            "recruitPageCount": "100",
            "recruitSort": "reg_dt",
        }
        return parse_search(self.http.get(SEARCH_URL, params=params).text)

    def _fetch_api(self, page: int) -> list[Job]:
        # https://oapi.saramin.co.kr/guide/job-search
        params = {
            "access-key": self.api_key,
            "loc_mcd": SEOUL,
            "exp_cd": NEWCOMER,
            "job_type": REGULAR,
            "sort": "pd",
            "start": str(page - 1),
            "count": "110",
        }
        resp = self.http.get(API_URL, params=params, headers={"Accept": "application/json"})
        return parse_api(resp.json())


def parse_search(html: str) -> list[Job]:
    jobs = []
    for item in BeautifulSoup(html, "lxml").select("div.item_recruit[value]"):
        rec_idx = item["value"]
        title = item.select_one("h2.job_tit a")
        conditions = [text(span) for span in item.select("div.job_condition > span")]
        conditions += [""] * (4 - len(conditions))
        registered = re.search(r"(\d{2})/(\d{2})/(\d{2})", text(item.select_one(".job_day")))
        jobs.append(
            Job(
                source="saramin",
                source_id=rec_idx,
                title=(title.get("title") or text(title)) if title else "",
                company=text(item.select_one(".corp_name a")),
                url=VIEW_URL.format(rec_idx),
                location=conditions[0],
                experience=conditions[1],
                education=conditions[2],
                employment_type=conditions[3],
                salary=next((c for c in conditions[4:] if "원" in c), ""),
                posted_at=_yymmdd(registered),
                deadline=text(item.select_one(".job_date .date")),
                tags=[text(a) for a in item.select(".job_sector a")],
            )
        )
    return jobs


def parse_api(data: dict) -> list[Job]:
    jobs = []
    for job in data.get("jobs", {}).get("job", []):
        position = job.get("position", {})
        jobs.append(
            Job(
                source="saramin",
                source_id=str(job["id"]),
                title=position.get("title", ""),
                company=job.get("company", {}).get("detail", {}).get("name", ""),
                url=job.get("url") or VIEW_URL.format(job["id"]),
                location=position.get("location", {}).get("name", "").replace("&gt;", ">"),
                experience=position.get("experience-level", {}).get("name", ""),
                education=position.get("required-education-level", {}).get("name", ""),
                employment_type=position.get("job-type", {}).get("name", ""),
                salary=job.get("salary", {}).get("name", ""),
                posted_at=parse_date(job.get("posting-date")),
                deadline=(job.get("expiration-date") or "")[:10],
                tags=[k.strip() for k in job.get("keyword", "").split(",") if k.strip()],
            )
        )
    return jobs


def _yymmdd(m: re.Match | None) -> date | None:
    return parse_date(f"20{m[1]}-{m[2]}-{m[3]}") if m else None
