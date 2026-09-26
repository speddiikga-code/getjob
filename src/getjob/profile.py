"""Search profile: what kind of job to look for, loaded from `config/search.yaml`."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from getjob.sources import SOURCES

EmploymentType = Literal["정규직", "계약직", "인턴", "파견직"]
NotifyChannel = Literal["telegram", "email"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(_Strict):
    city: str = "서울"
    districts: list[str] = Field(default_factory=list)


class Experience(_Strict):
    min_years: int = Field(0, ge=0)
    max_years: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _check_range(self) -> "Experience":
        if self.max_years is not None and self.max_years < self.min_years:
            raise ValueError("experience.max_years must be >= min_years")
        return self


class SourceToggle(_Strict):
    enabled: bool = True


class Notify(_Strict):
    channels: list[NotifyChannel] = Field(default_factory=lambda: ["telegram"])
    max_jobs_per_message: int = Field(20, ge=1, le=100)


class SearchProfile(_Strict):
    location: Location = Field(default_factory=Location)
    employment_types: list[EmploymentType] = Field(default_factory=lambda: ["정규직"])
    keywords: list[str] = Field(min_length=1)
    exclude_keywords: list[str] = Field(default_factory=list)
    experience: Experience = Field(default_factory=Experience)
    salary_min_manwon: int | None = Field(None, ge=0)
    exclude_companies: list[str] = Field(default_factory=list)
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


def load_profile(path: Path) -> SearchProfile:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SearchProfile.model_validate(data)
