"""Draft 자기소개서 answers for one posting and write them as a ready-to-review package.

Two engines:
- `template`: offline. Picks the best-fitting episodes from your experience bank and
  assembles STAR-structured answers with [확인 필요] markers where company research goes.
- `claude`: sends the posting, the questions and your experience bank to the Claude API
  (needs ANTHROPIC_API_KEY and `pip install 'getjob[ai]'`).

Either way the package also holds `prompt.md`, the full prompt, so you can paste it into
the Claude app instead of using an API key.
"""

import importlib.util
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from getjob.apply.config import Episode, Experience, QuestionSpec
from getjob.deadline import Deadline
from getjob.models import Job, mentions, normalize, strip_legal

QUESTIONS_FILE = "questions.txt"
DRAFT_FILE = "자기소개서.md"
PROMPT_FILE = "prompt.md"
PLACEHOLDER = re.compile(r"\[(?:확인|작성) 필요[^\]]*\]")
_TRAILING_NOTE = re.compile(r"\s*[(\[]([^()\[\]]*)[)\]]\s*$")
_CHARS = re.compile(r"(?<![제\d])(\d{2,5})\s*자")  # not 제3자
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s")
_WORD = re.compile(r"[0-9A-Za-z가-힣+#]{2,}")


class DraftError(Exception):
    pass


@dataclass
class Answer:
    question: QuestionSpec
    body: str

    @property
    def chars(self) -> int:
        """Characters incl. spaces (공백 포함), the count most application forms use."""
        return len(self.body.strip())

    @property
    def chars_no_spaces(self) -> int:
        return len(re.sub(r"\s", "", self.body))


@dataclass
class Draft:
    engine: str
    answers: list[Answer]
    todo: list[str] = field(default_factory=list)

    def warnings(self, company: str, other_companies: list[str]) -> list[str]:
        """Things to fix before submitting, as checklist lines."""
        out = []
        for i, a in enumerate(self.answers, 1):
            if a.chars > a.question.limit:
                out.append(f"문항 {i} 글자 수 초과 ({a.chars}/{a.question.limit}자) — 줄이기")
            elif a.chars < a.question.limit * 0.8:
                out.append(f"문항 {i} 분량 부족 ({a.chars}/{a.question.limit}자) — 80% 이상 채우기")
        placeholders = sum(len(PLACEHOLDER.findall(a.body)) for a in self.answers)
        if placeholders:
            out.append(f"[확인 필요]·[작성 필요] {placeholders}곳 채우기")
        text = " ".join(a.body for a in self.answers)
        own, own_core = normalize(company), strip_legal(company)
        # Where our own name holds a shorter one (SK in SK하이닉스), look only outside it;
        # an affiliate that contains our name (카카오뱅크 vs 카카오) is searched everywhere.
        outside_own = re.sub(re.escape(own_core), " ", text, flags=re.I) if own_core else text
        wrong = sorted(
            {
                c
                for c in other_companies
                if (n := normalize(c))
                and n != own
                and mentions(c, outside_own if n in own else text)
            }
        )
        if wrong:
            out.append(f"다른 회사 이름이 들어 있음: {', '.join(wrong)}")
        return out


# --- questions --------------------------------------------------------------------


def parse_questions(text: str, default_limit: int = 700) -> list[QuestionSpec]:
    """One question per line; `#` lines are comments.

    A trailing note sets the limit, written the ways application forms do: `(700자)`,
    `[800자 이내]`, `(공백 포함 1,000자 이내)`, `(최소 300자, 최대 1000자)`, `(500~1000자)`.
    """
    questions = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        limit = default_limit
        note = _TRAILING_NOTE.search(line)
        numbers = _CHARS.findall(note[1].replace(",", "")) if note else []
        if numbers and "소제목" not in note[1]:
            limit, line = max(map(int, numbers)), line[: note.start()].strip()
        questions.append(QuestionSpec(text=line, limit=limit))
    return questions


