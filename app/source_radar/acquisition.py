import json
import importlib
import os
import pathlib
import re
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
from .models import AcquisitionTrace, CandidateSource, QualityAssessment, SourceItem


@dataclass(frozen=True)
class AcquisitionRequest:
    query: str
    url: str | None = None
    repo: str | None = None
    limit: int = 5
    platforms: list[str] | None = None
    site: str | None = None
    page: int = 1


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
    quality: QualityAssessment | None = None

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
            quality=self.quality,
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


class GithubSearchProvider:
    """Search GitHub repositories and code using GitHub API."""
    provider = "github-search"
    provider_type = "search"

    def collect(self, request: AcquisitionRequest) -> AcquisitionResult:
        if not request.query.strip():
            return _needs_input(self.provider, self.provider_type, "missing-query")
        limit = min(request.limit or 5, 10)
        items: list[SourceItem] = []
        candidates: list[CandidateSource] = []
        warnings: list[str] = []

        # Search repositories
        try:
            repos = self._search_repos(request.query, limit)
            for repo in repos:
                url = repo.get("html_url", "")
                name = repo.get("full_name", "")
                desc = repo.get("description", "") or ""
                stars = repo.get("stargazers_count", 0)
                lang = repo.get("language", "") or ""
                snippet = f"{desc} | ⭐{stars} | {lang}" if desc else f"⭐{stars} | {lang}"
                candidates.append(CandidateSource(
                    title=name, url=url, snippet=snippet,
                    provider=self.provider, source_type="github-repo",
                ))
                items.append(SourceItem(
                    source_type="github-repo", title=name, url=url,
                    snippet=snippet, adapter=self.provider,
                    metadata={"stars": str(stars), "language": lang},
                    raw_content_length=len(desc),
                    retrieved_at=_utc_now(),
                ))
        except Exception as e:
            warnings.append(f"repo search: {e}")

        # Search code (if repo search returned few results)
        if len(items) < limit:
            try:
                code_results = self._search_code(request.query, limit - len(items))
                for code in code_results:
                    repo_name = code.get("repository", {}).get("full_name", "")
                    file_path = code.get("path", "")
                    url = code.get("html_url", "")
                    snippet = code.get("text_matches", [{}])[0].get("fragment", "") if code.get("text_matches") else ""
                    title = f"{repo_name}/{file_path}"
                    candidates.append(CandidateSource(
                        title=title, url=url, snippet=snippet[:200],
                        provider=self.provider, source_type="github-code",
                    ))
                    items.append(SourceItem(
                        source_type="github-code", title=title, url=url,
                        snippet=snippet[:200], adapter=self.provider,
                        metadata={"repo": repo_name, "path": file_path},
                        raw_content_length=len(snippet),
                        retrieved_at=_utc_now(),
                    ))
            except Exception as e:
                warnings.append(f"code search: {e}")

        status = "ok" if items else "no-evidence"
        reason = "candidates-found" if items else "no-candidates"
        result = AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status=status,
            reason=reason,
            message=f"GitHub search found {len(items)} results." if items else "GitHub search returned no results.",
            candidates=candidates,
            items=items,
        )
        if warnings:
            result = replace(result, warnings=warnings)
        return result

    def _search_repos(self, query: str, limit: int) -> list[dict]:
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&per_page={limit}"
        return self._api_call(url).get("items", [])

    def _search_code(self, query: str, limit: int) -> list[dict]:
        url = f"https://api.github.com/search/code?q={urllib.parse.quote(query)}&per_page={limit}"
        return self._api_call(url).get("items", [])

    def search_issues(self, query: str, limit: int = 5, page: int = 1) -> list[dict]:
        return self._search_issues(query, limit, page=page)

    def _search_issues(self, query: str, limit: int, page: int = 1) -> list[dict]:
        page = max(page, 1)
        url = f"https://api.github.com/search/issues?q={urllib.parse.quote(query)}&sort=updated&per_page={limit}&page={page}"
        return self._api_call(url).get("items", [])

    def _api_call(self, url: str) -> dict:
        headers = {"Accept": "application/vnd.github.v3+json"}
        # Use GITHUB_TOKEN if available for higher rate limits
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"token {token}"
        request = Request(url, headers=headers)
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def status(self) -> AcquisitionResult:
        return AcquisitionResult(
            provider=self.provider,
            provider_type=self.provider_type,
            status="ok",
            reason="provider-registered",
            message="GitHub search provider is available.",
        )


def _is_english_query(query: str) -> bool:
    """Detect if query is primarily English (no CJK characters, mostly ASCII)."""
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', query))
    ascii_letters = len(re.findall(r'[a-zA-Z]', query))
    if cjk > 0:
        return False
    return ascii_letters >= 3


