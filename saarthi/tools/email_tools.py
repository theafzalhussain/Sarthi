"""
Email tools — JARVIS se mail padhna aur bhejna.

DESIGN — ZERO naya dependency:

    Python stdlib mein hi IMAP (imaplib) aur SMTP (smtplib) hain.
    Gmail/Outlook/Yahoo sab kaam karte hain — App Password ke saath
    (normal password nahi chalta, 2FA wale account mein App Password
    milta hai: Google Account -> Security -> App passwords).

CONFIG (~/.saarthi/.env):

    EMAIL_ADDRESS=ravi@gmail.com
    EMAIL_PASSWORD=abcd efgh ijkl mnop     # App Password (16 char)
    EMAIL_IMAP_HOST=imap.gmail.com         # khud guess bhi karta hai
    EMAIL_SMTP_HOST=smtp.gmail.com

SECURITY (repo ke rules):

    - mail_padho / mail_dhoondho  -> SAFE (sirf padhna)
    - mail_bhejo                  -> RISKY (confirmation lena zaroori —
      ghalat banda ghalat mail nahi jaana chahiye)
    - Password sirf .env se — code/log/repo mein kabhi nahi

PURE LOGIC alag hain (testable, network ke bina):
    guess_mail_hosts(), format_mail_list(), extract_text_body(),
    build_search_criteria()
"""

from __future__ import annotations

import email as email_lib
import email.header
import email.utils
import imaplib
import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Any

from .base import Tool, ToolContext
from ..devices.base import ActionResult

log = logging.getLogger("saarthi.tools.email")


# ======================================================================
#  Pure logic — network ke bina test hota hai
# ======================================================================

# Domain -> (imap_host, smtp_host)
_KNOWN_MAIL_HOSTS: dict[str, tuple[str, str]] = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "googlemail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "outlook.com": ("outlook.office365.com", "smtp.office365.com"),
    "hotmail.com": ("outlook.office365.com", "smtp.office365.com"),
    "live.com": ("outlook.office365.com", "smtp.office365.com"),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"),
    "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com"),
    "rediffmail.com": ("imap.rediffmail.com", "smtp.rediffmail.com"),
    "zoho.com": ("imap.zoho.com", "smtp.zoho.com"),
}


def guess_mail_hosts(address: str) -> tuple[str, str]:
    """
    Email address se (imap_host, smtp_host) guess karo.

    >>> guess_mail_hosts("ravi@gmail.com")
    ('imap.gmail.com', 'smtp.gmail.com')
    """
    domain = address.rsplit("@", 1)[-1].strip().lower()
    return _KNOWN_MAIL_HOSTS.get(domain, ("", ""))


def _decode_header_value(raw: str | None) -> str:
    """RFC2047-encoded header ko insani text mein kholo."""
    if not raw:
        return ""
    try:
        parts = email.header.decode_header(raw)
        out: list[str] = []
        for text, charset in parts:
            if isinstance(text, bytes):
                out.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(text)
        return " ".join(out)
    except Exception:  # noqa: BLE001
        return raw or ""


def extract_text_body(msg: email_lib.message.Message, max_chars: int = 600) -> str:
    """
    Email message se plain-text body nikaalo (multipart handle karta hai).

    HTML-only mail se bhi kachra-free text deta hai (tags hatao nahi,
    text/plain part dhoondhte hain).
    """
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")[:max_chars].strip()
                except Exception:  # noqa: BLE001
                    continue
        # text/plain nahi mila — pehla part try karo
        for part in msg.walk():
            if part.get_content_type().startswith("text/"):
                try:
                    payload = part.get_payload(decode=True) or b""
                    return payload.decode("utf-8", errors="replace")[:max_chars].strip()
                except Exception:  # noqa: BLE001
                    continue
        return ""

    try:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")[:max_chars].strip()
    except Exception:  # noqa: BLE001
        return str(msg.get_payload())[:max_chars]


class MailSummary:
    """Ek email ki chhoti summary (display + LLM ke liye)."""

    def __init__(self, index: int, sender: str, subject: str, date: str, body: str, unread: bool):
        self.index = index
        self.sender = sender
        self.subject = subject
        self.date = date
        self.body = body
        self.unread = unread

    def to_line(self) -> str:
        flag = "🔵 " if self.unread else "   "
        body_preview = self.body[:120].replace("\n", " ") if self.body else ""
        line = f"{flag}[{self.index}] {self.sender}: {self.subject} ({self.date})"
        if body_preview:
            line += f"\n       {body_preview}"
        return line


