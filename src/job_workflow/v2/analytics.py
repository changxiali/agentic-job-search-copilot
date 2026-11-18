from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from job_workflow.models import AnalyticsReport
from job_workflow.v2.utils import field_text, is_interview_stage


def build_analytics(records: list[dict[str, Any]]) -> AnalyticsReport:
    stages: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    position_types: Counter[str] = Counter()
    active = 0
    interviewed = 0
    offers = 0

    for record in records:
        fields = record.get("fields", {})
        stage = field_text(fields.get("Current Stage")) or "未知"
        company = field_text(fields.get("Company")) or "未知"
        position = field_text(fields.get("Position")) or "未知"
        stages[stage] += 1
        companies[company] += 1
        position_types[classify_position(position)] += 1
        lowered = stage.lower()
        if not any(term in lowered for term in ("拒绝", "rejection", "offer")):
            active += 1
        if is_interview_stage(stage) or fields.get("Interview Time"):
            interviewed += 1
        if "offer" in lowered or "录用" in lowered:
            offers += 1

    total = len(records)
    return AnalyticsReport(
        generated_at=datetime.now(timezone.utc),
        total_applications=total,
        active_applications=active,
        stage_counts=dict(stages),
        company_counts=dict(companies),
        position_type_counts=dict(position_types),
        funnel_rates={
            "application_to_interview": _rate(interviewed, total),
            "interview_to_offer": _rate(offers, interviewed),
            "application_to_offer": _rate(offers, total),
        },
    )


def classify_position(position: str) -> str:
    value = position.lower()
    rules = [
        ("AI/算法", ("ai", "算法", "大模型", "机器学习", "数据挖掘")),
        ("产品", ("产品", "product", "策略")),
        ("数据", ("数据", "分析", "data", "bi")),
        ("工程", ("工程师", "开发", "研发", "software", "engineer")),
        ("运营/商业化", ("运营", "商业化", "增长", "marketing", "operation")),
    ]
    for category, keywords in rules:
        if any(keyword in value for keyword in keywords):
            return category
    return "其他"


def analytics_metrics(report: AnalyticsReport) -> list[dict[str, Any]]:
    generated_ms = int(report.generated_at.timestamp() * 1000)
    rows = [
        _metric("summary:total", "总申请数", "Summary", report.total_applications, generated_ms),
        _metric(
            "summary:active", "活跃申请数", "Summary", report.active_applications, generated_ms
        ),
    ]
    for stage, count in report.stage_counts.items():
        rows.append(_metric(f"stage:{stage}", stage, "Stage", count, generated_ms))
    for company, count in report.company_counts.items():
        rows.append(_metric(f"company:{company}", company, "Company", count, generated_ms))
    for position_type, count in report.position_type_counts.items():
        rows.append(
            _metric(
                f"position:{position_type}", position_type, "Position Type", count, generated_ms
            )
        )
    for name, rate in report.funnel_rates.items():
        rows.append(_metric(f"funnel:{name}", name, "Funnel", rate, generated_ms))
    return rows


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _metric(metric_id: str, name: str, dimension: str, value: float, generated: int):
    return {
        "Metric ID": metric_id,
        "Metric": name,
        "Dimension": dimension,
        "Value": value,
        "Generated At": generated,
    }
