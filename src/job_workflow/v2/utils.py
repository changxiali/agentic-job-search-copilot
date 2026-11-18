from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(*values: Any) -> str:
    payload = "\n".join(
        stable_json(value) if not isinstance(value, str) else value for value in values
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def field_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in value
        )
    return str(value) if value is not None else ""


def is_interview_stage(stage: str) -> bool:
    normalized = stage.strip().lower()
    terms = ("interview", "面试", "一面", "二面", "三面", "hr面", "终面")
    return any(term in normalized for term in terms)
