"""Optional email delivery of the digest over SMTP (standard library only).

A hallmark of the paid news-digest services is "delivered to your inbox".
OpenBioNews does the same, self-hosted: point it at any SMTP server (your own,
Gmail with an app password, Fastmail, a work relay…). The password is read from
an environment variable and never written to the config file.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from .models import Digest


class EmailError(Exception):
    """Raised when the digest email cannot be sent."""


def is_configured(email_cfg: dict) -> bool:
    return bool(
        email_cfg.get("enabled")
        and email_cfg.get("smtp_host")
        and email_cfg.get("from_addr")
        and email_cfg.get("to_addrs")
    )


def build_message(digest: Digest, html_body: str, text_body: str, email_cfg: dict) -> EmailMessage:
    msg = EmailMessage()
    date = digest.generated_at.strftime("%d %b %Y")
    msg["Subject"] = f"{digest.title} — {date}"
    msg["From"] = email_cfg["from_addr"]
    msg["To"] = ", ".join(email_cfg["to_addrs"])
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_digest(digest: Digest, html_body: str, text_body: str, email_cfg: dict) -> str:
    """Send the digest. Returns a status string. Raises EmailError on failure."""
    if not is_configured(email_cfg):
        raise EmailError("email is not fully configured (host/from/to and enabled)")

    password = ""
    env = email_cfg.get("password_env", "")
    if env:
        password = os.environ.get(env, "")

    msg = build_message(digest, html_body, text_body, email_cfg)
    host = email_cfg["smtp_host"]
    port = int(email_cfg.get("smtp_port", 587))
    username = email_cfg.get("username", "")

    try:
        if email_cfg.get("use_tls", True):
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls(context=context)
                if username:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                if username:
                    server.login(username, password)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(str(exc)) from exc

    return f"sent to {', '.join(email_cfg['to_addrs'])}"
