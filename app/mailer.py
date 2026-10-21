from __future__ import annotations

import logging
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from typing import Optional

from app import settings

logger = logging.getLogger("chesslytics")

SMTP_TIMEOUT_SECONDS = 15
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


def deliver(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from()
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
