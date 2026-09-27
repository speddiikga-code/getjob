"""Send a message to the channels in `notify.channels` (Telegram, email)."""

import smtplib
from email.message import EmailMessage

import httpx

from getjob.settings import Settings

TELEGRAM_LIMIT = 4096


def send(settings: Settings, channels: list[str], subject: str, text: str) -> list[str]:
    """Send to every ready channel; return one line per problem (empty = all sent)."""
    problems = []
    for channel in channels:
        try:
            if channel == "telegram":
                if not settings.telegram_ready:
                    problems.append("telegram: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
                    continue
                send_telegram(settings, f"{subject}\n\n{text}")
            elif channel == "email":
                if not settings.email_ready:
                    problems.append("email: SMTP_USER / SMTP_PASSWORD / NOTIFY_EMAIL_TO not set")
                    continue
                send_email(settings, subject, text)
        except (httpx.HTTPError, smtplib.SMTPException, OSError) as e:
            # Never include the exception text: the Telegram URL contains the bot token.
            problems.append(f"{channel}: sending failed ({type(e).__name__})")
    return problems


def send_telegram(settings: Settings, text: str) -> None:
    if len(text) > TELEGRAM_LIMIT:
        text = text[: TELEGRAM_LIMIT - 2] + "\n…"
    token = settings.telegram_bot_token.get_secret_value()
    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": True},
        timeout=settings.timeout,
    )
    resp.raise_for_status()


def send_email(settings: Settings, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_email_to
    msg.set_content(text)
    password = settings.smtp_password.get_secret_value()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.login(settings.smtp_user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, password)
            smtp.send_message(msg)
