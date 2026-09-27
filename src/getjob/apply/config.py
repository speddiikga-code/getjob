"""Application settings (config/apply.yaml) and your experience bank (config/experience.yaml)."""

import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from getjob.sources import SOURCES


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- config/apply.yaml ----------------------------------------------------------


class Milestone(_Strict):
    name: str
    date: dt.date
    confirmed: bool = False  # false = estimated (e.g. last year's schedule)
    source: str = ""


class QuietPeriod(_Strict):
    start: dt.date
    end: dt.date
    reason: str = ""


class Focus(_Strict):
    """The main pilot. Company applications must never eat into its time."""

    main: str = ""
    milestones: list[Milestone] = Field(default_factory=list)
    quiet_periods: list[QuietPeriod] = Field(default_factory=list)

    def next_milestone(self, today: dt.date) -> Milestone | None:
        upcoming = [m for m in self.milestones if m.date >= today]
        return min(upcoming, key=lambda m: m.date, default=None)

    def quiet_period(self, today: dt.date) -> QuietPeriod | None:
        return next((q for q in self.quiet_periods if q.start <= today <= q.end), None)


class Budget(_Strict):
    # Drafts you review and submit per week (Mon-Sun). Also caps the unreviewed backlog.
    max_per_week: int = Field(6, ge=0, le=50)


class Companies(_Strict):
    prefer: dict[str, int] = Field(default_factory=dict)
    exclude: list[str] = Field(default_factory=list)


class Target(_Strict):
    keywords: dict[str, int] = Field(default_factory=dict)
    exclude_keywords: list[str] = Field(default_factory=list)
    companies: Companies = Field(default_factory=Companies)
    sources: dict[str, int] = Field(default_factory=dict)
    min_score: int = 1
    min_days_left: int = Field(2, ge=0)
    lookback_days: int = Field(14, ge=1)

    @field_validator("sources")
    @classmethod
    def _known_sources(cls, sources: dict[str, int]) -> dict[str, int]:
        unknown = sorted(set(sources) - set(SOURCES))
        if unknown:
            raise ValueError(f"unknown source(s): {', '.join(unknown)}")
        return sources


class QuestionSpec(_Strict):
    text: str
    limit: int = Field(700, ge=50, le=5000)  # characters incl. spaces (공백 포함)


class Drafting(_Strict):
    # auto: Claude when ANTHROPIC_API_KEY is set, otherwise the offline template
    engine: Literal["auto", "template", "claude"] = "auto"
    model: str = "claude-opus-5"


class ApplyProfile(_Strict):
    focus: Focus = Field(default_factory=Focus)
    budget: Budget = Field(default_factory=Budget)
    target: Target = Field(default_factory=Target)
    questions: list[QuestionSpec] = Field(
        default_factory=lambda: [QuestionSpec(text="지원 동기와 입사 후 목표를 기술해 주십시오.")],
        min_length=1,
    )
    drafting: Drafting = Field(default_factory=Drafting)


def load_apply_profile(path: Path) -> ApplyProfile:
    return ApplyProfile.model_validate(_read_yaml(path))


# --- config/experience.yaml -----------------------------------------------------


class Episode(_Strict):
    """One experience, written once in STAR form and reused across applications."""

    title: str
    period: str = ""
    tags: list[str] = Field(default_factory=list)
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    lesson: str = ""


class Experience(_Strict):
    name: str = ""
    headline: str = ""
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    motivation: str = ""  # why this kind of work: reused in every 지원 동기
    goals: str = ""  # what you want to achieve after joining: reused in 입사 후 포부
    episodes: list[Episode] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.episodes or self.motivation or self.goals)


def load_experience(path: Path) -> Experience:
    """Your experience bank, or an empty one when the file doesn't exist yet."""
    if not path.exists():
        return Experience()
    return Experience.model_validate(_read_yaml(path))


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
