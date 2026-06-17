import asyncio
import base64
import ipaddress
import json
import re as _re
import sys
import urllib.parse
from typing import Any

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..acquisition import AcquisitionRequest, ExternalBridgeProvider, GithubSearchProvider, TrafilaturaProvider, dispatch_search
from ..cache import get_cached_result, put_cached_result
from ..models import QualityAssessment

SERVER_NAME = "source-radar"
SERVER_VERSION = "0.1.0"

_DEFAULT_SEARCH_LIMIT = 5
_MAX_SEARCH_LIMIT = 10
_DEFAULT_FETCH_MAX_CHARS = 15000
_FETCH_TIMEOUT = 30
_FETCH_PAGE_TIMEOUT_SECONDS = 15
_QUALITY_VERSION = 2  # bump when quality assessment logic changes

_search_backend = "unknown"  # "searxng" | "fallback" | "unknown"
_search_backend_detail = ""

_searxng_autostart_enabled = True
_searxng_last_autostart_result = "skipped"  # "ok" | "failed" | "skipped"
_searxng_last_autostart_error = ""
_searxng_last_autostart_time = 0.0
_searxng_autostart_just_succeeded = False
_SEARXNG_AUTOSTART_COOLDOWN = 60  # seconds


def _searxng_search_ready() -> tuple[bool, str]:
    try:
        status = ExternalBridgeProvider("searxng", "SOURCE_RADAR_SEARXNG_ENDPOINT").status()
    except Exception as e:
        return False, str(e) or type(e).__name__
    if status.status in ("ok", "degraded"):
        return True, ""
    return False, status.message or status.reason or status.status


def _ensure_searxng_for_search() -> tuple[bool, str]:
    """Lazy-start SearXNG if not running. Returns (ok, detail)."""
    global _searxng_last_autostart_result, _searxng_last_autostart_error, _searxng_last_autostart_time
    global _searxng_autostart_just_succeeded
    import time as _time
    from ..engine import run_engine_start

    _searxng_autostart_just_succeeded = False

    ready, ready_detail = _searxng_search_ready()
    if ready:
        return True, ""

    now = _time.time()
    if now - _searxng_last_autostart_time < _SEARXNG_AUTOSTART_COOLDOWN:
        return False, _searxng_last_autostart_error or ready_detail

    _searxng_last_autostart_time = now
    print("source-radar: SearXNG 不可用，尝试自动启动...", file=__import__("sys").stderr)
    try:
        result = run_engine_start("searxng")
        print(f"source-radar: {result}", file=__import__("sys").stderr)
        ready, ready_detail = _searxng_search_ready()
        if ready:
            _searxng_last_autostart_result = "ok"
            _searxng_last_autostart_error = ""
            _searxng_autostart_just_succeeded = True
            return True, ""
        _searxng_last_autostart_result = "failed"
        _searxng_last_autostart_error = result if not ready_detail else f"{result}\n{ready_detail}"
        return False, _searxng_last_autostart_error
    except Exception as e:
        _searxng_last_autostart_result = "failed"
        _searxng_last_autostart_error = str(e) or type(e).__name__
        return False, _searxng_last_autostart_error


def _error_result(text: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=True,
    )


def _ok_result(text: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=False,
    )


def _validate_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return f"Invalid URL: {url}"
    if parsed.scheme not in ("http", "https"):
        return f"Only http/https URLs are allowed, got: {parsed.scheme or '(none)'}"
    hostname = parsed.hostname or ""
    if not hostname:
        return "URL has no hostname"
    if hostname.lower() in ("localhost", "0.0.0.0", "[::1]", "[::0]"):
        return f"Refused: {hostname} is a local address"
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
            return f"Refused: {hostname} is a local/private address"
    except ValueError:
        pass
    if hostname.endswith(".local") or hostname.endswith(".localhost"):
        return f"Refused: {hostname} looks like a local hostname"
    return None


