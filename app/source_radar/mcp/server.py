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

from ..acquisition import AcquisitionRequest, BingSearchProvider, TrafilaturaProvider
from ..cache import get_cached_result, put_cached_result

SERVER_NAME = "source-radar"
SERVER_VERSION = "0.1.0"

_DEFAULT_SEARCH_LIMIT = 5
_MAX_SEARCH_LIMIT = 10
_DEFAULT_FETCH_MAX_CHARS = 8000
_FETCH_TIMEOUT = 30


def _validate_url(url: str) -> str | None:
    """Return error message if URL is unsafe, None if OK."""
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


async def handle_search(arguments: dict[str, Any]) -> list[types.TextContent]:
    query = arguments.get("query", "").strip()
    if not query:
        return [types.TextContent(type="text", text="Error: query is required", isError=True)]

    limit = min(int(arguments.get("limit", _DEFAULT_SEARCH_LIMIT)), _MAX_SEARCH_LIMIT)

    cached, age = get_cached_result("search", query=query, limit=limit, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("results"):
        text = _format_search_results(query, cached["results"], cached=True)
        return [types.TextContent(type="text", text=text)]

    provider = BingSearchProvider()
    result = provider.collect(AcquisitionRequest(query=query, limit=limit))

    if result.status == "error":
        return [types.TextContent(
            type="text",
            text=f"Search failed: {result.message}",
            isError=True,
        )]

    results = []
    for c in result.candidates[:limit]:
        results.append({
            "title": c.title or "",
            "url": c.url or "",
            "snippet": c.snippet or "",
        })

    put_cached_result(
        "search", {"results": results}, query=query, limit=limit, provider_signature="mcp",
    )

    if not results:
        return [types.TextContent(type="text", text=f"未找到关于 \"{query}\" 的搜索结果")]

    text = _format_search_results(query, results, cached=False)
    return [types.TextContent(type="text", text=text)]


async def handle_fetch(arguments: dict[str, Any]) -> list[types.TextContent]:
    url = arguments.get("url", "").strip()
    if not url:
        return [types.TextContent(type="text", text="Error: url is required", isError=True)]

    error = _validate_url(url)
    if error:
        return [types.TextContent(type="text", text=f"Error: {error}", isError=True)]

    max_chars = min(int(arguments.get("max_chars", _DEFAULT_FETCH_MAX_CHARS)), 50000)

    cached, age = get_cached_result("mcp:fetch", url=url, provider_signature="mcp")
    if cached and isinstance(cached, dict) and cached.get("content"):
        content = cached["content"][:max_chars]
        text = _format_fetch_result(
            url, content, cached.get("raw_length", len(content)),
            cached.get("extractor", "unknown"), max_chars, cached=True,
        )
        return [types.TextContent(type="text", text=text)]

    request = AcquisitionRequest(query="", url=url, limit=1)

    loop = asyncio.get_event_loop()
    result = await asyncio.wait_for(
        loop.run_in_executor(None, _collect_with_fallback, request),
        timeout=_FETCH_TIMEOUT,
    )

    if result.status == "error":
        return [types.TextContent(
            type="text",
            text=f"Fetch failed: {result.message}",
            isError=True,
        )]

    if not result.items:
        return [types.TextContent(
            type="text",
            text=f"无法提取 {url} 的正文内容",
            isError=True,
        )]

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
    return [types.TextContent(type="text", text=text)]


def _collect_with_fallback(request):
    from ..acquisition import Crawl4AIProvider

    trafilatura = TrafilaturaProvider()
    result = trafilatura.collect(request)
    if result.items and result.items[0].raw_content:
        if len(result.items[0].raw_content.strip()) >= 200:
            return result

    try:
        crawl4ai = Crawl4AIProvider()
        fallback = crawl4ai.collect(request)
        if fallback.items:
            if fallback.items[0].metadata is None:
                fallback.items[0].metadata = {}
            fallback.items[0].metadata["extractor"] = "crawl4ai"
            return fallback
    except Exception:
        pass

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
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            if name == "web_search":
                return await handle_search(arguments)
            if name == "fetch_url":
                return await handle_fetch(arguments)
            return [types.TextContent(type="text", text=f"Unknown tool: {name}", isError=True)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {e}", isError=True)]

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
