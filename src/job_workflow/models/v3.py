from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class V3Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchGoal(V3Model):
    goal_id: str = Field(min_length=3, max_length=80)
    title: str
    role_keywords: list[str] = Field(min_length=1)
    locations: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    published_within_days: int = Field(default=7, ge=1, le=90)
    max_results_per_query: int = Field(default=10, ge=1, le=50)
    active: bool = False
    cadence: Literal["manual", "daily", "weekly"] = "manual"
    notes: Optional[str] = None


class SourceEvidence(V3Model):
    url: HttpUrl
    title: str
    snippet: str = ""
    site_name: Optional[str] = None
    published_at: Optional[datetime] = None
    authority: int = Field(default=-1, ge=-1, le=4)
    rerank_score: float = Field(default=0, ge=0, le=3)


class Recommendation(str, Enum):
    strong = "strong_recommend"
    consider = "consider"
    skip = "skip"
    needs_review = "needs_review"


class JobLead(V3Model):
    lead_id: str
    goal_id: str
    source_url: HttpUrl
    canonical_url: str
    company: str = "待解析"
    position: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    published_at: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: SourceEvidence
    jd_raw: str = ""
    jd_json: Optional[str] = None
    match_json: Optional[str] = None
    match_score: Optional[int] = Field(default=None, ge=0, le=100)
    recommendation: Recommendation = Recommendation.needs_review
    recommendation_reason: str = "信息不足，等待分析"
    risk_flags: list[str] = Field(default_factory=list)
    duplicate_of: Optional[str] = None
    approval_status: Literal["not_required", "proposed", "approved", "rejected"] = "not_required"


class AgentTool(str, Enum):
    search_jobs = "search_jobs"
    read_job_page = "read_job_page"
    deduplicate_leads = "deduplicate_leads"
    analyze_leads = "analyze_leads"
    rank_leads = "rank_leads"
    create_approval_proposals = "create_approval_proposals"
    refresh_analytics = "refresh_analytics"


class PlanStep(V3Model):
    order: int = Field(ge=1)
    tool: AgentTool
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(V3Model):
    goal_id: str
    objective: str
    steps: list[PlanStep] = Field(min_length=1)

    @model_validator(mode="after")
    def orders_are_unique(self) -> AgentPlan:
        orders = [step.order for step in self.steps]
        if len(orders) != len(set(orders)):
            raise ValueError("plan step order 必须唯一")
        return self


class ApprovalRequest(V3Model):
    approval_id: str
    lead_id: str
    goal_id: str
    action_type: Literal["prepare_application", "submit_application", "send_message"]
    status: Literal["waiting", "approved", "rejected", "executed", "verified"] = "waiting"
    summary: str
    proposed_payload_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: Optional[datetime] = None


class ApplicationPackage(V3Model):
    lead_id: str
    resume_tailoring: list[str] = Field(default_factory=list)
    cover_letter: str
    application_answers: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