def _format_search_results(query: str, results: list[dict[str, str]], cached: bool, quality: QualityAssessment | None = None,
                           backend: str = "unknown", backend_detail: str = "",
                           warnings: list[str] | None = None, autostarted: bool = False,
                           autostart_failed_detail: str = "", searxng_available: bool = False) -> str:
    lines = []
    # Backend line — brief, not alarming
    if backend == "searxng":
        lines.append("搜索后端: searxng")
        if autostarted:
            lines.append("服务状态: SearXNG 已自动启动")
    elif backend == "fallback":
        lines.append(f"搜索后端: fallback/{backend_detail}")
        if autostart_failed_detail:
            lines.append(f"⚠️ SearXNG 自动启动失败: {autostart_failed_detail}")
        else:
            lines.append("⚠️ SearXNG 未运行，当前结果不适合实时/长尾/专业查询。")
        lines.append("修复: source-radar engine install --searxng 或 source-radar engine start searxng")
    elif backend == "unknown":
        pass

    # Results header
    lines.append(f"搜索结果 (query: \"{query}\", {len(results)} 条):")
    if cached:
        lines[-1] += " [cached]"

    # Quality assessment — the primary signal
    if quality is not None and quality.score != "high":
        lines.append(f"⚠️ 质量: {quality.score} — {quality.reason}")
        if quality.suggestions:
            lines.append(f"💡 建议: {quality.suggestions[0]}")

    lines.append("")

    # Results list
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '(无标题)')}")
        lines.append(f"   URL: {r.get('url', '')}")
        snippet = r.get("snippet", "")
        if snippet:
            lines.append(f"   摘要: {snippet[:300]}")
        lines.append("")

    # Quality-based actionable suggestions
    if quality is not None and quality.score == "low":
        has_pro = any(_looks_professional_domain(r.get("url", "")) for r in results[:5])
        lines.append("---")
        # Engine warnings only when quality is low — they help explain why
        if warnings:
            lines.append("⚠️ 引擎异常可能影响结果质量:")
            for w in warnings:
                lines.append(f"  - {w}")
        lines.append("💡 下一步操作建议:")
        if has_pro:
            pro_indices = [str(i+1) for i, r in enumerate(results[:5]) if _looks_professional_domain(r.get("url", ""))]
            lines.append(f"  - 结果 {'/'.join(pro_indices)} 疑似专业站，建议调用 fetch_url 提取正文")
        lines.append(f"  - 优先对结果 1/2/3 调用 fetch_url 获取完整内容")
        lines.append(f"  - 如果目标是专业站，尝试 site:hltv.org / site:liquipedia.net 等限定搜索")
        lines.append(f"  - 或调用 fetch_search_results 一次性批量提取搜索结果正文")

    return "\n".join(lines)


def _looks_professional_domain(url: str) -> bool:
    """Check if URL looks like a professional/specialized domain."""
    professional_patterns = (
        "hltv.org", "liquipedia.net", "fandom.com", "github.com",
        "stackoverflow.com", "docs.", "wiki.", "arxiv.org",
        "steamdb.info", "dotabuff.com", "op.gg",
    )
    url_lower = url.lower()
    return any(p in url_lower for p in professional_patterns)


_REALTIME_KEYWORDS = ("比分", "赛程", "结果", "今天", "正在", "刚刚", "实时", "live", "score", "现在")


def _is_realtime_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _REALTIME_KEYWORDS)


def _format_fetch_result(
    url: str, content: str, raw_length: int, extractor: str, max_chars: int, cached: bool,
    page: int = 1, total_pages: int = 1,
) -> str:
    header = (
        f"页面正文 (来源: {url}, 提取器: {extractor}, "
        f"原始长度: {raw_length} 字符, 每页 {max_chars} 字符"
    )
    if total_pages > 1:
        header += f", page {page}/{total_pages}"
    if cached:
        header += ", cached"
    header += "):\n"
    return header + "\n" + content


def _format_github_results(query: str, results: list[dict[str, str]], cached: bool) -> str:
    lines = [f"GitHub 搜索结果 (query: \"{query}\", {len(results)} 条):"]
    if cached:
        lines[0] += " [cached]"
    lines.append("")
    for i, r in enumerate(results, 1):
        state = r.get("state", "")
        labels = r.get("labels", "")
        meta = f" [{state}]" if state else ""
        if labels:
            meta += f" ({labels})"
        lines.append(f"{i}. {r.get('title', '(无标题)')}{meta}")
        lines.append(f"   URL: {r.get('url', '')}")
        snippet = r.get("snippet", "")
        if snippet:
            lines.append(f"   摘要: {snippet[:500]}")
        lines.append("")
    return "\n".join(lines)


async def handle_search_github(arguments: dict[str, Any]) -> types.CallToolResult:
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)
    page = max(int(arguments.get("page", 1)), 1)
    nocache = bool(arguments.get("nocache", False))

    cache_key = f"{query} p{page}" if page > 1 else query
    if not nocache:
        cached, age = get_cached_result("github-search", query=cache_key, limit=limit, provider_signature="mcp")
        if cached and isinstance(cached, dict) and cached.get("results"):
            text = _format_github_results(query, cached["results"], cached=True)
            return _ok_result(text)

    provider = GithubSearchProvider()
    try:
        issues = provider.search_issues(query, limit, page=page)
    except Exception as e:
        error_text = str(e) or type(e).__name__
        return _error_result(
            f"GitHub search failed: {error_text}\nQuery: {query}\nProvider: github-search"
        )

    results = []
    for item in issues[:limit]:
        title = item.get("title", "")
        url = item.get("html_url", "")
        state = item.get("state", "")
        is_pr = "pull_request" in item
        kind = "PR" if is_pr else "Issue"
        labels = ", ".join(l.get("name", "") for l in item.get("labels", []))
        body = (item.get("body") or "")[:500]
        results.append({
            "title": title,
            "url": url,
            "snippet": body,
            "state": f"{kind} {state}",
            "labels": labels,
        })

    put_cached_result(
        "github-search", {"results": results}, query=cache_key, limit=limit, provider_signature="mcp",
    )

    if not results:
        return _ok_result(f"未找到关于 \"{query}\" 的 GitHub issues/PRs")

    text = _format_github_results(query, results, cached=False)
    return _ok_result(text)