def _hostname_matches(url: str, target: str) -> bool:
    try:
        hostname = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    hostname = hostname.lower()
    return hostname == target or hostname.endswith("." + target)


_AUTHORITY_DOMAINS = {
    "fifa.com", "reuters.com", "espn.com", "bbc.com", "bbc.co.uk",
    "apnews.com", "theguardian.com", "nytimes.com", "washingtonpost.com",
    "who.int", "un.org", "worldbank.org",
}
_GENERAL_TRUSTED = {
    "wikipedia.org", "github.com", "stackoverflow.com", "python.org",
    "microsoft.com", "apple.com", "google.com", "mozilla.org",
}
_CHINESE_COMMUNITY = {
    "zhihu.com", "xiaohongshu.com", "bilibili.com", "douban.com",
    "tieba.baidu.com", "weibo.com", "douyin.com", "hupu.com",
    "smzdm.com", "v2ex.com", "jianshu.com", "csdn.net",
    "zhuanlan.zhihu.com", "post.smzdm.com",
}
_LIFE_FORUM_KEYWORDS = (
    "怎么样", "好不好", "值不值", "推荐", "体验", "测评", "评测",
    "怎么选", "哪个好", "区别", "对比", "开箱", "真实",
    "review", "experience", "recommend", "vs", "comparison",
)
_CANDIDATE_POOL = 30


def _domain_weight(url: str, query: str = "") -> int:
    try:
        hostname = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return 0
    is_life = any(kw in query for kw in _LIFE_FORUM_KEYWORDS)
    for d in _AUTHORITY_DOMAINS:
        if hostname == d or hostname.endswith("." + d):
            return 8 if is_life else 10
    for d in _GENERAL_TRUSTED:
        if hostname == d or hostname.endswith("." + d):
            return 5
    for d in _CHINESE_COMMUNITY:
        if hostname == d or hostname.endswith("." + d):
            return 6 if is_life else 2
    return 0


def _relevance_score(query: str, title: str, snippet: str) -> float:
    """Score how relevant a result is to the query. Higher = more relevant."""
    query_lower = query.lower()
    title_lower = title.lower()
    snippet_lower = snippet.lower()
    query_tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', query_lower))
    if not query_tokens:
        return 0.0
    title_hits = sum(1 for t in query_tokens if t in title_lower)
    snippet_hits = sum(1 for t in query_tokens if t in snippet_lower)
    title_ratio = title_hits / len(query_tokens)
    snippet_ratio = snippet_hits / len(query_tokens)
    exact_in_title = 1.0 if query_lower in title_lower else 0.0
    return title_ratio * 3.0 + snippet_ratio * 1.0 + exact_in_title * 2.0


