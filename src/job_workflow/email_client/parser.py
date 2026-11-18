from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from job_workflow.models import ParsedEmail


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError):
        return value


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p>", "\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"[ \t]+", " ", html.unescape(value)).strip()


def parse_email_bytes(raw: bytes, source: str = "imap") -> ParsedEmail:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    text_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if content_type == "text/plain":
            text_parts.append(str(content))
        else:
            html_parts.append(str(content))

    body = "\n".join(text_parts).strip()
    if not body:
        body = _html_to_text("\n".join(html_parts))

    sent_at: datetime | None = None
    if message.get("Date"):
        try:
            sent_at = parsedate_to_datetime(message["Date"])
        except (TypeError, ValueError, OverflowError):
            pass

    message_id = (message.get("Message-ID") or "").strip()
    if not message_id:
        basis = raw[:4096] + str(len(raw)).encode("ascii")
        message_id = f"<generated-{hashlib.sha256(basis).hexdigest()}@local>"

    return ParsedEmail(
        message_id=message_id,
        subject=_decode_header(message.get("Subject")),
        sender=_decode_header(message.get("From")),
        recipients=_decode_header(message.get("To")),
        sent_at=sent_at,
        body_text=body,
        raw_source=source,
    )
