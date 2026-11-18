from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ParsedEmail:
    message_id: str
    subject: str
    sender: str
    recipients: str
    sent_at: datetime | None
    body_text: str
    raw_source: str = "imap"
