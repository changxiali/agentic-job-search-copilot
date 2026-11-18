from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MailType(str, Enum):
    APPLICATION = "application"
    INTERVIEW = "interview"
    WRITTEN_TEST = "written_test"
    REJECTION = "rejection"
    OFFER = "offer"
    OTHER = "other"


class ApplicationData(BaseModel):
    """AI 的唯一合法输出结构。extra=forbid 可阻止模型偷偷增加未定义字段。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: MailType
    company: Optional[str] = None
    position: Optional[str] = None
    stage: Optional[str] = None
    application_date: Optional[date] = None
    interview_time: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("meeting_link")
    @classmethod
    def empty_link_to_none(cls, value: Optional[str]) -> Optional[str]:
        return value or None

    @field_validator("interview_time")
    @classmethod
    def interview_time_requires_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("interview_time 必须包含时区")
        return value

    def application_id(self, message_id: str) -> str:
        company = _slug(self.company or "unknown")
        position = _slug(self.position or "unknown")
        if company != "unknown" and position != "unknown":
            raw = f"{company}|{position}"
        else:
            raw = message_id
        digest = hashlib.sha256(raw.lower().encode("utf-8")).hexdigest()[:16]
        return f"APP-{digest.upper()}"


def _slug(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip().lower())
    return re.sub(r"[^\w\u4e00-\u9fff-]", "", normalized) or "unknown"
