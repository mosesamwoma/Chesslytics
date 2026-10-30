from __future__ import annotations

import base64
import json
import logging
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Optional

from app import settings

logger = logging.getLogger("chesslytics")

SMTP_TIMEOUT_SECONDS = 15
API_TIMEOUT_SECONDS = 20


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(), _NoRedirect())
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
RESEND_URL = "https://api.resend.com/emails"
MAILJET_URL = "https://api.mailjet.com/v3.1/send"
SMTP2GO_URL = "https://api.smtp2go.com/v3/email/send"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
TOKEN_MARGIN_SECONDS = 90
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


def post_raw(url: str, headers: dict[str, str], data: bytes, content_type: str) -> bytes:
    if not url.startswith("https://"):
        raise RuntimeError("mail services must be reached over HTTPS")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "Chesslytics/1.0",
            **headers,
        },
    )
    try:
        with _opener.open(request, timeout=API_TIMEOUT_SECONDS) as response:
            return response.read(65536)
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace")
        raise RuntimeError(f"the mail service answered {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("could not reach the mail service") from exc


def post_json(url: str, headers: dict[str, str], payload: dict) -> bytes:
    return post_raw(url, headers, json.dumps(payload).encode("utf-8"), "application/json")


_gmail_lock = threading.Lock()
_gmail_token: dict = {"value": "", "expires": 0.0}


def gmail_access_token() -> str:
    with _gmail_lock:
        if _gmail_token["value"] and time.time() < _gmail_token["expires"]:
            return str(_gmail_token["value"])
        form = urllib.parse.urlencode(
            {
                "client_id": settings.gmail_client_id(),
                "client_secret": settings.gmail_client_secret(),
                "refresh_token": settings.gmail_refresh_token(),
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        raw = post_raw(GMAIL_TOKEN_URL, {}, form, "application/x-www-form-urlencoded")
        try:
            answer = json.loads(raw.decode("utf-8"))
            token = str(answer["access_token"])
            lifetime = float(answer.get("expires_in", 3000))
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Google did not return an access token") from exc
        _gmail_token["value"] = token
        _gmail_token["expires"] = time.time() + max(60.0, lifetime - TOKEN_MARGIN_SECONDS)
        return token


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.mail_from()
    message["To"] = to
    message["Subject"] = subject
    try:
        message.set_content(body, cte="7bit")
    except ValueError:
        message.set_content(body)
    return message


def deliver_gmail(to: str, subject: str, body: str) -> None:
    message = build_message(to, subject, body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        post_json(
            GMAIL_SEND_URL,
            {"Authorization": f"Bearer {gmail_access_token()}"},
            {"raw": encoded},
        )
    except RuntimeError as exc:
        if " 401" in str(exc):
            with _gmail_lock:
                _gmail_token["value"] = ""
        raise


def deliver_mailjet(to: str, subject: str, body: str) -> None:
    name, address = parseaddr(settings.mail_from())
    if not address:
        raise RuntimeError("MAIL_FROM is not a valid address")
    sender = {"Email": address}
    if name:
        sender["Name"] = name
    credentials = f"{settings.mailjet_api_key()}:{settings.mailjet_secret_key()}"
    token = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    post_json(
        MAILJET_URL,
        {"Authorization": f"Basic {token}"},
        {"Messages": [{"From": sender, "To": [{"Email": to}], "Subject": subject, "TextPart": body}]},
    )


def deliver_smtp2go(to: str, subject: str, body: str) -> None:
    post_json(
        SMTP2GO_URL,
        {"X-Smtp2go-Api-Key": settings.smtp2go_api_key()},
        {"sender": settings.mail_from(), "to": [to], "subject": subject, "text_body": body},
    )


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
    if provider == "gmail":
        deliver_gmail(to, subject, body)
        return
    if provider == "mailjet":
        deliver_mailjet(to, subject, body)
        return
    if provider == "smtp2go":
        deliver_smtp2go(to, subject, body)
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
