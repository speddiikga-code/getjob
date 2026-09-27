"""Shortlisting, the tracker, the weekly budget, drafting and the brief — all offline."""

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from getjob.apply import brief, drafter, pipeline
from getjob.apply.config import (
    ApplyProfile,
    Experience,
    QuestionSpec,
    load_apply_profile,
    load_experience,
)
from getjob.apply.shortlist import rank, score
from getjob.apply.tracker import Tracker
from getjob.deadline import parse_deadline
from getjob.models import Job
from getjob.store import Store

ROOT = Path(__file__).resolve().parents[1]
MONDAY = date(2026, 9, 28)


def job(source_id="1", title="2026년 신입사원 공채", company="(주)테스트", **kw):
    kw.setdefault("source", "saramin")
    kw.setdefault("deadline", "~ 10/20(화)")
    source = kw.pop("source")
    url = f"https://example.com/{source}/{source_id}"
    return Job(source, source_id, title, company, url, location="서울 중구", **kw)


def make_profile(**overrides) -> ApplyProfile:
    data = {
        "target": {
            "keywords": {"신입사원": 2, "공채": 2, "신입직원": 2, "체험형": -1},
            "exclude_keywords": ["배송"],
            "companies": {"prefer": {"테스트": 1}, "exclude": ["블랙"]},
            "sources": {"alio": 2},
            "min_score": 2,
            "min_days_left": 3,
        },
        "budget": {"max_per_week": 3},
        "questions": [
            {"text": "지원 동기와 입사 후 목표를 기술해 주십시오.", "limit": 700},
            {"text": "직무 역량을 기르기 위해 노력한 경험을 기술해 주십시오.", "limit": 700},
            {"text": "다른 사람과 협업했던 경험을 기술해 주십시오.", "limit": 700},
            {"text": "어려운 목표에 도전해 해낸 경험을 기술해 주십시오.", "limit": 700},
        ],
    }
    data.update(overrides)
    return ApplyProfile.model_validate(data)


