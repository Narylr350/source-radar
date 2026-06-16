import argparse
import json
import logging
import os
import pathlib
import threading
import time

_log = logging.getLogger("source_radar.bridge")
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.request import Request, urlopen


JsonPayload = dict[str, object]
RequestJson = Callable[[str, str, JsonPayload | None, int], JsonPayload]

PLATFORM_COOKIE_ENVS: dict[str, str] = {
    "xhs": "SOURCE_RADAR_XHS_COOKIE",
    "wb": "SOURCE_RADAR_WEIBO_COOKIE",
    "bili": "SOURCE_RADAR_BILI_COOKIE",
    "tieba": "SOURCE_RADAR_TIEBA_COOKIE",
    "dy": "SOURCE_RADAR_DOUYIN_COOKIE",
}


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
        self._crawl_lock = threading.Lock()
        self._cancel = threading.Event()
        self._last_stages: list[str] = []

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
                "fix": "Run `source-radar config setup` to configure platform cookies interactively.",
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
        self._last_stages = []
        query = str(payload.get("query") or "").strip()
        limit = _limit(payload.get("limit"))
        enable_comments = bool(payload.get("enable_comments", False))
        enable_sub_comments = bool(payload.get("enable_sub_comments", False))
        max_comments_per_item = _limit(payload.get("max_comments_per_item")) if enable_comments else 0
        if not query:
            return _needs_query(self.provider)
        # Support caller-specified platforms (e.g. {"platforms": ["xhs", "wb"]})
        requested = payload.get("platforms")
        if isinstance(requested, list) and requested:
            active = [p for p in requested if p in self._active_platforms()]
        else:
            # Default: only 1 platform (first active) to avoid slow multi-platform runs
            all_active = self._active_platforms()
            active = all_active[:1] if all_active else []
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
        _log.info("collect start: query=%r, platforms=%s (waiting for lock)", query, active)
        with self._crawl_lock:
            _log.info("collect start: query=%r, platforms=%s (lock acquired)", query, active)
            for platform in active:
                t0 = time.time()
                try:
                    platform_items = self._collect_platform_with_timeout(
                        query, limit, platform,
                        enable_comments=enable_comments,
                        enable_sub_comments=enable_sub_comments,
                        max_comments_per_item=max_comments_per_item,
                    )
                    items.extend(platform_items)
                    _log.info("  %s done: items=%d, elapsed=%.1fs", platform, len(platform_items), time.time() - t0)
                except Exception as error:
                    _log.warning("  %s failed: %s, elapsed=%.1fs", platform, error, time.time() - t0)
                    warnings.append(f"{platform}: {error}")
            _log.info("collect done: total_items=%d (lock released)", len(items))
        payload = _items_payload(self.provider, items[:limit], query=query)
        if warnings:
            payload["warnings"] = warnings
        return payload

    def _active_platforms(self) -> list[str]:
        if self.login_type != "cookie":
            return self.platforms
        return [p for p in self.platforms if self.cookies_map.get(p)]

    def _collect_platform_with_timeout(self, query: str, limit: int, platform: str,
                                       enable_comments: bool = False,
                                       enable_sub_comments: bool = False,
                                       max_comments_per_item: int = 10) -> list[JsonPayload]:
        """Run _collect_platform with a per-platform timeout. On timeout, stop crawler and read partial results."""
        timeout = _PLATFORM_TIMEOUT.get(platform, 30)
        if enable_comments:
            timeout = timeout + 30
        self._cancel.clear()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._collect_platform, query, limit, platform,
                enable_comments=enable_comments,
                enable_sub_comments=enable_sub_comments,
                max_comments_per_item=max_comments_per_item,
            )
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                _log.warning("%s timed out after %ds, stopping crawler...", platform, timeout)
                self._cancel.set()
                self._stop_crawler()
                try:
                    result = self._read_partial_results(query, limit, platform)
                    self._last_stages.append(f"{platform}: timeout 后读取 partial ({len(result)} 条)")
                    return result
                except Exception as e:
                    _log.warning("%s partial read also failed: %s", platform, e)
                    raise RuntimeError(f"{platform} timed out after {timeout}s")

    def _read_partial_results(self, query: str, limit: int, platform: str) -> list[JsonPayload]:
        """Read already-written results from MediaCrawler data files after timeout."""
        data_platform = _data_dir_name(platform)
        files = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files?"
            + urllib.parse.urlencode({"platform": data_platform, "file_type": "json"}),
            None,
            10,
        )
        file_path = _newest_file_path(files)
        if not file_path:
            return []
        preview = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files/{urllib.parse.quote(file_path)}?"
            + urllib.parse.urlencode({"preview": "true", "limit": "100"}),
            None,
            10,
        )
        records = _records(preview)
        filtered = [r for r in records if r.get("source_keyword") == query]
        if filtered:
            records = filtered[-limit:]
        else:
            # No source_keyword match — return empty, don't pollute with other queries' results
            return []
        return [_mediacrawler_item(item, platform) for item in records if _item_url(item)]

    def _stop_crawler(self) -> None:
        """Call MediaCrawler API to stop a stuck crawler process."""
        try:
            self._request_json("POST", f"{self.api_url}/api/crawler/stop", {}, 10)
            _log.info("Sent stop command to MediaCrawler")
        except Exception as e:
            _log.warning("Failed to stop MediaCrawler: %s", e)

    def _collect_platform(self, query: str, limit: int, platform: str,
                          enable_comments: bool = False,
                          enable_sub_comments: bool = False,
                          max_comments_per_item: int = 10) -> list[JsonPayload]:
        self._last_stages.append(f"{platform}: 启动爬虫...")
        cookie = self.cookies_map.get(platform, self.cookies)
        start_payload: JsonPayload = {
            "platform": platform,
            "login_type": self.login_type,
            "crawler_type": "search",
            "keywords": query,
            "start_page": 1,
            "enable_comments": enable_comments,
            "enable_sub_comments": enable_sub_comments,
            "save_option": "json",
            "cookies": cookie,
            "headless": True,
            "max_notes_count": min(limit, 10),
        }
        if enable_comments and max_comments_per_item:
            start_payload["max_comments_count_singlenotes"] = max_comments_per_item
        self._request_json("POST", f"{self.api_url}/api/crawler/start", start_payload, 30)
        self._last_stages.append(f"{platform}: 等待完成...")
        status = self._wait_until_idle()
        if status.get("status") not in {"idle", "ok"}:
            raise RuntimeError("MediaCrawler task did not finish cleanly.")
        data_platform = _data_dir_name(platform)
        self._last_stages.append(f"{platform}: 读取结果...")
        files = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files?"
            + urllib.parse.urlencode({"platform": data_platform, "file_type": "json"}),
            None,
            30,
        )
        file_path = _newest_file_path(files)
        if not file_path:
            return []
        # Request more records to filter by source_keyword (file may contain multiple queries)
        fetch_limit = max(limit * 5, 50)
        preview = self._request_json(
            "GET",
            f"{self.api_url}/api/data/files/{urllib.parse.quote(file_path)}?"
            + urllib.parse.urlencode({"preview": "true", "limit": str(fetch_limit)}),
            None,
            30,
        )
        records = _records(preview)
        # Filter by source_keyword to isolate this query's results
        filtered = [r for r in records if r.get("source_keyword") == query]
        if filtered:
            # Take the last N (most recently appended)
            records = filtered[-limit:]
        else:
            # No source_keyword match — return empty, don't pollute with other queries' results
            _log.info("%s: no source_keyword=%r match in %d records, returning empty", platform, query, len(records))
            return []
        items = [_mediacrawler_item(item, platform) for item in records if _item_url(item)]
        # Warn if source_keyword matched but no URL was extracted
        if filtered and not items:
            _log.warning(
                "%s: matched %d records by source_keyword=%r but _item_url() returned empty for all. "
                "Sample keys: %s",
                platform, len(filtered), query, list(records[0].keys()) if records else [],
            )
        count = len(items)
        if enable_comments:
            comment_items = self._read_comments(data_platform, query, limit, platform)
            items.extend(comment_items)
            self._last_stages.append(f"{platform}: 完成 ({count} 帖 + {len(comment_items)} 评论)")
        else:
            self._last_stages.append(f"{platform}: 完成 ({count} 条)")
        return items

    def _read_comments(self, data_platform: str, query: str, limit: int, platform: str) -> list[JsonPayload]:
        """Read comment files from MediaCrawler data directory."""
        try:
            comment_files = self._request_json(
                "GET",
                f"{self.api_url}/api/data/files?"
                + urllib.parse.urlencode({"platform": data_platform, "file_type": "json"}),
                None,
                10,
            )
        except Exception as e:
            _log.info("%s: comment file listing failed: %s", platform, e)
            return []
        files = comment_files.get("files", []) if isinstance(comment_files, dict) else []
        comment_paths = [
            str(f.get("path"))
            for f in files
            if isinstance(f, dict) and "comment" in str(f.get("path", "")).lower()
            and "sub_comment" not in str(f.get("path", "")).lower()
        ]
        if not comment_paths:
            return []
        all_comments: list[JsonPayload] = []
        for path in comment_paths[:2]:
            try:
                preview = self._request_json(
                    "GET",
                    f"{self.api_url}/api/data/files/{urllib.parse.quote(path)}?"
                    + urllib.parse.urlencode({"preview": "true", "limit": str(limit * 3)}),
                    None,
                    10,
                )
                records = _records(preview)
                filtered = [r for r in records if r.get("source_keyword") == query]
                for item in filtered[-limit:]:
                    comment = _mediacrawler_comment_item(item, platform)
                    if comment.get("snippet"):
                        all_comments.append(comment)
            except Exception as e:
                _log.info("%s: failed to read comment file %s: %s", platform, path, e)
        return all_comments[:limit]

    def _wait_until_idle(self) -> JsonPayload:
        deadline = time.time() + self.timeout_seconds
        latest: JsonPayload = {}
        last_log_count = -1
        stale_polls = 0
        stale_threshold = 5  # 5 consecutive polls with no new logs = hung (10s at 2s interval)

        while time.time() <= deadline:
            if self._cancel.is_set():
                return {"status": "error", "error_message": "Cancelled by timeout"}

            latest = self._request_json("GET", f"{self.api_url}/api/crawler/status", None, 30)
            if latest.get("status") in {"idle", "error"}:
                return latest

            # Check log count for progress detection
            try:
                logs_resp = self._request_json("GET", f"{self.api_url}/api/crawler/logs?limit=5", None, 5)
                log_count = len(logs_resp.get("logs", []))
                if log_count > last_log_count:
                    last_log_count = log_count
                    stale_polls = 0
                else:
                    stale_polls += 1
            except Exception:
                stale_polls += 1

            if stale_polls >= stale_threshold:
                _log.warning("MediaCrawler appears hung (no new logs for %d polls)", stale_polls)
                return {"status": "error", "error_message": f"Crawler hung: no progress for {stale_polls * self.sleep_seconds}s"}

            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)

        return {
            "status": "error",
            "error_message": f"MediaCrawler task timed out after {self.timeout_seconds} seconds.",
        }


