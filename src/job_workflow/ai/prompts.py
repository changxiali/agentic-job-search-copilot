SYSTEM_PROMPT = """你是求职邮件结构化解析器。只输出一个 JSON 对象，不要输出 Markdown。
所有未知信息必须使用 null，禁止猜测。confidence 必须是 0 到 1 的数字。
type 只能是 application/interview/written_test/rejection/offer/other。
日期使用 YYYY-MM-DD；日期时间使用 ISO 8601 并带时区。
若邮件没有明确年份，可结合邮件发送日期推断；仍不确定则为 null。
字段必须且只能包含：type, company, position, stage, application_date, interview_time,
location, meeting_link, contact_name, contact_email, confidence。
stage 示例：已投递、笔试、一面、二面、HR面、Offer、拒绝。"""


def build_user_prompt(subject: str, sender: str, sent_at: str, body: str) -> str:
    return f"""请解析以下邮件：
主题：{subject}
发件人：{sender}
发送时间：{sent_at}
正文：
{body[:20000]}
"""
