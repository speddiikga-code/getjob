# getjob — 서울 신입 정규직 자동 채용 검색 + 지원서 초안 자동화

Automatically collects **entry-level (신입, incl. 경력무관) regular full-time (정규직) jobs
in Seoul** from LinkedIn and 9 Korean job sites, removes postings you've already seen
(and the same job listed on several sites), and reports only the new ones.

It then **picks the postings worth applying to, drafts the 자기소개서 for each one, and keeps
a queue of what is ready to submit** — inside a weekly budget, so the job hunt never eats
the time reserved for the main goal (the main pilot: 경희대 한의학과 편입). Everything up to
the submit button is automated; submitting stays with you.

## Status

| Step | What | State |
|------|------|-------|
| 1 | Environment: project, config, secrets, cloud check, CI | ✅ done |
| 2 | Site collectors for all 10 sites + de-duplication + CSV export | ✅ done |
| 3 | Application automation: shortlist → 자기소개서 drafts → review queue → tracker | ✅ done |
| 4 | Brief (main-pilot D-day + what needs your hands) by Telegram / email | ✅ done |
| 5 | Schedule `getjob run --send` on a machine with a Korean IP (e.g. 08:00 / 18:00 KST) | next |

## Sites

Each site is searched with its own filters for 서울 · 신입 · 정규직, newest first.

| Key | Site | How it's read | Seoul 신입 postings* |
|-----|------|---------------|---------------------|
| `saramin` | 사람인 | search page (`SARAMIN_API_KEY` → official Open API) | ~19,800 |
| `jobkorea` | 잡코리아 | 채용정보 list (신입 + 경력무관) | ~29,400 |
| `work24` | 고용24 (구 워크넷) | detailed search (정규직 = 기간의 정함이 없는 근로계약) | ~8,600 |
| `incruit` | 인크루트 | mobile list | ~1,150 |
| `wanted` | 원티드 | JSON API (years=0; interns/contract dropped) | — |
| `linkedin` | LinkedIn | public guest search: Seoul, Entry level, Full-time, past week | — |
| `peoplenjob` | 피플앤잡 (외국계) | list page (인턴.신입.2년이내) | — |
| `alio` | 잡알리오 (공공기관) | recruit board (정규직, 신입 / 신입+경력) | ~60 |
| `jumpit` | 점핏 (IT/개발) | JSON API (career=0) | ~10 |
| `remember` | 리멤버 커리어 | JSON API (experience range includes 0) | ~6 |

