"""고용24 Work24 (구 워크넷): the government job board's detailed search."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job

URL = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"
PARAMS = {
    "region": "11000",  # 서울
    "careerTypes": "N,Z",  # 신입, 경력무관
    "employGbn": "10",  # 기간의 정함이 없는 근로계약 (정규직)
    "resultCnt": "100",
    "sortField": "DATE",
    "sortOrderBy": "DESC",
}


class Work24Collector(Collector):
    key = "work24"

    def fetch_page(self, page: int) -> list[Job]:
        resp = self.http.get(URL, params={**PARAMS, "pageIndex": str(page)})
        return parse(resp.text)


def parse(html: str) -> list[Job]:
    jobs = []
    for row in BeautifulSoup(html, "lxml").select('tr[id^="list"]'):
        box = row.select_one('input[id^="chkboxWantedAuthNo"]')
        link = row.select_one("a[data-emp-detail]")
        if box is None or link is None:
            continue
        # value = "wantedAuthNo|infoTypeCd|company|title"
        auth_no, _, company, title = (box["value"].split("|") + ["", "", "", ""])[:4]
        member = [text(s) for s in row.select("li.member span.item")] + ["", ""]
        row_html = str(row)
        registered = re.search(r"등록일\s*:\s*(\d{4}-\d{2}-\d{2})", text(row))
        close = re.search(r"var date\s*=\s*'([\d-]+)'", row_html)
        deadline = close[1] if close else ""
        if deadline.startswith("2099"):
            deadline = "채용시까지"
        jobs.append(
            Job(
                source="work24",
                source_id=auth_no,
                title=title or text(link),
                company=company,
                url=urljoin(URL, link["href"]),
                location=text(row.select_one("li.site")),
                experience=member[0],
                education=member[1],
                employment_type="정규직",
                salary=text(row.select_one("li.dollar")),
                posted_at=parse_date(registered[1]) if registered else None,
                deadline=deadline,
            )
        )
    return jobs