_PLATFORM_NAMES = {
    "xhs": "小红书", "wb": "微博", "bili": "B站",
    "tieba": "贴吧", "dy": "抖音", "zhihu": "知乎",
}


def _format_chinese_platforms_results(query: str, items: list[dict], cached: bool) -> str:
    lines = [f"中文平台搜索结果 (query: \"{query}\", {len(items)} 条):"]
    if cached:
        lines[0] += " [cached]"
    lines.append("")
    for i, item in enumerate(items, 1):
        platform = item.get("platform", "")
        platform_name = _PLATFORM_NAMES.get(platform, platform)
        author = item.get("author", "")
        published = item.get("published_at", "")
        meta_parts = [f"[{platform_name}]"]
        if author:
            meta_parts.append(author)
        if published:
            meta_parts.append(published)
        lines.append(f"{i}. {' · '.join(meta_parts)}")
        lines.append(f"   {item.get('title', '(无标题)')}")
        lines.append(f"   URL: {item.get('url', '')}")
        snippet = item.get("snippet", "")
        if snippet:
            lines.append(f"   摘要: {snippet[:300]}")
        lines.append("")
    return "\n".join(lines)


async def handle_search_chinese_platforms(arguments: dict[str, Any]) -> types.CallToolResult:
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", 3)), 10)
    platforms = arguments.get("platforms") or None
    nocache = bool(arguments.get("nocache", False))

    cache_key = f"{query}|{','.join(sorted(platforms))}" if platforms else query
    if not nocache:
        cached, age = get_cached_result("mediacrawler", query=cache_key, limit=limit, provider_signature="mcp")
        if cached and isinstance(cached, dict) and cached.get("items"):
            text = _format_chinese_platforms_results(query, cached["items"], cached=True)
            return _ok_result(text)

    from ..acquisition import AcquisitionResult
    bridge = ExternalBridgeProvider("mediacrawler", "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT")
    status = bridge.status()

    if status.status != "ok":
        fix = status.fix or "Run: source-radar engine start mediacrawler"
        return _error_result(
            f"中文平台搜索不可用: {status.message}\n"
            f"修复: {fix}"
        )

    request = AcquisitionRequest(query=query, limit=limit, platforms=platforms)
    result = bridge.collect(request)

    if result.status == "error":
        return _error_result(
            f"中文平台搜索失败: {result.message}\n"
            f"Provider: {result.provider}"
        )

    items = []
    for item in result.items[:limit]:
        meta = item.metadata or {}
        items.append({
            "title": item.title or "",
            "url": item.url or "",
            "snippet": item.snippet or "",
            "platform": meta.get("platform", ""),
            "author": meta.get("author", ""),
            "published_at": meta.get("published_at", ""),
        })

    put_cached_result(
        "mediacrawler", {"items": items}, query=cache_key, limit=limit, provider_signature="mcp",
    )

    if not items:
        return _ok_result(f"中文平台未找到关于 \"{query}\" 的结果")

    text = _format_chinese_platforms_results(query, items, cached=False)
    return _ok_result(text)


