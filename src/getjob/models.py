"""The common shape every site's postings are converted into."""

import re
from dataclasses import dataclass, field
from datetime import date

_COMPANY_NOISE = re.compile(
    r"\(주\)|㈜|주식회사|\(유\)|\(사\)|\(재\)|\bco\.?,?\s*ltd\b\.?|\binc\b\.?|\bcorp\b\.?"
)
_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")


def normalize(text: str) -> str:
    """Lowercase and strip punctuation/legal suffixes, for comparing names across sites."""
    return _NON_WORD.sub("", _COMPANY_NOISE.sub("", text.lower()))


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    url: str
    location: str = ""
    experience: str = ""
    education: str = ""
    employment_type: str = ""
    salary: str = ""
    posted_at: date | None = None
    deadline: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Unique per site: `saramin:55121922`."""
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Same company + same title = same posting, even when listed on several sites."""
        return f"{normalize(self.company)}|{normalize(self.title)}"
