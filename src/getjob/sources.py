"""Registry of supported job sites.

Each entry records where the site lives and which URL `getjob doctor` probes to
check that the site is reachable from the current machine or cloud runner.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceInfo:
    key: str
    name: str
    homepage: str
    probe_url: str
    api_key_env: str | None = None
    note: str = ""


SOURCES: dict[str, SourceInfo] = {
    s.key: s
    for s in [
        SourceInfo(
            "linkedin",
            "LinkedIn",
            "https://www.linkedin.com/jobs/",
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            "?location=Seoul%2C%20South%20Korea",
            note="public guest listings only, no login",
        ),
        SourceInfo(
            "jobkorea",
            "잡코리아 JobKorea",
            "https://www.jobkorea.co.kr",
            "https://www.jobkorea.co.kr",
        ),
        SourceInfo(
            "saramin",
            "사람인 Saramin",
            "https://www.saramin.co.kr",
            "https://www.saramin.co.kr/zf_user/",
            api_key_env="SARAMIN_API_KEY",
            note="official Open API when SARAMIN_API_KEY is set",
        ),
        SourceInfo(
            "wanted", "원티드 Wanted", "https://www.wanted.co.kr", "https://www.wanted.co.kr/wdlist"
        ),
        SourceInfo(
            "incruit",
            "인크루트 Incruit",
            "https://www.incruit.com",
            "https://m.incruit.com/jobdb_list/searchjob.asp",
        ),
        SourceInfo(
            "work24",
            "고용24 Work24",
            "https://www.work24.go.kr",
            "https://www.work24.go.kr/cm/main.do",
            note="government job board (구 워크넷)",
        ),
        SourceInfo(
            "remember",
            "리멤버 커리어 Remember",
            "https://career.rememberapp.co.kr",
            "https://career.rememberapp.co.kr",
        ),
        SourceInfo(
            "jumpit",
            "점핏 Jumpit",
            "https://jumpit.saramin.co.kr",
            "https://jumpit.saramin.co.kr",
            note="IT/developer jobs only",
        ),
        SourceInfo(
            "peoplenjob",
            "피플앤잡 PeopleNJob",
            "https://www.peoplenjob.com",
            "https://www.peoplenjob.com",
            note="foreign companies in Korea",
        ),
        SourceInfo(
            "alio",
            "잡알리오 Job-ALIO",
            "https://job.alio.go.kr",
            "https://job.alio.go.kr",
            note="public institutions (공공기관)",
        ),
    ]
}
