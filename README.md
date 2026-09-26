# getjob — 서울 정규직 자동 채용 검색

Automatically searches LinkedIn and Korean job sites for **regular full-time (정규직)
jobs in Seoul**, filters them by your conditions, and sends new postings to you
(Telegram / email). It runs in the cloud on a schedule, so you don't have to check every site yourself.

## Status

| Step | What | State |
|------|------|-------|
| 1 | Environment: project, config, secrets, cloud check, CI | ✅ done |
| 2 | Site collectors (LinkedIn, 잡코리아, 사람인, 원티드, …) + de-duplication | next |
| 3 | Notifications + schedule (08:00 / 18:00 KST on GitHub Actions) | planned |

## Supported sites

| Key | Site | Default | Notes |
|-----|------|---------|-------|
| `linkedin` | LinkedIn | on | public guest listings only, no login |
| `jobkorea` | 잡코리아 | on | |
| `saramin` | 사람인 | on | official Open API if `SARAMIN_API_KEY` is set |
| `wanted` | 원티드 | on | |
| `incruit` | 인크루트 | on | |
| `work24` | 고용24 (구 워크넷) | on | government board; Open API with `WORK24_API_KEY` |
| `remember` | 리멤버 커리어 | on | |
| `jumpit` | 점핏 | off | IT/developer jobs only |
| `peoplenjob` | 피플앤잡 | off | foreign companies in Korea |
| `alio` | 잡알리오 | off | public institutions (공공기관) |

잡플래닛, 캐치 and 로켓펀치 block automated access (HTTP 403), so they are not included.

## Quick start (local)

Requires Python 3.11+.

```bash
./scripts/setup.sh              # creates .venv, installs, creates .env, runs an offline check
source .venv/bin/activate
getjob doctor                   # full check, including whether each job site is reachable
```

Then edit two files:

- **`config/search.yaml`** — what you're looking for: keywords (직무), districts (구),
  experience, minimum salary, excluded companies, which sites to use.
  The keywords shipped (`백엔드`, `backend`) are only an example — replace them with your role.
- **`.env`** — secrets (Telegram bot, Gmail app password, optional API keys).
  See `.env.example` for how to get each one. `.env` is git-ignored; never commit it.

## Cloud (GitHub Actions)

1. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**, add
   the values you use from `.env.example` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, …).
2. **Actions → Cloud environment check → Run workflow.** It runs `getjob doctor` on
   GitHub's servers and shows whether each Korean site is reachable from there.

Some Korean sites block foreign (non-Korean) IP addresses. If the cloud check shows a site
as blocked, run the Docker image on a small VM in a Korean region instead:

```bash
docker build -t getjob .
docker run --rm --env-file .env -v "$PWD/data:/app/data" getjob doctor
```

## Development

```bash
ruff check . && ruff format --check .
pytest -q
```

Claude Code on the web installs everything automatically at session start
(`.claude/hooks/session-start.sh`).

## Ground rules

- Personal use, low frequency (a couple of runs per day), with delays between requests.
- LinkedIn is read only through its public job listings; your LinkedIn password is never used.
- The tool finds and sends jobs to you; **you** apply. Auto-applying is deliberately not included.