EXPERIENCE = Experience(
    motivation="좋은 제품이 시장을 찾도록 돕는 일에 보람을 느꼈습니다.",
    goals="3년 안에 신규 시장 개척 프로젝트를 주도하겠습니다.",
    skills=["엑셀"],
    episodes=[
        {
            "title": "자격증 도전",
            "tags": ["도전", "끈기"],
            "situation": "처음 점수가 40점이었습니다.",
            "action": "틀린 유형을 매일 기록했습니다.",
            "result": "두 번째 시험에서 합격했습니다.",
        },
        {
            "title": "동아리 수출 프로젝트",
            "tags": ["협업", "소통", "무역"],
            "situation": "5명이 수출 프로젝트를 맡았습니다.",
            "action": "팀원들과 매주 결과를 공유했습니다.",
            "result": "응답률을 4%에서 12%로 올렸습니다.",
        },
    ],
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "jobs.db"
    store, tracker = Store(path), Tracker(path, clock=lambda: datetime(2026, 9, 28, 9, 0))
    yield store, tracker
    store.close()
    tracker.close()


# --- config --------------------------------------------------------------------------


def test_shipped_apply_profile_and_example_experience_are_valid():
    profile = load_apply_profile(ROOT / "config" / "apply.yaml")
    assert "한의학과" in profile.focus.main
    assert profile.focus.quiet_period(date(2026, 12, 26))  # 영어 필답 day: no new drafts
    assert profile.focus.quiet_period(MONDAY) is None
    assert profile.focus.next_milestone(MONDAY).date == date(2026, 11, 30)
    assert all(m.source.startswith("https://") for m in profile.focus.milestones)
    example = load_experience(ROOT / "config" / "experience.example.yaml")
    assert len(example.episodes) == 2 and not example.is_empty


def test_missing_experience_bank_is_empty(tmp_path):
    assert load_experience(tmp_path / "none.yaml").is_empty


def test_experience_bank_typos_are_rejected():
    with pytest.raises(ValueError):
        Experience.model_validate({"episodes": [{"title": "x", "reslut": "typo"}]})


# --- shortlist ------------------------------------------------------------------------


def test_score_adds_keywords_company_and_source_points():
    target = make_profile().target
    c = score(job(company="주식회사 테스트"), target, MONDAY)
    assert c.score == 5 and c.reasons == ["신입사원 +2", "공채 +2", "테스트 +1"]
    alio = score(
        job(title="신입직원 및 체험형 청년인턴", company="국가철도공단", source="alio"),
        target,
        MONDAY,
    )
    assert alio.score == 3  # 신입직원 +2, 체험형 -1, alio +2


@pytest.mark.parametrize(
    "posting",
    [
        job(title="신입사원 배송 기사"),  # excluded word
        job(company="(주)블랙기업"),  # excluded company
        job(deadline="~ 09/30(수)"),  # 2 days left, fewer than min_days_left
        job(deadline="2026-09-20"),  # already closed
    ],
)
def test_score_rejects(posting):
    assert score(posting, make_profile().target, MONDAY) is None


def test_open_ended_and_undated_postings_are_kept():
    target = make_profile().target
    assert score(job(deadline="상시채용"), target, MONDAY).score == 5
    assert score(job(deadline=""), target, MONDAY).score == 5


def test_rank_orders_by_score_then_deadline_and_skips_duplicates_and_taken():
    target = make_profile().target
    jobs = [
        job("1", title="신입사원 채용", deadline="~ 10/30(금)"),
        job("2", title="신입사원 공채", company="(주)다른회사"),
        job("3", title="신입사원 채용", company="(주)가나", deadline="~ 10/10(토)"),
        job("4", title="신입사원 공채", company="(주)다른회사", source="work24"),  # same job
        job("5", title="마케터"),  # score 1 < min_score
        job("6", title="신입사원 채용", company="(주)이미"),
    ]
    taken = {jobs[5].fingerprint}
    ranked = rank(jobs, target, MONDAY, taken)
    assert [c.job.source_id for c in ranked] == ["2", "1", "3"]


# --- tracker and budget ---------------------------------------------------------------


def candidate(posting, today=MONDAY):
    return score(posting, make_profile().target, today)


def test_deadline_is_fixed_when_added_so_a_year_less_date_still_expires(db):
    _, tracker = db
    app_id = tracker.add(candidate(job(deadline="~ 10/05(월)")))
    assert tracker.get(app_id).deadline.date == date(2026, 10, 5)
    # Read again in December, '~10/05' would mean next October; the stored date doesn't drift.
    expired = tracker.expire(date(2026, 12, 20))
    assert [a.id for a in expired] == [app_id]
    assert tracker.get(app_id).status == "expired"


def test_capacity_is_limited_by_this_week_and_by_the_unreviewed_backlog(db):
    _, tracker = db
    ids = [tracker.add(candidate(job(str(i), company=f"회사{i}"))) for i in range(3)]
    assert tracker.capacity(3, MONDAY) == 0  # 3 queued, none reviewed
    for i in ids:
        tracker.set_drafted(i, Path(f"/tmp/{i}"))
    tracker.mark(ids[0], "submitted")
    assert tracker.capacity(3, MONDAY) == 0  # this week's 3 drafts are used up
    next_monday = date(2026, 10, 5)
    assert tracker.capacity(3, next_monday) == 1  # new week, but 2 drafts still unreviewed


def test_mark_records_the_first_submission_and_next_stage(db):
    _, tracker = db
    app_id = tracker.add(candidate(job()))
    tracker.mark(app_id, "submitted")
    first = tracker.get(app_id).submitted_at
    tracker.mark(app_id, "next", stage="인적성", next_date=date(2026, 10, 18))
    app = tracker.get(app_id)
    assert (app.status, app.stage, app.next_date) == ("next", "인적성", date(2026, 10, 18))
    assert app.submitted_at == first
    with pytest.raises(ValueError):
        tracker.mark(app_id, "accepted")


def test_plan_takes_the_best_within_budget_and_nothing_in_a_quiet_period(db):
    store, tracker = db
    store.add([job(str(i), title="신입사원 공채", company=f"회사{i}") for i in range(5)])
    quiet = make_profile(
        focus={"quiet_periods": [{"start": "2026-09-01", "end": "2026-10-01", "reason": "시험"}]}
    )
    assert pipeline.plan(store, tracker, quiet, MONDAY) == []
    queued = pipeline.plan(store, tracker, make_profile(), MONDAY)
    assert len(queued) == 3  # max_per_week
    assert pipeline.plan(store, tracker, make_profile(), MONDAY) == []


def test_store_recent_reads_jobs_back(db):
    store, _ = db
    posting = job(tags=["무역", "영업"], posted_at=date(2026, 9, 25))
    store.add([posting])
    assert store.recent(datetime(2000, 1, 1)) == [posting]
    assert store.recent(datetime(2999, 1, 1)) == []
    assert store.get(posting.key) == posting


# --- drafting ------------------------------------------------------------------------


def test_template_matches_each_question_with_its_best_episode_once():
    questions = make_profile().questions
    draft = drafter.draft_with_template(job(), questions, EXPERIENCE)
    motivation, competence, teamwork, challenge = (a.body for a in draft.answers)
    assert motivation.startswith("[(주)테스트에서") and "[확인 필요:" in motivation
    assert "[동아리 수출 프로젝트]" in teamwork  # not the certificate story
    assert "[자격증 도전]" in challenge
    # Both episodes are taken, so competence doesn't repeat one: it asks for more.
    assert "동아리" not in competence and "자격증 도전" not in competence
    assert "엑셀" in competence and "[작성 필요:" in competence


def test_template_with_an_empty_experience_bank_leaves_guided_blanks():
    draft = drafter.draft_with_template(job(), make_profile().questions, Experience())
    assert all(drafter.PLACEHOLDER.search(a.body) for a in draft.answers)
    assert draft.todo


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("지원 동기와 입사 후 포부를 쓰시오", "motivation"),
        ("공동의 목표를 위해 협업했던 경험", "teamwork"),
        ("어려움을 극복하고 목표를 달성한 경험", "challenge"),
        ("가치관에 영향을 준 사건", "growth"),
        ("자유롭게 기술하시오", "competence"),
    ],
)
def test_question_kind(text, kind):
    assert drafter.question_kind(text) == kind


