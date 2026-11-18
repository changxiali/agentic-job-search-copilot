from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from job_workflow.ai import StructuredAIClient
from job_workflow.ai.v2_prompts import (
    CANDIDATE_SYSTEM,
    JD_SYSTEM,
    MATCH_SYSTEM,
    PREP_SYSTEM,
    REVIEW_SYSTEM,
    candidate_prompt,
    jd_prompt,
    match_prompt,
    prep_prompt,
    review_prompt,
)
from job_workflow.feishu import FeishuClient
from job_workflow.models import (
    AnalyticsReport,
    CandidateProfile,
    InterviewPrep,
    InterviewReview,
    JDProfile,
    MatchAnalysis,
)
from job_workflow.v2.analytics import analytics_metrics, build_analytics
from job_workflow.v2.render import prep_to_markdown
from job_workflow.v2.utils import content_hash, field_text, is_interview_stage, stable_json

logger = logging.getLogger(__name__)


@dataclass
class V2Stats:
    scanned: int = 0
    jd_parsed: int = 0
    matched: int = 0
    prep_generated: int = 0
    updated: int = 0
    skipped_no_jd: int = 0
    failed: int = 0


class V2Engine:
    def __init__(
        self,
        ai: StructuredAIClient,
        feishu: FeishuClient,
        profile_table_id: str,
        analytics_table_id: str,
        candidate_profile_path: Path,
    ) -> None:
        self.ai = ai
        self.feishu = feishu
        self.profile_table_id = profile_table_id
        self.analytics_table_id = analytics_table_id
        self.candidate_profile_path = candidate_profile_path

    def import_candidate(self, raw_resume: str, dry_run: bool = False) -> CandidateProfile:
        profile = self.ai.generate(CandidateProfile, CANDIDATE_SYSTEM, candidate_prompt(raw_resume))
        profile_json = stable_json(profile)
        profile_hash = content_hash(profile_json)
        if not dry_run:
            self.candidate_profile_path.parent.mkdir(parents=True, exist_ok=True)
            self.candidate_profile_path.write_text(
                json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.feishu.upsert_table_record(
                self.profile_table_id,
                "Profile ID",
                "PRIMARY",
                {
                    "Profile ID": "PRIMARY",
                    "Profile Summary": profile.profile_summary,
                    "Profile JSON": profile_json,
                    "Profile Hash": profile_hash,
                    "Updated At": int(datetime.now().timestamp() * 1000),
                },
            )
        return profile

    def load_candidate(self) -> CandidateProfile | None:
        if not self.candidate_profile_path.exists():
            return None
        return CandidateProfile.model_validate_json(
            self.candidate_profile_path.read_text(encoding="utf-8")
        )

    def enrich(
        self,
        application_id: str | None = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> V2Stats:
        profile = self.load_candidate()
        stats = V2Stats()
        for record in self.feishu.list_records():
            fields = record.get("fields", {})
            current_id = field_text(fields.get("Application ID"))
            if application_id and current_id != application_id:
                continue
            stats.scanned += 1
            try:
                if self._enrich_one(record, profile, force, dry_run, stats):
                    stats.updated += 1
            except Exception:
                stats.failed += 1
                logger.exception("V2 enrich 失败 application_id=%s", current_id)
        return stats

    def _enrich_one(
        self,
        record: dict,
        profile: CandidateProfile | None,
        force: bool,
        dry_run: bool,
        stats: V2Stats,
    ) -> bool:
        fields = record.get("fields", {})
        raw_jd = field_text(fields.get("JD Raw")).strip()
        if not raw_jd:
            stats.skipped_no_jd += 1
            return False
        application_id = field_text(fields.get("Application ID"))
        company = field_text(fields.get("Company")) or "未知公司"
        position = field_text(fields.get("Position")) or "未知岗位"
        updates: dict = {}

        jd_hash = content_hash(raw_jd)
        stored_jd_hash = field_text(fields.get("JD Hash"))
        stored_jd_json = field_text(fields.get("JD Structured JSON"))
        if force or stored_jd_hash != jd_hash or not stored_jd_json:
            jd = self.ai.generate(JDProfile, JD_SYSTEM, jd_prompt(raw_jd, company, position))
            stored_jd_json = stable_json(jd)
            updates.update({"JD Structured JSON": stored_jd_json, "JD Hash": jd_hash})
            stats.jd_parsed += 1
        else:
            jd = JDProfile.model_validate_json(stored_jd_json)

        match = None
        if profile:
            profile_json = stable_json(profile)
            match_hash = content_hash(stored_jd_json, profile_json)
            stored_match_hash = field_text(fields.get("Match Hash"))
            stored_match_json = field_text(fields.get("Match Analysis JSON"))
            if force or stored_match_hash != match_hash or not stored_match_json:
                match = self.ai.generate(MatchAnalysis, MATCH_SYSTEM, match_prompt(jd, profile))
                stored_match_json = stable_json(match)
                updates.update(
                    {
                        "Match Analysis JSON": stored_match_json,
                        "Match Hash": match_hash,
                        "Match Score": match.overall_score,
                        "Strengths": "\n".join(match.strengths),
                        "Gaps": "\n".join(match.gaps),
                        "Interview Focus": "\n".join(match.interview_focus),
                    }
                )
                stats.matched += 1
            else:
                match = MatchAnalysis.model_validate_json(stored_match_json)

        stage = field_text(fields.get("Current Stage"))
        if profile and match and is_interview_stage(stage):
            prep_hash = content_hash(
                application_id,
                stage,
                stored_jd_json,
                stable_json(profile),
                stable_json(match),
            )
            if force or field_text(fields.get("Prep Hash")) != prep_hash:
                prep = self.ai.generate(
                    InterviewPrep,
                    PREP_SYSTEM,
                    prep_prompt(application_id, company, position, jd, profile, match),
                ).model_copy(update={"application_id": application_id})
                updates.update(
                    {
                        "Interview Prep": prep_to_markdown(prep, company, position),
                        "Prep Hash": prep_hash,
                        "Prep Status": "Generated",
                    }
                )
                stats.prep_generated += 1
        elif is_interview_stage(stage):
            if field_text(fields.get("Prep Status")) != "Waiting for Candidate Profile":
                updates["Prep Status"] = "Waiting for Candidate Profile"
        else:
            if field_text(fields.get("Prep Status")) != "Not triggered":
                updates["Prep Status"] = "Not triggered"

        if not updates:
            return False
        updates["V2 Last Processed"] = int(datetime.now().timestamp() * 1000)
        if dry_run:
            logger.info("V2 DRY-RUN %s fields=%s", application_id, sorted(updates))
        else:
            self.feishu.update_record(record["record_id"], updates)
        return True

    def add_review(
        self, application_id: str, raw_review: str, dry_run: bool = False
    ) -> InterviewReview:
        record = self.feishu.find_record_by_application_id(application_id)
        if not record:
            raise ValueError(f"找不到 Application ID：{application_id}")
        review = self.ai.generate(
            InterviewReview,
            REVIEW_SYSTEM,
            review_prompt(application_id, raw_review),
        ).model_copy(update={"application_id": application_id})
        if not dry_run:
            self.feishu.update_record(
                record["record_id"],
                {
                    "Interview Review Raw": raw_review,
                    "Interview Review JSON": stable_json(review),
                    "Review Hash": content_hash(raw_review),
                    "V2 Last Processed": int(datetime.now().timestamp() * 1000),
                },
            )
        return review

    def refresh_analytics(self, output_path: Path, dry_run: bool = False) -> AnalyticsReport:
        report = build_analytics(self.feishu.list_records())
        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for row in analytics_metrics(report):
                self.feishu.upsert_table_record(
                    self.analytics_table_id,
                    "Metric ID",
                    row["Metric ID"],
                    row,
                )
        return report
