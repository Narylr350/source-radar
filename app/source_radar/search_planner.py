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


@dataclass
class SearchPlan:
    original_query: str
    attempts: list[SearchAttempt] = field(default_factory=list)
    strategy_notes: str = ""


_PLANNER_SYSTEM = (
    "You are source-radar's search planner. Your job is to generate effective "
    "search queries for a Chinese-aware internet research tool.\n\n"
    "Rules:\n"
    "- Remove filler words (怎么, 如何, 什么, 是不是, 请问, 想知道).\n"
    "- Extract core entities (product names, person names, events, version numbers).\n"
    "- Add domain terms when helpful (评测, 对比, 教程, 官方, 体验).\n"
    "- Translate CN↔EN when the other language likely has better results.\n"
    "- Choose site restrictions for known-good sources when appropriate "
    "(zhihu.com, bilibili.com, weibo.com, xiaohongshu.com, github.com, etc.).\n"
    "- On retry: change strategy based on failure signals — broaden/narrow query, "
    "try different site, use different keywords, switch language.\n\n"
    "Return valid JSON only:\n"
    '{"attempts": [{"query": "...", "site": "...", "reason": "..."}], '
    '"strategy_notes": "..."}\n\n'
    "Generate 1-3 attempts per query. site can be empty for unrestricted search."
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
) -> str:
    parts = [f"User query: {query}"]
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
) -> SearchPlan:
    """Call LLM to generate a search plan. Falls back to single-attempt on failure."""
    from .llm import _call_model, _extract_output_text, _extract_chat_text, _strip_code_fence

    user_prompt = build_planner_prompt(query, failed_attempts=failed_attempts, top_results=top_results)
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