def test_questions_file_round_trip():
    text = drafter.format_questions(
        [QuestionSpec(text="지원 동기", limit=500), QuestionSpec(text="협업 경험", limit=1000)], 7
    )
    assert "getjob draft --id 7" in text
    parsed = drafter.parse_questions(text + "\n성장 과정 [800자 이내]\n자유 기술\n")
    assert [(q.text, q.limit) for q in parsed] == [
        ("지원 동기", 500),
        ("협업 경험", 1000),
        ("성장 과정", 800),
        ("자유 기술", 700),
    ]


def test_fit_cuts_at_a_sentence_end():
    text = "첫 문장입니다. 두 번째 문장입니다. 세 번째 문장은 아주 깁니다."
    assert drafter.fit(text, 100) == text
    assert drafter.fit(text, 20) == "첫 문장입니다. 두 번째 문장입니다."


def test_warnings_catch_length_blanks_and_other_company_names():
    q = QuestionSpec(text="지원 동기", limit=50)
    draft = drafter.Draft(
        "template",
        [
            drafter.Answer(q, "가" * 60),
            drafter.Answer(q, "(주)다른회사에 꼭 가고 싶습니다. [확인 필요: x]"),
        ],
    )
    warnings = draft.warnings("(주)테스트", ["주식회사 다른회사", "(주)테스트", "무관"])
    assert warnings[0].startswith("문항 1 글자 수 초과 (60/50자)")
    assert warnings[1].startswith("문항 2 분량 부족")
    assert "[확인 필요]·[작성 필요] 1곳 채우기" in warnings
    assert warnings[-1] == "다른 회사 이름이 들어 있음: 주식회사 다른회사"