class SearXNGBridgeBackend:
    provider = "searxng"

    def __init__(
        self,
        *,
        upstream_url: str,
        request_json: RequestJson | None = None,
    ) -> None:
        self.upstream_url = upstream_url.rstrip("/")
        self._request_json = request_json or _request_json

    def manifest(self) -> JsonPayload:
        return {
            "provider": self.provider,
            "contract_version": "source-radar.bridge.v1",
            "capabilities": [{"name": "search"}],
            "ai_guidance": (
                "Use for free local/metasearch web search via SearXNG. "
                "Good as the default no-key search backend when configured."
            ),
        }

    def health(self) -> JsonPayload:
        if not self.upstream_url:
            return {
                "status": "needs-input",
                "reason": "missing-upstream-url",
                "message": "SearXNG upstream URL is not configured.",
                "fix": "Run `source-radar bridge searxng --upstream-url http://127.0.0.1:8888`.",
                "retryable": False,
            }
        try:
            data = self._request_json("GET", self._search_url("source-radar"), None, 10)
        except Exception as error:
            return _unreachable(
                self.provider,
                error,
                "Start SearXNG and ensure JSON output is enabled (`formats: [html, json]`).",
            )

        results_count = len(data.get("results", [])) if isinstance(data, dict) else 0
        diagnostics = {
            "upstream_url": self.upstream_url,
            "capabilities": "search",
            "runtime": "external-bridge",
            "results_count": str(results_count),
        }
        engine_health = _parse_engine_health(data)
        if engine_health:
            captcha = str(engine_health.get("diagnostics", {}).get("captcha_engines", ""))
            timeouts = str(engine_health.get("diagnostics", {}).get("timeout_engines", ""))
            others = str(engine_health.get("diagnostics", {}).get("other_issues", ""))
            if captcha:
                return {
                    "status": "degraded",
                    "reason": "captcha-suspended",
                    "message": f"搜索引擎被 CAPTCHA 暂停: {captcha}。搜索质量可能下降。",
                    "fix": engine_health.get("fix", ""),
                    "diagnostics": {**diagnostics, **engine_health.get("diagnostics", {})},
                }
            if timeouts:
                return {
                    "status": "degraded",
                    "reason": "engine-timeout",
                    "message": f"搜索引擎超时: {timeouts}。",
                    "diagnostics": {**diagnostics, **engine_health.get("diagnostics", {})},
                }
            if others:
                return {
                    "status": "degraded",
                    "reason": "engine-issues",
                    "message": f"搜索引擎异常: {others}",
                    "diagnostics": {**diagnostics, **engine_health.get("diagnostics", {})},
                }

        return {
            "status": "ok",
            "reason": "ready",
            "message": f"SearXNG upstream is reachable, {results_count} results.",
            "diagnostics": diagnostics,
        }

    def collect(self, payload: JsonPayload) -> JsonPayload:
        query = str(payload.get("query") or "").strip()
        limit = _limit(payload.get("limit"))
        if not query:
            return _needs_query(self.provider)
        try:
            response = self._request_json("GET", self._search_url(query), None, 30)
        except Exception as error:
            return _unreachable(
                self.provider,
                error,
                "Check SearXNG URL and enable JSON output (`formats: [html, json]`).",
            )
        items = [_searxng_item(item) for item in _records(response)]
        items = [item for item in items if item.get("url")][:limit]
        payload = _items_payload(self.provider, items, query=query)
        payload["candidates"] = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "provider": self.provider,
                "source_type": item.get("source_type", "search-result"),
                "metadata": item.get("metadata", {}),
            }
            for item in items
        ]
        engine_health = _parse_engine_health(response)
        if engine_health:
            payload.update(engine_health)
        return payload

    def _search_url(self, query: str) -> str:
        return (
            f"{self.upstream_url}/search?"
            + urllib.parse.urlencode({"q": query, "format": "json"})
        )


