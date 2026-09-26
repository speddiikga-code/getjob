"""잡코리아 JobKorea: the 채용정보 list (the same data the detailed-search page loads)."""

from bs4 import BeautifulSoup

from getjob.collectors.base import Collector, parse_date, text
from getjob.models import Job

URL = "https://www.jobkorea.co.kr/Recruit/Home/_GI_List/"
VIEW_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read/{}"
CONDITIONS = {
    "condition[local]": "I000",  # 서울
    "condition[jobtype]": "1",  # 정규직
    "condition[career]": "1,8",  # 신입, 경력무관
    "condition[menucode]": "local",
}


class JobKoreaCollector(Collector):
    key = "jobkorea"

    def fetch_page(self, page: int) -> list[Job]:
        data = {
            **CONDITIONS,
            "TotalCount": "0",
            "direct": "0",
            "page": str(page),
            "pagesize": "100",
            "order": "2",  # 등록일순 (newest first)
            "tabindex": "0",
            "onePick": "0",
            "confirm": "0",
            "profile": "0",
        }
        resp = self.http.post(URL, data=data, headers={"X-Requested-With": "XMLHttpRequest"})
        return parse(resp.text)


def parse(html: str) -> list[Job]:
    jobs = []
    for row in BeautifulSoup(html, "lxml").select("tr.devloopArea[data-gno]"):
        gno = row["data-gno"]
        title = row.select_one(".tplTit strong a")
        cells = [text(c) for c in row.select("p.etc span.cell")]
        cells += [""] * (4 - len(cells))
        # data-brazeinfo = title|gno|gino|registered|deadline|company|company id
        braze = row.select_one("[data-brazeinfo]")
        info = braze["data-brazeinfo"].split("|") if braze else []
        jobs.append(
            Job(
                source="jobkorea",
                source_id=gno,
                title=(title.get("title") or text(title)) if title else "",
                company=text(row.select_one(".tplCo a.link")),
                url=VIEW_URL.format(gno),
                location=cells[2],
                experience=cells[0],
                education=cells[1],
                employment_type=cells[3],
                salary=next((c for c in cells[4:] if "원" in c), ""),
                posted_at=parse_date(info[3]) if len(info) > 4 else None,
                deadline=info[4] if len(info) > 4 else text(row.select_one(".date")),
                tags=[t.strip() for t in text(row.select_one("p.dsc")).split(",") if t.strip()],
            )
        )
    return jobs
