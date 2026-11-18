from pathlib import Path

from job_workflow.ai import MockAIProvider
from job_workflow.email_client import parse_email_bytes
from job_workflow.state import StateDatabase
from job_workflow.workflow import WorkflowEngine

FIXTURE = Path(__file__).parent / "fixtures" / "interview.eml"


class FakeFeishu:
    def __init__(self):
        self.records = {}
        self.events = {}

    def upsert_application(self, application_id, data, message, known_record_id=None):
        record_id = known_record_id or "rec_mock_001"
        self.records[record_id] = {"application_id": application_id, "data": data}
        return record_id, None

    def create_calendar_event(self, application_id, data, message):
        self.events["evt_mock_001"] = data.interview_time
        return "evt_mock_001"

    def update_calendar_event(self, event_id, data, message):
        self.events[event_id] = data.interview_time

    def update_record(self, record_id, fields):
        self.records[record_id].update(fields)


def test_live_like_run_and_local_idempotency(tmp_path):
    message = parse_email_bytes(FIXTURE.read_bytes())
    state = StateDatabase(tmp_path / "state.db")
    feishu = FakeFeishu()
    engine = WorkflowEngine(MockAIProvider(), state, feishu, dry_run=False)

    first = engine.run([message])
    second = engine.run([message])

    assert first.written == 1
    assert first.events_created == 1
    assert second.duplicates == 1
    assert len(feishu.records) == 1
    assert len(feishu.events) == 1


def test_dry_run_does_not_persist(tmp_path):
    message = parse_email_bytes(FIXTURE.read_bytes())
    state = StateDatabase(tmp_path / "state.db")
    engine = WorkflowEngine(MockAIProvider(), state, None, dry_run=True)
    stats = engine.run([message])
    assert stats.parsed == 1
    assert not state.is_processed(message.message_id)
