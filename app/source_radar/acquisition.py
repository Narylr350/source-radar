import json
import importlib
import os
import pathlib
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.request import Request, urlopen


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

from .adapters import (
    collect_fixture_items,
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from .config import load_provider_config
from .models import AcquisitionTrace, CandidateSource, SourceItem


@dataclass(frozen=True)
class AcquisitionRequest:
    query: str
    url: str | None = None
    repo: str | None = None
    limit: int = 5


@dataclass(frozen=True)
class AcquisitionResult:
    provider: str
    provider_type: str
    status: str
    reason: str
    message: str
    candidates: list[CandidateSource] = field(default_factory=list)
    items: list[SourceItem] = field(default_factory=list)
    fix: str = ""
    retryable: bool = False
    warnings: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)

    def to_trace(self) -> AcquisitionTrace:
        return AcquisitionTrace(
            provider=self.provider,
            provider_type=self.provider_type,
            status=self.status,
            reason=self.reason,
            message=self.message,
            candidate_count=len(self.candidates),
            items_found=len(self.items),
            candidates=self.candidates,
            fix=self.fix,
            retryable=self.retryable,
            warnings=self.warnings,
            evidence_gaps=self.evidence_gaps,
            diagnostics=self.diagnostics,
        )


class AcquisitionProvider(Protocol):
    provider: str
    provider_type: str

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        ...


class FixtureProvider:
    provider = "fixture"
    provider_type = "builtin-adapter"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        items = collect_fixture_items(request.query)
        return _items_result(self.provider, self.provider_type, items)

    def status(self) -> AcquisitionResult:
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="provider-registered",
            message="Fixture provider is available for deterministic smoke checks.",
        )


class WebProvider:
    provider = "web"
    provider_type = "builtin-adapter"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        if not request.url:
            return _needs_input(self.provider, self.provider_type, "missing-url")
        return _items_result(
            self.provider,
            self.provider_type,
            collect_web_page(request.url),
        )

    def status(self) -> AcquisitionResult:
        return _needs_input(self.provider, self.provider_type, "missing-url")


class OfficialProvider:
    provider = "official"
    provider_type = "builtin-adapter"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        if not request.url:
            return _needs_input(self.provider, self.provider_type, "missing-url")
        return _items_result(
            self.provider,
            self.provider_type,
            collect_official_page(request.url),
        )

    def status(self) -> AcquisitionResult:
        return _needs_input(self.provider, self.provider_type, "missing-url")


class GithubProvider:
    provider = "github"
    provider_type = "builtin-adapter"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        target = request.repo or request.query
        items = collect_github_repo(target)
        return _items_result(self.provider, self.provider_type, items)

    def status(self) -> AcquisitionResult:
        return _needs_input(self.provider, self.provider_type, "missing-repo")


class _BingResultParser(HTMLParser):
    """Parse Bing search results from b_algo list items."""

    def __init__(self) -> None:
        super().__init__()
        self.candidates: list[CandidateSource] = []
        self._in_result = False
        self._in_h2 = False
        self._in_caption = False
        self._href = ""
        self._text_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        cls = attrs_dict.get("class", "")

        if tag == "li" and "b_algo" in cls:
            self._in_result = True
            self._in_h2 = False
            self._in_caption = False
            self._href = ""
            self._text_parts = []
            self._snippet_parts = []
            self._depth = 0
            return

        if not self._in_result:
            return

        if tag == "h2":
            self._in_h2 = True
            self._text_parts = []
        elif tag == "a" and self._in_h2:
            self._href = attrs_dict.get("href", "")
        elif tag == "div" and "b_caption" in cls:
            self._in_caption = True
            self._depth = 0
        elif self._in_caption:
            self._depth += 1

    def handle_data(self, data: str) -> None:
        if not self._in_result:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_h2:
            self._text_parts.append(text)
        elif self._in_caption:
            self._snippet_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_result:
            return

        if tag == "li":
            self._flush_result()
        elif tag == "h2":
            self._in_h2 = False
        elif self._in_caption:
            if self._depth > 0:
                self._depth -= 1
            else:
                self._in_caption = False

    def _flush_result(self) -> None:
        title = " ".join(self._text_parts).strip()
        url = _normalize_result_url(self._href.strip())
        snippet = " ".join(self._snippet_parts).strip()
        if title and url:
            self.candidates.append(
                CandidateSource(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider="search",
                    source_type="search-result",
                )
            )
        self._in_result = False
        self._in_h2 = False
        self._in_caption = False
        self._href = ""
        self._text_parts = []
        self._snippet_parts = []


