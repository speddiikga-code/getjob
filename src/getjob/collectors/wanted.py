"""원티드 Wanted: the JSON API behind the job list page."""

from getjob.collectors.base import Collector
from getjob.models import Job

URL = "https://www.wanted.co.kr/api/chaos/navigation/v1/results"
PAGE_SIZE = 100
EMPLOYMENT_TYPES = {"regular": "정규직", "contract": "계약직", "intern": "인턴"}
PARAMS = {
    "country": "kr",
    "locations": "seoul.all",
    "years": "0",  # open to 0 years of experience
    "job_sort": "job.latest_order",
}


class WantedCollector(Collector):
    key = "wanted"

    def fetch_page(self, page: int) -> list[Job]:
        params = {**PARAMS, "limit": str(PAGE_SIZE), "offset": str((page - 1) * PAGE_SIZE)}
        return parse(self.http.get(URL, params=params).json())

    def keep(self, job: Job) -> bool:
        # The list has no employment-type filter, so interns/contractors are dropped here.
        return job.employment_type == "정규직"


def parse(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("data", []):
        address = item.get("address") or {}
        low, high = item.get("annual_from"), item.get("annual_to")
        jobs.append(
            Job(
                source="wanted",
                source_id=str(item["id"]),
                title=item.get("position", ""),
                company=(item.get("company") or {}).get("name", ""),
                url=f"https://www.wanted.co.kr/wd/{item['id']}",
                location=" ".join(filter(None, [address.get("location"), address.get("district")])),
                experience=_years(low, high),
                employment_type=EMPLOYMENT_TYPES.get(
                    item.get("employment_type"), item.get("employment_type") or ""
                ),
            )
        )
    return jobs


def _years(low: int | None, high: int | None) -> str:
    if low in (None, 0) and high in (None, 0, 100):
        return "신입" if high == 0 else "경력무관"
    if low in (None, 0):
        return f"신입~{high}년"
    return f"{low}~{high}년"