def _rank_candidates(candidates: list[CandidateSource], query: str = "") -> list[CandidateSource]:
    """Rank by composite score: original_position + domain_weight + relevance."""
    if not candidates:
        return candidates
    n = len(candidates)
    scored = []
    for i, c in enumerate(candidates):
        original_score = max(0, n - i)
        domain = _domain_weight(c.url or "", query)
        relevance = _relevance_score(query, c.title or "", c.snippet or "")
        total = original_score * 0.4 + domain + relevance
        scored.append((c, total))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]


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
        has_site = bool(request.site)
        target = max(request.limit * 4, 20)
        if has_site:
            target = max(target, 40)
        per_page = min(target, _CANDIDATE_POOL)
        pages_needed = (target + per_page - 1) // per_page
        query = request.query
        if has_site:
            query = f"{query} site:{request.site}"
        params_base: dict[str, str | int] = {"q": query}
        base_url = "https://cn.bing.com/search?"
        all_candidates: list[CandidateSource] = []
        seen_urls: set[str] = set()
        for page in range(pages_needed):
            page_params = dict(params_base)
            if page > 0:
                page_params["first"] = page * per_page + 1
            url = base_url + urllib.parse.urlencode(page_params)
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
                if page == 0:
                    return AcquisitionResult(
                        provider=self.provider,
                        provider_type=self.provider_type,
                        status="error",
                        reason=last_error.__class__.__name__ if last_error else "empty-response",
                        message=str(last_error) if last_error else "Bing returned empty response.",
                        retryable=True,
                    )
                break
            parser = _BingResultParser()
            parser.feed(html)
            for c in parser.candidates:
                norm = (c.url or "").split("?")[0].rstrip("/").lower()
                if norm and norm not in seen_urls:
                    seen_urls.add(norm)
                    all_candidates.append(c)
            if len(parser.candidates) < per_page // 2:
                break
        if has_site:
            site_lower = request.site.lower()
            all_candidates = [
                c for c in all_candidates
                if _hostname_matches(c.url or "", site_lower)
            ]
        ranked = _rank_candidates(all_candidates, request.query)
        start = (max(request.page, 1) - 1) * request.limit
        candidates = ranked[start:start + request.limit]
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
        quality = _assess_quality(
            AcquisitionResult(
                provider=self.provider,
                provider_type=self.provider_type,
                status=status,
                reason=reason,
                message="",
                candidates=candidates,
                items=items,
            ),
            request.query,
        )
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
            quality=quality,
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
        bridge_payload = {"query": request.query, "limit": request.limit}
        if request.platforms:
            bridge_payload["platforms"] = request.platforms
        payload = json.dumps(bridge_payload).encode("utf-8")
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
        GithubSearchProvider(),
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
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    with urlopen(request, timeout=15) as response:
        data = response.read()
        # Handle gzip/deflate encoding
        encoding = response.headers.get("Content-Encoding", "")
        if encoding == "gzip":
            import gzip
            data = gzip.decompress(data)
        elif encoding == "deflate":
            import zlib
            data = zlib.decompress(data)
        return data.decode("utf-8", errors="replace")


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
    if not isinstance(markdown, str):
        fit = getattr(markdown, "fit_markdown", "")
        if fit:
            return str(fit)
        raw = getattr(markdown, "raw_markdown", "")
        if raw:
            text = _extract_main_content(str(raw), is_html=False)
            if text and len(text) >= 200:
                return text
    cleaned_html = getattr(result, "cleaned_html", "")
    if cleaned_html:
        text = _extract_main_content(str(cleaned_html), is_html=True)
        if text and len(text) >= 200:
            return text
    if isinstance(markdown, str) and markdown:
        return markdown
    return str(cleaned_html or "")


def _extract_main_content(content: str, is_html: bool) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    main = (
        soup.find("div", class_="mw-parser-output")
        or soup.find("main")
        or soup.find("article")
        or soup.find("div", {"id": "content"})
        or soup.find("div", class_="content")
    )
    if main:
        return main.get_text(separator="\n", strip=True)
    return ""


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


_URL_RE = re.compile(r'https?://\S+')
_NEWS_KEYWORDS = ("事件", "回应", "声明", "官方", "突发", "新闻", "公告", "真相", "辟谣", "通报", "热搜")
_NEWS_CONTEXT_KEYWORDS = ("最新", "近日", "刚刚", "紧急")
_TECH_INTENT_KEYWORDS = ("评测", "测评", "排行", "榜单", "benchmark", "排名", "对比", "跑分", "天梯", "模型", "配置", "超频", "参数")
_MAINSTREAM_DOMAINS = {
    "weibo.com", "xiaohongshu.com", "bilibili.com",
    "people.com.cn", "xinhuanet.com", "cctv.com",
}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))


def _is_all_ascii(text: str) -> bool:
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    ascii_letters = len(re.findall(r'[a-zA-Z]', text))
    return cjk == 0 and ascii_letters >= 3


def _cjk_ratio(text: str) -> float:
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    total = len(re.findall(r'\S', text))
    if total == 0:
        return 0.0
    return cjk / total


def _assess_navigation(raw_content: str) -> QualityAssessment | None:
    if not raw_content:
        return None
    lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
    if not lines:
        return None
    url_count = sum(1 for line in lines if _URL_RE.search(line))
    url_ratio = url_count / len(lines)
    if url_ratio > 0.15:
        return QualityAssessment(
            score="low",
            signals=["navigation-heavy"],
            reason="页面主要是导航菜单或链接索引",
            suggestions=["尝试其他 URL 或用 search_github 查 issues"],
        )
    from collections import Counter
    counts = Counter(lines)
    repeated = sum(count for count in counts.values() if count > 1)
    if lines and (repeated / len(lines)) > 0.3:
        return QualityAssessment(
            score="low",
            signals=["navigation-heavy"],
            reason="页面主要是导航菜单或链接索引",
            suggestions=["尝试其他 URL 或用 search_github 查 issues"],
        )
    return None


