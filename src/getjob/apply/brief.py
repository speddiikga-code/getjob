"""`getjob brief`: a short status message — main pilot first, then what needs your hands."""

from datetime import date, timedelta

from getjob.apply.config import ApplyProfile
from getjob.apply.tracker import Tracker

SHOW = 5  # items per list; the rest is summarised as "외 N건"
NEXT_STAGE_DAYS = 21


def build(tracker: Tracker, profile: ApplyProfile, today: date) -> tuple[str, str]:
    """Return (subject, text)."""
    lines = []
    focus = profile.focus
    if focus.main:
        line = f"주 파일럿: {focus.main}"
        if m := focus.next_milestone(today):
            estimate = "" if m.confirmed else " (추정)"
            line += f" · {m.name} {_dday(m.date, today)}{estimate}"
        lines.append(line)
    if quiet := focus.quiet_period(today):
        lines.append(f"집중 기간 ~{_md(quiet.end)} ({quiet.reason}): 새 회사 초안 중지")

    monday = today - timedelta(days=today.weekday())
    cap = profile.budget.max_per_week
    lines.append(
        f"이번 주 회사 지원: 초안 {tracker.drafted_since(monday)}/{cap} · "
        f"제출 {tracker.submitted_since(monday)}"
    )

    ready = sorted(tracker.find(("drafted",)), key=lambda a: (a.deadline.date or date.max, a.id))
    if ready:
        lines += ["", f"검토·제출 대기 {len(ready)}건 (마감 순)"]
        for app in ready[:SHOW]:
            lines.append(f"  #{app.id} {app.company} · {app.deadline.label(today)}")
            lines.append(f"      {app.url}")
        if len(ready) > SHOW:
            lines.append(f"  외 {len(ready) - SHOW}건 — getjob apps")

    upcoming = sorted(
        (
            a
            for a in tracker.find(("next",))
            if a.next_date and 0 <= (a.next_date - today).days <= NEXT_STAGE_DAYS
        ),
        key=lambda a: a.next_date,
    )
    if upcoming:
        lines += ["", "다음 전형"]
        for app in upcoming[:SHOW]:
            weekday = "월화수목금토일"[app.next_date.weekday()]
            lines.append(
                f"  #{app.id} {app.company} {app.stage or '다음 전형'} "
                f"{_md(app.next_date)}({weekday}) {_dday(app.next_date, today)}"
            )

    waiting = tracker.find(("submitted",))
    if waiting:
        lines += ["", f"결과 대기 {len(waiting)}건"]
    if not (ready or upcoming or waiting):
        lines += ["", "처리할 회사 지원이 없습니다. 새 공고는 다음 실행 때 자동으로 고릅니다."]

    subject = f"[getjob] {_md(today)} 제출 대기 {len(ready)}건"
    if upcoming:
        subject += f" · 다음 전형 {len(upcoming)}건"
    return subject, "\n".join(lines)


def _md(day: date) -> str:
    return f"{day.month}/{day.day}"


def _dday(day: date, today: date) -> str:
    left = (day - today).days
    return f"D-{left}" if left > 0 else "D-day"
