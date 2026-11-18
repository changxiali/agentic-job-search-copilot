from __future__ import annotations

from job_workflow.models import ParsedEmail

JOB_KEYWORDS = {
    "投递",
    "应聘",
    "申请",
    "简历",
    "招聘",
    "面试",
    "笔试",
    "测评",
    "offer",
    "录用",
    "职位",
    "岗位",
    "interview",
    "application",
    "assessment",
    "candidate",
    "recruit",
}

NON_ACTIONABLE_KEYWORDS = {
    "一次性验证码",
    "面试满意度",
    "面试体验问卷",
    "面试体验反馈",
    "邀请您反馈面试体验",
    "邀请您对面试满意度进行评价",
}


def is_job_related(message: ParsedEmail) -> bool:
    haystack = f"{message.subject}\n{message.sender}\n{message.body_text[:10000]}".lower()
    if any(keyword in haystack for keyword in NON_ACTIONABLE_KEYWORDS):
        return False
    return any(keyword in haystack for keyword in JOB_KEYWORDS)