class FakeClient:
    def __init__(self, stop_reason="end_turn", payload=None):
        self.calls = []
        text = json.dumps(payload if payload is not None else {"answers": [], "todo": []})
        self.response = SimpleNamespace(
            stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_claude_engine_request_and_answers():
    questions = make_profile().questions[:2]
    client = FakeClient(
        payload={"answers": [{"index": 2, "body": " [역량]\n본문 "}], "todo": ["인재상 확인", " "]}
    )
    posting = job()
    deadline = parse_deadline(posting.deadline, MONDAY)
    draft = drafter.draft_with_claude(
        posting, deadline, questions, EXPERIENCE, "claude-opus-5", client
    )
    (call,) = client.calls
    assert call["model"] == "claude-opus-5"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["schema"] == drafter.OUTPUT_SCHEMA
    assert call["thinking"] == {"type": "adaptive"}
    rules, bank = call["system"]
    assert bank["cache_control"] == {"type": "ephemeral"} and "동아리 수출 프로젝트" in bank["text"]
    assert "(주)테스트" in call["messages"][0]["content"]
    assert "2. (700자 이내) 직무 역량" in call["messages"][0]["content"]
    assert draft.engine == "claude"
    assert draft.answers[1].body == "[역량]\n본문"
    assert drafter.PLACEHOLDER.search(draft.answers[0].body)  # missing answer is flagged
    assert draft.todo == ["인재상 확인"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_engine_errors(stop_reason):
    posting = job()
    with pytest.raises(drafter.DraftError):
        drafter.draft_with_claude(
            posting,
            parse_deadline(posting.deadline, MONDAY),
            make_profile().questions,
            EXPERIENCE,
            "claude-opus-5",
            FakeClient(stop_reason),
        )


def test_run_writes_packages_and_redraft_uses_edited_questions(db, tmp_path):
    store, tracker = db
    store.add([job("1", company="(주)가나"), job("2", company="(주)다라")])
    profile, out_dir = make_profile(), tmp_path / "applications"

    code = pipeline.run(store, tracker, profile, EXPERIENCE, "template", out_dir, MONDAY)

    assert code == 0
    apps = tracker.find(("drafted",))
    assert len(apps) == 2
    folder = Path(apps[0].folder)
    assert folder.parent == out_dir and folder.name == "001_가나"
    draft_md = (folder / drafter.DRAFT_FILE).read_text(encoding="utf-8")
    assert "# (주)가나 — 2026년 신입사원 공채" in draft_md
    assert "`getjob mark 1 submitted`" in draft_md
    assert "(주)가나" in (folder / drafter.PROMPT_FILE).read_text(encoding="utf-8")

    # The company's real questions replace the defaults on the next draft of this one.
    (folder / drafter.QUESTIONS_FILE).write_text(
        "우리 회사를 고른 이유 (300자)\n", encoding="utf-8"
    )
    assert pipeline.run(store, tracker, profile, EXPERIENCE, "template", out_dir, MONDAY, [1]) == 0
    draft_md = (folder / drafter.DRAFT_FILE).read_text(encoding="utf-8")
    assert "## 1. 우리 회사를 고른 이유 (300자)" in draft_md and "## 2." not in draft_md
    assert tracker.drafted_since(MONDAY) == 2  # re-drafting doesn't use up the budget


def test_run_reports_engine_errors_and_keeps_the_application_queued(db, tmp_path):
    store, tracker = db
    store.add([job()])
    client = FakeClient("refusal")
    code = pipeline.run(
        store, tracker, make_profile(), EXPERIENCE, "claude", tmp_path, MONDAY, client=client
    )
    assert code == 1
    assert [a.status for a in tracker.find()] == ["queued"]


# --- brief ---------------------------------------------------------------------------


def test_brief_puts_the_main_pilot_first_then_what_needs_hands(db):
    _, tracker = db
    profile = make_profile(
        focus={
            "main": "경희대 한의학과 편입",
            "milestones": [{"name": "영어 필답", "date": "2026-12-26"}],
        }
    )
    ready = tracker.add(candidate(job("1", company="(주)가나", deadline="~ 10/08(목)")))
    tracker.set_drafted(ready, Path("/tmp/x"))
    nxt = tracker.add(candidate(job("2", company="(주)다라")))
    tracker.mark(nxt, "next", stage="1차 면접", next_date=date(2026, 10, 2))

    subject, text = brief.build(tracker, profile, MONDAY)

    assert subject == "[getjob] 9/28 제출 대기 1건 · 다음 전형 1건"
    lines = text.splitlines()
    assert lines[0] == "주 파일럿: 경희대 한의학과 편입 · 영어 필답 D-89 (추정)"
    assert lines[1] == "이번 주 회사 지원: 초안 1/3 · 제출 1"
    assert "  #1 (주)가나 · 10/08(목) D-10" in lines
    assert "  #2 (주)다라 1차 면접 10/2(금) D-4" in lines


def test_brief_in_a_quiet_period_with_nothing_to_do(db):
    _, tracker = db
    profile = make_profile(
        focus={"quiet_periods": [{"start": "2026-09-01", "end": "2026-10-01", "reason": "필답"}]}
    )
    subject, text = brief.build(tracker, profile, MONDAY)
    assert subject == "[getjob] 9/28 제출 대기 0건"
    assert "집중 기간 ~10/1 (필답): 새 회사 초안 중지" in text
    assert "처리할 회사 지원이 없습니다" in text
