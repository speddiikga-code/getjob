"""Sending the brief, and the CLI commands around applications — no network."""

import smtplib

import httpx

from getjob import cli, notify
from getjob.settings import Settings


def settings(tmp_path, **kw) -> Settings:
    return Settings(_env_file=None, db_path=tmp_path / "jobs.db", **kw)


def test_channels_without_secrets_are_reported_not_raised(tmp_path):
    problems = notify.send(settings(tmp_path), ["telegram", "email"], "s", "t")
    assert problems == [
        "telegram: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set",
        "email: SMTP_USER / SMTP_PASSWORD / NOTIFY_EMAIL_TO not set",
    ]


def test_telegram_message_and_failures_never_leak_the_token(tmp_path, monkeypatch):
    sent = {}

    def post(url, json, timeout):
        sent.update(url=url, json=json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(notify.httpx, "post", post)
    s = settings(tmp_path, telegram_bot_token="123:SECRET", telegram_chat_id="42")
    assert notify.send(s, ["telegram"], "[getjob] 9/28", "x" * 5000) == []
    assert sent["url"] == "https://api.telegram.org/bot123:SECRET/sendMessage"
    assert sent["json"]["chat_id"] == "42"
    assert sent["json"]["text"].startswith("[getjob] 9/28\n\nxxx")
    assert len(sent["json"]["text"]) <= notify.TELEGRAM_LIMIT

    def fail(url, json, timeout):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(notify.httpx, "post", fail)
    (problem,) = notify.send(s, ["telegram"], "s", "t")
    assert problem == "telegram: sending failed (ConnectError)"
    assert "SECRET" not in problem


def test_email(tmp_path, monkeypatch):
    log = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            log.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            log.append(("starttls",))

        def login(self, user, password):
            log.append(("login", user, password))

        def send_message(self, msg):
            log.append(("send", msg["Subject"], msg["To"], msg.get_content().strip()))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    s = settings(
        tmp_path, smtp_user="me@gmail.com", smtp_password="app-pw", notify_email_to="me@gmail.com"
    )
    assert notify.send(s, ["email"], "[getjob] 9/28 제출 대기 1건", "본문") == []
    assert log == [
        ("connect", "smtp.gmail.com", 587),
        ("starttls",),
        ("login", "me@gmail.com", "app-pw"),
        ("send", "[getjob] 9/28 제출 대기 1건", "me@gmail.com", "본문"),
    ]


def test_cli_apps_mark_and_brief(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GETJOB_DB_PATH", str(tmp_path / "jobs.db"))
    assert cli.main(["apps"]) == 0
    assert "[Applications: 0]" in capsys.readouterr().out
    assert cli.main(["mark", "3", "submitted"]) == 1
    assert "No application with id 3" in capsys.readouterr().err
    assert cli.main(["brief"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("[getjob] ") and "주 파일럿: 경희대 한의학과" in out


def test_cli_draft_refuses_the_claude_engine_without_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GETJOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["draft", "--engine", "claude"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
