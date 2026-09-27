"""`getjob doctor`: check that this machine (or cloud runner) is ready to search."""

import sys
import time
import unicodedata
from typing import TextIO

import httpx
import yaml
from pydantic import ValidationError

from getjob.apply.config import load_apply_profile, load_experience
from getjob.apply.drafter import claude_available, resolve_engine
from getjob.profile import SearchProfile, load_profile
from getjob.settings import Settings
from getjob.sources import SOURCES

PROBE_ATTEMPTS = 2


def _pad(text: str, width: int) -> str:
    """Left-align `text`, counting Korean (wide) characters as two columns."""
    used = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(width - used, 0)


class Doctor:
    def __init__(self, settings: Settings, out: TextIO = sys.stdout) -> None:
        self.settings = settings
        self.out = out
        self.errors = 0
        self.warnings = 0

    def run(self, offline: bool = False, all_sources: bool = False) -> int:
        self._section("Python")
        self._ok(f"Python {sys.version.split()[0]}")

        profile = self._check_profile()
        self._check_secrets(profile)
        self._check_storage()
        self._check_apply()
        if not offline:
            keys = list(SOURCES) if all_sources or profile is None else profile.enabled_sources()
            self._check_sites(keys)
            self._check_telegram()

        self._section("Result")
        if self.errors:
            self._line("FAIL", f"{self.errors} error(s), {self.warnings} warning(s)")
            return 1
        self._ok(f"environment ready ({self.warnings} warning(s))")
        return 0

    # --- checks ---------------------------------------------------------------

    def _check_profile(self) -> SearchProfile | None:
        path = self.settings.profile_path
        self._section(f"Search profile ({path})")
        try:
            profile = load_profile(path)
        except FileNotFoundError:
            self._fail(f"{path} not found (set GETJOB_PROFILE or create it)")
            return None
        except (ValidationError, ValueError) as e:
            self._fail(f"invalid profile: {e}")
            return None

        districts = ", ".join(profile.location.districts) or "전체"
        self._ok(f"searching: 서울 ({districts}) · 신입 (경력무관 포함) · 정규직")
        self._ok(f"keywords: {', '.join(profile.keywords) or '(none - every posting)'}")
        self._ok(f"newest postings per site per run: {profile.limits.max_per_source}")
        enabled = profile.enabled_sources()
        if enabled:
            self._ok(f"sources: {', '.join(enabled)}")
        else:
            self._fail("no sources enabled in `sources:`")
        return profile

    def _check_secrets(self, profile: SearchProfile | None) -> None:
        s = self.settings
        self._section("Secrets (.env / environment)")
        self._status("TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID", s.telegram_ready)
        self._status("SMTP_USER + SMTP_PASSWORD + NOTIFY_EMAIL_TO", s.email_ready)

        ready = {"telegram": s.telegram_ready, "email": s.email_ready}
        channels = profile.notify.channels if profile else []
        for channel in channels:
            if not ready[channel]:
                self._warn(f"notify channel '{channel}' is selected but its secrets are missing")
        if channels and not any(ready[c] for c in channels):
            self._warn("no notification channel is ready - new jobs will only be printed")

        enabled = set(profile.enabled_sources()) if profile else set()
        for key in sorted(enabled):
            env = SOURCES[key].api_key_env
            if env:
                has_key = getattr(s, env.lower()) is not None
                self._status(f"{env} ({SOURCES[key].name}, optional)", has_key)

    def _check_storage(self) -> None:
        db_dir = self.settings.db_path.parent
        self._section("Storage")
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            probe = db_dir / ".write-test"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            self._fail(f"cannot write to {db_dir}: {e}")
        else:
            self._ok(f"database directory writable: {db_dir}")

    def _check_apply(self) -> None:
        path = self.settings.apply_path
        self._section(f"Application drafts ({path})")
        try:
            profile = load_apply_profile(path)
        except FileNotFoundError:
            self._warn(f"{path} not found - `getjob draft` needs it")
            return
        except (ValidationError, ValueError, yaml.YAMLError) as e:
            self._fail(f"invalid {path}: {e}")
            return
        self._ok(
            f"main pilot: {profile.focus.main or '(not set)'} · "
            f"at most {profile.budget.max_per_week} drafts per week"
        )
        experience = self.settings.experience_path
        if not experience.exists():
            self._warn(
                f"{experience} missing - drafts will be skeletons "
                f"(cp config/experience.example.yaml {experience})"
            )
        else:
            try:
                bank = load_experience(experience)
            except (ValidationError, ValueError, yaml.YAMLError) as e:
                self._fail(f"invalid {experience}: {e}")
            else:
                self._ok(f"experience bank: {len(bank.episodes)} episode(s)")
        key = self.settings.anthropic_key
        self._status(
            "ANTHROPIC_API_KEY + anthropic SDK (Claude drafts, optional)", claude_available(key)
        )
        engine = resolve_engine(profile.drafting.engine, key)
        if engine is None:
            self._fail("drafting.engine is 'claude' but ANTHROPIC_API_KEY or the SDK is missing")
        else:
            self._ok(f"draft engine: {engine}")

    def _check_sites(self, keys: list[str]) -> None:
        self._section("Job sites reachable from this machine")
        reachable = 0
        with self._client() as client:
            for key in keys:
                info = SOURCES[key]
                name = _pad(info.name, 24)
                started = time.monotonic()
                for attempt in range(1, PROBE_ATTEMPTS + 1):
                    try:
                        resp = client.get(info.probe_url)
                        break
                    except httpx.RequestError as e:
                        error = e
                        if attempt < PROBE_ATTEMPTS:
                            time.sleep(self.settings.request_delay)
                else:
                    self._warn(f"{name} unreachable ({type(error).__name__})")
                    continue
                ms = int((time.monotonic() - started) * 1000)
                if resp.status_code < 400:
                    reachable += 1
                    self._ok(f"{name} HTTP {resp.status_code} in {ms} ms")
                elif resp.status_code in (401, 403, 429):
                    self._warn(f"{name} blocked (HTTP {resp.status_code})")
                else:
                    self._warn(f"{name} HTTP {resp.status_code}")
        if keys and reachable == 0:
            self._fail("none of the enabled job sites are reachable")

    def _check_telegram(self) -> None:
        token = self.settings.telegram_bot_token
        if token is None:
            return
        self._section("Telegram bot")
        try:
            with self._client() as client:
                resp = client.get(f"https://api.telegram.org/bot{token.get_secret_value()}/getMe")
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            # Never print the exception text: it can contain the URL with the token.
            self._warn(f"could not reach Telegram ({type(e).__name__})")
            return
        if data.get("ok"):
            self._ok(f"bot token valid: @{data['result'].get('username')}")
        else:
            self._fail("TELEGRAM_BOT_TOKEN was rejected by Telegram")

    # --- output helpers -------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": self.settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9"},
            timeout=self.settings.timeout,
            follow_redirects=True,
        )

    def _section(self, title: str) -> None:
        print(f"\n[{title}]", file=self.out, flush=True)

    def _line(self, tag: str, msg: str) -> None:
        print(f"  {tag:<5} {msg}", file=self.out, flush=True)

    def _ok(self, msg: str) -> None:
        self._line("OK", msg)

    def _warn(self, msg: str) -> None:
        self.warnings += 1
        self._line("WARN", msg)

    def _fail(self, msg: str) -> None:
        self.errors += 1
        self._line("FAIL", msg)

    def _status(self, label: str, present: bool) -> None:
        self._line("OK" if present else "--", f"{label}: {'set' if present else 'not set'}")
