"""Rank collected postings by how worth applying they are (`target:` in config/apply.yaml)."""

from dataclasses import dataclass, field
from datetime import date

from getjob.apply.config import Target
from getjob.deadline import Deadline, parse_deadline
from getjob.models import Job, normalize


@dataclass
class Candidate:
    job: Job
    deadline: Deadline
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def score(job: Job, target: Target, today: date) -> Candidate | None:
    """Score one posting; None when it must not be applied to at all."""
    title = job.title.lower()
    if any(word.lower() in title for word in target.exclude_keywords):
        return None
    company = normalize(job.company)
    if any(normalize(c) and normalize(c) in company for c in target.companies.exclude):
        return None
    deadline = parse_deadline(job.deadline, today)
    days_left = deadline.days_left(today)
    if days_left is not None and days_left < target.min_days_left:
        return None  # already closed, or too close to write anything decent

    candidate = Candidate(job, deadline)
    searchable = " ".join([title, *job.tags]).lower()
    for word, points in target.keywords.items():
        if word.lower() in searchable:
            candidate.score += points
            candidate.reasons.append(f"{word} {points:+d}")
    for name, points in target.companies.prefer.items():
        if normalize(name) and normalize(name) in company:
            candidate.score += points
            candidate.reasons.append(f"{name} {points:+d}")
    if points := target.sources.get(job.source):
        candidate.score += points
        candidate.reasons.append(f"{job.source} {points:+d}")
    return candidate


def rank(
    jobs: list[Job], target: Target, today: date, taken: set[str] = frozenset()
) -> list[Candidate]:
    """Best first. `taken` holds fingerprints already in the tracker (one application per job)."""
    best: dict[str, Candidate] = {}
    for job in jobs:
        if job.fingerprint in taken or job.fingerprint in best:
            continue
        candidate = score(job, target, today)
        if candidate and candidate.score >= target.min_score:
            best[job.fingerprint] = candidate
    return sorted(best.values(), key=lambda c: (-c.score, c.deadline.date or date.max))