def format_mail_list(mails: list[MailSummary]) -> str:
    """
    Emails ki readable list (PURE LOGIC — tested).

    >>> format_mail_list([])
    'Koi mail nahi mila.'
    """
    if not mails:
        return "Koi mail nahi mila."
    return "\n".join(m.to_line() for m in mails)


def build_search_criteria(query: str) -> str:
    """
    User query ko IMAP SEARCH criteria banao (PURE LOGIC — tested).

    Simple heuristics: "from:xyz" -> FROM "xyz", warna TEXT.
    >>> build_search_criteria("from:rahul")
    'FROM \\"rahul\\"'
    """
    q = (query or "").strip()
    if not q:
        return "ALL"

    lowered = q.lower()
    for prefix, field in (("from:", "FROM"), ("subject:", "SUBJECT")):
        if lowered.startswith(prefix):
            term = q[len(prefix) :].strip().strip('"')
            return f'{field} "{term}"'

    return f'TEXT "{q}"'


def _mail_config() -> dict[str, str]:
    """Env se mail config (hosts khud guess karta hai)."""
    address = os.getenv("EMAIL_ADDRESS", "").strip()
    imap_host = os.getenv("EMAIL_IMAP_HOST", "").strip()
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "").strip()

    if address and (not imap_host or not smtp_host):
        g_imap, g_smtp = guess_mail_hosts(address)
        imap_host = imap_host or g_imap
        smtp_host = smtp_host or g_smtp

    return {
        "address": address,
        "password": os.getenv("EMAIL_PASSWORD", "").strip(),
        "imap_host": imap_host,
        "smtp_host": smtp_host,
        "imap_port": int(os.getenv("EMAIL_IMAP_PORT", "993") or "993"),
        "smtp_port": int(os.getenv("EMAIL_SMTP_PORT", "587") or "587"),
    }


def is_mail_configured() -> bool:
    cfg = _mail_config()
    return bool(cfg["address"] and cfg["password"] and cfg["imap_host"])


def mail_setup_help() -> str:
    return (
        "Email setup adhoora hai. ~/.saarthi/.env mein daalo:\n"
        "  EMAIL_ADDRESS=tu@gmail.com\n"
        "  EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # App Password (normal nahi chalega)\n"
        "  Gmail App Password: Google Account -> Security -> 2-Step Verification -> App passwords\n"
        "  (IMAP/SMTP hosts khud guess ho jaate hain; alag ho to EMAIL_IMAP_HOST/EMAIL_SMTP_HOST)"
    )


# ======================================================================
#  Blocking I/O — threads mein chalenge
# ======================================================================