def _normalize_site(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.startswith("site:"):
        s = s[5:]
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    s = s.strip().lower()
    return s or None


def _cache_is_fresh(cached: dict) -> bool:
    return cached.get("_quality_version") == _QUALITY_VERSION


async def handle_search(arguments: dict[str, Any]) -> types.CallToolResult:
    global _search_backend, _search_backend_detail
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)
    site = _normalize_site(arguments.get("site", ""))
    page = max(int(arguments.get("page", 1)), 1)
    nocache = bool(arguments.get("nocache", False))

    searxng_ok, searxng_fail_detail = await asyncio.to_thread(_ensure_searxng_for_search)

    cache_key_query = f"{query} site:{site}" if site else query
    if page > 1:
        cache_key_query = f"{cache_key_query} p{page}"
    if not nocache:
        cached, age = get_cached_result("search", query=cache_key_query, limit=limit, provider_signature="mcp")
        if cached and isinstance(cached, dict) and cached.get("results") and _cache_is_fresh(cached):
            cached_backend = cached.get("_backend", "unknown")
            # If cache is fallback but SearXNG is now up, skip cache and re-search
            if cached_backend == "fallback" and searxng_ok:
                pass  # fall through to fresh search
            else:
                display_query = f"{query} (site:{site})" if site else query
                cached_backend_detail = cached.get("_backend_detail", "")
                cached_warnings = list(cached.get("_warnings", []))
                text = _format_search_results(display_query, cached["results"], cached=True,
                                              backend=cached_backend, backend_detail=cached_backend_detail,
                                              warnings=cached_warnings)
                if cached_backend == "fallback" and _is_realtime_query(query):
                    text = "⚠️ 实时查询正在使用 fallback 搜索，结果可能严重过期或语义不相关，不能直接用于结论。\n\n" + text
                return _ok_result(text)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(dispatch_search, query, limit=limit, site=site, page=page),
            timeout=30,
        )
    except asyncio.TimeoutError:
        return _error_result(f"Search timeout after 30s\nQuery: {query}\nProvider: dispatch_search")

    if result.provider == "searxng":
        _search_backend = "searxng"
        _search_backend_detail = ""
    else:
        _search_backend = "fallback"
        _search_backend_detail = result.provider

    searxng_warnings = list(result.warnings) if result.warnings else []

    if result.status == "error":
        warning_text = ""
        if searxng_warnings:
            warning_text = "\nSearXNG diagnostics:\n" + "\n".join(f"- {w}" for w in searxng_warnings)
        return _error_result(
            f"Search failed: {result.message}\nQuery: {query}\nProvider: {result.provider}{warning_text}"
        )

    results = []
    for c in result.candidates[:limit]:
        results.append({
            "title": c.title or "",
            "url": c.url or "",
            "snippet": c.snippet or "",
        })

    put_cached_result(
        "search", {
            "results": results,
            "_quality_version": _QUALITY_VERSION,
            "_backend": _search_backend,
            "_backend_detail": _search_backend_detail,
            "_warnings": searxng_warnings,
        }, query=cache_key_query, limit=limit, provider_signature="mcp",
    )

    if not results:
        display_query = f"{query} (site:{site})" if site else query
        return _ok_result(f"未找到关于 \"{display_query}\" 的搜索结果")

    display_query = f"{query} (site:{site})" if site else query
    text = _format_search_results(display_query, results, cached=False, quality=result.quality,
                                  backend=_search_backend, backend_detail=_search_backend_detail,
                                  warnings=searxng_warnings,
                                  autostarted=_searxng_autostart_just_succeeded,
                                  autostart_failed_detail=searxng_fail_detail if _search_backend == "fallback" else "",
                                  searxng_available=searxng_ok)
    if _search_backend == "fallback" and _is_realtime_query(query):
        text = "⚠️ 实时查询正在使用 fallback 搜索，结果可能严重过期或语义不相关，不能直接用于结论。\n\n" + text
    return _ok_result(text)


async def handle_fetch(arguments: dict[str, Any]) -> types.CallToolResult:
    url = arguments.get("url", "").strip()
    if not url:
        return _error_result("Error: url is required")

    error = _validate_url(url)
    if error:
        return _error_result(f"Error: {error}")

    max_chars = min(int(arguments.get("max_chars", _DEFAULT_FETCH_MAX_CHARS)), 50000)
    page = max(int(arguments.get("page", 1)), 1)

    cached, age = get_cached_result("mcp:fetch", url=url, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("content"):
        raw_content = cached["content"]
        actual_len = len(raw_content)
        raw_length = cached.get("raw_length", actual_len)
        extractor = cached.get("extractor", "unknown")
        start = (page - 1) * max_chars
        content = raw_content[start:start + max_chars]
        if not content and page > 1:
            return _ok_result(f"页面正文已到末尾 (缓存长度 {actual_len} 字符, page {page} 无内容)")
        total_pages = (actual_len + max_chars - 1) // max_chars if actual_len else 1
        text = _format_fetch_result(url, content, raw_length, extractor, max_chars, cached=True, page=page, total_pages=total_pages)
        return _ok_result(text)

    request = AcquisitionRequest(query="", url=url, limit=1)

    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _collect_with_fallback, request),
            timeout=_FETCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return _error_result(
            f"Fetch timeout after {_FETCH_TIMEOUT}s\n"
            f"URL: {url}\n"
            f"Suggestion: try a simpler page or increase timeout"
        )
    except Exception as e:
        return _error_result(
            f"Fetch error: {type(e).__name__}: {e}\nURL: {url}"
        )

    if result.status == "error":
        return _error_result(
            f"Fetch failed: {result.message}\n"
            f"URL: {url}\n"
            f"Provider: {result.provider}"
        )

    if not result.items:
        return _error_result(
            f"无法提取正文内容\n"
            f"URL: {url}\n"
            f"Provider: {result.provider}\n"
            f"Suggestion: try built-in Fetch or another URL"
        )

    item = result.items[0]
    raw_content = item.raw_content or item.snippet or ""
    extractor = item.metadata.get("extractor", "trafilatura") if item.metadata else "trafilatura"
    raw_length = item.raw_content_length or len(raw_content)

    put_cached_result(
        "mcp:fetch",
        {"content": raw_content, "raw_length": raw_length, "extractor": extractor},
        url=url, provider_signature="mcp",
    )

    actual_len = len(raw_content)
    start = (page - 1) * max_chars
    content = raw_content[start:start + max_chars]
    if not content and page > 1:
        return _ok_result(f"页面正文已到末尾 (缓存长度 {actual_len} 字符, page {page} 无内容)")
    total_pages = (actual_len + max_chars - 1) // max_chars if actual_len else 1
    text = _format_fetch_result(url, content, raw_length, extractor, max_chars, cached=False, page=page, total_pages=total_pages)
    return _ok_result(text)


_CRAWL4AI_DOMAINS = (
    "liquipedia.net", "hltv.org", "fandom.com", "gamepedia.com",
    "esportsearnings.com",
)


def _collect_with_fallback(request):
    from ..acquisition import Crawl4AIProvider

    trafilatura = TrafilaturaProvider()
    result = trafilatura.collect(request)

    url = request.url or ""
    try:
        hostname = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        hostname = ""

    needs_crawl4ai = any(
        hostname == d or hostname.endswith("." + d) for d in _CRAWL4AI_DOMAINS
    )

    if result.items and result.items[0].raw_content:
        content = result.items[0].raw_content.strip()
        if len(content) >= 200 and not needs_crawl4ai:
            return result

    # Trafilatura fetched the page but found no/short content
    # Only fallback to Crawl4AI if:
    # 1. Wiki/forum domain (needs JS rendering), OR
    # 2. Trafilatura completely failed (no items at all)
    if result.items and not needs_crawl4ai:
        # Page was fetched but content is short — simple page, Crawl4AI won't help
        return result

    try:
        crawl4ai = Crawl4AIProvider()
        fallback = crawl4ai.collect(request)
        if fallback.items:
            if fallback.items[0].metadata is None:
                fallback.items[0].metadata = {}
            fallback.items[0].metadata["extractor"] = "crawl4ai"
            return fallback
    except ImportError:
        if needs_crawl4ai:
            from ..acquisition import AcquisitionResult as _AR
            return _AR(
                provider="crawl4ai", provider_type="generic-crawler",
                status="error", reason="dependency-missing",
                message=(
                    f"This page ({hostname}) requires Crawl4AI for proper extraction, "
                    "but Crawl4AI is not installed. Run: "
                    "uv run python -m source_radar engine install --browser"
                ),
            )
    except Exception as e:
        if needs_crawl4ai:
            error_text = str(e) or type(e).__name__
            from ..acquisition import AcquisitionResult as _AR
            return _AR(
                provider="crawl4ai", provider_type="generic-crawler",
                status="error", reason="crawl4ai-failed",
                message=(
                    f"This page ({hostname}) requires Crawl4AI for proper extraction, "
                    f"but Crawl4AI failed: {error_text}"
                ),
            )

    return result


