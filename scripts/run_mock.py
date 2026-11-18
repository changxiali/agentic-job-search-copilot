"""一条命令运行离线样例；不读取 .env 中的任何真实密钥。"""

from pathlib import Path

from job_workflow.ai import MockAIProvider
from job_workflow.email_client import parse_email_bytes
from job_workflow.logging_config import configure_logging
from job_workflow.state import StateDatabase
from job_workflow.workflow import WorkflowEngine


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    configure_logging(project_root / "data" / "logs", "INFO")
    message = parse_email_bytes(
        (project_root / "tests" / "fixtures" / "interview.eml").read_bytes(),
        source="offline-fixture",
    )
    state = StateDatabase(project_root / "data" / "mock_state.db")
    stats = WorkflowEngine(MockAIProvider(), state, None, dry_run=True).run([message])
    print(stats)


if __name__ == "__main__":
    main()
