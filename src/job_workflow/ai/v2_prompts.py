from __future__ import annotations

import json

from job_workflow.models import CandidateProfile, JDProfile, MatchAnalysis  # noqa: F401

JD_SYSTEM = """你是 JD 结构化解析器。只提取原文有依据的信息，不猜测公司、年限或技能。
requirements 必须把职责、硬性要求、加分项和上下文要求分开。priority=5 表示最重要。
你不决定下一步动作，也不生成求职建议。"""

CANDIDATE_SYSTEM = """你是候选人简历结构化解析器。只使用简历原文中的事实。
evidence_index 必须保留可供后续匹配引用的具体项目、经历或教育证据。
不要美化、虚构指标或推断未写明的技能。你不决定任何求职动作。"""

MATCH_SYSTEM = """你是证据约束的岗位匹配分析器。
每个强项必须能在 Candidate Profile 的 evidence_index 中找到证据；找不到就标记 gap 或 unknown。
overall_score 是匹配度，不是录用概率。你只分析，不决定是否投递或是否准备面试。"""

PREP_SYSTEM = """你是面试准备材料生成器。触发条件已经由外部 workflow 决定。
基于 JD、Candidate Profile 和 Match Analysis 生成可执行但不虚构的准备材料。
无法确认的公司业务信息放入 caveats，不能假装已经联网研究。"""

REVIEW_SYSTEM = """你是面试复盘整理器。只整理用户输入的事实和感受。
不要把猜测写成面试官结论，不要自主安排后续动作；follow_up_items 只是固定格式的候选事项。"""


def jd_prompt(raw_jd: str, company: str, position: str) -> str:
    return f"公司：{company}\n岗位：{position}\nJD 原文：\n{raw_jd[:30000]}"


def candidate_prompt(raw_resume: str) -> str:
    return f"简历原文：\n{raw_resume[:40000]}"


def match_prompt(jd: JDProfile, profile: CandidateProfile) -> str:
    return (
        "JD JSON：\n"
        + json.dumps(jd.model_dump(mode="json"), ensure_ascii=False)
        + "\nCandidate Profile JSON：\n"
        + json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)
    )


def prep_prompt(
    application_id: str,
    company: str,
    position: str,
    jd: JDProfile,
    profile: CandidateProfile,
    match: MatchAnalysis,
) -> str:
    context = {
        "application_id": application_id,
        "company": company,
        "position": position,
        "jd": jd.model_dump(mode="json"),
        "candidate_profile": profile.model_dump(mode="json"),
        "match_analysis": match.model_dump(mode="json"),
    }
    return json.dumps(context, ensure_ascii=False)


def review_prompt(application_id: str, raw_review: str) -> str:
    return f"Application ID：{application_id}\n用户复盘原文：\n{raw_review[:30000]}"