async def handle_fetch_search_results(arguments: dict[str, Any]) -> types.CallToolResult:
    """Search + batch fetch: search first, then extract full text from top N URLs."""
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)
    site = _normalize_site(arguments.get("site", ""))
    page = max(int(arguments.get("page", 1)), 1)
    max_chars_per_page = min(int(arguments.get("max_chars_per_page", 5000)), 15000)
    fetch_count = min(int(arguments.get("fetch_count", 3)), 5)

    # Step 1: Search
    searxng_ok, searxng_fail_detail = await asyncio.to_thread(_ensure_searxng_for_search)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(dispatch_search, query, limit=limit, site=site, page=page),
            timeout=30,
        )
    except asyncio.TimeoutError:
        return _error_result(f"Search timeout after 30s\nQuery: {query}")
    if result.status == "error":
        return _error_result(f"Search failed: {result.message}")

    if not result.candidates:
        return _ok_result(f"未找到关于 \"{query}\" 的搜索结果")

    # Step 2: Batch fetch top N URLs
    lines = []
    if result.provider == "searxng":
        lines.append("搜索后端: searxng")
    else:
        lines.append(f"搜索后端: fallback/{result.provider}")
        if searxng_fail_detail:
            lines.append(f"⚠️ SearXNG 自动启动失败: {searxng_fail_detail}")
        elif searxng_ok:
            lines.append("⚠️ SearXNG 未返回可用搜索结果，已使用 fallback 搜索。")
            for w in result.warnings:
                lines.append(f"⚠️ {w}")
        else:
            lines.append("⚠️ SearXNG 未运行，提取结果可能不适合专业查询。")
    lines.append(f"搜索+提取结果 (query: \"{query}\", 搜索 {len(result.candidates)} 条, 提取 top {fetch_count}):")
    lines.append("")

    for i, candidate in enumerate(result.candidates[:fetch_count], 1):
        url = candidate.url or ""
        title = candidate.title or "(无标题)"
        lines.append(f"--- 结果 {i}: {title} ---")
        lines.append(f"URL: {url}")

        if not url:
            lines.append("提取: 跳过（无 URL）")
            lines.append("")
            continue

        # Validate URL
        error = _validate_url(url)
        if error:
            lines.append(f"提取: 跳过 — {error}")
            lines.append("")
            continue

        # Fetch content
        try:
            request = AcquisitionRequest(query="", url=url, limit=1)
            fetch_result = await asyncio.wait_for(
                asyncio.to_thread(_collect_with_fallback, request),
                timeout=_FETCH_PAGE_TIMEOUT_SECONDS,
            )
            if fetch_result.items:
                content = fetch_result.items[0].raw_content or fetch_result.items[0].snippet or ""
                extractor = fetch_result.items[0].metadata.get("extractor", "unknown")
                if len(content) > max_chars_per_page:
                    content = content[:max_chars_per_page] + f"\n... (截断，全文 {len(content)} 字符)"
                lines.append(f"提取器: {extractor}")
                lines.append(f"正文 ({len(content)} 字符):")
                lines.append(content if content else "(空)")
            else:
                lines.append(f"提取: 失败 — {fetch_result.message or '无内容'}")
        except asyncio.TimeoutError:
            lines.append(f"提取: 超时 — 超过 {_FETCH_PAGE_TIMEOUT_SECONDS} 秒")
        except Exception as e:
            lines.append(f"提取: 异常 — {str(e) or type(e).__name__}")

        lines.append("")

    # Add remaining search results as references
    if len(result.candidates) > fetch_count:
        lines.append(f"--- 其余搜索结果（未提取正文）---")
        for i, c in enumerate(result.candidates[fetch_count:], fetch_count + 1):
            lines.append(f"{i}. {c.title or '(无标题)'}")
            lines.append(f"   URL: {c.url or ''}")
            if c.snippet:
                lines.append(f"   摘要: {c.snippet[:200]}")

    return _ok_result("\n".join(lines))


async def handle_source_status(arguments: dict[str, Any]) -> types.CallToolResult:
    import os
    from ..engine import _http_ok, _searxng_health_check, _root
    from ..acquisition import ExternalBridgeProvider

    lines = ["=== source-radar 环境状态 ===", ""]

    searxng_bridge_ok = _http_ok("http://127.0.0.1:3004/health")
    searxng_state = "unknown"
    searxng_fix = ""
    if searxng_bridge_ok:
        health = _searxng_health_check("http://127.0.0.1:8888")
        if health["status"] == "ok":
            searxng_state = "running"
            lines.append("searxng: running")
        elif health["status"] == "degraded":
            searxng_state = "degraded"
            searxng_fix = str(health.get("fix", ""))
            lines.append(f"searxng: degraded — {health.get('reason', '')}")
            diag = health.get("diagnostics", {})
            if diag.get("captcha_engines"):
                lines.append(f"  captcha_engines: {diag['captcha_engines']}")
            if searxng_fix:
                lines.append(f"  fix: {searxng_fix}")
        else:
            searxng_state = str(health["status"])
            searxng_fix = str(health.get("fix", ""))
            lines.append(f"searxng: {health['status']} — {health.get('message', '')}")
    else:
        searxng_installed = (_root() / "external" / "searxng").exists()
        if searxng_installed:
            searxng_state = "stopped"
            lines.append("searxng: stopped")
            lines.append("  修复: source-radar engine start searxng")
        else:
            searxng_state = "missing"
            lines.append("searxng: missing")
            lines.append("  修复: source-radar engine install --searxng")

    lines.append(f"last_search_backend: {_search_backend}")
    lines.append(f"searxng_autostart: {'enabled' if _searxng_autostart_enabled else 'disabled'}")
    lines.append(f"last_autostart_result: {_searxng_last_autostart_result}")

    mc_bridge = ExternalBridgeProvider("mediacrawler", "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT")
    mc_status = mc_bridge.status()
    if mc_status.status == "ok":
        lines.append("mediacrawler: running")
    elif mc_status.status == "disabled":
        lines.append("mediacrawler: not configured")
    else:
        lines.append(f"mediacrawler: {mc_status.status} — {mc_status.reason}")

    from ..cache import cache_status
    cs = cache_status()
    total_mb = round(cs.get("total_bytes", 0) / 1024 / 1024, 2)
    lines.append(f"cache: {cs.get('entry_count', 0)} entries, {total_mb} MB")

    lines.append("")
    lines.append("recommended fixes:")
    if searxng_state in ("stopped", "missing", "error"):
        lines.append("  source-radar engine start searxng")
        lines.append("  或: source-radar mcp --with-services")
    elif searxng_state == "degraded" and searxng_fix:
        lines.append(f"  {searxng_fix}")
    if mc_status.status != "ok":
        lines.append("  source-radar engine start mediacrawler")

    return _ok_result("\n".join(lines))


