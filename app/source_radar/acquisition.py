import json
import os
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol
from urllib.request import Request, urlopen

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


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.candidates: list[CandidateSource] = []
        self._href = ""
        self._text_parts: list[str] = []
        self._in_result = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = attrs_dict.get("class", "")
        href = attrs_dict.get("href", "")
        if "result-link" in classes and href:
            self._href = href
            self._text_parts = []
            self._in_result = True

    def handle_data(self, data: str) -> None:
        if self._in_result:
            text = " ".join(data.split())
            if text:
                self._text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result:
            title = " ".join(self._text_parts).strip()
            url = _normalize_result_url(self._href)
            if title and url:
                self.candidates.append(
                    CandidateSource(
                        title=title,
                        url=url,
                        provider="search",
                        source_type="search-result",
                    )
                )
            self._href = ""
            self._text_parts = []
            self._in_result = False


class DuckDuckGoSearchProvider:
    provider = "search"
    provider_type = "search"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        if not request.query.strip():
            return _needs_input(self.provider, self.provider_type, "missing-query")
        url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode(
            {"q": request.query}
        )
        try:
            html = _fetch(url)
        except Exception as error:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=error.__class__.__name__,
                message=str(error),
            )
        parser = _SearchResultParser()
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
            message="Search provider is available; run probe with --query for a live check.",
        )


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
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(bridge_request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            return AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status="error",
                reason=error.__class__.__name__,
                message=str(error),
            )

        items = [
            SourceItem(
                source_type=str(item.get("source_type") or "web-page"),
                title=str(item.get("title") or item.get("url") or "Untitled source"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or item.get("summary") or ""),
                adapter=self.provider,
            )
            for item in data.get("items", [])
            if item.get("url")
        ]
        candidates = [
            CandidateSource(
                title=item.title,
                url=item.url,
                provider=self.provider,
                snippet=item.snippet,
                source_type=item.source_type,
            )
            for item in items
        ]
        return _items_result(
            self.provider,
            self.provider_type,
            items,
            candidates=candidates,
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
            )
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="endpoint-configured",
            message=f"{self.provider} bridge endpoint is configured.",
        )

    def _endpoint(self) -> str:
        return (
            os.environ.get(self.env_var, "").strip()
            or load_provider_config(self.provider).get("endpoint", "").strip()
        )


def default_providers() -> list[AcquisitionProvider]:
    return [
        FixtureProvider(),
        WebProvider(),
        OfficialProvider(),
        GithubProvider(),
        DuckDuckGoSearchProvider(),
        ExternalBridgeProvider("firecrawl", "SOURCE_RADAR_FIRECRAWL_ENDPOINT"),
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
    return AcquisitionResult(
        provider=provider,
        provider_type=provider_type,
        status="needs-input",
        reason=reason,
        message=f"{provider} provider requires {reason.removeprefix('missing-')}.",
    )


def _fetch(url: str) -> str:
    request = Request(
        url,
        headers={"User-Agent": "source-radar/0.1"},
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def _normalize_result_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urllib.parse.urlparse(href)
    query = urllib.parse.parse_qs(parsed.query)
    uddg = query.get("uddg")
    if uddg:
        return uddg[0]
    return ""
