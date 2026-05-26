import argparse
import concurrent.futures
import json
import os
import pathlib
import shlex
import subprocess
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import BinaryIO, Callable
from urllib.request import Request, urlopen


JsonPayload = dict[str, object]
RequestJson = Callable[[str, str, JsonPayload | None, int], JsonPayload]
McpCall = Callable[[str, str, JsonPayload, dict[str, str], int], JsonPayload]

PLATFORM_COOKIE_ENVS: dict[str, str] = {
    "xhs": "SOURCE_RADAR_XHS_COOKIE",
    "wb": "SOURCE_RADAR_WEIBO_COOKIE",
    "bili": "SOURCE_RADAR_BILI_COOKIE",
    "tieba": "SOURCE_RADAR_TIEBA_COOKIE",
    "dy": "SOURCE_RADAR_DOUYIN_COOKIE",
}


class FirecrawlBridgeBackend:
    provider = "firecrawl"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        transport: str = "mcp",
        mcp_command: str = "",
        timeout_seconds: int = 60,
        mcp_call: McpCall | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.mcp_command = mcp_command.strip()
        self.timeout_seconds = timeout_seconds
        self._mcp_call = mcp_call or _call_mcp_tool

    def manifest(self) -> JsonPayload:
        return {
            "provider": self.provider,
            "contract_version": "source-radar.bridge.v1",
            "capabilities": [{"name": "search"}],
            "transport": self.transport,
            "ai_guidance": "Use for broad web discovery, documentation, tutorials, and normal pages.",
        }

    def health(self) -> JsonPayload:
        if self.transport == "mcp" and not (self.api_key or self.api_url):
            return _needs_firecrawl_mcp_auth()
        return {
            "status": "ok",
            "reason": "ready",
            "message": "Firecrawl bridge is configured and ready.",
            "diagnostics": {
                "transport": self.transport,
                "api_url": self.api_url,
                "auth": "configured" if self.api_key else "none",
                "mcp_command": self.mcp_command if self.transport == "mcp" else "",
            },
        }

    def collect(self, payload: JsonPayload) -> JsonPayload:
        query = str(payload.get("query") or "").strip()
        limit = _limit(payload.get("limit"))
        if not query:
            return _needs_query(self.provider)
        if self.transport == "mcp":
            if not (self.api_key or self.api_url):
                return _needs_firecrawl_mcp_auth()
            try:
                response = self._mcp_call(
                    self.mcp_command or "npx -y firecrawl-mcp",
                    "firecrawl_search",
                    {"query": query, "limit": limit},
                    _firecrawl_mcp_env(self.api_key, self.api_url),
                    self.timeout_seconds,
                )
            except Exception as error:
                return _unreachable(
                    self.provider,
                    error,
                    "Check FIRECRAWL_API_KEY and the firecrawl-mcp command, then retry.",
                )
            payload = _mcp_tool_payload(response)
            items = [_firecrawl_item(item) for item in _records(payload) if _item_url(item)]
            return _items_payload(self.provider, items, query=query)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = _post_json(
                f"{self.api_url}/v1/search",
                {"query": query, "limit": limit},
                headers,
            )
        except Exception as error:
            return _unreachable(self.provider, error, "Check the Firecrawl API URL and API key.")
        items = [_firecrawl_item(item) for item in _records(response) if _item_url(item)]
        return _items_payload(self.provider, items, query=query)


