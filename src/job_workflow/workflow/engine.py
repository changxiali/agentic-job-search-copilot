from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from job_workflow.ai import AIProvider
from job_workflow.email_client import is_job_related
from job_workflow.feishu import FeishuClient
from job_workflow.models import MailType, ParsedEmail
from job_workflow.state import StateDatabase

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStats:
    scanned: int = 0
    filtered_out: int = 0
    duplicates: int = 0
    parsed: int = 0
    written: int = 0
    events_created: int = 0
    events_updated: int = 0
    failed: int = 0


class WorkflowEngine:
    def __init__(
        self,
        ai_provider: AIProvider,
        state: StateDatabase,
        feishu: FeishuClient | None,
        dry_run: bool,
    ) -> None:
        self.ai_provider = ai_provider
        self.state = state
        self.feishu = feishu
        self.dry_run = dry_run

    def run(self, messages: list[ParsedEmail]) -> WorkflowStats:
        stats = WorkflowStats(scanned=len(messages))
        for message in messages:
            try:
                self._process_one(message, stats)
            except Exception as exc:  # 单封失败不能阻断整个批次
                stats.failed += 1
                logger.exception("处理邮件失败 message_id=%s", message.message_id)
                if not self.dry_run:
                    self.state.mark_failure(message.message_id, str(exc))
        logger.info("本批次统计：%s", stats)
        return stats

    def _process_one(self, message: ParsedEmail, stats: WorkflowStats) -> None:
        if not is_job_related(message):
            stats.filtered_out += 1
            logger.debug("规则过滤：%s", message.subject)
            return
        if self.state.is_processed(message.message_id):
            stats.duplicates += 1
            logger.info("跳过已处理邮件：%s", message.message_id)
            return

        data = self.ai_provider.parse_email(message)
        if data.type == MailType.APPLICATION and data.application_date is None and message.sent_at:
            data = data.model_copy(update={"application_date": message.sent_at.date()})
        stats.parsed += 1
        application_id = data.application_id(message.message_id)
        logger.info(
            "AI 结果 message_id=%s type=%s company=%s position=%s confidence=%.2f",
            message.message_id,
            data.type.value,
            data.company,
            data.position,
            data.confidence,
        )

        if data.type == MailType.OTHER:
            logger.info("AI 判定为 other，不写飞书：%s", message.subject)
            if not self.dry_run:
                self.state.mark_success(message.message_id, application_id)
            return

        if self.dry_run:
            logger.info("DRY-RUN 将写入 Application：%s", data.model_dump(mode="json"))
            if data.type == MailType.INTERVIEW:
                if _is_future_interview(data.interview_time):
                    logger.info("DRY-RUN 将创建/更新面试日程：%s", data.interview_time.isoformat())
                elif data.interview_time:
                    logger.info(
                        "历史面试只写表，不补建过去日程：%s",
                        data.interview_time.isoformat(),
                    )
                else:
                    logger.warning("识别为面试但没有明确时间，不创建日程")
            return

        if self.feishu is None:
            raise RuntimeError("非 dry-run 模式必须提供 FeishuClient")

        local = self.state.get_application(application_id) or {}
        record_id, existing_record = self.feishu.upsert_application(
            application_id,
            data,
            message,
            known_record_id=_as_string(local.get("feishu_record_id")),
        )
        stats.written += 1

        calendar_event_id = _as_string(local.get("calendar_event_id"))
        if not calendar_event_id and existing_record:
            calendar_event_id = _extract_field_text(
                existing_record.get("fields", {}).get("Calendar Event ID")
            )

        if data.type == MailType.INTERVIEW and _is_future_interview(data.interview_time):
            if calendar_event_id:
                self.feishu.update_calendar_event(calendar_event_id, data, message)
                stats.events_updated += 1
            else:
                calendar_event_id = self.feishu.create_calendar_event(application_id, data, message)
                stats.events_created += 1
            self.feishu.update_record(record_id, {"Calendar Event ID": calendar_event_id})
        elif data.type == MailType.INTERVIEW:
            if data.interview_time:
                logger.info("历史面试只写表，不补建过去日程：%s", data.interview_time.isoformat())
            else:
                logger.warning("识别为面试但没有明确时间，不创建日程：%s", message.subject)

        self.state.upsert_application(application_id, record_id, calendar_event_id)
        self.state.mark_success(message.message_id, application_id)


def _as_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _extract_field_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        text = "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value
        )
        return text or None
    return None


def _is_future_interview(value: datetime | None) -> bool:
    return bool(value and value.astimezone(timezone.utc) > datetime.now(timezone.utc))
