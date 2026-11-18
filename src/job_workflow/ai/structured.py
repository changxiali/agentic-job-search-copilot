from __future__ import annotations

import json
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from job_workflow.ai.openai_compatible import AIProviderError, _strip_code_fence

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredAIClient:
    """V2 通用结构化生成器；只生成 schema，不决定调用哪个能力。"""

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
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def generate(self, schema: type[ModelT], system_prompt: str, user_prompt: str) -> ModelT:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n只输出 JSON，不输出 Markdown。"
                        f"输出必须严格符合以下 JSON Schema：{schema_json}"
                    ),
                },
                {"role": "user", "content": user_prompt},
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
            return schema.model_validate(json.loads(_strip_code_fence(content)))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise AIProviderError(f"结构化输出未通过 {schema.__name__} 校验：{exc}") from exc