class MediaCrawlerBridgeBackend:
    provider = "mediacrawler"
    platforms = ["xiaohongshu", "xhs", "douyin", "dy", "bilibili", "bili", "weibo", "wb", "tieba", "zhihu"]

    def __init__(
        self,
        *,
        api_url: str,
        platform: str = "xhs",
        login_type: str = "cookie",
        cookies: str = "",
        cookies_map: dict[str, str] | None = None,
        timeout_seconds: int = 120,
        sleep_seconds: float = 2,
        request_json: RequestJson | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.platforms = _platform_aliases(platform)
        self.platform = self.platforms[0]
        self.login_type = login_type
        # cookies_map takes precedence; cookies is a fallback for single-platform compat
        if cookies_map is not None:
            self.cookies_map = {p: c for p, c in cookies_map.items() if c}
        elif cookies:
            self.cookies_map = {p: cookies for p in self.platforms}
        else:
            self.cookies_map = {}
        self.cookies = cookies
        self.timeout_seconds = timeout_seconds
        self.sleep_seconds = sleep_seconds
        self._request_json = request_json or _request_json

    def manifest(self) -> JsonPayload:
        return {
            "provider": self.provider,
            "contract_version": "source-radar.bridge.v1",
            "capabilities": [{"name": "search"}],
            "platforms": ["xiaohongshu", "bilibili", "weibo", "tieba", "douyin", "zhihu"],
            "ai_guidance": "Use for Chinese community posts, experience reports, tests, cases, and discussion sources.",
        }

    def health(self) -> JsonPayload:
        if self.login_type == "cookie" and not self.cookies_map:
            return {
                "status": "needs-input",
                "reason": "missing-cookies",
                "message": "MediaCrawler bridge has no cookies configured; collection will be skipped.",
                "fix": "Set SOURCE_RADAR_XHS_COOKIE (or other platform cookie env vars) before starting the bridge.",
                "retryable": False,
                "diagnostics": {
                    "api_url": self.api_url,
                    "platform": self.platform,
                    "platforms": ",".join(self.platforms),
                    "active_platforms": ",".join(self._active_platforms()),
                    "login_type": self.login_type,
                },
            }
        try:
            response = self._request_json("GET", f"{self.api_url}/api/health", None, 10)
        except Exception as error:
            return _unreachable(
                self.provider,
                error,
                "Start MediaCrawler WebUI API with `uv run uvicorn api.main:app --port 8080`.",
            )
        return {
            "status": str(response.get("status") or "ok"),
            "reason": "ready",
            "message": str(response.get("message") or "MediaCrawler API is reachable."),
            "diagnostics": {
                "api_url": self.api_url,
                "platform": self.platform,
                "platforms": ",".join(self.platforms),
                "active_platforms": ",".join(self._active_platforms()),
                "login_type": self.login_type,
            },
        }

    def collect(self, payload: JsonPayload) -> JsonPayload:
        query = str(payload.get("query") or "").strip()
        limit = _limit(payload.get("limit"))
        if not query:
            return _needs_query(self.provider)
        active = self._active_platforms()
        if not active and self.login_type == "cookie":
            return {
                "status": "needs-input",
                "reason": "missing-cookies",
                "message": "No platforms have cookies configured; set SOURCE_RADAR_XHS_COOKIE or other platform cookie env vars.",
                "retryable": False,
                "items": [],
            }
        items: list[JsonPayload] = []
        warnings: list[str] = []
        for platform in active:
            try:
                items.extend(self._collect_platform(query, limit, platform))
            except Exception as error:
                warnings.append(f"{platform}: {error}")
        payload = _items_payload(self.provider, items[:limit], query=query)
        if warnings:
            payload["warnings"] = warnings
        return payload

    def _active_platforms(self) -> list[str]:
        if self.login_type != "cookie":
            return self.platforms
        return [p for p in self.platforms if self.cookies_map.get(p)]

    def _collect_platform(self, query: str, limit: int, platform: str) -> list[JsonPayload]:
        cookie = self.cookies_map.get(platform, self.cookies)
        start_payload = {
            "platform": platform,
            "login_type": self.login_type,
            "crawler_type": "search",
            "keywords": query,
            "start_page": 1,
            "enable_comments": False,
            "enable_sub_comments": False,
            "save_option": "json",
            "cookies": cookie,
            "headless": True,
        }
        self._request_json("POST", f"{self.api_url}/api/crawler/start", start_payload, 30)
        status = self._wait_until_idle()
        if status.get("status") not in {"idle", "ok"}:
            raise RuntimeError("MediaCrawler task did not finish cleanly.")
        files = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files?"
            + urllib.parse.urlencode({"platform": platform, "file_type": "json"}),
            None,
            30,
        )
        file_path = _newest_file_path(files)
        if not file_path:
            return []
        preview = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files/{urllib.parse.quote(file_path)}?"
            + urllib.parse.urlencode({"preview": "true", "limit": str(limit)}),
            None,
            30,
        )
        return [_mediacrawler_item(item, platform) for item in _records(preview) if _item_url(item)]

    def _wait_until_idle(self) -> JsonPayload:
        deadline = time.time() + self.timeout_seconds
        latest: JsonPayload = {}
        while time.time() <= deadline:
            latest = self._request_json("GET", f"{self.api_url}/api/crawler/status", None, 30)
            if latest.get("status") in {"idle", "error"}:
                return latest
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)
        return {
            "status": "error",
            "error_message": f"MediaCrawler task timed out after {self.timeout_seconds} seconds.",
        }