class BingSearchProvider:
    provider = "search"
    provider_type = "search"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        if not request.query.strip():
            return _needs_input(self.provider, self.provider_type, "missing-query")
        url = "https://www.bing.com/search?" + urllib.parse.urlencode(
            {"q": request.query, "count": request.limit}
        )
        html = ""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                html = _fetch(url)
                break
            except Exception as error:
                last_error = error
                if attempt < 2:
                    import time
                    time.sleep(1 + attempt)
        if not html:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=last_error.__class__.__name__ if last_error else "empty-response",
                message=str(last_error) if last_error else "Bing returned empty response.",
                retryable=True,
            )
        parser = _BingResultParser()
        parser.feed(html)
        candidates = parser.candidates[: request.limit]
        items = [
            SourceItem(
                source_type="search-result",
                title=candidate.title,
                url=candidate.url,
                snippet=candidate.snippet or f"Search candidate for {request.query}.",
                adapter=self.provider,
                metadata={"provider": self.provider},
                raw_content_length=len(candidate.snippet or ""),
                retrieved_at=_utc_now(),
            )
            for candidate in candidates
        ]
        status = "ok" if candidates else "no-evidence"
        reason = "candidates-found" if candidates else "no-candidates"
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status=status,
            reason=reason,
            message=(
                "Search provider returned candidate sources."
                if candidates
                else "Search provider returned no candidate sources."
            ),
            candidates=candidates,
            items=items,
        )

    def status(self) -> AcquisitionResult:
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="provider-registered",
            message="Bing search provider is available; run probe with --query for a live check.",
        )


class TrafilaturaProvider:
    provider = "trafilatura"
    provider_type = "generic-crawler"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        dependency = _dependency("trafilatura", "python -m pip install trafilatura")
        if dependency:
            return dependency
        trafilatura = importlib.import_module("trafilatura")
        candidates = _target_candidates(request)
        if not candidates:
            search = BingSearchProvider().collect(request)
            candidates = search.candidates
        items: list[SourceItem] = []
        warnings: list[str] = []
        for candidate in candidates[: request.limit]:
            try:
                downloaded = trafilatura.fetch_url(candidate.url)
                if not downloaded:
                    warnings.append(f"No HTML downloaded from {candidate.url}")
                    continue
                text = trafilatura.extract(downloaded, include_comments=False)
                if not text:
                    warnings.append(f"No main text extracted from {candidate.url}")
                    continue
                metadata = _trafilatura_metadata(trafilatura, downloaded)
            except Exception as error:
                warnings.append(f"{candidate.url}: {error}")
                continue
            title = metadata.get("title") or candidate.title or candidate.url
            raw_text = " ".join(text.split())
            raw_limited = raw_text[:12000]
            items.append(
                SourceItem(
                    source_type="web-page",
                    title=title,
                    url=candidate.url,
                    snippet=_snippet(text),
                    adapter=self.provider,
                    metadata={
                        "author": metadata.get("author", ""),
                        "date": metadata.get("date", ""),
                        "extractor": "trafilatura",
                    },
                    raw_content=raw_limited,
                    raw_content_length=len(raw_text),
                    raw_content_truncated=len(raw_text) > 12000,
                    retrieved_at=_utc_now(),
                )
            )
        result = _items_result(self.provider, self.provider_type, items, candidates=candidates)
        return _with_warnings(result, warnings)

    def status(self) -> AcquisitionResult:
        dependency = _dependency("trafilatura", "python -m pip install trafilatura")
        if dependency:
            return dependency
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="ready",
            message="Trafilatura is installed for local static-page extraction.",
            diagnostics={"capabilities": "extract", "runtime": "local"},
        )


class Crawl4AIProvider:
    provider = "crawl4ai"
    provider_type = "generic-crawler"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        _ensure_crawl4ai_base_directory()
        dependency = _dependency("crawl4ai", "python -m pip install crawl4ai && crawl4ai-setup")
        if dependency:
            return dependency
        candidates = _target_candidates(request)
        if not candidates:
            search = BingSearchProvider().collect(request)
            candidates = search.candidates
        try:
            import asyncio
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                items = asyncio.run(_crawl4ai_collect(candidates[: request.limit]))
        except Exception as error:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=error.__class__.__name__,
                message=str(error),
                fix="Run `crawl4ai-setup` and ensure Playwright Chromium is installed.",
                retryable=True,
                diagnostics={"capabilities": "render,extract", "runtime": "local-browser"},
            )
        return _items_result(self.provider, self.provider_type, items, candidates=candidates)

    def status(self) -> AcquisitionResult:
        _ensure_crawl4ai_base_directory()
        dependency = _dependency("crawl4ai", "python -m pip install crawl4ai && crawl4ai-setup")
        if dependency:
            return dependency
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="ready",
            message="Crawl4AI is installed for local browser-backed crawling.",
            diagnostics={"capabilities": "render,extract", "runtime": "local-browser"},
        )


