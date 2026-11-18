from __future__ import annotations

import re
from datetime import datetime

from job_workflow.models import ApplicationData, MailType, ParsedEmail


class MockAIProvider:
    """离线测试 Provider：结果可预测，不访问任何网络。"""

    def parse_email(self, message: ParsedEmail) -> ApplicationData:
        text = f"{message.subject}\n{message.body_text}"
        mail_type = MailType.OTHER
        stage = None
        if "面试" in text or "interview" in text.lower():
            mail_type, stage = MailType.INTERVIEW, "一面"
        elif "笔试" in text or "测评" in text:
            mail_type, stage = MailType.WRITTEN_TEST, "笔试"
        elif "遗憾" in text or "不匹配" in text:
            mail_type, stage = MailType.REJECTION, "拒绝"
        elif "offer" in text.lower() or "录用" in text:
            mail_type, stage = MailType.OFFER, "Offer"
        elif "投递" in text or "申请" in text:
            mail_type, stage = MailType.APPLICATION, "已投递"

        company_match = re.search(r"公司[：:]\s*([^\n，,]+)", text)
        position_match = re.search(r"(?:岗位|职位)[：:]\s*([^\n，,]+)", text)
        time_match = re.search(r"(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2})", text)
        interview_time = None
        if time_match:
            interview_time = datetime.fromisoformat(
                f"{time_match.group(1)}T{time_match.group(2)}:00+08:00"
            )
        return ApplicationData(
            type=mail_type,
            company=company_match.group(1).strip() if company_match else "示例科技",
            position=position_match.group(1).strip() if position_match else "示例岗位",
            stage=stage,
            application_date=message.sent_at.date() if message.sent_at else None,
            interview_time=interview_time,
            location="线上" if "线上" in text else None,
            meeting_link=None,
            contact_name=None,
            contact_email=None,
            confidence=0.99,
        )
