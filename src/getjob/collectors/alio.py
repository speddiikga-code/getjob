"""잡알리오 Job-ALIO (공공기관): the public-institution recruitment board."""

import re

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job

URL = "https://job.alio.go.kr/recruit.do"
PARAMS = [
    ("location", "R3010"),  # 서울특별시
    ("work_type", "R1010"),  # 정규직
    ("career", "R2010"),  # 신입
    ("career", "R2030"),  # 신입+경력
]


class AlioCollector(Collector):
    key = "alio"

    def fetch_page(self, page: int) -> list[Job]:
        return parse(self.http.get(URL, params=[*PARAMS, ("pageNo", str(page))]).text)


def parse(html: str) -> list[Job]:
    jobs = []
    for row in BeautifulSoup(html, "lxml").select("table tbody tr"):
        link = row.select_one('a[href*="recruitview.do?idx="]')
        cells = row.select("td")
        if link is None or len(cells) < 9:
            continue
        # columns: [checkbox, 번호, 채용제목, 기관명, 근무지, 고용형태, 등록일, 마감일, 상태]
        if "마감" in text(cells[8]):
            continue
        idx = re.search(r"idx=(\d+)", link["href"])[1]
        deadline = re.sub(r"\s*D-\d+$", "", text(cells[7]))
        jobs.append(
            Job(
                source="alio",
                source_id=idx,
                title=text(cells[2]),
                company=text(cells[3]),
                url=f"https://job.alio.go.kr/recruitview.do?idx={idx}",
                location=text(cells[4]),
                experience="신입",
                employment_type=text(cells[5]),
                posted_at=parse_date(text(cells[6])),
                deadline=deadline,
            )
        )
    return jobs
