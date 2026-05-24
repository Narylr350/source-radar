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
            _bridge_url(endpoint, "/collect"),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(bridge_request, timeout=30) as response:
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
                    f"Configure {self.provider} with `source-radar config set-provider "
                    f"--name {self.provider} --endpoint <bridge-url>`."
                ),
            )
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
                fix="Upgrade the bridge service or point source-radar at a compatible bridge.",
                retryable=False,
                diagnostics={
                    "contract_version": contract_version,
                    "expected_contract_version": "source-radar.bridge.v1",
                },
            )
        diagnostics = _manifest_diagnostics(manifest)
        diagnostics.update(_string_dict(health.get("diagnostics")))
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
            fix=f"Start the {self.provider} bridge service or update the provider endpoint.",
            retryable=True,
            diagnostics={"error_type": error.__class__.__name__},
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


def _bridge_url(endpoint: str, suffix: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith(suffix):
        return endpoint
    return endpoint + suffix


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
