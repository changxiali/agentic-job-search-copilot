from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import dotenv_values, set_key

PROJECT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT / ".env"
CONFIG = dotenv_values(ENV_PATH)
BASE_URL = str(CONFIG.get("FEISHU_BASE_URL") or "https://open.feishu.cn/open-apis").rstrip("/")
APP_TOKEN = str(CONFIG.get("FEISHU_BITABLE_APP_TOKEN") or "")

TABLES = {
    "FEISHU_SEARCH_GOALS_TABLE_ID": (
        "Search Goals",
        [
            ("Goal ID", 1),
            ("Title", 1),
            ("Goal JSON", 1),
            ("Active", 1),
            ("Cadence", 1),
            ("Updated At", 5),
        ],
    ),
    "FEISHU_JOB_LEADS_TABLE_ID": (
        "Job Leads",
        [
            ("Lead ID", 1),
            ("Goal ID", 1),
            ("Company", 1),
            ("Position", 1),
            ("Location", 1),
            ("Source URL", 15),
            ("Published At", 5),
            ("JD Raw", 1),
            ("JD JSON", 1),
            ("Match JSON", 1),
            ("Match Score", 2),
            ("Recommendation", 1),
            ("Reason", 1),
            ("Risk Flags", 1),
            ("Approval Status", 1),
            ("Discovered At", 5),
        ],
    ),
    "FEISHU_APPROVAL_TABLE_ID": (
        "Approval Queue",
        [
            ("Approval ID", 1),
            ("Lead ID", 1),
            ("Goal ID", 1),
            ("Action Type", 1),
            ("Status", 1),
            ("Summary", 1),
            ("Payload JSON", 1),
            ("Created At", 5),
            ("Decided At", 5),
        ],
    ),
    "FEISHU_AGENT_RUNS_TABLE_ID": (
        "Agent Runs",
        [
            ("Run ID", 1),
            ("Goal ID", 1),
            ("Status", 1),
            ("Plan JSON", 1),
            ("Stats JSON", 1),
            ("Updated At", 5),
        ],
    ),
    "FEISHU_DECISIONS_TABLE_ID": (
        "Decision Logs",
        [
            ("Decision ID", 1),
            ("Run ID", 1),
            ("Lead ID", 1),
            ("Decision", 1),
            ("Reason", 1),
            ("Evidence URL", 15),
            ("Created At", 5),
        ],
    ),
    "FEISHU_ARTIFACTS_TABLE_ID": (
        "Generated Artifacts",
        [
            ("Artifact ID", 1),
            ("Lead ID", 1),
            ("Type", 1),
            ("Content", 1),
            ("Status", 1),
            ("Created At", 5),
        ],
    ),
}


def checked(response: requests.Response, action: str) -> dict[str, Any]:
    payload = response.json()
    if not response.ok or payload.get("code", 0) != 0:
        raise RuntimeError(
            f"{action}失败 HTTP={response.status_code} "
            f"code={payload.get('code')} msg={payload.get('msg')}"
        )
    return payload


def list_tables(session: requests.Session, headers: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables"
    return (
        checked(
            session.get(url, headers=headers, params={"page_size": 100}, timeout=30), "列出数据表"
        )
        .get("data", {})
        .get("items", [])
    )


def ensure_fields(
    session: requests.Session, headers: dict[str, str], table_id: str, fields: list[tuple[str, int]]
) -> None:
    url = (
        f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables/"
        f"{quote(table_id, safe='')}/fields"
    )
    current = (
        checked(
            session.get(url, headers=headers, params={"page_size": 100}, timeout=30), "列出字段"
        )
        .get("data", {})
        .get("items", [])
    )
    names = {item.get("field_name") for item in current}
    for name, kind in fields:
        if name not in names:
            checked(
                session.post(
                    url, headers=headers, json={"field_name": name, "type": kind}, timeout=30
                ),
                f"创建字段 {name}",
            )


def ensure_table(
    session: requests.Session, headers: dict[str, str], name: str, fields: list[tuple[str, int]]
) -> str:
    existing = next(
        (item for item in list_tables(session, headers) if item.get("name") == name), None
    )
    if existing:
        table_id = existing["table_id"]
        ensure_fields(session, headers, table_id, fields)
        return table_id
    url = f"{BASE_URL}/bitable/v1/apps/{quote(APP_TOKEN, safe='')}/tables"
    payload = checked(
        session.post(
            url,
            headers=headers,
            json={
                "table": {
                    "name": name,
                    "default_view_name": "全部",
                    "fields": [{"field_name": field, "type": kind} for field, kind in fields],
                }
            },
            timeout=30,
        ),
        f"创建数据表 {name}",
    )
    return payload["data"]["table_id"]


def main() -> int:
    session = requests.Session()
    token = checked(
        session.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": CONFIG.get("FEISHU_APP_ID"),
                "app_secret": CONFIG.get("FEISHU_APP_SECRET"),
            },
            timeout=30,
        ),
        "获取 token",
    )["tenant_access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for env_name, (table_name, fields) in TABLES.items():
        table_id = ensure_table(session, headers, table_name, fields)
        set_key(str(ENV_PATH), env_name, table_id, quote_mode="never")
        print(f"{table_name}={table_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PROVISION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc
