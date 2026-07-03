"""Native Bilibili search backend."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from ...acquisition import AcquisitionRequest, AcquisitionResult
from ...models import CandidateSource, SourceItem

_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
_COOKIE_FIX = "设置 SOURCE_RADAR_BILI_COOKIE，或运行: uv run python -m source_radar cookie --platform bili"


class BilibiliNativeBackend:
    provider = "bilibili"
    provider_type = "native"

    def __init__(self, *, cookie: str | None = None, request_json=None) -> None:
        self.cookie = cookie if cookie is not None else os.environ.get("SOURCE_RADAR_BILI_COOKIE", "")
        self._request_json = request_json or _request_json

    def status(self) -> AcquisitionResult:
        if not self.cookie:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="degraded",
                reason="missing-cookie",
                message="B站 cookie 未配置；公开视频搜索仍可尝试，但登录态、风控和个性化结果诊断受限。",
                fix=_COOKIE_FIX,
                retryable=False,
                diagnostics={"platform": "bili", "backend_key": "community.bilibili"},
            )
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="ready",
            message="B站 native backend 已配置 cookie，可尝试搜索。",
            diagnostics={"platform": "bili", "backend_key": "community.bilibili"},
        )

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        query = request.query.strip()
        if not query:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="needs-input",
                reason="missing-query",
                message="B站搜索缺少 query。",
                retryable=False,
                diagnostics={"platform": "bili"},
            )

        limit = min(max(request.limit or 3, 1), 10)
        url = _search_url(query, limit=limit, page=max(request.page, 1))
        headers = {
            "Accept": "application/json",
            "Referer": "https://search.bilibili.com/",
            "User-Agent": _USER_AGENT,
        }
        warnings: list[str] = []
        if self.cookie:
            headers["Cookie"] = self.cookie
        else:
            warnings.append("missing-cookie: B站 cookie 未配置，公开视频搜索可尝试但结果可能受限")

        try:
            payload = self._request_json(url, headers, 10)
        except urllib.error.HTTPError as error:
            if error.code in {412, 429}:
                return _error_from_code(-412, f"HTTP {error.code} {error.reason}")
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=f"http-{error.code}",
                message=f"B站 native 搜索 HTTP 错误: {error.code} {error.reason}",
                retryable=True,
                diagnostics={"platform": "bili", "url": url, "http_status": str(error.code)},
            )
        except Exception as error:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=type(error).__name__,
                message=f"B站 native 搜索异常: {error}",
                retryable=True,
                diagnostics={"platform": "bili", "url": url},
            )

        code = int(payload.get("code", 0) or 0)
        if code != 0:
            return _error_from_code(code, str(payload.get("message") or payload.get("msg") or ""))

        raw_items = payload.get("data", {}).get("result", [])
        if not isinstance(raw_items, list):
            raw_items = []

        candidates: list[CandidateSource] = []
        items: list[SourceItem] = []
        for entry in raw_items[:limit]:
            if not isinstance(entry, dict):
                continue
            title = _clean_text(str(entry.get("title") or ""))
            url = str(entry.get("arcurl") or entry.get("url") or "")
            if url.startswith("//"):
                url = "https:" + url
            if not title or not url:
                continue
            snippet = _clean_text(str(entry.get("description") or entry.get("desc") or ""))
            author = str(entry.get("author") or entry.get("upic") or "")
            published_at = _published_at(entry.get("pubdate"))
            metadata = {
                "platform": "bili",
                "author": author,
                "published_at": published_at,
                "play": str(entry.get("play") or ""),
                "danmaku": str(entry.get("danmaku") or ""),
            }
            candidates.append(CandidateSource(
                title=title,
                url=url,
                snippet=snippet,
                provider=self.provider,
                source_type="community-video",
                metadata=metadata,
            ))
            items.append(SourceItem(
                source_type="community-video",
                title=title,
                url=url,
                snippet=snippet,
                adapter=self.provider,
                metadata=metadata,
                retrieved_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
                raw_content_length=len(snippet),
            ))

        if not items:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="no-evidence",
                reason="no-results",
                message=f"B站 native 搜索未返回关于「{query}」的可用结果。",
                retryable=True,
                warnings=warnings,
                diagnostics={"platform": "bili", "raw_count": str(len(raw_items))},
            )

        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="items-found",
            message=f"B站 native 搜索返回 {len(items)} 条结果。",
            candidates=candidates,
            items=items,
            retryable=True,
            warnings=warnings,
            diagnostics={"platform": "bili", "raw_count": str(len(raw_items))},
        )


def _request_json(url: str, headers: dict[str, str], timeout: int) -> dict:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _search_url(query: str, *, limit: int, page: int) -> str:
    params = {
        "search_type": "video",
        "keyword": query,
        "page": str(page),
        "page_size": str(limit),
    }
    return _SEARCH_URL + "?" + urllib.parse.urlencode(params)


def _error_from_code(code: int, message: str) -> AcquisitionResult:
    if code == -101:
        return AcquisitionResult(
            provider="bilibili",
            provider_type="native",
            status="needs-input",
            reason="cookie-expired",
            message=f"B站 cookie 缺失或已过期: {message or code}",
            fix=_COOKIE_FIX,
            retryable=False,
            diagnostics={"platform": "bili", "code": str(code)},
        )
    if code in {-412, -352}:
        return AcquisitionResult(
            provider="bilibili",
            provider_type="native",
            status="error",
            reason="rate-limited",
            message=f"B站风控/限流: {message or code}",
            fix="稍后重试，或配置有效 SOURCE_RADAR_BILI_COOKIE 后重试。",
            retryable=True,
            diagnostics={"platform": "bili", "code": str(code)},
        )
    return AcquisitionResult(
        provider="bilibili",
        provider_type="native",
        status="error",
        reason="backend-error",
        message=f"B站 native 搜索返回错误: {message or code}",
        retryable=True,
        diagnostics={"platform": "bili", "code": str(code)},
    )


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(html.unescape(value).split())


def _published_at(value: object) -> str:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, UTC).date().isoformat()
