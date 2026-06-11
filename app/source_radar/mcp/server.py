import asyncio
import ipaddress
import sys
import urllib.parse
from typing import Any

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..acquisition import AcquisitionRequest, BingSearchProvider, ExternalBridgeProvider, GithubSearchProvider, TrafilaturaProvider
from ..cache import get_cached_result, put_cached_result

SERVER_NAME = "source-radar"
SERVER_VERSION = "0.1.0"

_DEFAULT_SEARCH_LIMIT = 5
_MAX_SEARCH_LIMIT = 10
_DEFAULT_FETCH_MAX_CHARS = 8000
_FETCH_TIMEOUT = 30


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


def _format_search_results(query: str, results: list[dict[str, str]], cached: bool) -> str:
    lines = [f"搜索结果 (query: \"{query}\", {len(results)} 条):"]
    if cached:
        lines[0] += " [cached]"
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '(无标题)')}")
        lines.append(f"   URL: {r.get('url', '')}")
        snippet = r.get("snippet", "")
        if snippet:
            lines.append(f"   摘要: {snippet[:300]}")
        lines.append("")
    return "\n".join(lines)


def _format_fetch_result(
    url: str, content: str, raw_length: int, extractor: str, max_chars: int, cached: bool,
) -> str:
    header = (
        f"页面正文 (来源: {url}, 提取器: {extractor}, "
        f"原始长度: {raw_length} 字符, 截取前 {max_chars} 字符"
    )
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
            lines.append(f"   摘要: {snippet[:300]}")
        lines.append("")
    return "\n".join(lines)


async def handle_search_github(arguments: dict[str, Any]) -> types.CallToolResult:
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)
    page = max(int(arguments.get("page", 1)), 1)

    cache_key = f"{query} p{page}" if page > 1 else query
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
        body = (item.get("body") or "")[:300]
        results.append({
            "title": title,
            "url": url,
            "snippet": body,
            "state": f"{kind} {state}",
            "labels": labels,
        })

    put_cached_result(
        "github-search", {"results": results}, query=query, limit=limit, provider_signature="mcp",
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

    cache_key = f"{query}|{','.join(sorted(platforms))}" if platforms else query
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


async def handle_search(arguments: dict[str, Any]) -> types.CallToolResult:
    query = arguments.get("query", "").strip()
    if not query:
        return _error_result("Error: query is required")

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)
    site = _normalize_site(arguments.get("site", ""))
    page = max(int(arguments.get("page", 1)), 1)

    cache_key_query = f"{query} site:{site}" if site else query
    if page > 1:
        cache_key_query = f"{cache_key_query} p{page}"
    cached, age = get_cached_result("search", query=cache_key_query, limit=limit, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("results"):
        display_query = f"{query} (site:{site})" if site else query
        text = _format_search_results(display_query, cached["results"], cached=True)
        return _ok_result(text)

    provider = BingSearchProvider()
    result = provider.collect(AcquisitionRequest(query=query, limit=limit, site=site, page=page))

    if result.status == "error":
        return _error_result(
            f"Search failed: {result.message}\nQuery: {query}\nProvider: {result.provider}"
        )

    results = []
    for c in result.candidates[:limit]:
        results.append({
            "title": c.title or "",
            "url": c.url or "",
            "snippet": c.snippet or "",
        })

    put_cached_result(
        "search", {"results": results}, query=cache_key_query, limit=limit, provider_signature="mcp",
    )

    if not results:
        display_query = f"{query} (site:{site})" if site else query
        return _ok_result(f"未找到关于 \"{display_query}\" 的搜索结果")

    display_query = f"{query} (site:{site})" if site else query
    text = _format_search_results(display_query, results, cached=False)
    return _ok_result(text)


async def handle_fetch(arguments: dict[str, Any]) -> types.CallToolResult:
    url = arguments.get("url", "").strip()
    if not url:
        return _error_result("Error: url is required")

    error = _validate_url(url)
    if error:
        return _error_result(f"Error: {error}")

    max_chars = min(int(arguments.get("max_chars", _DEFAULT_FETCH_MAX_CHARS)), 50000)

    cached, age = get_cached_result("mcp:fetch", url=url, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("content"):
        content = cached["content"][:max_chars]
        text = _format_fetch_result(
            url, content, cached.get("raw_length", len(content)),
            cached.get("extractor", "unknown"), max_chars, cached=True,
        )
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

    content = raw_content[:max_chars]
    text = _format_fetch_result(url, content, raw_length, extractor, max_chars, cached=False)
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
                            "description": "Restrict results to this domain (e.g. 'hltv.org', 'liquipedia.net')",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (default 1). Note: cn.bing.com may not support pagination.",
                            "default": 1,
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
                            "description": "Maximum characters to return (default 8000)",
                            "default": 8000,
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
                    },
                    "required": ["query"],
                },
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
