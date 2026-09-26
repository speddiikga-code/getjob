"""리멤버 커리어 Remember: the JSON search API behind career.rememberapp.co.kr."""

from getjob.collectors.base import Collector, parse_date
from getjob.models import Job

URL = "https://career-api.rememberapp.co.kr/job_postings/search"
PAGE_SIZE = 30


class RememberCollector(Collector):
    key = "remember"

    def fetch_page(self, page: int) -> list[Job]:
        body = {
            "page": page,
            "per": PAGE_SIZE,
            "sort": "starts_at_desc",
            "search": {
                "include_applied_job_posting": False,
                "addresses": [{"address_level1": "서울특별시"}],
                "career_year": 0,  # postings whose experience range includes 0 years
            },
        }
        return parse(self.http.post(URL, json=body).json())


def parse(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("data", []):
        addresses = item.get("addresses") or []
        seoul = [a for a in addresses if a.get("address_level1") == "서울특별시"] or addresses
        first = seoul[0] if seoul else {}
        low, high = item.get("min_experience"), item.get("max_experience")
        company = (item.get("organization") or {}).get("name") or (item.get("company") or {}).get(
            "name", ""
        )
        jobs.append(
            Job(
                source="remember",
                source_id=str(item["id"]),
                title=item.get("title", ""),
                company=company,
                url=f"https://career.rememberapp.co.kr/job/posting/{item['id']}",
                location=" ".join(
                    filter(None, [first.get("address_level1"), first.get("address_level2")])
                ),
                experience=f"{low or 0}~{high}년" if high is not None else "경력무관",
                posted_at=parse_date(item.get("starts_at")),
                deadline=(item.get("ends_at") or "")[:10] if item.get("explicit_due") else "채용시",
            )
        )
    return jobs
