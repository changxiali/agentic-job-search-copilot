from __future__ import annotations

from typing import Protocol

from job_workflow.models import ApplicationData, ParsedEmail


class AIProvider(Protocol):
    def parse_email(self, message: ParsedEmail) -> ApplicationData:
        """把邮件转换为经过 schema 校验的结构化数据。"""
        ...
