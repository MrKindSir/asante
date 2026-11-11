"""Admin notification helpers for Asante human-review events."""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("asante.notify")

DEFAULT_ADMIN_EMAILS = ("vmafunisa@outlook.com",)


def admin_notify_emails() -> list[str]:
    raw = (os.environ.get("ASANTE_ADMIN_NOTIFY_EMAILS") or ",".join(DEFAULT_ADMIN_EMAILS)).strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def _smtp_settings() -> dict[str, str | int | bool] | None:
    host = (os.environ.get("ASANTE_SMTP_HOST") or "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("ASANTE_SMTP_PORT") or "587"),
        "user": (os.environ.get("ASANTE_SMTP_USER") or "").strip(),
        "password": (os.environ.get("ASANTE_SMTP_PASSWORD") or "").strip(),
        "from_addr": (os.environ.get("ASANTE_SMTP_FROM") or os.environ.get("ASANTE_SMTP_USER") or "asante-noreply@localhost").strip(),
        "use_tls": (os.environ.get("ASANTE_SMTP_TLS") or "true").strip().lower() not in {"0", "false", "no"},
    }


def _write_outbox(subject: str, body: str, recipients: list[str]) -> Path:
    root = Path(os.environ.get("ASANTE_NOTIFY_OUTBOX") or "/tmp/asante-notify-outbox")
    root.mkdir(parents=True, exist_ok=True)
    stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"notify-{stamp}.eml"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "asante-local@localhost"
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    path.write_text(message.as_string(), encoding="utf-8")
    return path


def send_admin_email(subject: str, body: str) -> dict[str, str | bool]:
    """Send an admin email when SMTP is configured; always keep a local outbox copy."""
    recipients = admin_notify_emails()
    if not recipients:
        return {"sent": False, "reason": "no_recipients"}
    outbox = _write_outbox(subject, body, recipients)
    settings = _smtp_settings()
    if not settings:
        logger.warning("ASANTE_SMTP_HOST is not set; saved notification to %s", outbox)
        return {"sent": False, "reason": "smtp_not_configured", "outbox": str(outbox)}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = str(settings["from_addr"])
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    try:
        if settings["use_tls"]:
            context = ssl.create_default_context()
            with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=20) as smtp:
                smtp.starttls(context=context)
                if settings["user"]:
                    smtp.login(str(settings["user"]), str(settings["password"]))
                smtp.send_message(message)
        else:
            with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=20) as smtp:
                if settings["user"]:
                    smtp.login(str(settings["user"]), str(settings["password"]))
                smtp.send_message(message)
        logger.info("Admin notification emailed to %s", recipients)
        return {"sent": True, "outbox": str(outbox), "recipients": ",".join(recipients)}
    except Exception as error:
        logger.exception("Failed to email admin notification")
        return {"sent": False, "reason": error.__class__.__name__, "outbox": str(outbox)}


def notify_submission_for_review(packet: dict) -> dict[str, str | bool]:
    title = str(packet.get("title") or "Untitled story")
    contributor = str(packet.get("contributor_name") or "Contributor")
    submission_id = str(packet.get("submission_id") or packet.get("id") or "")
    language = str(packet.get("language") or "")
    media_format = str(packet.get("media_format") or "")
    subject = f"[Asante] Review needed: {title}"
    body = (
        "A contributor submitted a story packet for human review.\n\n"
        f"Title: {title}\n"
        f"Contributor: {contributor}\n"
        f"Language: {language}\n"
        f"Media: {media_format}\n"
        f"Submission: {submission_id}\n"
        f"Status: {packet.get('status') or 'pending_review'}\n\n"
        "Open the Asante review desk:\n"
        "http://localhost/asante/portal/\n"
        "or\n"
        "http://localhost/asante/review/\n\n"
        "Nothing was published automatically. A human decision is still required.\n"
    )
    return send_admin_email(subject, body)
