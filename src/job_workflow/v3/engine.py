from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_workflow.ai import StructuredAIClient
from job_workflow.ai.v2_prompts import JD_SYSTEM, MATCH_SYSTEM, jd_prompt, match_prompt
from job_workflow.feishu import FeishuClient
from job_workflow.models import CandidateProfile, JDProfile, MatchAnalysis
from job_workflow.models.v3 import (
    ApplicationPackage,
    ApprovalRequest,
    JobLead,
    Recommendation,
    SearchGoal,
    SourceEvidence,
)
from job_workflow.v2.utils import field_text, stable_json
from job_workflow.v3.planner import SafePlanner
from job_workflow.v3.search import DeepSeekSearchProvider, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class V3Tables:
    goals: str
    leads: str
    approvals: str
    runs: str
    decisions: str
    artifacts: str


@dataclass
class V3Stats:
    found: int = 0
    unique: int = 0
    analyzed: int = 0
    recommended: int = 0
    approvals_created: int = 0
    failed: int = 0
    dry_run: bool = False


class V3Engine:
    def __init__(
        self,
        ai: StructuredAIClient,
        search: DeepSeekSearchProvider,
        feishu: FeishuClient,
        tables: V3Tables,
        candidate_profile_path: Path,
        planner: Optional[SafePlanner] = None,
    ) -> None:
        self.ai, self.search, self.feishu = ai, search, feishu
        self.tables, self.candidate_profile_path = tables, candidate_profile_path
        self.planner = planner or SafePlanner()

    def save_goal(self, goal: SearchGoal, dry_run: bool = False) -> SearchGoal:
        if not dry_run:
            self.feishu.upsert_table_record(
                self.tables.goals,
                "Goal ID",
                goal.goal_id,
                {
                    "Goal ID": goal.goal_id,
                    "Title": goal.title,
                    "Goal JSON": stable_json(goal),
                    "Active": "Yes" if goal.active else "No",
                    "Cadence": goal.cadence,
                    "Updated At": _millis(),
                },
            )
        return goal

    def load_goal(self, goal_id: Optional[str] = None) -> SearchGoal:
        goals = []
        for record in self.feishu.list_table_records(self.tables.goals):
            raw = field_text(record.get("fields", {}).get("Goal JSON"))
            if raw:
                goals.append(SearchGoal.model_validate_json(raw))
        if goal_id:
            match = next((goal for goal in goals if goal.goal_id == goal_id), None)
            if not match:
                raise ValueError(f"找不到 Search Goal：{goal_id}")
            return match
        active = [goal for goal in goals if goal.active]
        if len(active) != 1:
            raise ValueError("未指定 goal-id 时，飞书中必须恰好有一个 Active Search Goal")
        return active[0]

    def run(self, goal_id: Optional[str] = None, dry_run: bool = False) -> V3Stats:
        goal = self.load_goal(goal_id)
        if not goal.active:
            raise ValueError(f"Search Goal {goal.goal_id} 未启用")
        existing = self.feishu.list_table_records(self.tables.leads)
        plan = self.planner.create_plan(goal, len(existing))
        run_id = _id("run", goal.goal_id, datetime.now(timezone.utc).isoformat())
        stats = V3Stats(dry_run=dry_run)
        if dry_run:
            logger.info("V3 DRY-RUN goal=%s plan=%s", goal.goal_id, stable_json(plan))
            return stats
        self._write_run(run_id, goal.goal_id, "running", plan=stable_json(plan))
        try:
            raw = self._search_goal(goal)
            stats.found = len(raw)
            leads = self._deduplicate(self._to_lead(goal, item) for item in raw)
            stats.unique = len(leads)
            profile = self._load_candidate()
            analyzed: list[JobLead] = []
            for lead in leads:
                try:
                    self._analyze(lead, profile, goal)
                    stats.analyzed += 1
                    analyzed.append(lead)
                except Exception:
                    stats.failed += 1
                    logger.exception("V3 lead 分析失败 url=%s", lead.source_url)
            analyzed.sort(
                key=lambda item: (
                    item.recommendation == Recommendation.strong,
                    item.match_score or 0,
                    item.source.rerank_score,
                ),
                reverse=True,
            )
            for lead in analyzed:
                if lead.recommendation == Recommendation.strong:
                    stats.recommended += 1
                    if self._create_approval(lead):
                        stats.approvals_created += 1
                self._upsert_lead(lead)
                self._decision(run_id, lead)
            self._write_run(run_id, goal.goal_id, "completed", stats=stable_json(stats.__dict__))
            return stats
        except Exception as exc:
            self._write_run(run_id, goal.goal_id, "failed", stats=str(exc))
            raise

    def decide_approval(self, approval_id: str, decision: str) -> None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision 只能是 approved 或 rejected")
        record = self.feishu.find_table_record(self.tables.approvals, "Approval ID", approval_id)
        if not record:
            raise ValueError(f"找不到 Approval ID：{approval_id}")
        self.feishu.update_table_record(
            self.tables.approvals,
            record["record_id"],
            {"Status": decision, "Decided At": _millis()},
        )

    def create_package(self, lead_id: str) -> ApplicationPackage:
        approval = next(
            (
                item
                for item in self.feishu.list_table_records(self.tables.approvals)
                if field_text(item.get("fields", {}).get("Lead ID")) == lead_id
                and field_text(item.get("fields", {}).get("Status")) == "approved"
            ),
            None,
        )
        if not approval:
            raise PermissionError("没有已批准的 prepare_application 审批，不能生成申请材料")
        lead_record = self.feishu.find_table_record(self.tables.leads, "Lead ID", lead_id)
        if not lead_record:
            raise ValueError(f"找不到 Lead ID：{lead_id}")
        fields = lead_record.get("fields", {})
        profile = self._load_candidate()
        if not profile:
            raise ValueError("Candidate Profile 尚未结构化，无法生成个性化申请材料")
        jd_context = field_text(fields.get("JD JSON")) or field_text(fields.get("JD Raw"))
        prompt = (
            "请根据候选人和岗位生成申请材料草案。不得虚构经历或技能。\n"
            f"候选人：{stable_json(profile)}\n岗位：{jd_context}"
        )
        package = self.ai.generate(
            ApplicationPackage,
            "你是求职申请材料助手。只基于提供的事实写作，所有不确定内容列入 caveats。",
            prompt,
        ).model_copy(update={"lead_id": lead_id})
        artifact_id = _id("artifact", lead_id, "application_package")
        self.feishu.upsert_table_record(
            self.tables.artifacts,
            "Artifact ID",
            artifact_id,
            {
                "Artifact ID": artifact_id,
                "Lead ID": lead_id,
                "Type": "application_package",
                "Content": stable_json(package),
                "Status": "draft",
                "Created At": _millis(),
            },
        )
        return package

    def _search_goal(self, goal: SearchGoal) -> list[SearchResult]:
        since = (datetime.now(timezone.utc) - timedelta(days=goal.published_within_days)).date()
        results = []
        for role in goal.role_keywords:
            for location in goal.locations or [""]:
                parts = (
                    [role, location, "招聘", f"after:{since.isoformat()}"]
                    + [f'"{word}"' for word in goal.required_keywords]
                    + [f'-"{word}"' for word in goal.excluded_keywords]
                )
                query = " ".join(item for item in parts if item)[:128]
                results.extend(
                    self.search.search(query, goal.max_results_per_query, need_content=True)
                )
        return results

    def _to_lead(self, goal: SearchGoal, item: SearchResult) -> JobLead:
        canonical = canonical_url(item.url)
        published = datetime.fromisoformat(item.date.replace("Z", "+00:00")) if item.date else None
        return JobLead(
            lead_id=_id("lead", canonical),
            goal_id=goal.goal_id,
            source_url=item.url,
            canonical_url=canonical,
            position=item.title or "待解析岗位",
            published_at=published,
            source=SourceEvidence(
                url=item.url,
                title=item.title,
                snippet=item.snippet,
                site_name=item.site_name,
                published_at=published,
                authority=item.authority,
                rerank_score=item.rerank_score,
            ),
            jd_raw=item.content or item.summary or item.snippet,
        )

    @staticmethod
    def _deduplicate(leads: Iterable[JobLead]) -> list[JobLead]:
        unique = {}
        for lead in leads:
            current = unique.get(lead.canonical_url)
            if current is None or lead.source.rerank_score > current.source.rerank_score:
                unique[lead.canonical_url] = lead
        return list(unique.values())

    def _analyze(
        self,
        lead: JobLead,
        profile: Optional[CandidateProfile],
        goal: SearchGoal,
    ) -> None:
        if len(lead.jd_raw.strip()) < 60:
            try:
                lead.jd_raw = self.search.fetch(str(lead.source_url))
            except Exception as exc:
                lead.risk_flags.append(f"页面正文读取失败：{type(exc).__name__}")
        if len(lead.jd_raw.strip()) < 60:
            lead.risk_flags.append("JD 信息不足")
            return
        jd = self.ai.generate(JDProfile, JD_SYSTEM, jd_prompt(lead.jd_raw, "", lead.position))
        lead.jd_json = stable_json(jd)
        lead.company, lead.position = (
            jd.company or lead.source.site_name or "待确认",
            jd.title or lead.position,
        )
        lead.location, lead.employment_type = jd.location, jd.employment_type
        searchable = f"{lead.company}\n{lead.position}\n{lead.jd_raw}".lower()
        if any(company.lower() in lead.company.lower() for company in goal.excluded_companies):
            lead.recommendation = Recommendation.skip
            lead.recommendation_reason = "公司位于 Search Goal 排除列表"
            lead.risk_flags.append("命中排除公司")
            return
        if any(word.lower() in searchable for word in goal.excluded_keywords):
            lead.recommendation = Recommendation.skip
            lead.recommendation_reason = "岗位正文命中 Search Goal 排除关键词"
            lead.risk_flags.append("命中排除关键词")
            return
        missing_required = [
            word for word in goal.required_keywords if word.lower() not in searchable
        ]
        if missing_required:
            lead.risk_flags.append("缺少必需关键词：" + "、".join(missing_required))
        if goal.employment_types and lead.employment_type:
            allowed = any(
                value.lower() in lead.employment_type.lower()
                or lead.employment_type.lower() in value.lower()
                for value in goal.employment_types
            )
            if not allowed:
                lead.risk_flags.append("用工类型与目标不一致")
        if not profile:
            lead.match_score = round(min(100, lead.source.rerank_score / 3 * 100))
            lead.recommendation_reason = "Candidate Profile 缺失，仅完成 JD 解析和来源评分"
            lead.risk_flags.append("Candidate Profile 缺失")
            return
        match = self.ai.generate(MatchAnalysis, MATCH_SYSTEM, match_prompt(jd, profile))
        lead.match_json, lead.match_score = stable_json(match), match.overall_score
        score = min(
            100,
            match.overall_score
            + (10 if _recent(lead.published_at, 14) else 0)
            + max(0, lead.source.authority) * 2,
        )
        if missing_required:
            score = max(0, score - 20)
        if goal.preferred_companies and any(
            company.lower() in lead.company.lower() for company in goal.preferred_companies
        ):
            score = min(100, score + 5)
        lead.recommendation = (
            Recommendation.strong
            if score >= 80
            else Recommendation.consider
            if score >= 60
            else Recommendation.skip
        )
        lead.recommendation_reason = match.summary

    def _upsert_lead(self, lead: JobLead) -> None:
        self.feishu.upsert_table_record(
            self.tables.leads,
            "Lead ID",
            lead.lead_id,
            {
                "Lead ID": lead.lead_id,
                "Goal ID": lead.goal_id,
                "Company": lead.company,
                "Position": lead.position,
                "Location": lead.location or "",
                "Source URL": str(lead.source_url),
                "Published At": _millis(lead.published_at) if lead.published_at else 0,
                "JD Raw": lead.jd_raw,
                "JD JSON": lead.jd_json or "",
                "Match JSON": lead.match_json or "",
                "Match Score": lead.match_score or 0,
                "Recommendation": lead.recommendation.value,
                "Reason": lead.recommendation_reason,
                "Risk Flags": "\n".join(lead.risk_flags),
                "Approval Status": lead.approval_status,
                "Discovered At": _millis(lead.discovered_at),
            },
        )

    def _create_approval(self, lead: JobLead) -> bool:
        approval_id = _id("approval", lead.lead_id, "prepare_application")
        existing = self.feishu.find_table_record(self.tables.approvals, "Approval ID", approval_id)
        if existing:
            lead.approval_status = (
                "approved"
                if field_text(existing.get("fields", {}).get("Status")) == "approved"
                else "proposed"
            )
            return False
        request = ApprovalRequest(
            approval_id=approval_id,
            lead_id=lead.lead_id,
            goal_id=lead.goal_id,
            action_type="prepare_application",
            summary=f"为 {lead.company}｜{lead.position} 生成个性化申请材料草案",
        )
        self.feishu.create_table_record(
            self.tables.approvals,
            {
                "Approval ID": request.approval_id,
                "Lead ID": request.lead_id,
                "Goal ID": request.goal_id,
                "Action Type": request.action_type,
                "Status": request.status,
                "Summary": request.summary,
                "Payload JSON": request.proposed_payload_json,
                "Created At": _millis(request.created_at),
            },
        )
        lead.approval_status = "proposed"
        return True

    def _write_run(self, run_id: str, goal_id: str, status: str, **extra: str) -> None:
        fields = {"Run ID": run_id, "Goal ID": goal_id, "Status": status, "Updated At": _millis()}
        if "plan" in extra:
            fields["Plan JSON"] = extra["plan"]
        if "stats" in extra:
            fields["Stats JSON"] = extra["stats"]
        self.feishu.upsert_table_record(self.tables.runs, "Run ID", run_id, fields)

    def _decision(self, run_id: str, lead: JobLead) -> None:
        decision_id = _id("decision", run_id, lead.lead_id)
        self.feishu.upsert_table_record(
            self.tables.decisions,
            "Decision ID",
            decision_id,
            {
                "Decision ID": decision_id,
                "Run ID": run_id,
                "Lead ID": lead.lead_id,
                "Decision": lead.recommendation.value,
                "Reason": lead.recommendation_reason,
                "Evidence URL": str(lead.source_url),
                "Created At": _millis(),
            },
        )

    def _load_candidate(self) -> Optional[CandidateProfile]:
        if not self.candidate_profile_path.exists():
            return None
        return CandidateProfile.model_validate_json(
            self.candidate_profile_path.read_text(encoding="utf-8")
        )


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")]
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:20]}"


def _millis(value: Optional[datetime] = None) -> int:
    return int((value or datetime.now(timezone.utc)).timestamp() * 1000)


def _recent(value: Optional[datetime], days: int) -> bool:
    if not value:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value >= datetime.now(timezone.utc) - timedelta(days=days)
