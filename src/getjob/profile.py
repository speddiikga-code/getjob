"""Search profile: what kind of job to look for, loaded from `config/search.yaml`.

Every collector already searches 서울 · 신입 (incl. 경력무관) · 정규직 using each site's
own filters; the settings here narrow those results further.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from getjob.models import Job, normalize
from getjob.sources import SOURCES

NotifyChannel = Literal["telegram", "email"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(_Strict):
    districts: list[str] = Field(default_factory=list)


class Limits(_Strict):
    max_per_source: int = Field(300, ge=1)


class SourceToggle(_Strict):
    enabled: bool = True


class Notify(_Strict):
    channels: list[NotifyChannel] = Field(default_factory=lambda: ["telegram"])
    max_jobs_per_message: int = Field(20, ge=1, le=100)


class SearchProfile(_Strict):
    location: Location = Field(default_factory=Location)
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    sources: dict[str, SourceToggle] = Field(default_factory=dict)
    notify: Notify = Field(default_factory=Notify)

    @field_validator("keywords", "exclude_keywords", "exclude_companies")
    @classmethod
    def _strip_blank(cls, values: list[str]) -> list[str]:
        return [v.strip() for v in values if v and v.strip()]

    @field_validator("sources")
    @classmethod
    def _known_sources(cls, sources: dict[str, SourceToggle]) -> dict[str, SourceToggle]:
        unknown = sorted(set(sources) - set(SOURCES))
        if unknown:
            raise ValueError(
                f"unknown source(s): {', '.join(unknown)}; known: {', '.join(SOURCES)}"
            )
        return sources

    def enabled_sources(self) -> list[str]:
        return [key for key, toggle in self.sources.items() if toggle.enabled]

    def accepts(self, job: Job) -> bool:
        title = job.title.lower()
        if self.keywords:
            searchable = " ".join([title, *job.tags]).lower()
            if not any(k.lower() in searchable for k in self.keywords):
                return False
        if any(k.lower() in title for k in self.exclude_keywords):
            return False
        company = normalize(job.company)
        if any(normalize(c) and normalize(c) in company for c in self.exclude_companies):
            return False
        # A location without a district (e.g. "서울", "서울 외") might still be in one.
        if self.location.districts and "구" in job.location:
            return any(d in job.location for d in self.location.districts)
        return True


def load_profile(path: Path) -> SearchProfile:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SearchProfile.model_validate(data)
