import json
from datetime import datetime, timezone

from job_workflow.models import (
    CandidateProfile,
    InterviewPrep,
    JDProfile,
    MatchAnalysis,
)
from job_workflow.v2.analytics import build_analytics, classify_position
from job_workflow.v2.engine import V2Engine, V2Stats
from job_workflow.v2.utils import content_hash, is_interview_stage


class FakeAI:
    def generate(self, schema, system_prompt, user_prompt):
        if schema is JDProfile:
            return JDProfile(
                title="AI 产品经理",
                company="示例科技",
                responsibilities=["负责 AI 产品规划"],
                must_have=["数据分析"],
                nice_to_have=[],
                skills=["SQL"],
                keywords=["AI", "SQL"],
                requirements=[],
                role_summary="负责 AI 产品",
                confidence=0.9,
            )
        if schema is MatchAnalysis:
            return MatchAnalysis(
                overall_score=80,
                strengths=["有数据分析经验"],
                gaps=["缺少行业经验"],
                missing_keywords=[],
                interview_focus=["产品规划"],
                recommended_stories=["分析项目"],
                evidence_mapping=[],
                summary="整体匹配",
                caveats=[],
            )
        if schema is InterviewPrep:
            return InterviewPrep(
                application_id="APP-TEST",
                role_summary="AI 产品",
                role_priorities=["产品规划"],
                likely_questions=[],
                resume_mapping=["数据分析项目"],
                star_story_prompts=[],
                technical_review=["SQL"],
                case_practice=[],
                questions_to_ask=[],
                checklist=["检查设备"],
                caveats=[],
                generated_at=datetime.now(timezone.utc),
            )
        raise AssertionError(schema)


class FakeFeishu:
    def __init__(self, records):
        self.records = records
        self.updates = []

    def list_records(self):
        return self.records

    def update_record(self, record_id, fields):
        self.updates.append((record_id, fields))


def _profile():
    return CandidateProfile(
        name="测试候选人",
        education=[],
        experiences=["数据分析实习"],
        projects=["SQL 分析项目"],
        skills=["SQL"],
        languages=[],
        certifications=[],
        preferences=[],
        evidence_index=[],
        profile_summary="具备数据分析经验",
        confidence=0.9,
    )


def test_v2_deterministic_trigger_and_hash(tmp_path):
    profile_path = tmp_path / "candidate.json"
    profile_path.write_text(
        json.dumps(_profile().model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    records = [
        {
            "record_id": "rec1",
            "fields": {
                "Application ID": "APP-TEST",
                "Company": "示例科技",
                "Position": "AI 产品经理",
                "Current Stage": "一面",
                "JD Raw": "负责 AI 产品规划，需要 SQL 和数据分析能力。",
            },
        }
    ]
    feishu = FakeFeishu(records)
    engine = V2Engine(FakeAI(), feishu, "profile", "analytics", profile_path)
    stats = engine.enrich()
    assert stats == V2Stats(scanned=1, jd_parsed=1, matched=1, prep_generated=1, updated=1)
    updated = feishu.updates[0][1]
    assert updated["Match Score"] == 80
    assert updated["Prep Status"] == "Generated"
    assert "面试准备" in updated["Interview Prep"]
    assert len(updated["JD Hash"]) == 64


def test_analytics_and_position_classification():
    records = [
        {"fields": {"Current Stage": "已投递", "Company": "A", "Position": "AI 产品经理"}},
        {
            "fields": {
                "Current Stage": "一面",
                "Company": "B",
                "Position": "数据分析实习生",
                "Interview Time": 1,
            }
        },
        {"fields": {"Current Stage": "拒绝", "Company": "A", "Position": "后端工程师"}},
    ]
    report = build_analytics(records)
    assert report.total_applications == 3
    assert report.active_applications == 2
    assert report.funnel_rates["application_to_interview"] == 0.3333
    assert classify_position("AI 产品经理") == "AI/算法"


def test_v2_helpers_are_deterministic():
    assert content_hash("a", {"b": 1}) == content_hash("a", {"b": 1})
    assert is_interview_stage("HR面")
    assert not is_interview_stage("已投递")
