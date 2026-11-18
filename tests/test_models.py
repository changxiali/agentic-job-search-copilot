from datetime import datetime

import pytest
from pydantic import ValidationError

from job_workflow.models import ApplicationData


def test_schema_accepts_valid_interview():
    value = ApplicationData.model_validate(
        {
            "type": "interview",
            "company": "示例科技",
            "position": "AI 产品经理",
            "stage": "一面",
            "application_date": "2026-11-01",
            "interview_time": "2026-11-20T14:00:00+08:00",
            "location": "线上",
            "meeting_link": None,
            "contact_name": None,
            "contact_email": "hr@example.test",
            "confidence": 0.96,
        }
    )
    assert isinstance(value.interview_time, datetime)
    assert value.type.value == "interview"


def test_schema_rejects_extra_field_and_bad_confidence():
    with pytest.raises(ValidationError):
        ApplicationData.model_validate(
            {
                "type": "interview",
                "company": None,
                "position": None,
                "stage": None,
                "application_date": None,
                "interview_time": None,
                "location": None,
                "meeting_link": None,
                "contact_name": None,
                "contact_email": None,
                "confidence": 1.5,
                "invented": "not allowed",
            }
        )


def test_application_id_is_stable():
    data = ApplicationData(
        type="application", company="示例科技", position="AI 产品经理", confidence=1
    )
    assert data.application_id("<a>") == data.application_id("<b>")


def test_unknown_position_does_not_merge_different_emails():
    data = ApplicationData(type="application", company="字节跳动", position=None, confidence=1)
    assert data.application_id("<a>") != data.application_id("<b>")


def test_interview_time_requires_timezone():
    with pytest.raises(ValidationError):
        ApplicationData(type="interview", interview_time="2026-11-20T14:00:00", confidence=1)
