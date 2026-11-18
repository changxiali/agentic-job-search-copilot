from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from job_workflow.models.v3 import AgentPlan, JobLead, PlanStep, SearchGoal, SourceEvidence
from job_workflow.v3.engine import V3Engine, canonical_url
from job_workflow.v3.planner import SafePlanner


def goal() -> SearchGoal:
    return SearchGoal(
        goal_id="ai-intern",
        title="AI 产品实习",
        role_keywords=["AI 产品经理"],
        locations=["上海"],
        active=True,
    )


def lead(url: str, score: float) -> JobLead:
    return JobLead(
        lead_id=url,
        goal_id="ai-intern",
        source_url=url,
        canonical_url=canonical_url(url),
        position="AI Product",
        source=SourceEvidence(url=url, title="AI Product", rerank_score=score),
    )


def test_safe_plan_contains_no_external_action_tools():
    plan = SafePlanner().create_plan(goal())
    names = {step.tool.value for step in plan.steps}
    assert "submit_application" not in names
    assert "send_message" not in names
    assert "search_jobs" in names


def test_plan_schema_rejects_unknown_tool():
    with pytest.raises(ValidationError):
        AgentPlan(
            goal_id="x",
            objective="x",
            steps=[PlanStep(order=1, tool="submit_application", reason="unsafe")],
        )


def test_canonical_url_removes_tracking_and_fragment():
    value = canonical_url("HTTPS://Example.com/jobs/1/?utm_source=x&ref=abc#apply")
    assert value == "https://example.com/jobs/1?ref=abc"


def test_deduplication_keeps_best_source():
    first = lead("https://example.com/jobs/1?utm_source=a", 1.0)
    second = lead("https://example.com/jobs/1", 2.5)
    unique = V3Engine._deduplicate([first, second])
    assert len(unique) == 1
    assert unique[0].source.rerank_score == 2.5


def test_recent_data_model_accepts_timestamps():
    item = lead("https://example.com/jobs/2", 2.0).model_copy(
        update={"published_at": datetime.now(timezone.utc)}
    )
    assert item.published_at is not None
