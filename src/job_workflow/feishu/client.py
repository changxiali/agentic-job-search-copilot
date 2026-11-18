from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from job_workflow.models import ApplicationData, ParsedEmail

logger = logging.getLogger(__name__)


class FeishuError(RuntimeError):
    pass


class FeishuClient:
    def __init__(
        self,
        base_url: str,
        app_id: str,
        app_secret: str,
        bitable_app_token: str,
        bitable_table_id: str,
        calendar_id: str,
        timezone_name: str = "Asia/Shanghai",
        default_event_duration_minutes: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.bitable_app_token = bitable_app_token
        self.bitable_table_id = bitable_table_id
        self.calendar_id = calendar_id
        self.timezone_name = timezone_name
        self.default_event_duration_minutes = default_event_duration_minutes
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_expires_at = 0.0

    def get_tenant_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        response = self.session.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise FeishuError(f"获取 tenant_access_token 失败：{payload.get('msg', payload)}")
        self._token = payload["tenant_access_token"]
        self._token_expires_at = time.time() + int(payload.get("expire", 7200))
        return self._token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.get_tenant_access_token()}"
        headers["Content-Type"] = "application/json; charset=utf-8"
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=30, **kwargs
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise FeishuError(f"飞书 API 失败 code={payload.get('code')} msg={payload.get('msg')}")
        return payload

    def list_records(self) -> list[dict[str, Any]]:
        return self.list_table_records(self.bitable_table_id)

    def list_table_records(self, table_id: str) -> list[dict[str, Any]]:
        path = (
            f"/bitable/v1/apps/{quote(self.bitable_app_token, safe='')}/tables/"
            f"{quote(table_id, safe='')}/records"
        )
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params).get("data", {})
            records.extend(data.get("items", []))
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")

    def find_record_by_application_id(self, application_id: str) -> dict[str, Any] | None:
        for record in self.list_records():
            if _field_text(record.get("fields", {}).get("Application ID")) == application_id:
                return record
        return None

    def create_record(self, fields: dict[str, Any]) -> str:
        return self.create_table_record(self.bitable_table_id, fields)

    def create_table_record(self, table_id: str, fields: dict[str, Any]) -> str:
        path = (
            f"/bitable/v1/apps/{quote(self.bitable_app_token, safe='')}/tables/"
            f"{quote(table_id, safe='')}/records"
        )
        payload = self._request("POST", path, json={"fields": fields})
        return payload["data"]["record"]["record_id"]

    def update_record(self, record_id: str, fields: dict[str, Any]) -> None:
        self.update_table_record(self.bitable_table_id, record_id, fields)

    def update_table_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        path = (
            f"/bitable/v1/apps/{quote(self.bitable_app_token, safe='')}/tables/"
            f"{quote(table_id, safe='')}/records/{quote(record_id, safe='')}"
        )
        self._request("PUT", path, json={"fields": fields})

    def find_table_record(
        self, table_id: str, field_name: str, expected: str
    ) -> dict[str, Any] | None:
        for record in self.list_table_records(table_id):
            if _field_text(record.get("fields", {}).get(field_name)) == expected:
                return record
        return None

    def upsert_table_record(
        self,
        table_id: str,
        key_field: str,
        key_value: str,
        fields: dict[str, Any],
    ) -> str:
        existing = self.find_table_record(table_id, key_field, key_value)
        if existing:
            self.update_table_record(table_id, existing["record_id"], fields)
            return existing["record_id"]
        return self.create_table_record(table_id, fields)

    def upsert_application(
        self,
        application_id: str,
        data: ApplicationData,
        message: ParsedEmail,
        known_record_id: str | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        existing = None
        if known_record_id:
            existing = {"record_id": known_record_id, "fields": {}}
        else:
            existing = self.find_record_by_application_id(application_id)
        fields = application_to_fields(application_id, data, message)
        if existing:
            self.update_record(existing["record_id"], fields)
            return existing["record_id"], existing
        return self.create_record(fields), None

    def create_calendar_event(
        self, application_id: str, data: ApplicationData, message: ParsedEmail
    ) -> str:
        if data.interview_time is None:
            raise ValueError("创建面试日程必须提供 interview_time")
        path = f"/calendar/v4/calendars/{quote(self.calendar_id, safe='')}/events"
        payload = self._event_payload(data, message)
        response = self._request(
            "POST",
            path,
            params={"idempotency_key": application_id[:50]},
            json=payload,
        )
        return response["data"]["event"]["event_id"]

    def update_calendar_event(
        self, event_id: str, data: ApplicationData, message: ParsedEmail
    ) -> None:
        if data.interview_time is None:
            raise ValueError("更新面试日程必须提供 interview_time")
        path = (
            f"/calendar/v4/calendars/{quote(self.calendar_id, safe='')}/events/"
            f"{quote(event_id, safe='')}"
        )
        self._request("PATCH", path, json=self._event_payload(data, message))

    def _event_payload(self, data: ApplicationData, message: ParsedEmail) -> dict[str, Any]:
        assert data.interview_time is not None
        start = data.interview_time
        end = start + timedelta(minutes=self.default_event_duration_minutes)
        description_lines = [
            f"岗位：{data.position or '未知'}",
            f"阶段：{data.stage or '面试'}",
            f"地点：{data.location or '待确认'}",
            f"会议链接：{data.meeting_link or '无'}",
            f"联系人：{data.contact_name or '未知'} {data.contact_email or ''}".strip(),
            f"来源邮件：{message.subject}",
        ]
        return {
            "summary": f"面试｜{data.company or '未知公司'}｜{data.position or '未知岗位'}",
            "description": "\n".join(description_lines),
            "start_time": {
                "timestamp": str(int(start.timestamp())),
                "timezone": self.timezone_name,
            },
            "end_time": {"timestamp": str(int(end.timestamp())), "timezone": self.timezone_name},
            "visibility": "default",
            "need_notification": False,
        }


def application_to_fields(
    application_id: str, data: ApplicationData, message: ParsedEmail
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "Application ID": application_id,
        "Company": data.company or "未知",
        "Position": data.position or "未知",
        "Current Stage": data.stage or data.type.value,
        "Mail Type": data.type.value,
        "Email Subject": message.subject,
        "Email Message ID": message.message_id,
        "Source Email Sender": message.sender,
        "AI Confidence": data.confidence,
        "Last Updated": int(datetime.now().timestamp() * 1000),
    }
    optional = {
        "Application Date": _date_to_millis(data.application_date),
        "Interview Time": _datetime_to_millis(data.interview_time),
        "Location": data.location,
        "Meeting Link": data.meeting_link,
        "Contact Name": data.contact_name,
        "Contact Email": data.contact_email,
    }
    fields.update({key: value for key, value in optional.items() if value is not None})
    return fields


def _date_to_millis(value: Any) -> int | None:
    if value is None:
        return None
    dt = datetime.combine(value, datetime.min.time())
    return int(dt.timestamp() * 1000)


def _datetime_to_millis(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1000) if value else None


def _field_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in value
        )
    return str(value) if value is not None else ""