def _assess_language(query: str, results: list[dict]) -> QualityAssessment | None:
    if not results:
        return None
    query_has_cjk = _has_cjk(query)
    query_is_ascii = _is_all_ascii(query)
    if not query_has_cjk and not query_is_ascii:
        return None
    texts = []
    for r in results:
        texts.append(r.get("title", "") + " " + r.get("snippet", ""))
    combined = " ".join(texts)
    results_cjk_ratio = _cjk_ratio(combined)
    results_all_ascii = _is_all_ascii(combined)
    mismatch = (query_has_cjk and results_all_ascii) or (query_is_ascii and results_cjk_ratio >= 0.8)
    if not mismatch:
        return None
    return QualityAssessment(
        score="low",
        signals=["language-mismatch"],
        reason="搜索结果语言与查询语言不匹配",
        suggestions=["尝试用目标语言重新搜索或添加语言限定词"],
    )


def _assess_domain_concentration(results: list[dict]) -> QualityAssessment | None:
    if len(results) < 5:
        return None
    top5 = results[:5]
    from collections import Counter
    hostnames = []
    for r in top5:
        url = r.get("url", "")
        try:
            host = urllib.parse.urlparse(url).hostname or ""
            host = host.lower()
        except Exception:
            host = ""
        if host:
            hostnames.append(host)
    counts = Counter(hostnames)
    if not counts:
        return None
    domain, count = counts.most_common(1)[0]
    if count > 3:
        return QualityAssessment(
            score="low",
            signals=["domain-concentration"],
            reason=f"结果集中在单一域名 ({domain})",
            suggestions=["尝试其他搜索关键词以获取更多来源"],
        )
    return None


def _assess_snippet_only(result: AcquisitionResult) -> QualityAssessment | None:
    if result.items:
        return None
    if not result.candidates:
        return None
    return QualityAssessment(
        score="medium",
        signals=["snippet-only"],
        reason="仅有搜索摘要，未能提取正文内容",
        suggestions=["尝试直接访问 URL 获取完整内容"],
    )


def _assess_key_platform_missing(query: str, results: list[dict]) -> QualityAssessment | None:
    # Strong news keywords alone are enough
    has_strong_news = any(kw in query for kw in _NEWS_KEYWORDS)
    # Context keywords (最新/近日) need another news keyword to trigger
    has_context_news = any(kw in query for kw in _NEWS_CONTEXT_KEYWORDS)
    # Tech intent keywords suppress news classification
    has_tech_intent = any(kw in query for kw in _TECH_INTENT_KEYWORDS)
    if not has_strong_news and not (has_context_news and not has_tech_intent):
        return None
    for r in results:
        url = r.get("url", "")
        try:
            host = urllib.parse.urlparse(url).hostname or ""
            host = host.lower()
        except Exception:
            host = ""
        if any(host == d or host.endswith("." + d) for d in _MAINSTREAM_DOMAINS):
            return None
    return QualityAssessment(
        score="medium",
        signals=["key-platform-missing"],
        reason="新闻类查询缺少主流平台结果",
        suggestions=["尝试在微博、小红书、B站等平台搜索"],
    )


_SEMANTIC_TOKEN_RE = re.compile(r'[\u4e00-\u9fff]{2,}|[a-z0-9]+(?:[x×][a-z0-9]+)*')
_SEMANTIC_STOP_WORDS = frozenset({
    "的", "是", "了", "在", "和", "与", "或", "及", "等", "中", "为", "对", "到",
    "从", "被", "将", "把", "让", "给", "用", "向", "以", "也", "都", "就", "还",
    "又", "再", "很", "太", "最", "更", "比", "不", "没", "有", "这", "那", "个",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "like",
    "through", "after", "over", "between", "out", "against", "during",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than", "too",
    "very", "just", "because", "if", "when", "where", "how", "what",
    "which", "who", "whom", "this", "that", "these", "those", "it", "its",
    "how", "最新", "新闻", "资讯", "首页", "官网", "下载", "登录", "注册",
})


def _semantic_tokens(text: str) -> set[str]:
    tokens = set()
    for m in _SEMANTIC_TOKEN_RE.finditer(text.lower()):
        t = m.group()
        if t not in _SEMANTIC_STOP_WORDS and len(t) >= 2:
            tokens.add(t)
            # CJK bigrams: "正常查询" → {"正常", "常查", "查询"}
            if len(t) >= 3 and all(ord(c) > 0x4e00 for c in t):
                for i in range(len(t) - 1):
                    bigram = t[i:i+2]
                    if bigram not in _SEMANTIC_STOP_WORDS:
                        tokens.add(bigram)
    return tokens


