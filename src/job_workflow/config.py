from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    app_env: str
    dry_run: bool
    log_level: str
    timezone: str
    state_db_path: Path
    log_dir: Path
    email_imap_host: str
    email_imap_port: int
    email_username: str
    email_auth_code: str
    email_mailbox: str
    email_lookback_days: int
    email_only_unseen: bool
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: int
    ai_temperature: float
    feishu_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_bitable_app_token: str
    feishu_bitable_table_id: str
    feishu_profile_table_id: str
    feishu_analytics_table_id: str
    feishu_search_goals_table_id: str
    feishu_job_leads_table_id: str
    feishu_approval_table_id: str
    feishu_agent_runs_table_id: str
    feishu_decisions_table_id: str
    feishu_artifacts_table_id: str
    feishu_calendar_id: str
    feishu_default_event_duration_minutes: int
    v2_candidate_input_path: Path
    v2_candidate_profile_path: Path
    v2_analytics_path: Path

    @classmethod
    def load(cls, env_file: str | Path | None = None) -> Settings:
        load_dotenv(dotenv_path=env_file, override=False)
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            dry_run=_bool("DRY_RUN", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
            state_db_path=Path(os.getenv("STATE_DB_PATH", "data/state.db")),
            log_dir=Path(os.getenv("LOG_DIR", "data/logs")),
            email_imap_host=os.getenv("EMAIL_IMAP_HOST", "imap.163.com"),
            email_imap_port=_int("EMAIL_IMAP_PORT", 993),
            email_username=os.getenv("EMAIL_USERNAME", ""),
            email_auth_code=os.getenv("EMAIL_AUTH_CODE", ""),
            email_mailbox=os.getenv("EMAIL_MAILBOX", "INBOX"),
            email_lookback_days=_int("EMAIL_LOOKBACK_DAYS", 7),
            email_only_unseen=_bool("EMAIL_ONLY_UNSEEN", False),
            ai_base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            ai_api_key=os.getenv("AI_API_KEY", ""),
            ai_model=os.getenv("AI_MODEL", ""),
            ai_timeout_seconds=_int("AI_TIMEOUT_SECONDS", 60),
            ai_temperature=_float("AI_TEMPERATURE", 0.0),
            feishu_base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn/open-apis").rstrip(
                "/"
            ),
            feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            feishu_bitable_app_token=os.getenv("FEISHU_BITABLE_APP_TOKEN", ""),
            feishu_bitable_table_id=os.getenv("FEISHU_BITABLE_TABLE_ID", ""),
            feishu_profile_table_id=os.getenv("FEISHU_PROFILE_TABLE_ID", ""),
            feishu_analytics_table_id=os.getenv("FEISHU_ANALYTICS_TABLE_ID", ""),
            feishu_search_goals_table_id=os.getenv("FEISHU_SEARCH_GOALS_TABLE_ID", ""),
            feishu_job_leads_table_id=os.getenv("FEISHU_JOB_LEADS_TABLE_ID", ""),
            feishu_approval_table_id=os.getenv("FEISHU_APPROVAL_TABLE_ID", ""),
            feishu_agent_runs_table_id=os.getenv("FEISHU_AGENT_RUNS_TABLE_ID", ""),
            feishu_decisions_table_id=os.getenv("FEISHU_DECISIONS_TABLE_ID", ""),
            feishu_artifacts_table_id=os.getenv("FEISHU_ARTIFACTS_TABLE_ID", ""),
            feishu_calendar_id=os.getenv("FEISHU_CALENDAR_ID", ""),
            feishu_default_event_duration_minutes=_int("FEISHU_DEFAULT_EVENT_DURATION_MINUTES", 60),
            v2_candidate_input_path=Path(
                os.getenv("V2_CANDIDATE_INPUT_PATH", "data/candidate_profile_input.md")
            ),
            v2_candidate_profile_path=Path(
                os.getenv("V2_CANDIDATE_PROFILE_PATH", "data/candidate_profile.json")
            ),
            v2_analytics_path=Path(os.getenv("V2_ANALYTICS_PATH", "data/analytics.json")),
        )

    def validate_for_live_run(self) -> None:
        required = {
            "EMAIL_USERNAME": self.email_username,
            "EMAIL_AUTH_CODE": self.email_auth_code,
            "AI_API_KEY": self.ai_api_key,
            "AI_MODEL": self.ai_model,
            "FEISHU_APP_ID": self.feishu_app_id,
            "FEISHU_APP_SECRET": self.feishu_app_secret,
            "FEISHU_BITABLE_APP_TOKEN": self.feishu_bitable_app_token,
            "FEISHU_BITABLE_TABLE_ID": self.feishu_bitable_table_id,
            "FEISHU_CALENDAR_ID": self.feishu_calendar_id,
        }
        missing = [name for name, value in required.items() if not value or "replace_with" in value]
        if missing:
            raise ValueError("真实运行缺少配置：" + ", ".join(missing))
