from __future__ import annotations

import json
import logging
import re
import smtplib
import ssl
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Optional

from app import settings

logger = logging.getLogger("chesslytics")

SMTP_TIMEOUT_SECONDS = 15
API_TIMEOUT_SECONDS = 20
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
RESEND_URL = "https://api.resend.com/emails"
MAX_EMAIL_LENGTH = 254
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def email_error(value: str) -> Optional[str]:
    text = value.strip()
    if not text:
        return "enter an email address"
    if len(text) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(text):
        return "that does not look like a valid email address"
    return None


def post_json(url: str, headers: dict[str, str], payload: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Chesslytics/1.0",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            response.read(65536)
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace")
        raise RuntimeError(f"the mail service answered {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("could not reach the mail service") from exc


def deliver_brevo(to: str, subject: str, body: str) -> None:
    name, address = parseaddr(settings.mail_from())
    if not address:
        raise RuntimeError("MAIL_FROM is not a valid address")
    sender = {"email": address}
    if name:
        sender["name"] = name
    post_json(
        BREVO_URL,
        {"api-key": settings.brevo_api_key()},
        {"sender": sender, "to": [{"email": to}], "subject": subject, "textContent": body},
    )


def deliver_resend(to: str, subject: str, body: str) -> None:
    post_json(
        RESEND_URL,
        {"Authorization": f"Bearer {settings.resend_api_key()}"},
        {"from": settings.mail_from(), "to": [to], "subject": subject, "text": body},
    )


def deliver(to: str, subject: str, body: str) -> None:
    provider = settings.mail_provider()
    if provider == "brevo":
        deliver_brevo(to, subject, body)
        return
    if provider == "resend":
        deliver_resend(to, subject, body)
        return
    deliver_smtp(to, subject, body)


def deliver_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    security = settings.smtp_security()
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(
            settings.smtp_host(),
            settings.smtp_port(),
            timeout=SMTP_TIMEOUT_SECONDS,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            settings.smtp_host(), settings.smtp_port(), timeout=SMTP_TIMEOUT_SECONDS
        )
    with client:
        if security == "starttls":
            client.starttls(context=context)
        if settings.smtp_user():
            client.login(settings.smtp_user(), settings.smtp_password())
        client.send_message(message)


def _send_safely(to: str, subject: str, body: str) -> None:
    try:
        deliver(to, subject, body)
    except Exception:
        domain = to.rsplit("@", 1)[-1]
        logger.exception("could not send email to a %s address", domain)


def send_async(to: str, subject: str, body: str) -> None:
    thread = threading.Thread(
        target=_send_safely, args=(to, subject, body), name="mailer", daemon=True
    )
    thread.start()


def verification_message(link: str) -> tuple[str, str]:
    return (
        "Confirm your email address for Chesslytics",
        "Confirm this email address for your Chesslytics account by opening the link "
        "below. It works once and expires in 24 hours.\n\n"
        f"{link}\n\n"
        "If you did not ask for this, you can ignore this message.\n",
    )


def reset_message(link: str) -> tuple[str, str]:
    return (
        "Reset your Chesslytics password",
        "Someone asked to reset the password for a Chesslytics account that uses this "
        "address. Open the link below to choose a new password. It works once and "
        "expires in 1 hour.\n\n"
        f"{link}\n\n"
        "If you did not ask for this, you can ignore this message; your password has "
        "not changed.\n",
    )
