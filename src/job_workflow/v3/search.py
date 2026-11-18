from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class SearchProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    summary: str
    content: str
    site_name: Optional[str]
    date: Optional[str]
    authority: int
    rerank_score: float


class DeepSeekSearchProvider:
    """DeepSeek 官方 Search/Fetch API；仅执行公开网页的只读访问。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 60,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def search(self, query: str, count: int = 10, need_content: bool = False) -> list[SearchResult]:
        response = self.session.post(
            f"{self.base_url}/v1/tools/search",
            headers=self._headers(),
            json={"query": query[:128], "count": count, "need_content": need_content},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise SearchProviderError(str(payload["error"]))
        return [self._result(item) for item in payload.get("results", [])]

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def fetch(self, url: str) -> str:
        _validate_public_url(url)
        response = self.session.post(
            f"{self.base_url}/v1/tools/fetch",
            headers=self._headers(),
            json={"url": url},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise SearchProviderError(str(payload["error"]))
        return str(payload.get("content", ""))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _result(item: dict[str, Any]) -> SearchResult:
        return SearchResult(
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            snippet=str(item.get("snippet", "")),
            summary=str(item.get("summary", "")),
            content=str(item.get("content", "")),
            site_name=item.get("site_name"),
            date=item.get("date"),
            authority=int(item.get("authority", -1)),
            rerank_score=float(item.get("rerank_score", 0)),
        )


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("只允许不带凭据的公开 HTTP/HTTPS URL")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("不允许访问本机或内网地址")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise ValueError(f"域名无法解析：{host}") from exc
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("不允许访问本机、内网或保留地址")