def _github_api_get(url: str) -> dict | list:
    """Call GitHub API with optional token auth."""
    from urllib.request import Request, urlopen
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = __import__("os").environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_github_file_url(url: str) -> tuple[str, str, str] | None:
    """Parse GitHub URL into (repo, path, ref). Returns None if not a valid GitHub file URL."""
    m = _re.match(
        r"https?://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.+)",
        url.strip(),
    )
    if m:
        return m.group(1), m.group(3), m.group(2)
    return None


async def handle_fetch_github_file(arguments: dict[str, Any]) -> types.CallToolResult:
    url = arguments.get("url", "").strip()
    repo = arguments.get("repo", "").strip()
    path = arguments.get("path", "").strip()
    ref = arguments.get("ref", "").strip() or "main"
    max_chars = min(int(arguments.get("max_chars", _DEFAULT_FETCH_MAX_CHARS)), 50000)
    page = max(int(arguments.get("page", 1)), 1)

    # Parse URL if provided
    if url and not repo:
        parsed = _parse_github_file_url(url)
        if not parsed:
            return _error_result(f"Error: not a valid GitHub file URL: {url}")
        repo, path, ref = parsed

    if not repo:
        return _error_result("Error: repo is required (e.g. 'owner/name' or use url)")
    if not path:
        return _error_result("Error: path is required (e.g. 'README.md')")

    # Cache key includes repo + path + ref
    cache_key = f"{repo}/{path}@{ref}"
    cached, age = get_cached_result("github-file", url=cache_key, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("content"):
        full = cached["content"]
        actual_len = len(full)
        start = (page - 1) * max_chars
        content = full[start:start + max_chars]
        if not content and page > 1:
            return _ok_result(f"GitHub 文件已到末尾 ({actual_len} 字符, page {page} 无内容)")
        total_pages = (actual_len + max_chars - 1) // max_chars if actual_len else 1
        page_info = f", page {page}/{total_pages}" if total_pages > 1 else ""
        return _ok_result(
            f"GitHub 文件 ({repo}/{path} @ {ref}, {cached.get('size', '?')} bytes{page_info}, cached):\n\n"
            + content
        )

    api_url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}?ref={urllib.parse.quote(ref, safe='')}"
    try:
        data = _github_api_get(api_url)
    except Exception as e:
        code = getattr(e, "code", None)
        if code == 404:
            return _error_result(f"Error: file not found: {repo}/{path} @ {ref}\nGitHub API returned 404")
        error_text = str(e) or type(e).__name__
        return _error_result(f"Error: GitHub API failed: {error_text}\nURL: {api_url}")

    # If it's a directory listing, not a file
    if isinstance(data, list):
        entries = [f"{d.get('name', '')} ({d.get('type', '')})" for d in data[:20]]
        return _error_result(
            f"Error: {repo}/{path} is a directory, not a file.\n"
            f"Contents: {', '.join(entries)}"
        )

    if not isinstance(data, dict):
        return _error_result(f"Error: unexpected response from GitHub API")

    content_b64 = data.get("content", "")
    encoding = data.get("encoding", "")
    size = data.get("size", 0)

    if encoding == "base64" and content_b64:
        try:
            content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except Exception:
            return _error_result(f"Error: failed to decode file content from {repo}/{path}")
    else:
        return _error_result(f"Error: unsupported encoding: {encoding}")

    put_cached_result(
        "github-file",
        {"content": content, "size": size},
        url=cache_key, provider_signature="mcp",
    )

    actual_len = len(content)
    start = (page - 1) * max_chars
    display = content[start:start + max_chars]
    if not display and page > 1:
        return _ok_result(f"GitHub 文件已到末尾 ({actual_len} 字符, page {page} 无内容)")
    total_pages = (actual_len + max_chars - 1) // max_chars if actual_len else 1
    page_info = f", page {page}/{total_pages}" if total_pages > 1 else ""
    suffix = "" if actual_len <= max_chars and page == 1 else ""
    return _ok_result(
        f"GitHub 文件 ({repo}/{path} @ {ref}, {size} bytes{page_info}):\n\n"
        + display
    )


