from .application import ApplicationData, MailType
from .email_message import ParsedEmail
from .v2 import (
    AnalyticsReport,
    CandidateProfile,
    InterviewPrep,
    InterviewReview,
    JDProfile,
    MatchAnalysis,
)
from .v3 import AgentPlan, ApplicationPackage, ApprovalRequest, JobLead, SearchGoal

__all__ = [
    "AnalyticsReport",
    "AgentPlan",
    "ApplicationPackage",
    "ApplicationData",
    "CandidateProfile",
    "ApprovalRequest",
    "InterviewPrep",
    "InterviewReview",
    "JDProfile",
    "JobLead",
    "MailType",
    "MatchAnalysis",
    "ParsedEmail",
    "SearchGoal",
]
