from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = dotenv_values(PROJECT / ".env")
BASE_URL = str(CONFIG.get("FEISHU_BASE_URL") or "https://open.feishu.cn/open-apis").rstrip("/")
APP_TOKEN = str(CONFIG.get("FEISHU_BITABLE_APP_TOKEN") or "")


APPLICATION_FIELDS = [
    ("JD Raw", 1),
    ("JD Structured JSON", 1),
    ("JD Hash", 1),
    ("Match Analysis JSON", 1),
    ("Match Hash", 1),
    ("Match Score", 2),
    ("Strengths", 1),
    ("Gaps", 1),
    ("Interview Focus", 1),
    ("Interview Prep", 1),
    ("Prep Hash", 1),
    ("Prep Status", 1),
    ("Interview Review Raw", 1),
    ("Interview Review JSON", 1),
    ("Review Hash", 1),
    ("V2 Last Processed", 5),
]

PROFILE_FIELDS = [
    {"field_name": "Profile ID", "type": 1},
    {"field_name": "Profile Summary", "type": 1},
    {"field_name": "Profile JSON", "type": 1},
    {"field_name": "Profile Hash", "type": 1},
    {"field_name": "Updated At", "type": 5},
]

ANALYTICS_FIELDS = [
    {"field_name": "Metric ID", "type": 1},
    {"field_name": "Metric", "type": 1},
    {"field_name": "Dimension", "type": 1},
    {"field_name": "Value", "type": 2},
    {"field_name": "Generated At", "type": 5},
]


def checked(response: requests.Response, action: str) -> dict[str, Any]:
    payload = response.json()
    if not response.ok or payload.get("code", 0) != 0:
        raise RuntimeError(
            f"{action}失败 HTTP={response.status_code} code={payload.get('code')} "
            f"msg={payload.get('msg')}"
        )
    return payload


def main() -> int:
    session = requests.Session()
    token_data = checked(
        session.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": CONFIG.get("FEISHU_APP_ID"),
                "app_secret": CONFIG.get("FEISHU_APP_SECRET"),
            },
            timeout=30,
        ),
        "获取 token",
    )
    headers = {
        "Authorization": f"Bearer {token_data['tenant_access_token']}",
        "Content-Type": "application/json",
    }
    application_table_id = str(CONFIG.get("FEISHU_BITABLE_TABLE_ID") or "")
    ensure_fields(session, headers, application_table_id, APPLICATION_FIELDS)
    profile_table_id = ensure_table(session, headers, "Candidate Profile", PROFILE_FIELDS)
    analytics_table_id = ensure_table(session, headers, "Analytics", ANALYTICS_FIELDS)
    print(f"PROFILE_TABLE_ID={profile_table_id}")
    print(f"ANALYTICS_TABLE_ID={analytics_table_id}")
    print(f"APPLICATION_V2_FIELDS={len(APPLICATION_FIELDS)}")
    return 0


def list_tables(session: requests.Session, headers: dict[str, str]) -> list[dict[str, Any]]:
    path = f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables"
    return (
        checked(
            session.get(path, headers=headers, params={"page_size": 100}, timeout=30),
            "列出数据表",
        )
        .get("data", {})
        .get("items", [])
    )


def ensure_table(
    session: requests.Session,
    headers: dict[str, str],
    name: str,
    fields: list[dict[str, Any]],
) -> str:
    existing = next(
        (item for item in list_tables(session, headers) if item.get("name") == name),
        None,
    )
    if existing:
        table_id = existing["table_id"]
        ensure_fields(
            session,
            headers,
            table_id,
            [(item["field_name"], item["type"]) for item in fields],
        )
        return table_id
    path = f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables"
    payload = checked(
        session.post(
            path,
            headers=headers,
            json={
                "table": {
                    "name": name,
                    "default_view_name": "全部",
                    "fields": fields,
                }
            },
            timeout=30,
        ),
        f"创建数据表 {name}",
    )
    return payload["data"]["table_id"]


def ensure_fields(
    session: requests.Session,
    headers: dict[str, str],
    table_id: str,
    fields: list[tuple[str, int]],
) -> None:
    path = (
        f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables/"
        f"{quote(table_id, safe='')}/fields"
    )
    current = (
        checked(
            session.get(path, headers=headers, params={"page_size": 100}, timeout=30),
            "列出字段",
        )
        .get("data", {})
        .get("items", [])
    )
    current_names = {item.get("field_name") for item in current}
    for field_name, field_type in fields:
        if field_name in current_names:
            continue
        checked(
            session.post(
                path,
                headers=headers,
                json={"field_name": field_name, "type": field_type},
                timeout=30,
            ),
            f"创建字段 {field_name}",
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PROVISION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc
