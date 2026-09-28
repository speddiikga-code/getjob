"""Sending the brief, and the CLI commands around applications — no network."""

import smtplib
import ssl

import httpx

from getjob import cli, notify
from getjob.apply import drafter
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

        def starttls(self, context=None):
            # The server certificate must be verified, or a MITM could read the password.
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
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


def test_email_over_ssl_verifies_the_certificate(tmp_path, monkeypatch):
    seen = {}

    class FakeSSL:
        def __init__(self, host, port, timeout, context):
            seen["context"] = context

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            pass

        def send_message(self, msg):
            seen["sent"] = msg["Subject"]

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    s = settings(
        tmp_path,
        smtp_port=465,
        smtp_user="me@x.com",
        smtp_password="pw",
        notify_email_to="me@x.com",
    )
    assert notify.send(s, ["email"], "subject", "text") == []
    assert seen["sent"] == "subject"
    assert seen["context"].verify_mode == ssl.CERT_REQUIRED and seen["context"].check_hostname


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
    monkeypatch.setattr(drafter, "claude_available", lambda key: False)  # even with a .env key
    assert cli.main(["draft", "--engine", "claude"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_run_sends_the_brief_even_when_drafting_breaks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GETJOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(cli.collect, "run", lambda *a, **kw: 0)

    def broken(args, settings):
        raise RuntimeError("disk full")

    monkeypatch.setattr(cli, "cmd_draft", broken)
    assert cli.main(["run"]) == 1
    captured = capsys.readouterr()
    assert "drafting stopped: RuntimeError: disk full" in captured.err
    assert "Traceback" in captured.err  # unattended runs need the line that broke
    assert "[Brief]" in captured.out and "주 파일럿:" in captured.out


def test_doctor_fails_when_claude_is_required_but_missing(tmp_path, monkeypatch):
    import io

    from getjob.doctor import Doctor

    apply = tmp_path / "apply.yaml"
    apply.write_text("drafting: {engine: claude}\n", encoding="utf-8")
    monkeypatch.setattr("getjob.doctor.claude_available", lambda key: False)
    monkeypatch.setattr(drafter, "claude_available", lambda key: False)
    s = settings(tmp_path, apply_path=apply)
    out = io.StringIO()
    assert Doctor(s, out=out).run(offline=True) == 1
    assert "drafting.engine is 'claude'" in out.getvalue()
