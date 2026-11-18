from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from job_workflow.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from job_workflow.models import ApplicationData, ParsedEmail

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        temperature: float = 0.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.session = session or requests.Session()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.RequestException, AIProviderError)),
        reraise=True,
    )
    def parse_email(self, message: ParsedEmail) -> ApplicationData:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        message.subject,
                        message.sender,
                        message.sent_at.isoformat() if message.sent_at else "未知",
                        message.body_text,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(_strip_code_fence(content))
            return ApplicationData.model_validate(data)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            logger.error("AI 响应未通过 schema 校验：%s", exc)
            raise AIProviderError(f"AI 输出无效：{exc}") from exc


def _strip_code_fence(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else value