def serve_bridge(backend: object, host: str, port: int) -> None:
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

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def add_bridge_subparsers(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="bridge_provider", required=True)
    mediacrawler = subparsers.add_parser("mediacrawler", help="run a MediaCrawler source-radar bridge")
    mediacrawler.add_argument("--host", default="127.0.0.1")
    mediacrawler.add_argument("--port", type=int, default=3003)
    mediacrawler.add_argument("--api-url", default="")
    mediacrawler.add_argument("--platform", default="")
    mediacrawler.add_argument("--login-type", default="")
    mediacrawler.add_argument("--timeout", type=int, default=120)

    searxng = subparsers.add_parser("searxng", help="run a SearXNG source-radar bridge")
    searxng.add_argument("--host", default="127.0.0.1")
    searxng.add_argument("--port", type=int, default=3004)
    searxng.add_argument("--upstream-url", default="")


def build_bridge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-radar bridge")
    add_bridge_subparsers(parser)
    return parser


def run_bridge_from_args(args: argparse.Namespace) -> None:
    load_local_env()
    if args.bridge_provider == "mediacrawler":
        cookies_map = {p: os.environ.get(env, "") for p, env in PLATFORM_COOKIE_ENVS.items()}
        requested_platforms = args.platform or os.environ.get("MEDIACRAWLER_PLATFORM", ",".join(PLATFORM_COOKIE_ENVS))
        backend = MediaCrawlerBridgeBackend(
            api_url=args.api_url or os.environ.get("MEDIACRAWLER_API_URL", "http://127.0.0.1:8080"),
            platform=requested_platforms,
            login_type=args.login_type or os.environ.get("MEDIACRAWLER_LOGIN_TYPE", "cookie"),
            cookies_map=cookies_map,
            timeout_seconds=args.timeout,
        )
    elif args.bridge_provider == "searxng":
        backend = SearXNGBridgeBackend(
            upstream_url=(
                args.upstream_url
                or os.environ.get("SEARXNG_URL", "")
                or os.environ.get("SOURCE_RADAR_SEARXNG_UPSTREAM_URL", "")
            ),
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


def _mediacrawler_comment_item(item: dict[str, object], platform: str) -> JsonPayload:
    content = str(item.get("content") or item.get("comment_text") or item.get("text") or "")
    parent_nickname = str(item.get("parent_comment_nickname") or "")
    prefix = f"回复 {parent_nickname}: " if parent_nickname else ""
    note_url = str(item.get("note_url") or item.get("video_url") or "")
    return {
        "title": f"评论: {content[:60]}",
        "url": note_url or _item_url(item),
        "snippet": prefix + content,
        "source_type": "community-comment",
        "metadata": {
            "platform": platform,
            "author": str(item.get("nickname") or item.get("user_name") or ""),
            "published_at": str(item.get("create_time") or item.get("time") or ""),
            "sub_comment_count": str(item.get("sub_comment_count") or "0"),
            "parent_comment_id": str(item.get("parent_comment_id") or ""),
        },
    }


def _item_url(item: dict[str, object]) -> str:
    for key in ("url", "note_url", "video_url", "aweme_url", "source_url", "link"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _searxng_item(item: dict[str, object]) -> JsonPayload:
    return {
        "title": str(item.get("title") or item.get("url") or "Untitled search result"),
        "url": str(item.get("url") or ""),
        "snippet": str(item.get("content") or item.get("snippet") or ""),
        "source_type": "search-result",
        "metadata": {
            "engine": str(item.get("engine") or ""),
            "score": str(item.get("score") or ""),
            "category": str(item.get("category") or ""),
        },
    }


def _parse_engine_health(data: JsonPayload) -> JsonPayload:
    unresponsive = data.get("unresponsive_engines", []) if isinstance(data, dict) else []
    if not unresponsive:
        return {}
    captcha_engines: list[str] = []
    timeout_engines: list[str] = []
    other_issues: list[str] = []
    for entry in unresponsive:
        if isinstance(entry, list) and len(entry) >= 2:
            engine, reason = entry[0], entry[1]
            if "CAPTCHA" in reason or "captcha" in reason.lower():
                captcha_engines.append(engine)
            elif "timeout" in reason.lower():
                timeout_engines.append(engine)
            else:
                other_issues.append(f"{engine}: {reason}")
    if not (captcha_engines or timeout_engines or other_issues):
        return {}
    warnings: list[str] = []
    fix = ""
    diagnostics: dict[str, str] = {}
    if captcha_engines:
        warnings.append(f"CAPTCHA 暂停: {', '.join(captcha_engines)}")
        fix = "等待 CAPTCHA 解除（通常 10-30 分钟），或更换 IP，或在 SearXNG settings.yml 中禁用这些引擎"
        diagnostics["captcha_engines"] = ", ".join(captcha_engines)
    if timeout_engines:
        warnings.append(f"引擎超时: {', '.join(timeout_engines)}")
        diagnostics["timeout_engines"] = ", ".join(timeout_engines)
    if other_issues:
        warnings.append(f"引擎异常: {'; '.join(other_issues)}")
        diagnostics["other_issues"] = "; ".join(other_issues)
    result: JsonPayload = {"warnings": warnings, "diagnostics": diagnostics}
    if fix:
        result["fix"] = fix
    return result


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
    contents_files = [f for f in valid if "search_contents" in str(f.get("path", ""))]
    if contents_files:
        valid = contents_files
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


_PLATFORM_TIMEOUT = {
    "xhs": 20,
    "wb": 20,
    "bili": 45,
    "tieba": 45,
    "dy": 30,
    "zhihu": 30,
}


def _data_dir_name(platform: str) -> str:
    """Map platform name to MediaCrawler data directory name.
    
    MediaCrawler API uses these platform values:
    - bili (not bilibili)
    - xhs (not xiaohongshu)
    - weibo (not wb)
    - tieba, dy, zhihu (same)
    """
    # wb → weibo is the only alias needed; others use their API name as dir name
    alias = {"wb": "weibo"}
    return alias.get(platform.lower(), platform.lower())


def _platform_aliases(platforms: str) -> list[str]:
    parsed = [
        _platform_alias(platform.strip())
        for platform in platforms.split(",")
        if platform.strip()
    ]
    return parsed or ["xhs"]


def _string_dict(payload: JsonPayload) -> dict[str, str]:
    return {str(key): str(value) for key, value in payload.items() if value not in {"", None}}