def serve_bridge(backend: FirecrawlBridgeBackend | MediaCrawlerBridgeBackend, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/manifest":
                return self._json(backend.manifest())
            if self.path == "/health":
                return self._json(backend.health())
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path != "/collect":
                self.send_response(404)
                self.end_headers()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if not isinstance(payload, dict):
                    payload = {}
            except json.JSONDecodeError:
                payload = {}
            self._json(backend.collect(payload))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _json(self, payload: JsonPayload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    HTTPServer((host, port), Handler).serve_forever()


def add_bridge_subparsers(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="bridge_provider", required=True)
    firecrawl = subparsers.add_parser("firecrawl", help="run a Firecrawl source-radar bridge")
    firecrawl.add_argument("--host", default="127.0.0.1")
    firecrawl.add_argument("--port", type=int, default=3002)
    firecrawl.add_argument("--transport", choices=("mcp", "api"), default="")
    firecrawl.add_argument("--api-url", default="")
    firecrawl.add_argument("--api-key", default="")
    firecrawl.add_argument("--mcp-command", default="")
    firecrawl.add_argument("--timeout", type=int, default=60)
    mediacrawler = subparsers.add_parser("mediacrawler", help="run a MediaCrawler source-radar bridge")
    mediacrawler.add_argument("--host", default="127.0.0.1")
    mediacrawler.add_argument("--port", type=int, default=3003)
    mediacrawler.add_argument("--api-url", default="")
    mediacrawler.add_argument("--platform", default="")
    mediacrawler.add_argument("--login-type", default="")
    mediacrawler.add_argument("--timeout", type=int, default=120)


def build_bridge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-radar bridge")
    add_bridge_subparsers(parser)
    return parser


def run_bridge_from_args(args: argparse.Namespace) -> None:
    load_local_env()
    if args.bridge_provider == "firecrawl":
        transport = args.transport or os.environ.get("FIRECRAWL_TRANSPORT", "mcp")
        api_url = args.api_url or os.environ.get("FIRECRAWL_API_URL", "")
        if transport == "api" and not api_url:
            api_url = "https://api.firecrawl.dev"
        backend = FirecrawlBridgeBackend(
            api_url=api_url,
            api_key=args.api_key or os.environ.get("FIRECRAWL_API_KEY", ""),
            transport=transport,
            mcp_command=args.mcp_command or os.environ.get("FIRECRAWL_MCP_COMMAND", "npx -y firecrawl-mcp"),
            timeout_seconds=args.timeout,
        )
    elif args.bridge_provider == "mediacrawler":
        cookies_map = {p: os.environ.get(env, "") for p, env in PLATFORM_COOKIE_ENVS.items()}
        requested_platforms = args.platform or os.environ.get("MEDIACRAWLER_PLATFORM", ",".join(PLATFORM_COOKIE_ENVS))
        backend = MediaCrawlerBridgeBackend(
            api_url=args.api_url or os.environ.get("MEDIACRAWLER_API_URL", "http://127.0.0.1:8080"),
            platform=requested_platforms,
            login_type=args.login_type or os.environ.get("MEDIACRAWLER_LOGIN_TYPE", "cookie"),
            cookies_map=cookies_map,
            timeout_seconds=args.timeout,
        )
    else:
        raise ValueError(f"unknown bridge provider: {args.bridge_provider}")
    serve_bridge(backend, args.host, args.port)


def load_local_env(root: str | os.PathLike[str] = ".") -> None:
    path = pathlib.Path(root) / ".source-radar" / "local.env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _post_json(url: str, payload: JsonPayload, headers: dict[str, str]) -> JsonPayload:
    return _request_json("POST", url, payload, 30, headers=headers)


def _request_json(
    method: str,
    url: str,
    payload: JsonPayload | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> JsonPayload:
    data = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def _call_mcp_tool(
    command: str,
    tool_name: str,
    arguments: JsonPayload,
    env: dict[str, str],
    timeout: int,
) -> JsonPayload:
    args = shlex.split(command, posix=os.name != "nt")
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("MCP process did not expose stdio.")
    try:
        _mcp_send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "source-radar", "version": "0"},
                },
            },
        )
        _mcp_read_response(process, 1, timeout)
        _mcp_send(
            process.stdin,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        _mcp_send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        return _mcp_read_response(process, 2, timeout)
    finally:
        _stop_process(process)


def _mcp_send(stream: BinaryIO, payload: JsonPayload) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def _mcp_read_response(process: subprocess.Popen[bytes], request_id: int, timeout: int) -> JsonPayload:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        while True:
            future = executor.submit(_read_mcp_message, process.stdout)
            try:
                message = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as error:
                _stop_process(process)
                raise TimeoutError(f"MCP request timed out after {timeout} seconds.") from error
            if not message:
                error_text = _process_error_text(process)
                raise RuntimeError(error_text or "MCP server exited without a response.")
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            result = message.get("result", {})
            return result if isinstance(result, dict) else {}


def _read_mcp_message(stream: BinaryIO | None) -> JsonPayload:
    if stream is None:
        return {}
    header = bytearray()
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return {}
        header.extend(chunk)
    length = 0
    for line in header.decode("ascii", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if not length:
        return {}
    parsed = json.loads(stream.read(length).decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


def _process_error_text(process: subprocess.Popen[bytes]) -> str:
    if process.stderr is None or process.poll() is None:
        return ""
    return process.stderr.read().decode("utf-8", errors="replace").strip()


def _firecrawl_mcp_env(api_key: str, api_url: str) -> dict[str, str]:
    env = os.environ.copy()
    if api_key:
        env["FIRECRAWL_API_KEY"] = api_key
    if api_url:
        env["FIRECRAWL_API_URL"] = api_url
    return env


def _mcp_tool_payload(response: JsonPayload) -> JsonPayload:
    content = response.get("content", [])
    if not isinstance(content, list):
        return response
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"data": [{"title": "Firecrawl MCP result", "url": "", "description": text}]}
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    return response


def _records(payload: JsonPayload) -> list[dict[str, object]]:
    data = payload.get("data", payload.get("items", payload.get("results", [])))
    if isinstance(data, dict):
        for key in ("web", "results", "items", "records"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _firecrawl_item(item: dict[str, object]) -> JsonPayload:
    return {
        "title": str(item.get("title") or item.get("url") or "Untitled Firecrawl result"),
        "url": _item_url(item),
        "snippet": str(
            item.get("description")
            or item.get("snippet")
            or item.get("markdown")
            or item.get("content")
            or ""
        ),
        "source_type": "web-page",
    }


def _mediacrawler_item(item: dict[str, object], platform: str) -> JsonPayload:
    return {
        "title": str(item.get("title") or item.get("desc") or item.get("content") or item.get("url") or "Untitled community result"),
        "url": _item_url(item),
        "snippet": str(item.get("desc") or item.get("content") or item.get("description") or item.get("title") or ""),
        "source_type": "community-post",
        "metadata": {
            "platform": platform,
            "author": str(item.get("nickname") or item.get("user_name") or item.get("author") or ""),
            "published_at": str(item.get("time") or item.get("create_time") or item.get("publish_time") or ""),
        },
    }


def _item_url(item: dict[str, object]) -> str:
    for key in ("url", "note_url", "video_url", "aweme_url", "source_url", "link"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _items_payload(provider: str, items: list[JsonPayload], *, query: str) -> JsonPayload:
    return {
        "status": "ok" if items else "no-evidence",
        "reason": "items-found" if items else "no-usable-items",
        "message": (
            f"{provider} bridge collected source items."
            if items
            else f"{provider} bridge returned no usable items for {query}."
        ),
        "items": items,
    }


def _needs_query(provider: str) -> JsonPayload:
    return {
        "status": "needs-input",
        "reason": "missing-query",
        "message": f"{provider} bridge requires a query.",
    }


def _needs_firecrawl_mcp_auth() -> JsonPayload:
    return {
        "status": "needs-input",
        "reason": "auth-missing",
        "message": "Firecrawl MCP requires FIRECRAWL_API_KEY, or FIRECRAWL_API_URL for a self-hosted API.",
        "fix": "Set FIRECRAWL_API_KEY in `.source-radar/local.env` or run `source-radar config setup` when prompted.",
        "retryable": False,
    }


def _unreachable(provider: str, error: Exception, fix: str) -> JsonPayload:
    return {
        "status": "error",
        "reason": "service-unreachable",
        "message": f"Cannot reach {provider} upstream: {error}",
        "fix": fix,
        "retryable": True,
        "diagnostics": {"error_type": error.__class__.__name__},
    }


def _newest_file_path(payload: JsonPayload) -> str:
    files = payload.get("files", [])
    if not isinstance(files, list):
        return ""
    valid = [item for item in files if isinstance(item, dict) and item.get("path")]
    valid.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
    return str(valid[0]["path"]) if valid else ""


def _limit(value: object) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return 5
    return max(1, min(parsed, 50))


def _platform_alias(platform: str) -> str:
    aliases = {
        "xiaohongshu": "xhs",
        "douyin": "dy",
        "bilibili": "bili",
        "weibo": "wb",
    }
    return aliases.get(platform.lower(), platform.lower())


def _platform_aliases(platforms: str) -> list[str]:
    parsed = [
        _platform_alias(platform.strip())
        for platform in platforms.split(",")
        if platform.strip()
    ]
    return parsed or ["xhs"]


def _string_dict(payload: JsonPayload) -> dict[str, str]:
    return {str(key): str(value) for key, value in payload.items() if value not in {"", None}}
