from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JDRequirement(StrictModel):
    text: str
    category: Literal["responsibility", "must_have", "nice_to_have", "context"]
    priority: int = Field(ge=1, le=5)
    keywords: list[str] = Field(default_factory=list)


class JDProfile(StrictModel):
    title: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    experience_years: Optional[float] = Field(default=None, ge=0, le=50)
    education: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    requirements: list[JDRequirement] = Field(default_factory=list)
    role_summary: str
    confidence: float = Field(ge=0, le=1)


class CandidateEvidence(StrictModel):
    source_type: Literal["education", "experience", "project", "skill", "other"]
    source_name: str
    evidence: str
    skills: list[str] = Field(default_factory=list)


class CandidateProfile(StrictModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    education: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    evidence_index: list[CandidateEvidence] = Field(default_factory=list)
    profile_summary: str
    confidence: float = Field(ge=0, le=1)


class MatchEvidence(StrictModel):
    requirement: str
    evidence: Optional[str] = None
    assessment: Literal["strong", "partial", "gap", "unknown"]
    explanation: str


class MatchAnalysis(StrictModel):
    overall_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)
    recommended_stories: list[str] = Field(default_factory=list)
    evidence_mapping: list[MatchEvidence] = Field(default_factory=list)
    summary: str
    caveats: list[str] = Field(default_factory=list)


class InterviewQuestion(StrictModel):
    question: str
    why_likely: str
    answer_outline: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)


class InterviewPrep(StrictModel):
    application_id: str
    role_summary: str
    role_priorities: list[str] = Field(default_factory=list)
    likely_questions: list[InterviewQuestion] = Field(default_factory=list)
    resume_mapping: list[str] = Field(default_factory=list)
    star_story_prompts: list[str] = Field(default_factory=list)
    technical_review: list[str] = Field(default_factory=list)
    case_practice: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InterviewReview(StrictModel):
    application_id: str
    summary: str
    questions_asked: list[str] = Field(default_factory=list)
    answers_that_worked: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    follow_up_items: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    facts_to_update: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AnalyticsReport(StrictModel):
    generated_at: datetime
    total_applications: int = Field(ge=0)
    active_applications: int = Field(ge=0)
    stage_counts: dict[str, int]
    company_counts: dict[str, int]
    position_type_counts: dict[str, int]
    funnel_rates: dict[str, float]