_BRIDGE_PORT: dict[str, str] = {
    "mediacrawler": "http://127.0.0.1:3003",
}


def _auto_discover_bridge_endpoint(provider: str) -> str:
    if provider == "mediacrawler":
        from .bridge import PLATFORM_COOKIE_ENVS

        if any(os.environ.get(v) for v in PLATFORM_COOKIE_ENVS.values()):
            return _BRIDGE_PORT["mediacrawler"]
    return ""


class ExternalBridgeProvider:
    provider_type = "external-bridge"

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        endpoint = self._endpoint()
        if not endpoint:
            return self.status()
        payload = json.dumps({"query": request.query, "limit": request.limit}).encode("utf-8")
        bridge_request = Request(
            _bridge_url(endpoint, "/collect"),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(bridge_request, timeout=200) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            return self._unreachable(error)

        items = [
            SourceItem(
                source_type=str(item.get("source_type") or "web-page"),
                title=str(item.get("title") or item.get("url") or "Untitled source"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or item.get("summary") or ""),
                adapter=self.provider,
                metadata=_string_dict(item.get("metadata")),
                raw_content=str(item.get("raw_content") or "")[:12000],
                raw_content_length=int(item.get("raw_content_length") or 0) or len(str(item.get("raw_content") or "")),
                raw_content_truncated=bool(item.get("raw_content_truncated")),
                retrieved_at=str(item.get("retrieved_at") or _utc_now()),
            )
            for item in data.get("items", [])
            if item.get("url")
        ]
        candidates = _candidate_sources(
            data.get("candidates", []),
            provider=self.provider,
        ) or [
            CandidateSource(
                title=item.title,
                url=item.url,
                provider=self.provider,
                snippet=item.snippet,
                source_type=item.source_type,
            )
            for item in items
        ]
        status = str(data.get("status") or ("ok" if items else "no-evidence"))
        reason = str(data.get("reason") or ("items-found" if items else "no-usable-items"))
        message = str(
            data.get("message")
            or (
                f"{self.provider} bridge returned usable source items."
                if items
                else f"{self.provider} bridge returned no usable source items."
            )
        )
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status=status,
            reason=reason,
            message=message,
            candidates=candidates,
            items=items,
            fix=str(data.get("fix") or ""),
            retryable=_bool_value(data.get("retryable")),
            warnings=_string_list(data.get("warnings")),
            evidence_gaps=_string_list(data.get("evidence_gaps")),
            diagnostics=_string_dict(data.get("diagnostics")),
        )

    def status(self) -> AcquisitionResult:
        endpoint = self._endpoint()
        if not endpoint:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="disabled",
                reason="missing-endpoint",
                message=(
                    f"{self.provider} bridge endpoint is not configured; "
                    f"set {self.env_var} or local config before use."
                ),
                fix=(
                    f"Run `source-radar config setup` to configure {self.provider}, or "
                    f"`source-radar config set-provider --name {self.provider} --endpoint <url>`."
                ),
            )
        endpoint_auto_repair = ""
        repaired_endpoint = _bridge_base_url(endpoint)
        if repaired_endpoint != endpoint.rstrip("/"):
            endpoint_auto_repair = "stripped-route"
            endpoint = repaired_endpoint
        try:
            manifest = self._get_json(_bridge_url(endpoint, "/manifest"))
            health = self._get_json(_bridge_url(endpoint, "/health"))
        except Exception as error:
            return self._unreachable(error)

        contract_version = str(manifest.get("contract_version") or "")
        if contract_version != "source-radar.bridge.v1":
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason="contract-mismatch",
                message=(
                    f"{self.provider} bridge contract is {contract_version or 'missing'}, "
                    "expected source-radar.bridge.v1."
                ),
                fix="Upgrade the bridge service or run `source-radar config set-provider "
                    f"--name {self.provider} --endpoint <url>` to point to a compatible bridge.",
                retryable=False,
                diagnostics={
                    "contract_version": contract_version,
                    "expected_contract_version": "source-radar.bridge.v1",
                    "endpoint_auto_repair": endpoint_auto_repair,
                },
            )
        diagnostics = _manifest_diagnostics(manifest)
        diagnostics.update(_string_dict(health.get("diagnostics")))
        if endpoint_auto_repair:
            diagnostics["endpoint_auto_repair"] = endpoint_auto_repair
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status=str(health.get("status") or "ok"),
            reason=str(health.get("reason") or "ready"),
            message=str(health.get("message") or f"{self.provider} bridge is ready."),
            fix=str(health.get("fix") or ""),
            retryable=_bool_value(health.get("retryable")),
            warnings=_string_list(health.get("warnings")),
            evidence_gaps=_string_list(health.get("evidence_gaps")),
            diagnostics=diagnostics,
        )

    def _endpoint(self) -> str:
        return (
            os.environ.get(self.env_var, "").strip()
            or load_provider_config(self.provider).get("endpoint", "").strip()
            or _auto_discover_bridge_endpoint(self.provider)
        )

    def _get_json(self, url: str) -> dict[str, object]:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _unreachable(self, error: Exception) -> AcquisitionResult:
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="error",
            reason="service-unreachable",
            message=f"Cannot reach {self.provider} bridge: {error}",
            fix=(
                    f"Run `source-radar bridge {self.provider}` to start a local bridge, or "
                    f"`source-radar config set-provider --name {self.provider} --endpoint <url>` "
                    f"to configure an external one."
                ),
            retryable=True,
            diagnostics={"error_type": error.__class__.__name__},
        )