_METHOD_INTENT_KEYWORDS = frozenset({
    "怎么", "如何", "方法", "教程", "判断", "检测", "验证", "鉴别",
    "how to", "tutorial", "guide", "diagnose",
    "步骤", "技巧", "攻略", "入门", "上手", "操作",
})
_METHOD_RESPONSE_KEYWORDS = frozenset({
    "教程", "步骤", "方法", "操作", "设置", "调", "进bios", "跑分", "烤机",
    "稳定性", "温度", "电压", "频率", "负压", "pbo", "curve", "optimizer",
    "tutorial", "guide", "step", "setting", "config", "stable", "stress",
    "测试", "验证", "实测", "经验", "分享",
})


def _assess_semantic_mismatch(query: str, results: list[dict[str, str]]) -> QualityAssessment | None:
    if not results:
        return None
    query_tokens = _semantic_tokens(query)
    if not query_tokens:
        return None
    coverages = []
    for r in results[:5]:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        result_tokens = _semantic_tokens(text)
        if not query_tokens:
            coverages.append(0.0)
            continue
        # Check both exact token match and substring containment
        hits = 0
        for qt in query_tokens:
            if qt in result_tokens:
                hits += 1
            elif any(qt in rt for rt in result_tokens):
                hits += 0.5
            elif any(rt in qt for rt in result_tokens if len(rt) >= 2):
                hits += 0.5
        coverages.append(hits / len(query_tokens))
    avg_coverage = sum(coverages) / len(coverages) if coverages else 0
    # Low coverage on majority of results → semantic mismatch
    low_count = sum(1 for c in coverages if c < 0.3)
    signals = []
    if low_count >= 3 or avg_coverage < 0.25:
        signals.append("semantic-mismatch")
    # Method-intent check: if query asks "how to" but results are just reviews/specs
    query_lower = query.lower()
    has_method_intent = any(kw in query_lower for kw in _METHOD_INTENT_KEYWORDS)
    if has_method_intent:
        method_response_count = 0
        for r in results[:5]:
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            if any(kw in text for kw in _METHOD_RESPONSE_KEYWORDS):
                method_response_count += 1
        if method_response_count < 2:
            signals.append("method-answers-missing")
    if signals:
        reasons = []
        if "semantic-mismatch" in signals:
            reasons.append(f"搜索结果与查询语义不相关 (平均覆盖率 {avg_coverage:.0%})")
        if "method-answers-missing" in signals:
            reasons.append("方法型查询但结果多为评测/参数页，缺少教程/步骤/实测内容")
        return QualityAssessment(
            score="low",
            signals=signals,
            reason="; ".join(reasons),
            suggestions=["尝试换关键词、加 site: 过滤、或用 search_chinese_platforms 补充社区经验"],
        )
    return None


_SCORE_RANK = {"low": 0, "medium": 1, "high": 2}


def _assess_quality(result: AcquisitionResult, query: str) -> QualityAssessment:
    signals: list[str] = []
    suggestions: list[str] = []
    reasons: list[str] = []
    worst = "high"

    # No results at all → low
    if not result.candidates:
        return QualityAssessment(
            score="low",
            signals=["no-candidates"],
            reason="未返回任何搜索结果",
            suggestions=["尝试换关键词或去掉 site: 限制"],
        )

    def _merge(qa: QualityAssessment | None) -> None:
        nonlocal worst
        if qa is None:
            return
        signals.extend(qa.signals)
        suggestions.extend(qa.suggestions)
        reasons.append(qa.reason)
        if _SCORE_RANK.get(qa.score, 2) < _SCORE_RANK.get(worst, 2):
            worst = qa.score

    try:
        raw = result.items[0].raw_content if result.items else ""
        _merge(_assess_navigation(raw))
    except Exception:
        pass

    try:
        top5 = [{"title": c.title, "snippet": c.snippet or ""} for c in result.candidates[:5]]
        _merge(_assess_language(query, top5))
    except Exception:
        pass

    try:
        url_dicts = [{"url": c.url or ""} for c in result.candidates[:5]]
        _merge(_assess_domain_concentration(url_dicts))
    except Exception:
        pass

    try:
        _merge(_assess_snippet_only(result))
    except Exception:
        pass

    try:
        kp_dicts = [{"url": c.url or "", "title": c.title or ""} for c in result.candidates[:5]]
        _merge(_assess_key_platform_missing(query, kp_dicts))
    except Exception:
        pass

    try:
        sem_dicts = [{"title": c.title or "", "snippet": c.snippet or ""} for c in result.candidates[:5]]
        _merge(_assess_semantic_mismatch(query, sem_dicts))
    except Exception:
        pass

    if not signals:
        return QualityAssessment(score="high", signals=[], reason="", suggestions=[])

    return QualityAssessment(
        score=worst,
        signals=signals,
        reason="; ".join(reasons),
        suggestions=list(dict.fromkeys(suggestions)),
    )
