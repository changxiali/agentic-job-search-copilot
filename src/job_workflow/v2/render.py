from __future__ import annotations

from job_workflow.models import InterviewPrep


def prep_to_markdown(prep: InterviewPrep, company: str, position: str) -> str:
    lines = [
        f"# {company}｜{position}｜面试准备",
        "",
        f"> 生成时间：{prep.generated_at.isoformat()}",
        "",
        "## 岗位摘要",
        prep.role_summary,
        "",
        "## 岗位重点",
        *_bullets(prep.role_priorities),
        "",
        "## 高频问题与回答框架",
    ]
    for index, question in enumerate(prep.likely_questions, start=1):
        lines.extend(
            [
                f"### {index}. {question.question}",
                f"为什么可能问：{question.why_likely}",
                "回答框架：",
                *_bullets(question.answer_outline),
                "可用证据：",
                *_bullets(question.supporting_evidence),
                "",
            ]
        )
    sections = [
        ("简历映射", prep.resume_mapping),
        ("STAR 案例提示", prep.star_story_prompts),
        ("专业知识复习", prep.technical_review),
        ("Case 练习", prep.case_practice),
        ("反问问题", prep.questions_to_ask),
        ("面试前 Checklist", prep.checklist),
        ("不确定项", prep.caveats),
    ]
    for title, items in sections:
        lines.extend([f"## {title}", *_bullets(items), ""])
    return "\n".join(lines).strip()


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- 暂无"]
