import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from .models import SourceItem


FIXTURE_ITEMS = [
    SourceItem(
        source_type="project-doc",
        title="source-radar project README",
        url="local://README.md",
        snippet=(
            "source-radar is a local, AI-friendly CLI and collection "
            "engine for Chinese internet source verification."
        ),
        adapter="fixture",
    )
]


def collect_fixture_items(claim: str) -> list[SourceItem]:
    normalized = claim.lower()
    if "source-radar" in normalized or "本地 cli" in normalized:
        return FIXTURE_ITEMS
    return []


class _PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip_depth:
            self.text_parts.append(text)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _fetch_text(url: str, timeout: int = 10) -> str:
    request = Request(url, headers={"User-Agent": "source-radar/0.1"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _extract_page(url: str, html: str, source_type: str, adapter: str) -> list[SourceItem]:
    parser = _PageTextParser()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip() or url
    text = " ".join(parser.text_parts)
    snippet = text[:500].strip()
    if not snippet:
        return []
    return [
        SourceItem(
            source_type=source_type,
            title=title,
            url=url,
            snippet=snippet,
            adapter=adapter,
            retrieved_at=_utc_now(),
        )
    ]


def collect_web_page(url: str, html: str | None = None) -> list[SourceItem]:
    page_html = html if html is not None else _fetch_text(url)
    return _extract_page(url, page_html, "web-page", "web")


def collect_official_page(url: str, html: str | None = None) -> list[SourceItem]:
    page_html = html if html is not None else _fetch_text(url)
    return _extract_page(url, page_html, "official-announcement", "official")


def collect_github_repo(
    repo: str, payload: dict[str, object] | None = None
) -> list[SourceItem]:
    repo_slug = repo.strip().removeprefix("https://github.com/").strip("/")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo_slug):
        return []
    if payload is None:
        url = f"https://api.github.com/repos/{repo_slug}"
        payload = json.loads(_fetch_text(url))

    full_name = str(payload.get("full_name") or repo_slug)
    html_url = str(payload.get("html_url") or f"https://github.com/{repo_slug}")
    description = str(payload.get("description") or "No repository description.")
    stars = payload.get("stargazers_count", "unknown")
    forks = payload.get("forks_count", "unknown")
    pushed_at = payload.get("pushed_at", "unknown")
    snippet = (
        f"{description} stars: {stars}; forks: {forks}; "
        f"last pushed: {pushed_at}"
    )
    return [
        SourceItem(
            source_type="github-repository",
            title=f"GitHub repository {full_name}",
            url=html_url,
            snippet=snippet,
            adapter="github",
            retrieved_at=_utc_now(),
            metadata={
                "full_name": full_name,
                "stars": str(stars),
                "forks": str(forks),
                "pushed_at": str(pushed_at),
            },
        )
    ]
