from __future__ import annotations

import imaplib
import logging
from datetime import datetime, timedelta

from job_workflow.email_client.parser import parse_email_bytes
from job_workflow.models import ParsedEmail

logger = logging.getLogger(__name__)


class ImapEmailClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        auth_code: str,
        mailbox: str = "INBOX",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.auth_code = auth_code
        self.mailbox = mailbox

    def fetch_recent(self, lookback_days: int = 7, only_unseen: bool = False) -> list[ParsedEmail]:
        since = (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
        criteria = ["SINCE", since]
        if only_unseen:
            criteria.append("UNSEEN")

        logger.info("连接 IMAP %s:%s，邮箱=%s", self.host, self.port, self.mailbox)
        client = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            client.login(self.username, self.auth_code)
            self._send_client_id(client)
            status, select_data = client.select(self.mailbox, readonly=True)
            if status != "OK":
                detail = " ".join(
                    item.decode(errors="replace") if isinstance(item, bytes) else str(item)
                    for item in (select_data or [])
                )
                raise RuntimeError(f"无法选择邮箱目录 {self.mailbox}：{detail}")
            status, data = client.search(None, *criteria)
            if status != "OK":
                raise RuntimeError("IMAP 搜索失败")
            messages: list[ParsedEmail] = []
            for uid in data[0].split():
                status, parts = client.fetch(uid, "(RFC822)")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    logger.warning("跳过读取失败的邮件 UID=%s", uid.decode(errors="replace"))
                    continue
                messages.append(parse_email_bytes(parts[0][1]))
            logger.info("IMAP 共读取 %d 封候选邮件", len(messages))
            return messages
        finally:
            try:
                client.logout()
            except imaplib.IMAP4.error:
                logger.debug("IMAP logout 失败", exc_info=True)

    @staticmethod
    def _send_client_id(client: imaplib.IMAP4_SSL) -> None:
        """网易 163/126 要求客户端在 LOGIN 后发送 RFC 2971 ID。"""
        capabilities = {
            item.decode(errors="replace").upper() if isinstance(item, bytes) else str(item).upper()
            for item in client.capabilities
        }
        if "ID" not in capabilities:
            return
        # Python 标准库能够发送任意 IMAP 命令，但 ID 未登记在命令状态表中。
        imaplib.Commands.setdefault("ID", ("AUTH",))
        status, data = client._simple_command(
            "ID",
            '("name" "JobSearchWorkflowV1" "version" "0.1.0" '
            '"vendor" "LocalWorkflow" "contact" "local")',
        )
        if status != "OK":
            detail = " ".join(
                item.decode(errors="replace") if isinstance(item, bytes) else str(item)
                for item in (data or [])
            )
            raise RuntimeError(f"IMAP 服务器拒绝客户端 ID：{detail}")