def create_server() -> Server:
    server = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="web_search",
                description="Search the web using Bing. Returns a list of results with title, URL, and snippet.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results (default 5, max 10)",
                            "default": 5,
                        },
                        "site": {
                            "type": "string",
                            "description": "限定搜索结果到指定域名，如 'hltv.org' 或 'github.com'。不带 http:// 和路径。留空则搜全网。",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (default 1). Paginates within cached candidate pool (~30 results).",
                            "default": 1,
                        },
                        "nocache": {
                            "type": "boolean",
                            "description": "Skip cache and fetch fresh results (default false)",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="fetch_url",
                description=(
                    "Fetch and extract the main text content of a web page. "
                    "Uses Trafilatura for static pages, falls back to Crawl4AI for dynamic ones."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch (http/https only)",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters per page (default 15000)",
                            "default": 15000,
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number for long documents (default 1). page=2 returns the next chunk.",
                            "default": 1,
                        },
                    },
                    "required": ["url"],
                },
            ),
            types.Tool(
                name="search_github",
                description="Search GitHub issues and pull requests. Returns results with title, URL, state, and snippet.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results (default 5, max 10)",
                            "default": 5,
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (default 1)",
                            "default": 1,
                        },
                        "nocache": {
                            "type": "boolean",
                            "description": "Skip cache and fetch fresh results (default false)",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="search_chinese_platforms",
                description="Search Chinese community platforms (小红书/微博/B站/贴吧/抖音/知乎). Requires MediaCrawler bridge running.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Platform keys to search (xhs, wb, bili, tieba, dy, zhihu). Empty = all configured.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Results per platform (default 3, max 10)",
                            "default": 3,
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (default 1). Note: not supported by bridge yet.",
                            "default": 1,
                        },
                        "nocache": {
                            "type": "boolean",
                            "description": "Skip cache and fetch fresh results (default false)",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="fetch_github_file",
                description="Fetch a file from a GitHub repository. Returns raw file content. Supports repo+path or full GitHub URL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "Repository in owner/name format (e.g. 'Narylr350/source-radar')",
                        },
                        "path": {
                            "type": "string",
                            "description": "File path in the repo (e.g. 'README.md', 'src/index.ts')",
                        },
                        "ref": {
                            "type": "string",
                            "description": "Branch, tag, or commit (default 'main')",
                            "default": "main",
                        },
                        "url": {
                            "type": "string",
                            "description": "Full GitHub URL (alternative to repo+path). e.g. 'https://github.com/owner/repo/blob/main/README.md'",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to return (default 15000)",
                            "default": 15000,
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number for long files (default 1). page=2 returns the next chunk.",
                            "default": 1,
                        },
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name="fetch_search_results",
                description=(
                    "Search + batch fetch: search first, then extract full text from top N URLs. "
                    "Returns search results with full page content/extracts. "
                    "Use when web_search snippets are not enough and you need full page content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of search results (default 5, max 10)",
                            "default": 5,
                        },
                        "site": {
                            "type": "string",
                            "description": "限定搜索结果到指定域名，如 'hltv.org' 或 'github.com'。不带 http:// 和路径。留空则搜全网。",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (default 1). Paginates within cached candidate pool (~30 results).",
                            "default": 1,
                        },
                        "fetch_count": {
                            "type": "integer",
                            "description": "How many top results to fetch full text (default 3, max 5)",
                            "default": 3,
                        },
                        "max_chars_per_page": {
                            "type": "integer",
                            "description": "Max characters per fetched page (default 5000, max 15000)",
                            "default": 5000,
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="source_status",
                description=(
                    "返回 source-radar 环境状态：SearXNG、搜索后端、MediaCrawler、缓存。"
                    "外部 AI 在开始复杂搜索前可以先调用它。"
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "web_search":
                return await handle_search(arguments)
            if name == "fetch_url":
                return await handle_fetch(arguments)
            if name == "search_github":
                return await handle_search_github(arguments)
            if name == "search_chinese_platforms":
                return await handle_search_chinese_platforms(arguments)
            if name == "fetch_github_file":
                return await handle_fetch_github_file(arguments)
            if name == "fetch_search_results":
                return await handle_fetch_search_results(arguments)
            if name == "source_status":
                return await handle_source_status(arguments)
            return _error_result(f"Unknown tool: {name}")
        except Exception as e:
            error_text = str(e) or type(e).__name__
            return _error_result(f"Error: {error_text}")

    return server


async def _run_server() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_stdio() -> None:
    asyncio.run(_run_server())


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
