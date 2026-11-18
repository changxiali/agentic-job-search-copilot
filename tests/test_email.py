from pathlib import Path

from job_workflow.email_client import ImapEmailClient, is_job_related, parse_email_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mime_email():
    message = parse_email_bytes((FIXTURES / "interview.eml").read_bytes())
    assert message.message_id == "<interview-demo-001@example-tech.test>"
    assert "面试邀请" in message.subject
    assert "示例科技" in message.body_text
    assert is_job_related(message)


def test_filter_non_job_email():
    message = parse_email_bytes((FIXTURES / "not_job.eml").read_bytes())
    assert not is_job_related(message)


def test_filter_interview_satisfaction_survey():
    message = parse_email_bytes(
        b"From: hr@example.test\r\n"
        b"Subject: Interview survey\r\n"
        b"Message-ID: <survey@example.test>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + "邀请您反馈面试体验".encode()
    )
    assert not is_job_related(message)


def test_netease_imap_id_is_sent_when_supported():
    class FakeClient:
        capabilities = ("IMAP4REV1", "ID")

        def __init__(self):
            self.command = None

        def _simple_command(self, command, payload):
            self.command = (command, payload)
            return "OK", [b"ID completed"]

    client = FakeClient()
    ImapEmailClient._send_client_id(client)
    assert client.command[0] == "ID"
    assert "JobSearchWorkflowV1" in client.command[1]
