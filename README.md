# getjob — 서울 신입 정규직 자동 채용 검색

Automatically collects **entry-level (신입, incl. 경력무관) regular full-time (정규직) jobs
in Seoul** from LinkedIn and 9 Korean job sites, removes postings you've already seen
(and the same job listed on several sites), and reports only the new ones.

## Status

| Step | What | State |
|------|------|-------|
| 1 | Environment: project, config, secrets, cloud check, CI | ✅ done |
| 2 | Site collectors for all 10 sites + de-duplication + CSV export | ✅ done |
| 3 | Notifications (Telegram / email) + schedule (e.g. 08:00 / 18:00 KST) | next |

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
- The tool finds jobs for you; **you** apply. Auto-applying is deliberately not included.