def default_providers() -> list[AcquisitionProvider]:
    return [
        FixtureProvider(),
        WebProvider(),
        OfficialProvider(),
        GithubProvider(),
        BingSearchProvider(),
        TrafilaturaProvider(),
        Crawl4AIProvider(),
        ExternalBridgeProvider("mediacrawler", "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"),
    ]


def _items_result(
    provider: str,
    provider_type: str,
    items: list[SourceItem],
    *,
    candidates: list[CandidateSource] | None = None,
) -> AcquisitionResult:
    built_candidates = candidates or [
        CandidateSource(
            title=item.title,
            url=item.url,
            provider=provider,
            snippet=item.snippet,
            source_type=item.source_type,
            metadata=item.metadata,
        )
        for item in items
    ]
    return AcquisitionResult(
        provider=provider,
        provider_type=provider_type,
        status="ok" if items else "no-evidence",
        reason="items-found" if items else "no-usable-items",
        message=(
            f"{provider} provider returned usable source items."
            if items
            else f"{provider} provider returned no usable source items."
        ),
        candidates=built_candidates,
        items=items,
    )


def _needs_input(provider: str, provider_type: str, reason: str) -> AcquisitionResult:
    fixes: dict[str, str] = {
        "missing-url": "Pass --url <url> to provide a target URL.",
        "missing-repo": "Pass --repo <owner/name> to provide a GitHub repository.",
        "missing-query": "Pass a query or claim to search for.",
    }
    return AcquisitionResult(
        provider=provider,
        provider_type=provider_type,
        status="needs-input",
        reason=reason,
        message=f"{provider} provider requires {reason.removeprefix('missing-')}.",
        fix=fixes.get(reason, ""),
    )


_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"


