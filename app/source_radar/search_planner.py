import json
import logging
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote_plus

_log = logging.getLogger("source_radar.search_planner")


@dataclass
class SearchAttempt:
    query: str
    site: str = ""
    engine: str = "bing"
    reason: str = ""
    platform: str = ""
    page: int = 1


@dataclass
class SearchPlan:
    original_query: str
    attempts: list[SearchAttempt] = field(default_factory=list)
    strategy_notes: str = ""


_PLANNER_SYSTEM = (
    "You are source-radar's search planner. Generate short, focused search queries.\n\n"
    "Rules:\n"
    "- Queries: 3-6 words, 2-4 terms. No filler (怎么, 如何, 什么, 请问).\n"
    "- site: restrict to known-good domains (chiphell.com, zhihu.com, github.com, bilibili.com).\n"
    "- platform: use MediaCrawler platforms when useful — "
    "tieba=hardware/PC, bili=tutorials/reviews, wb=news/hot topics, xhs=consumer/lifestyle, dy=consumer/video.\n"
    "- page: set >1 to deepen search on retry.\n"
    "- On retry: change strategy (different site/platform/keywords), not just longer query.\n\n"
    "Examples:\n"
    '- "amd9800x3d怎么判断体质" → {"query":"9800X3D 体质 PBO","site":"chiphell.com","platform":"","page":1}\n'
    '- "小米15拍照怎么样" → {"query":"小米15 拍照评测","site":"zhihu.com","platform":"xhs","page":1}\n'
    '- "显卡温度高" → {"query":"GPU 温度高 散热","site":"","platform":"tieba","page":1}\n\n'
    "Return valid JSON:\n"
    '{"attempts": [{"query": "...", "site": "", "platform": "", "page": 1, "reason": "..."}], '
    '"strategy_notes": "..."}\n\n'
    "Generate 1-3 attempts. site/platform can be empty strings."
)


def clean_query(raw: str) -> str:
    """Generic cleanup: whitespace, fullwidth->halfwidth, URL decode. No domain logic."""
    s = unquote_plus(raw.strip())
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())
    return s


def build_planner_prompt(
    query: str,
    failed_attempts: list[SearchAttempt] | None = None,
    top_results: list[dict] | None = None,
    quality_signals: list[str] | None = None,
) -> str:
    parts = [f"User query: {query}"]
    if quality_signals:
        parts.append(f"Quality signals: {', '.join(quality_signals)}")
    if failed_attempts:
        lines = []
        for a in failed_attempts:
            line = f"- query={a.query!r}, site={a.site!r}, reason={a.reason!r}"
            lines.append(line)
        parts.append("Previous failed attempts:\n" + "\n".join(lines))
    if top_results:
        lines = []
        for r in top_results[:5]:
            lines.append(f"- {r.get('title', '')} | {r.get('url', '')} | {r.get('snippet', '')[:100]}")
        parts.append("Top results from last attempt:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def plan_search(
    query: str,
    *,
    llm_response: str | None = None,
    failed_attempts: list[SearchAttempt] | None = None,
    top_results: list[dict] | None = None,
) -> SearchPlan:
    cleaned = clean_query(query)
    if llm_response:
        try:
            parsed = json.loads(llm_response)
            if isinstance(parsed, dict) and isinstance(parsed.get("attempts"), list):
                attempts = []
                for item in parsed["attempts"]:
                    if isinstance(item, dict) and item.get("query"):
                        attempts.append(SearchAttempt(
                            query=str(item["query"]),
                            site=str(item.get("site", "")),
                            reason=str(item.get("reason", "")),
                            platform=str(item.get("platform", "")),
                            page=int(item.get("page", 1)),
                        ))
                if attempts:
                    return SearchPlan(
                        original_query=query,
                        attempts=attempts,
                        strategy_notes=str(parsed.get("strategy_notes", "")),
                    )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return SearchPlan(
        original_query=query,
        attempts=[SearchAttempt(query=cleaned)],
        strategy_notes="fallback: single attempt with cleaned query",
    )


def call_planner_llm(
    endpoint: str,
    headers: dict,
    model: str,
    query: str,
    failed_attempts: list[SearchAttempt] | None = None,
    top_results: list[dict] | None = None,
    quality_signals: list[str] | None = None,
) -> SearchPlan:
    """Call LLM to generate a search plan. Falls back to single-attempt on failure."""
    from .llm import _call_model, _extract_output_text, _extract_chat_text, _strip_code_fence

    user_prompt = build_planner_prompt(query, failed_attempts=failed_attempts, top_results=top_results, quality_signals=quality_signals)
    full_prompt = _PLANNER_SYSTEM + "\n\n" + user_prompt
    try:
        data = _call_model(endpoint, headers, model, full_prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        text = _strip_code_fence(text)
        if not text:
            _log.warning("planner LLM returned empty response")
            return plan_search(query, failed_attempts=failed_attempts, top_results=top_results)
        plan = plan_search(query, llm_response=text, failed_attempts=failed_attempts, top_results=top_results)
        if plan.strategy_notes.startswith("fallback"):
            _log.warning("planner LLM returned non-JSON (first 300 chars): %s", text[:300])
        return plan
    except Exception as e:
        _log.warning("planner LLM call failed: %s, using fallback", e)
        return plan_search(query, failed_attempts=failed_attempts, top_results=top_results)
