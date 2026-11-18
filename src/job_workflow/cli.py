from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from job_workflow.ai import MockAIProvider, OpenAICompatibleProvider, StructuredAIClient
from job_workflow.config import Settings
from job_workflow.email_client import ImapEmailClient, parse_email_bytes
from job_workflow.feishu import FeishuClient
from job_workflow.logging_config import configure_logging
from job_workflow.models.v3 import SearchGoal
from job_workflow.state import StateDatabase
from job_workflow.v2 import V2Engine
from job_workflow.v3 import DeepSeekSearchProvider, V3Engine, V3Tables
from job_workflow.workflow import WorkflowEngine

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="网易邮箱 → AI → 飞书求职工作流")
    parser.add_argument("--env-file", default=".env", help="环境变量文件，默认 .env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="运行一次扫描")
    run.add_argument("--dry-run", action="store_true", help="覆盖配置，仅输出动作，不写飞书/状态库")
    run.add_argument("--mock-ai", action="store_true", help="使用离线 Mock AI，不调用外部模型")
    run.add_argument("--fixture", type=Path, help="读取本地 .eml，不连接网易邮箱")

    subparsers.add_parser("self-check", help="检查项目、依赖和配置文件是否可读取")

    profile = subparsers.add_parser("profile", help="V2：把简历结构化为 Candidate Profile")
    profile.add_argument("--input", type=Path, help="简历纯文本/Markdown 文件")
    profile.add_argument("--dry-run", action="store_true")

    enrich = subparsers.add_parser("v2-enrich", help="V2：解析 JD、匹配并按条件生成 Prep")
    enrich.add_argument("--application-id")
    enrich.add_argument("--force", action="store_true", help="忽略内容哈希，强制重算")
    enrich.add_argument("--dry-run", action="store_true")

    review = subparsers.add_parser("v2-review", help="V2：结构化一份面试复盘")
    review.add_argument("--application-id", required=True)
    review.add_argument("--input", type=Path, required=True)
    review.add_argument("--dry-run", action="store_true")

    analytics = subparsers.add_parser("v2-analytics", help="V2：刷新漏斗与分类统计")
    analytics.add_argument("--dry-run", action="store_true")

    goal = subparsers.add_parser("v3-goal", help="V3：从 JSON 新增或更新求职搜索目标")
    goal.add_argument("--input", type=Path, required=True)
    goal.add_argument("--dry-run", action="store_true")
    agent = subparsers.add_parser("v3-run", help="V3：按目标自主搜索、分析、排序并建立审批提案")
    agent.add_argument("--goal-id")
    agent.add_argument("--dry-run", action="store_true", help="只生成安全计划，不联网、不写飞书")
    approval = subparsers.add_parser("v3-approve", help="V3：批准或拒绝一个提案")
    approval.add_argument("--approval-id", required=True)
    approval.add_argument("--decision", choices=["approved", "rejected"], required=True)
    package = subparsers.add_parser("v3-package", help="V3：为已批准线索生成申请材料草案")
    package.add_argument("--lead-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load(args.env_file)
    configure_logging(settings.log_dir, settings.log_level)

    if args.command == "self-check":
        return self_check(settings)

    if args.command in {"profile", "v2-enrich", "v2-review", "v2-analytics"}:
        return run_v2_command(args, settings)

    if args.command.startswith("v3-"):
        return run_v3_command(args, settings)

    dry_run = settings.dry_run or args.dry_run
    try:
        _validate_selected_mode(settings, args.fixture, args.mock_ai, dry_run)
        messages = _load_messages(settings, args.fixture)
        ai_provider = (
            MockAIProvider()
            if args.mock_ai
            else OpenAICompatibleProvider(
                settings.ai_base_url,
                settings.ai_api_key,
                settings.ai_model,
                settings.ai_timeout_seconds,
                settings.ai_temperature,
            )
        )
        feishu = None if dry_run else _build_feishu(settings)
        state = StateDatabase(settings.state_db_path)
        stats = WorkflowEngine(ai_provider, state, feishu, dry_run).run(messages)
        return 1 if stats.failed else 0
    except Exception:
        logger.exception("工作流启动或执行失败")
        return 1


def self_check(settings: Settings) -> int:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.state_db_path.parent.mkdir(parents=True, exist_ok=True)
    StateDatabase(settings.state_db_path)
    print("[OK] Python 模块导入成功")
    print(f"[OK] 状态库可用：{settings.state_db_path.resolve()}")
    print(f"[OK] 日志目录可用：{settings.log_dir.resolve()}")
    print("[INFO] self-check 不会验证真实邮箱、AI 或飞书凭据")
    return 0


def _validate_selected_mode(
    settings: Settings, fixture: Path | None, mock_ai: bool, dry_run: bool
) -> None:
    missing: list[str] = []
    if fixture is None:
        if not settings.email_username:
            missing.append("EMAIL_USERNAME")
        if not settings.email_auth_code or "replace_with" in settings.email_auth_code:
            missing.append("EMAIL_AUTH_CODE")
    if not mock_ai:
        if not settings.ai_api_key or "replace_with" in settings.ai_api_key:
            missing.append("AI_API_KEY")
        if not settings.ai_model or "replace_with" in settings.ai_model:
            missing.append("AI_MODEL")
    if not dry_run:
        feishu_values = {
            "FEISHU_APP_ID": settings.feishu_app_id,
            "FEISHU_APP_SECRET": settings.feishu_app_secret,
            "FEISHU_BITABLE_APP_TOKEN": settings.feishu_bitable_app_token,
            "FEISHU_BITABLE_TABLE_ID": settings.feishu_bitable_table_id,
            "FEISHU_CALENDAR_ID": settings.feishu_calendar_id,
        }
        missing.extend(
            name for name, value in feishu_values.items() if not value or "replace_with" in value
        )
    if missing:
        raise ValueError("当前运行模式缺少配置：" + ", ".join(dict.fromkeys(missing)))


def _load_messages(settings: Settings, fixture: Path | None):
    if fixture:
        return [parse_email_bytes(fixture.read_bytes(), source=str(fixture))]
    return ImapEmailClient(
        settings.email_imap_host,
        settings.email_imap_port,
        settings.email_username,
        settings.email_auth_code,
        settings.email_mailbox,
    ).fetch_recent(settings.email_lookback_days, settings.email_only_unseen)


def _build_feishu(settings: Settings) -> FeishuClient:
    return FeishuClient(
        settings.feishu_base_url,
        settings.feishu_app_id,
        settings.feishu_app_secret,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
        settings.feishu_calendar_id,
        settings.timezone,
        settings.feishu_default_event_duration_minutes,
    )


def _build_v2(settings: Settings) -> V2Engine:
    missing = [
        name
        for name, value in {
            "AI_API_KEY": settings.ai_api_key,
            "AI_MODEL": settings.ai_model,
            "FEISHU_PROFILE_TABLE_ID": settings.feishu_profile_table_id,
            "FEISHU_ANALYTICS_TABLE_ID": settings.feishu_analytics_table_id,
        }.items()
        if not value or "replace_with" in value
    ]
    if missing:
        raise ValueError("V2 缺少配置：" + ", ".join(missing))
    ai = StructuredAIClient(
        settings.ai_base_url,
        settings.ai_api_key,
        settings.ai_model,
        settings.ai_timeout_seconds,
        settings.ai_temperature,
    )
    return V2Engine(
        ai,
        _build_feishu(settings),
        settings.feishu_profile_table_id,
        settings.feishu_analytics_table_id,
        settings.v2_candidate_profile_path,
    )


def run_v2_command(args: argparse.Namespace, settings: Settings) -> int:
    try:
        engine = _build_v2(settings)
        if args.command == "profile":
            input_path = args.input or settings.v2_candidate_input_path
            raw = input_path.read_text(encoding="utf-8").strip()
            if "Candidate Profile 输入模板" in raw or len(raw) < 100:
                raise ValueError(f"请先把真实简历内容写入 {input_path}")
            profile = engine.import_candidate(raw, args.dry_run)
            print(f"Candidate Profile 完成：{profile.profile_summary}")
        elif args.command == "v2-enrich":
            stats = engine.enrich(args.application_id, args.force, args.dry_run)
            print(f"V2 enrich 完成：{stats}")
            return 1 if stats.failed else 0
        elif args.command == "v2-review":
            raw = args.input.read_text(encoding="utf-8").strip()
            review = engine.add_review(args.application_id, raw, args.dry_run)
            print(f"Interview Review 完成：{review.summary}")
        elif args.command == "v2-analytics":
            report = engine.refresh_analytics(settings.v2_analytics_path, args.dry_run)
            print(
                f"Analytics 完成：total={report.total_applications}, "
                f"active={report.active_applications}"
            )
        return 0
    except Exception:
        logger.exception("V2 命令执行失败")
        return 1


def _build_v3(settings: Settings) -> V3Engine:
    table_values = {
        "FEISHU_SEARCH_GOALS_TABLE_ID": settings.feishu_search_goals_table_id,
        "FEISHU_JOB_LEADS_TABLE_ID": settings.feishu_job_leads_table_id,
        "FEISHU_APPROVAL_TABLE_ID": settings.feishu_approval_table_id,
        "FEISHU_AGENT_RUNS_TABLE_ID": settings.feishu_agent_runs_table_id,
        "FEISHU_DECISIONS_TABLE_ID": settings.feishu_decisions_table_id,
        "FEISHU_ARTIFACTS_TABLE_ID": settings.feishu_artifacts_table_id,
    }
    missing = [name for name, value in table_values.items() if not value or "replace_with" in value]
    if not settings.ai_api_key or "replace_with" in settings.ai_api_key:
        missing.append("AI_API_KEY")
    if missing:
        raise ValueError("V3 缺少配置：" + ", ".join(missing))
    ai = StructuredAIClient(
        settings.ai_base_url,
        settings.ai_api_key,
        settings.ai_model,
        settings.ai_timeout_seconds,
        settings.ai_temperature,
    )
    search_base = settings.ai_base_url.removesuffix("/v1")
    search = DeepSeekSearchProvider(settings.ai_api_key, search_base, settings.ai_timeout_seconds)
    return V3Engine(
        ai,
        search,
        _build_feishu(settings),
        V3Tables(
            goals=settings.feishu_search_goals_table_id,
            leads=settings.feishu_job_leads_table_id,
            approvals=settings.feishu_approval_table_id,
            runs=settings.feishu_agent_runs_table_id,
            decisions=settings.feishu_decisions_table_id,
            artifacts=settings.feishu_artifacts_table_id,
        ),
        settings.v2_candidate_profile_path,
    )


def run_v3_command(args: argparse.Namespace, settings: Settings) -> int:
    try:
        engine = _build_v3(settings)
        if args.command == "v3-goal":
            goal = SearchGoal.model_validate_json(args.input.read_text(encoding="utf-8"))
            engine.save_goal(goal, args.dry_run)
            print(f"Search Goal 完成：{goal.goal_id} active={goal.active}")
        elif args.command == "v3-run":
            stats = engine.run(args.goal_id, args.dry_run)
            print(f"V3 Agent 完成：{stats}")
            return 1 if stats.failed else 0
        elif args.command == "v3-approve":
            engine.decide_approval(args.approval_id, args.decision)
            print(f"审批完成：{args.approval_id} -> {args.decision}")
        elif args.command == "v3-package":
            package = engine.create_package(args.lead_id)
            print(f"申请材料草案完成：{package.lead_id}")
        return 0
    except Exception:
        logger.exception("V3 命令执行失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
