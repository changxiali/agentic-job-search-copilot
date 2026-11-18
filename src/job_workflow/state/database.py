from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class StateDatabase:
    """本地幂等状态。SQLite 单文件便于备份，不保存邮箱或飞书密码。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_emails (
                    message_id TEXT PRIMARY KEY,
                    application_id TEXT,
                    status TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS applications (
                    application_id TEXT PRIMARY KEY,
                    feishu_record_id TEXT,
                    calendar_event_id TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def is_processed(self, message_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_emails WHERE message_id = ? AND status = 'success'",
                (message_id,),
            ).fetchone()
        return row is not None

    def mark_success(self, message_id: str, application_id: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO processed_emails(message_id, application_id, status, processed_at)
                   VALUES (?, ?, 'success', ?)
                   ON CONFLICT(message_id) DO UPDATE SET
                     application_id=excluded.application_id,
                     status='success', processed_at=excluded.processed_at, error_message=NULL""",
                (message_id, application_id, now),
            )

    def mark_failure(self, message_id: str, error_message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO processed_emails(message_id, status, processed_at, error_message)
                   VALUES (?, 'failed', ?, ?)
                   ON CONFLICT(message_id) DO UPDATE SET
                     status='failed', processed_at=excluded.processed_at,
                     error_message=excluded.error_message""",
                (message_id, now, error_message[:2000]),
            )

    def get_application(self, application_id: str) -> dict[str, str | None] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE application_id = ?", (application_id,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_application(
        self,
        application_id: str,
        feishu_record_id: str | None,
        calendar_event_id: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO applications(
                       application_id, feishu_record_id, calendar_event_id, updated_at
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(application_id) DO UPDATE SET
                     feishu_record_id=COALESCE(
                         excluded.feishu_record_id, applications.feishu_record_id
                     ),
                     calendar_event_id=COALESCE(
                         excluded.calendar_event_id, applications.calendar_event_id
                     ),
                     updated_at=excluded.updated_at""",
                (application_id, feishu_record_id, calendar_event_id, now),
            )