def format_questions(questions: list[QuestionSpec], app_id: int) -> str:
    lines = [
        "# 한 줄에 한 문항, 끝의 (700자)는 글자 수 제한(공백 포함).",
        "# 회사 지원서의 실제 문항으로 고친 뒤 다시 만들기: getjob draft --id " + str(app_id),
    ]
    return "\n".join(lines + [f"{q.text} ({q.limit}자)" for q in questions]) + "\n"


# --- prompt (shared by the Claude engine and prompt.md) --------------------------------

SYSTEM_PROMPT = """\
당신은 한국 기업 신입 채용 자기소개서를 대신 초안으로 써 주는 작성자입니다. 아래 [경험 은행]에 \
적힌 사실만 사용해 지원자 본인의 목소리(1인칭 '저는')로 씁니다.

규칙
1. 경험 은행에 없는 경력·수치·자격·수상은 만들지 않습니다. 꼭 필요한데 없으면 본문에 \
[작성 필요: 무엇]을 남깁니다.
2. 회사 고유 정보(사업, 제품, 인재상, 최근 소식)는 확실할 때만 쓰고, 아니면 \
[확인 필요: 무엇]을 남깁니다.
3. 각 답의 첫 줄은 [소제목] 한 줄입니다. 이어서 두괄식으로 결론 → 근거 경험(상황·과제·행동·결과) → \
입사 후 어떻게 쓰일지 순서로 씁니다.
4. 글자 수는 공백 포함 기준으로 문항 제한의 90~100%를 채우고, 절대 넘기지 않습니다.
5. 한 지원서 안에서 같은 경험을 두 문항에 되풀이하지 않습니다.
6. 다른 회사 이름을 쓰지 않습니다. 근거 없는 다짐이나 과장된 수식어로 분량을 채우지 않습니다.
7. todo에는 지원자가 제출 전에 직접 확인하거나 채워야 할 것만 짧게 적습니다.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "body": {"type": "string"}},
                "required": ["index", "body"],
                "additionalProperties": False,
            },
        },
        "todo": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answers", "todo"],
    "additionalProperties": False,
}


def experience_block(experience: Experience) -> str:
    data = experience.model_dump(exclude_defaults=True)
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False) if data else "(비어 있음)\n"
    return "[경험 은행]\n" + dumped


def posting_block(job: Job, deadline: Deadline, questions: list[QuestionSpec]) -> str:
    facts = [
        ("회사", job.company),
        ("공고 제목", job.title),
        ("태그", ", ".join(job.tags)),
        ("근무지", job.location),
        ("경력", job.experience),
        ("고용형태", job.employment_type),
        ("마감", deadline.raw),
        ("링크", job.url),
    ]
    lines = ["[공고]"] + [f"{k}: {v}" for k, v in facts if v]
    lines += ["", "[문항]"]
    lines += [f"{i}. ({q.limit}자 이내) {q.text}" for i, q in enumerate(questions, 1)]
    lines += ["", "문항마다 답을 쓰고, index는 문항 번호(1부터)로 합니다."]
    return "\n".join(lines)


def prompt_markdown(job: Job, deadline: Deadline, questions, experience: Experience) -> str:
    return (
        "# Claude에 붙여 넣을 프롬프트\n\n"
        "API 키 없이 쓸 때: 아래 전체를 Claude 앱에 붙여 넣고, 결과를 자기소개서.md에 옮기세요.\n\n"
        "```text\n"
        + SYSTEM_PROMPT
        + "\n"
        + experience_block(experience)
        + "\n"
        + posting_block(job, deadline, questions)
        + "\n```\n"
    )


# --- engines ------------------------------------------------------------------------


def claude_available(api_key: str | None) -> bool:
    return bool(api_key) and importlib.util.find_spec("anthropic") is not None


def resolve_engine(choice: str, api_key: str | None) -> str | None:
    """The engine to use for `drafting.engine`; None when 'claude' is required but not set up."""
    if choice == "template":
        return "template"
    if claude_available(api_key):
        return "claude"
    return "template" if choice == "auto" else None


def draft_with_claude(
    job: Job,
    deadline: Deadline,
    questions: list[QuestionSpec],
    experience: Experience,
    model: str,
    client=None,
    api_key: str | None = None,
) -> Draft:
    if client is None:
        try:
            import anthropic
        except ImportError as e:
            raise DraftError("the Claude engine needs: pip install 'getjob[ai]'") from e
        client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            # Rules and your experience bank are identical for every posting: cache them.
            system=[
                {"type": "text", "text": SYSTEM_PROMPT},
                {
                    "type": "text",
                    "text": experience_block(experience),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": posting_block(job, deadline, questions)}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            # If a safety classifier declines, retry on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except _api_errors() as e:
        # Network, key, rate limit, unknown model...: fail this posting, not the whole run.
        detail = getattr(e, "message", "") or str(e)
        raise DraftError(f"Claude API error ({type(e).__name__}): {detail}") from e
    if response.stop_reason == "refusal":
        raise DraftError("Claude declined to draft this posting")
    if response.stop_reason == "max_tokens":
        raise DraftError("Claude's answer was cut off (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        bodies = {a["index"]: a["body"].strip() for a in data.get("answers", [])}
        todo = [t for t in data.get("todo", []) if t.strip()]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        raise DraftError(f"Claude returned an unexpected answer: {e!r}") from e
    answers = [
        Answer(q, bodies.get(i, "[작성 필요: 답이 비어 있음]")) for i, q in enumerate(questions, 1)
    ]
    return Draft("claude", answers, todo)


def _api_errors() -> tuple[type[Exception], ...]:
    try:
        import anthropic
    except ImportError:
        return ()
    return (anthropic.APIError,)


# Question kinds, matched by words in the question text.
_KIND_WORDS = {
    "teamwork": ("협업", "협력", "팀", "갈등", "소통", "조율", "공동", "함께"),
    "challenge": ("도전", "어려", "극복", "실패", "한계", "끈기", "성취", "해낸"),
    "competence": ("역량", "직무", "전문성", "강점", "준비", "노력", "지식"),
    "growth": ("성장", "가치관", "영향", "성격", "장단점", "신념"),
}
_KIND_TAGS = {
    "teamwork": ("협업", "소통", "갈등", "리더십", "팀워크", "조율"),
    "challenge": ("도전", "끈기", "실패", "극복", "성취", "문제해결"),
    "competence": ("직무", "전문성", "분석", "데이터", "실무"),
    "growth": ("가치관", "성장", "책임감", "성실"),
}
_BRIDGE = {
    "teamwork": "구성원의 이야기를 먼저 듣고 공동의 목표로 묶어 팀의 성과에 기여하겠습니다.",
    "challenge": "어려운 과제일수록 목표를 잘게 나누고 끝까지 책임지며 결과를 만들겠습니다.",
    "competence": "이렇게 쌓은 역량을 실무에 바로 적용해 빠르게 제 몫을 해내겠습니다.",
    "growth": "이 경험에서 세운 기준을 지키며 꾸준히 성장하는 구성원이 되겠습니다.",
}
# 지원 동기 / 지원한 이유 / 지원하게 된 계기·배경 / 입사 동기 — but not 지원자 or 입사 동기들
_MOTIVATION = re.compile(r"(지원|입사)(?!자)\S*(\s+\S+)?\s*(동기(?!들)|이유|사유|계기|배경)")
# Looser hints, only when the question doesn't ask for an experience
_MOTIVATION_HINT = re.compile(r"선택한 이유|입사하고 싶|포부|입사 후")


def question_kind(text: str) -> str:
    if _MOTIVATION.search(text) or (_MOTIVATION_HINT.search(text) and "경험" not in text):
        return "motivation"
    hits = {kind: sum(w in text for w in words) for kind, words in _KIND_WORDS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else "competence"


def draft_with_template(job: Job, questions: list[QuestionSpec], experience: Experience) -> Draft:
    kinds = [question_kind(q.text) for q in questions]
    episodes = assign_episodes(kinds, experience.episodes, job)
    answers = []
    for q, kind, episode in zip(questions, kinds, episodes, strict=True):
        if kind == "motivation":
            body = _motivation(job, experience)
        elif episode is None and kind == "competence":
            body = _competence(job, experience)
        else:
            body = _episode_answer(job, episode, kind)
        answers.append(Answer(q, fit(body, q.limit)))
    todo = ["경험 은행(config/experience.yaml)을 채우면 더 구체적인 초안이 나옵니다."]
    return Draft("template", answers, todo if experience.is_empty else [])


def assign_episodes(kinds: list[str], episodes: list[Episode], job: Job) -> list[Episode | None]:
    """Give each episode-based question its best-fitting episode, each episode at most once.

    Best pairs are matched first, so a teamwork question gets the teamwork story even when
    a generic question comes before it. Questions left without an episode get None (the
    answer then asks you to add one) rather than repeating a story already used.
    """
    job_words = {w.lower() for w in _WORD.findall(" ".join([job.title, *job.tags]))}

    def fitness(kind: str, episode: Episode) -> int:
        tags = {t.lower() for t in episode.tags}
        has_number = bool(re.search(r"\d", episode.result))
        return 2 * len(tags & set(_KIND_TAGS[kind])) + len(tags & job_words) + has_number

    pairs = sorted(
        (
            (-fitness(kind, e), qi, ei)
            for qi, kind in enumerate(kinds)
            if kind != "motivation"
            for ei, e in enumerate(episodes)
        )
    )
    chosen: list[Episode | None] = [None] * len(kinds)
    used: set[int] = set()
    for _, qi, ei in pairs:
        if chosen[qi] is None and ei not in used:
            chosen[qi] = episodes[ei]
            used.add(ei)
    return chosen


# Longer words first, so 채용형 isn't read as 채용 + 형.
_TITLE_NOISE = re.compile(
    r"\[[^\]]*\]|\([^)]*\)|\d{2,4}년도?|(?<!\d)20\d{2}(?!\d)|[상하]반기|제\s*\d+\s*차|"
    r"\d+\s*차(?![가-힣])|신입사원|신입직원|신입행원|신규직원|신입|경력무관|경력직|경력|정규직|"
    r"공개경쟁|공개채용|공채|채용연계형|채용전환형|채용형|채용공고|채용|공고|모집|체험형|"
    r"청년인턴|인턴|대졸|블라인드|직원|및|[~/·,|-]"
)


def _role(job: Job) -> str:
    """The position's name from the title, or '지원 직무' when the title is a notice.

    `R&D 부문 신입사원 채용` -> `R&D 부문`;
    `2026년도 제2차 국가철도공단 신입직원 채용공고` -> `지원 직무`.
    """
    title = _TITLE_NOISE.sub(" ", strip_legal(job.title))
    if company := strip_legal(job.company):
        title = title.replace(company, " ")
    title = " ".join(title.split())
    return title if 1 < len(title) <= 20 else "지원 직무"


def _josa(word: str, with_final: str, without_final: str) -> str:
    """The particle that fits `word`: 으로/로 (a final ㄹ takes 로), 을/를, 이/가."""
    last = word.strip()[-1:].lower()
    if last.isdigit() or last.isascii():
        # How the last character is read: 1 일, 3 삼, 6 육, 7 칠, 8 팔, 0 영 / PM 엠, BL 엘
        final = {"1": 8, "7": 8, "8": 8, "l": 8, "3": 16, "m": 16, "6": 1, "0": 21, "n": 4}
        final = final.get(last, 0)
    elif "가" <= last <= "힣":
        final = (ord(last) - ord("가")) % 28
    else:
        return without_final
    if final == 0 or (with_final == "으로" and final == 8):
        return without_final
    return with_final


def _episode_answer(job: Job, episode: Episode | None, kind: str) -> str:
    if episode is None:
        return (
            "[작성 필요: 소제목]\n"
            "[작성 필요: 이 문항에 맞는 경험 한 가지 — 상황과 맡은 과제]\n"
            "[작성 필요: 내가 한 행동 2~3가지]\n"
            "[작성 필요: 결과를 숫자로]\n"
            f"이 경험을 바탕으로 {job.company}에서도 {_BRIDGE[kind]}"
        )
    parts = [
        f"[{episode.title}]",
        " ".join(p for p in (episode.situation, episode.task) if p),
        episode.action,
        episode.result or "[작성 필요: 결과를 숫자로]",
        episode.lesson,
        f"이 경험을 바탕으로 {job.company}의 {_role(job)}에서도 {_BRIDGE[kind]}",
    ]
    return "\n".join(p for p in parts if p)


def _competence(job: Job, experience: Experience) -> str:
    """A competence answer built from skills and certificates when no episode is left."""
    assets = [*experience.skills, *experience.certificates, *experience.languages]
    have = f"저는 {', '.join(assets)} 등을 갖추고 있습니다. " if assets else ""
    return "\n".join(
        [
            f"[{_role(job)}에 필요한 역량을 준비해 왔습니다]",
            have + "[작성 필요: 이 역량을 기르기 위해 한 일과 결과를 숫자로]",
            f"[확인 필요: {job.company} 공고의 우대 사항과 내 역량의 연결]",
            f"{job.company}에서도 {_BRIDGE['competence']}",
        ]
    )


def _motivation(job: Job, experience: Experience) -> str:
    focus = ", ".join(job.tags[:3])
    parts = [
        f"[{job.company}에서 {(role := _role(job))}{_josa(role, '으로', '로')} 일하고 싶은 이유]",
        experience.motivation or "[작성 필요: 이 산업·직무를 택한 이유 2~3문장]",
        (f"이번 공고에서 특히 {focus} 업무에 주목했습니다. " if focus else "")
        + f"[확인 필요: {job.company}의 최근 사업이나 인재상 한 가지와 제 경험의 연결]",
        experience.goals or "[작성 필요: 입사 후 1년·3년 목표]",
    ]
    return "\n".join(parts)


def fit(text: str, limit: int) -> str:
    """Cut to `limit` characters at a sentence end (or a line end) when too long."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cuts = [m.end() - 1 for m in _SENTENCE_END.finditer(head)] + [
        i for i, ch in enumerate(head) if ch == "\n"
    ]
    cut = max((c for c in cuts if c >= limit // 2), default=limit)
    return head[:cut].rstrip()


# --- package ------------------------------------------------------------------------


def folder_name(app_id: int, company: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", normalize(company) or company).strip("_")
    return f"{app_id:03d}_{slug[:30] or 'company'}"


def render(
    app_id: int,
    job: Job,
    deadline: Deadline,
    score: int,
    reasons: str,
    draft: Draft,
    warnings: list[str],
    today: date,
) -> str:
    lines = [
        f"# {job.company} — {job.title}",
        "",
        f"- 공고: {job.url}",
        f"- 마감: {deadline.label(today)}" + (f" ({deadline.raw})" if deadline.raw else ""),
        f"- 선정 점수: {score}" + (f" ({reasons})" if reasons else ""),
        f"- 초안: {draft.engine} · {today.isoformat()}",
        f"- 제출한 뒤: `getjob mark {app_id} submitted`",
        "",
        "## 제출 전 확인",
        "",
    ]
    checks = (
        warnings
        + draft.todo
        + [
            f"실제 지원서 문항·글자 수가 {QUESTIONS_FILE}와 같은지 확인 "
            f"(다르면 고치고 `getjob draft --id {app_id}`)",
            "사진·증빙·어학 성적 등 첨부 서류 준비",
        ]
    )
    lines += [f"- [ ] {c}" for c in checks]
    for i, a in enumerate(draft.answers, 1):
        lines += [
            "",
            f"## {i}. {a.question.text} ({a.question.limit}자)",
            "",
            f"_공백 포함 {a.chars}자 · 공백 제외 {a.chars_no_spaces}자_",
            "",
            a.body,
        ]
    return "\n".join(lines) + "\n"


def write_package(folder: Path, files: dict[str, str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
