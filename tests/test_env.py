import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from getjob.doctor import Doctor
from getjob.profile import SearchProfile, load_profile
from getjob.settings import Settings
from getjob.sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_profile_is_valid():
    profile = load_profile(ROOT / "config" / "search.yaml")
    assert profile.keywords == []
    assert set(profile.sources) == set(SOURCES)
    assert profile.enabled_sources() == list(SOURCES)


def test_profile_rejects_unknown_source():
    with pytest.raises(ValidationError, match="unknown source"):
        SearchProfile.model_validate({"keywords": ["x"], "sources": {"monster": {}}})


def test_profile_rejects_unknown_settings():
    with pytest.raises(ValidationError):
        SearchProfile.model_validate({"keyword": ["typo"]})


def test_empty_env_values_mean_not_set(monkeypatch):
    # GitHub Actions passes unset secrets as empty strings.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GETJOB_REQUEST_DELAY", "0.5")
    settings = Settings(_env_file=None)
    assert settings.telegram_bot_token is None
    assert not settings.telegram_ready
    assert settings.request_delay == 0.5


def test_doctor_offline_passes_with_shipped_profile(tmp_path):
    settings = Settings(
        _env_file=None,
        profile_path=ROOT / "config" / "search.yaml",
        db_path=tmp_path / "data" / "jobs.db",
    )
    out = io.StringIO()
    assert Doctor(settings, out=out).run(offline=True) == 0
    assert "environment ready" in out.getvalue()
    assert (tmp_path / "data").is_dir()


def test_doctor_fails_on_missing_profile(tmp_path):
    settings = Settings(
        _env_file=None, profile_path=tmp_path / "nope.yaml", db_path=tmp_path / "db"
    )
    assert Doctor(settings, out=io.StringIO()).run(offline=True) == 1