def _fetch_mails(
    cfg: dict[str, str],
    folder: str,
    limit: int,
    unread_only: bool,
    criteria: str,
) -> list[MailSummary]:
    """IMAP se mails uthao (BLOCKING — asyncio.to_thread se chalao)."""
    conn: imaplib.IMAP4_SSL | None = None
    try:
        ctx = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], ssl_context=ctx)
        conn.login(cfg["address"], cfg["password"])
        conn.select(folder, readonly=True)

        if criteria and criteria != "ALL":
            status, data = conn.search(None, criteria)
        elif unread_only:
            status, data = conn.search(None, "UNSEEN")
        else:
            status, data = conn.search(None, "ALL")

        if status != "OK" or not data or not data[0]:
            return []

        ids = data[0].split()
        latest = ids[-limit:]  # sabse naye pehle
        latest.reverse()

        mails: list[MailSummary] = []
        for i, mail_id in enumerate(latest, start=1):
            status, msg_data = conn.fetch(mail_id, "(RFC822 FLAGS)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue

            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            flags = msg_data[0][0].decode("utf-8", "ignore") if isinstance(msg_data[0], tuple) else ""
            msg = email_lib.message_from_bytes(raw)

            sender = _decode_header_value(msg.get("From", ""))
            # Sirf naam/email saaf karo
            sender = email.utils.parseaddr(sender)[1] or sender

            mails.append(
                MailSummary(
                    index=i,
                    sender=sender,
                    subject=_decode_header_value(msg.get("Subject", "")) or "(no subject)",
                    date=(msg.get("Date") or "")[:22],
                    body=extract_text_body(msg),
                    unread="\\Unseen" in flags,
                )
            )
        return mails

    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass


def _send_mail(cfg: dict[str, str], to: str, subject: str, body: str) -> None:
    """SMTP se mail bhejo (BLOCKING — asyncio.to_thread se chalao)."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = cfg["address"]
    msg["To"] = to
    msg["Subject"] = subject

    ctx = ssl.create_default_context()
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(cfg["address"], cfg["password"])
        server.sendmail(cfg["address"], [to], msg.as_string())


# ======================================================================
#  Tools
# ======================================================================


class MailPadhoTool(Tool):
    """Recent/unread emails padho — SAFE (sirf dekhna)."""

    name = "mail_padho"
    description = (
        "Read recent or unread emails from the configured mailbox. "
        "Use for: 'mere mails dikhao', 'koi naya mail aaya kya'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "unread_only": {
                "type": "boolean",
                "description": "Sirf unread dikhao (default false = last mails)",
            },
            "limit": {
                "type": "integer",
                "description": "Kitne mails (default 5, max 15)",
            },
        },
        "properties_required": [],
    }

    async def run(
        self, ctx: ToolContext, unread_only: bool = False, limit: int = 5
    ) -> ActionResult:
        if not is_mail_configured():
            return ActionResult.failure(mail_setup_help())

        limit = max(1, min(int(limit or 5), 15))
        cfg = _mail_config()

        try:
            mails = await asyncio.to_thread(
                _fetch_mails, cfg, "INBOX", limit, bool(unread_only), "ALL"
            )
        except imaplib.IMAP4.error as exc:
            return ActionResult.failure(
                f"Login fail — App Password sahi hai? ({exc})"
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Mail nahi mile: {exc}")

        header = (
            f"{len(mails)} unread mails:"
            if unread_only
            else f"Last {len(mails)} mails:"
        )
        return ActionResult.success(header + "\n" + format_mail_list(mails))


class MailDhoondhoTool(Tool):
    """Mailbox mein search karo — from/subject/text."""

    name = "mail_dhoondho"
    description = (
        "Search emails. Query like 'from:rahul', 'subject:invoice', "
        "or plain text. Use for: 'rahul ka mail dhundo'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "from:xyz / subject:abc / plain text",
            },
            "limit": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str, limit: int = 5) -> ActionResult:
        if not is_mail_configured():
            return ActionResult.failure(mail_setup_help())

        limit = max(1, min(int(limit or 5), 15))
        cfg = _mail_config()
        criteria = build_search_criteria(query)

        try:
            mails = await asyncio.to_thread(
                _fetch_mails, cfg, "INBOX", limit, False, criteria
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Search fail: {exc}")

        return ActionResult.success(
            f'"{query}" ke {len(mails)} mails:\n' + format_mail_list(mails)
        )


class MailBhejoTool(Tool):
    """Email bhejo — RISKY: confirmation ke bina ek line bhi nahi jaati."""

    name = "mail_bhejo"
    description = (
        "Send an email from the user's mailbox. RISKY — user confirmation "
        "will be asked. Use for: 'rahul ko mail kar de ki meeting 5 baje hai'."
    )
    risky = True

    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Receiver ki email address"},
            "subject": {"type": "string", "description": "Subject line"},
            "body": {"type": "string", "description": "Email ka text (plain)"},
        },
        "required": ["to", "subject", "body"],
    }

    async def run(self, ctx: ToolContext, to: str, subject: str, body: str) -> ActionResult:
        if not is_mail_configured():
            return ActionResult.failure(mail_setup_help())

        # SMTP host chahiye — config check
        cfg = _mail_config()
        if not cfg["smtp_host"]:
            return ActionResult.failure(
                f"SMTP host nahi mila '{to}' ke domain se — EMAIL_SMTP_HOST set karo"
            )

        # RISKY — confirmation lo (fail-safe default: nahi)
        ok = await ctx.ask_confirmation(
            f"Email bhejna hai {to} ko",
            {"subject": subject, "body_preview": body[:120]},
        )
        if not ok:
            return ActionResult.success("Theek hai, mail bheja NAHI.")

        try:
            await asyncio.to_thread(_send_mail, cfg, to.strip(), subject.strip(), body)
        except smtplib.SMTPAuthenticationError:
            return ActionResult.failure("Login fail — App Password check karo")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Mail nahi gaya: {exc}")

        return ActionResult.success(f"Mail bhej diya ✅ -> {to} | Subject: {subject}")


def email_tools() -> list[Tool]:
    """Saare email tools."""
    return [MailPadhoTool(), MailDhoondhoTool(), MailBhejoTool()]


# asyncio import neeche rakha (module-level circular se bachne ke liye nahi —
# bas consistency: tools ise run() ke andar use karte hain)
import asyncio  # noqa: E402