\* totals the sites reported in September 2026 (— = site doesn't show a total). 잡플래닛, 캐치 and 로켓펀치 block automated access (HTTP 403).

The same job is often listed on several sites (고용24 re-lists many 사람인 postings). A
posting counts as new only if no site has shown the same company + title before.

## Quick start

Requires Python 3.11+.

```bash
./scripts/setup.sh                  # .venv, dependencies, .env, offline check
source .venv/bin/activate
getjob doctor                       # checks config, secrets, and that every site is reachable

getjob collect --all --csv          # first run: read EVERY posting (takes a while) and save a CSV
getjob collect --csv                # later runs: only the newest postings, stops at ones already seen
```

`getjob collect` options:

| Option | Meaning |
|--------|---------|
| `--source saramin` | only this site (repeatable) |
| `--limit 100` | newest postings to read per site (default: `limits.max_per_source`, 300) |
| `--all` | no limit — every posting on every site |
| `--csv [path]` | save new postings to a CSV (Excel-friendly); default `data/new_jobs_<time>.csv` |
| `--show 20` | how many new postings to print (default 50) |

Every posting ever seen is kept in `data/jobs.db` (SQLite), which is how later runs know what's new.

## Application automation (지원서 자동화)

```
collect ──▶ shortlist ──▶ draft ──▶ you review & submit ──▶ mark ──▶ brief
 (sites)    (score, budget)  (자기소개서 package)   (the only manual step)   (tracker)
```

| Command | What it does |
|---------|--------------|
| `getjob shortlist` | which collected postings would be picked, with the score breakdown (changes nothing) |
| `getjob draft` | queue the best postings that fit this week's budget and draft their 자기소개서 |
| `getjob draft --id 12` | re-draft one application, e.g. after putting the company's real questions in its `questions.txt` |
| `getjob apps [--all]` | the tracker: 초안 대기 · 검토·제출 대기 · 제출함 · 다음 전형 · 최종 합격 · 불합격 · 건너뜀 · 마감 지남 |
| `getjob mark 12 submitted` | record what happened: `submitted`, `next --stage 인적성 --date 2026-10-18`, `rejected`, `offer`, `skipped` |
| `getjob brief [--send]` | the status message: main pilot's next date first, then drafts to submit (by deadline) and upcoming stages |
| `getjob run [--send]` | `collect` + `draft` + `brief` — the one command to schedule |

### Setting it up

1. `cp config/experience.example.yaml config/experience.yaml` and write your experiences once,
   in STAR form (상황·과제·행동·결과). Drafts use **only** facts from this file; anything
   missing is left as `[작성 필요: …]`, company facts as `[확인 필요: …]`.
   The file is git-ignored — this repository is public, so never commit it.
2. Edit `config/apply.yaml`:
   - `target.keywords` — job words you want, with points (negative = penalty); `exclude_keywords`,
     `companies.prefer / exclude`, bonus points per site, `min_score`, `min_days_left`
   - `budget.max_per_week` — drafts per week = what you review and submit (default 6 ≈ two 90-minute blocks)
   - `focus` — the main pilot, its dates (shown as D-day in the brief) and quiet periods
   - `questions` — default questions when the company's are unknown
3. Optional: put `ANTHROPIC_API_KEY` in `.env` and `pip install -e ".[ai]"` to have Claude
   (`drafting.model`, default `claude-opus-5`) write the drafts. Without a key, the offline
   template engine assembles them from your experience bank, and every package includes
   `prompt.md` to paste into the Claude app instead. With a key, your experience bank and
   the posting are sent to the Claude API.

`getjob doctor` shows whether the experience bank and the Claude engine are ready.

### What a draft package contains

`data/applications/012_회사/` (next to the database, git-ignored):

- `자기소개서.md` — posting link, deadline (D-day), why it was picked, a pre-submit checklist
  (over/under the character limit, unfilled `[확인 필요]`, another company's name left in the
  text, attachments), then each answer with its 공백 포함 / 공백 제외 character counts
- `questions.txt` — the questions used; replace them with the company's real ones and run
  `getjob draft --id 12`
- `prompt.md` — the full prompt, for the Claude app

### The weekly budget and the main pilot

- At most `budget.max_per_week` new drafts per week (Mon–Sun), and never more unreviewed
  drafts than that: if you don't review, the pipeline stops adding work instead of piling it up.
- `focus.quiet_periods`: no new postings are picked (e.g. 12/1–1/22 for the 편입 원서,
  영어 필답 and 면접); applications already submitted are still tracked.
- Drafts whose deadline passes are moved to `마감 지남` automatically.
- Each posting gets one application, even when several sites list it; `skipped` ones never come back.

### Scheduling

On a machine with a Korean IP (see below), twice a day:

```cron
# 08:00 and 18:00 KST
0 8,18 * * * cd ~/getjob && .venv/bin/getjob run --send >> data/run.log 2>&1
```

The brief goes to `notify.channels` in `config/search.yaml`. Its subject starts with `[getjob]`,
so a mail filter or another assistant can pick it up.

### Narrowing results — `config/search.yaml`

- `keywords`: keep only postings whose title/tags contain one of these (empty = everything)
- `exclude_keywords`: drop titles containing these (default: 계약직, 파견, 아르바이트, 알바, 단기)
- `location.districts`: e.g. `[강남구, 서초구]` (empty = all of Seoul)
- `exclude_companies`, `limits.max_per_source`, and `sources:` to turn sites on/off

Secrets go in **`.env`** (see `.env.example`; git-ignored, never commit it).

## Running in the cloud

**GitHub Actions can't be used for the Korean sites**: the *Cloud environment check* run
showed that from GitHub's (US) servers 잡코리아 and 사람인 time out and 원티드 answers
HTTP 403 — they block foreign IPs. LinkedIn, 인크루트, 고용24, 리멤버, 점핏, 피플앤잡 and
잡알리오 were reachable.

So the scheduled runs need a machine with a Korean IP, for example a small VM in a Seoul
cloud region, using the Docker image:

```bash
docker build -t getjob .
docker run --rm --env-file .env -v "$PWD/data:/app/data" getjob doctor
docker run --rm --env-file .env -v "$PWD/data:/app/data" getjob collect --csv
docker run --rm --env-file .env -v "$PWD/data:/app/data" \
  -v "$PWD/config/experience.yaml:/app/config/experience.yaml:ro" getjob run --send
```

To see what a location can reach: **Actions → Cloud environment check → Run workflow**
(runs `getjob doctor --all-sources` on GitHub), or `getjob doctor --all-sources` anywhere else.

## Development

```bash
ruff check . && ruff format --check .
pytest -q
```

Parser tests run against trimmed real responses in `tests/fixtures/`. When a site changes
its layout, `getjob collect` reports `FAIL` for that site (the others keep working); save a
fresh response as its fixture and update the parser in `src/getjob/collectors/`.

Claude Code on the web installs everything automatically at session start
(`.claude/hooks/session-start.sh`).

## Ground rules

- Personal use, low frequency (a couple of runs per day), with a delay between requests to each site.
- LinkedIn is read only through its public job listings; your LinkedIn password is never used.
- The tool finds jobs and drafts the applications; **you** submit them. getjob never logs in
  to a job site or company career page and never submits anything — auto-applying is
  deliberately not included (sites forbid it, and a 5-minute human review is what keeps
  a draft from going out with the wrong company name).
- Drafts contain only facts from your experience bank; everything else is marked for you to check.
