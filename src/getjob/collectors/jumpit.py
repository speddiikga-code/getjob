"""점핏 Jumpit (IT/개발 직군): the JSON API behind jumpit.saramin.co.kr."""

from getjob.collectors.base import Collector
from getjob.models import Job

URL = "https://jumpit-api.saramin.co.kr/api/positions"
PARAMS = {
    "sort": "reg_dt",  # newest first
    "highlight": "false",
    "career": "0",  # 신입
    "locationTag": "101010",  # 서울
}


class JumpitCollector(Collector):
    key = "jumpit"

    def fetch_page(self, page: int) -> list[Job]:
        return parse(self.http.get(URL, params={**PARAMS, "page": str(page)}).json())


def parse(data: dict) -> list[Job]:
    jobs = []
    for item in (data.get("result") or {}).get("positions", []):
        low, high = item.get("minCareer"), item.get("maxCareer")
        closed = item.get("closedAt") or ""
        jobs.append(
            Job(
                source="jumpit",
                source_id=str(item["id"]),
                title=item.get("title", ""),
                company=item.get("companyName", ""),
                url=f"https://jumpit.saramin.co.kr/position/{item['id']}",
                location=", ".join(item.get("locations") or []),
                experience=_career(low, high),
                deadline="상시채용" if item.get("alwaysOpen") else closed[:10],
                tags=item.get("techStacks") or [],
            )
        )
    return jobs


def _career(low: int | None, high: int | None) -> str:
    if not high:
        return "신입"
    return f"신입~{high}년" if not low else f"{low}~{high}년"