def _fetch(url: str) -> str:
    request = Request(
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def _dependency(package: str, install_hint: str) -> AcquisitionResult | None:
    try:
        importlib.import_module(package)
    except ImportError:
        return AcquisitionResult(
            provider=package,
            provider_type="generic-crawler",
            status="needs-input",
            reason="missing-dependency",
            message=f"{package} is not installed.",
            fix=f"Install it locally with `{install_hint}`.",
            retryable=False,
        )
    return None


def _ensure_crawl4ai_base_directory() -> None:
    if os.environ.get("CRAWL4_AI_BASE_DIRECTORY"):
        return
    base = pathlib.Path(".source-radar") / "crawl4ai"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    os.environ["CRAWL4_AI_BASE_DIRECTORY"] = str(base.resolve())


def _target_candidates(request: AcquisitionRequest) -> list[CandidateSource]:
    if not request.url:
        return []
    return [
        CandidateSource(
            title=request.url,
            url=request.url,
            provider="direct-url",
            source_type="web-page",
        )
    ]


def _trafilatura_metadata(trafilatura: object, downloaded: object) -> dict[str, str]:
    extract_metadata = getattr(trafilatura, "extract_metadata", None)
    if not extract_metadata:
        return {}
    metadata = extract_metadata(downloaded)
    if not metadata:
        return {}
    return {
        "title": str(getattr(metadata, "title", "") or ""),
        "author": str(getattr(metadata, "author", "") or ""),
        "date": str(getattr(metadata, "date", "") or ""),
    }


async def _crawl4ai_collect(candidates: list[CandidateSource]) -> list[SourceItem]:
    crawl4ai = importlib.import_module("crawl4ai")
    crawler_cls = getattr(crawl4ai, "AsyncWebCrawler")
    items: list[SourceItem] = []
    async with crawler_cls() as crawler:
        for candidate in candidates:
            result = await crawler.arun(url=candidate.url)
            text = _crawl4ai_text(result)
            if not text:
                continue
            metadata = getattr(result, "metadata", {}) or {}
            title = (
                str(metadata.get("title") or "")
                if isinstance(metadata, dict)
                else ""
            ) or candidate.title or candidate.url
            raw_text = " ".join(text.split())
            raw_limited = raw_text[:12000]
            items.append(
                SourceItem(
                    source_type="web-page",
                    title=title,
                    url=candidate.url,
                    snippet=_snippet(text),
                    adapter="crawl4ai",
                    metadata={"extractor": "crawl4ai"},
                    raw_content=raw_limited,
                    raw_content_length=len(raw_text),
                    raw_content_truncated=len(raw_text) > 12000,
                    retrieved_at=_utc_now(),
                )
            )
    return items


def _crawl4ai_text(result: object) -> str:
    markdown = getattr(result, "markdown", "")
    if isinstance(markdown, str):
        return markdown
    for attr in ("raw_markdown", "fit_markdown"):
        value = getattr(markdown, attr, "")
        if value:
            return str(value)
    return str(getattr(result, "cleaned_html", "") or "")


def _snippet(text: object, limit: int = 1500) -> str:
    return " ".join(str(text).split())[:limit].strip()


def _with_warnings(result: AcquisitionResult, warnings: list[str]) -> AcquisitionResult:
    if not warnings:
        return result
    return AcquisitionResult(
        provider=result.provider,
        provider_type=result.provider_type,
        status=result.status,
        reason=result.reason,
        message=result.message,
        candidates=result.candidates,
        items=result.items,
        fix=result.fix,
        retryable=result.retryable,
        warnings=warnings,
        evidence_gaps=result.evidence_gaps,
        diagnostics=result.diagnostics,
    )


def _normalize_result_url(href: str) -> str:
    """Extract real URL from search engine redirect URLs (DuckDuckGo uddg, Bing u=)."""
    parsed = urllib.parse.urlparse(href)
    query = urllib.parse.parse_qs(parsed.query)
    # DuckDuckGo redirect
    uddg = query.get("uddg")
    if uddg:
        return uddg[0]
    # Bing redirect: u=a1aHR0cHM6Ly93d3cucHl0aG9uLm9yZy8
    bing_u = query.get("u")
    if bing_u:
        encoded = bing_u[0]
        if encoded.startswith("a1"):
            import base64
            try:
                padded = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
                return base64.b64decode(padded).decode("utf-8")
            except Exception:
                pass
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return ""


def _bridge_url(endpoint: str, suffix: str) -> str:
    endpoint = _bridge_base_url(endpoint)
    if endpoint.endswith(suffix):
        return endpoint
    return endpoint + suffix


def _bridge_base_url(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    for suffix in ("/collect", "/health", "/manifest"):
        if endpoint.endswith(suffix):
            return endpoint[: -len(suffix)]
    return endpoint


def _candidate_sources(payload: object, *, provider: str) -> list[CandidateSource]:
    if not isinstance(payload, list):
        return []
    candidates: list[CandidateSource] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        candidates.append(
            CandidateSource(
                title=str(item.get("title") or item.get("url")),
                url=str(item.get("url")),
                provider=provider,
                snippet=str(item.get("snippet") or ""),
                source_type=str(item.get("source_type") or "web-page"),
                metadata=_string_dict(item.get("metadata")),
            )
        )
    return candidates


def _manifest_diagnostics(manifest: dict[str, object]) -> dict[str, str]:
    capabilities: list[str] = []
    for capability in manifest.get("capabilities", []):
        if isinstance(capability, dict) and capability.get("name"):
            capabilities.append(str(capability["name"]))
        elif isinstance(capability, str):
            capabilities.append(capability)
    return {
        "contract_version": str(manifest.get("contract_version") or ""),
        "capabilities": ",".join(capabilities),
        "platforms": ",".join(_string_list(manifest.get("platforms"))),
        "ai_guidance": str(manifest.get("ai_guidance") or ""),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in {"", None}]


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item not in {"", None}}


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return False
