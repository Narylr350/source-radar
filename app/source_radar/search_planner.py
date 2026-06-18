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
    source_hint: str = ""
    enable_comments: bool = False


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
    "- source_hint: tell the evaluator what source types to prefer:\n"
    "  - 'official+github' for technical errors, bugs, config (prefer docs, GitHub issues)\n"
    "  - 'authoritative' for news, celebrity status (prefer confirmed sources, not rumors)\n"
    "  - 'event_confirmation' for person status events (death, arrest, resignation, illness) — "
    "MUST include 讣告/官方/公司/声明 keywords in queries\n"
    "  - 'benchmark' for comparisons, evaluations, rankings (prefer leaderboards, reviews)\n"
    "  - 'community' for experiences, how-tos (prefer forums, tutorials)\n"
    "  - '' (empty) for general queries\n"
    "- For 'benchmark' queries, always include attempts WITHOUT site restriction too "
    "(leaderboards like artificialanalysis.ai, chat.lmsys.org, livebench.ai may not be indexed by Bing)\n"
    "- For 'official+github' queries, try site:github.com for issues AND a separate unrestricted search for docs\n"
    "- Queries with 评测/排行/对比/哪个好/哪个强 MUST use source_hint='benchmark'\n"
    "- Queries with 怎么/如何/教程/排查 MUST use source_hint='official+github' or 'community'\n"
    "- enable_comments: set true ONLY for queries needing user feedback/experience:\n"
    "  - 翻车/体验反馈 (小米15拍照翻车)\n"
    "  - 硬件实测/体质/温度/兼容 (9800X3D怎么判断体质)\n"
    "  - 报错解决方案 with community experience\n"
    "  - B站/微博/小红书 explicitly asking for comment area\n"
    "  Do NOT enable for: official facts, regulations, prices, schedules, GitHub issues, general tutorials\n"
    "- Queries about someone's death/status (死了吗/去世/逝世/怎么了/被抓/辞职/出事了) "
    "MUST use source_hint='event_confirmation'. Generate attempts that include:\n"
    "  1. Entity name + 讣告 (official obituary)\n"
    "  2. Entity name + 公司/工作室/团队 + 声明/讣告 (company/studio statement)\n"
    "  3. Entity name + 官方账号 (official social media)\n"
    "  Do NOT use 辟谣 or 最新动态 as primary queries — these find rumors, not confirmation.\n"
    "- Exact entity protection: when a person name is a common word (张/王/李), "
    "always quote the full name in the query (e.g. '张雪峰' not just 张雪峰) to avoid "
    "being split into individual characters.\n"
    "- On retry: change strategy (different site/platform/keywords), not just longer query.\n\n"
    "Examples:\n"
    '- "vllm报CUDA OOM" → attempts: '
    '{"query":"vllm gpu_memory_utilization max_model_len","site":"docs.vllm.ai","source_hint":"official+github"}, '
    '{"query":"vllm CUDA out of memory github issues","site":"github.com","source_hint":"official+github"}\n'
    '- "张雪峰死了吗" → attempts: '
    '{"query":"张雪峰 讣告","source_hint":"event_confirmation"}, '
    '{"query":"苏州峰学蔚来 声明 讣告","source_hint":"event_confirmation"}, '
    '{"query":"张雪峰 官方账号 最新","platform":"wb","source_hint":"event_confirmation"}\n'
    '- "AI模型评测哪个靠谱" → attempts: '
    '{"query":"Artificial Analysis LLM leaderboard","source_hint":"benchmark"}, '
    '{"query":"Chatbot Arena leaderboard 2026","source_hint":"benchmark"}, '
    '{"query":"AI模型评测 排行榜","source_hint":"benchmark"}\n'
    '- "amd9800x3d怎么判断体质" → '
    '{"query":"9800X3D 体质 PBO","site":"chiphell.com","platform":"tieba","source_hint":"community"}\n'
    '- "小米15拍照翻车" → '
    '{"query":"小米15 拍照 翻车","platform":"xhs","source_hint":"community","enable_comments":true}\n\n'
    "Return valid JSON:\n"
    '{"attempts": [{"query": "...", "site": "", "platform": "", "page": 1, "source_hint": "", "reason": "...", "enable_comments": false}], '
    '"strategy_notes": "..."}\n\n'
    "Generate 1-3 attempts. site/platform/source_hint can be empty strings. enable_comments defaults to false."
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
    from datetime import UTC, datetime
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    parts = [f"Current date: {today} (UTC)", f"User query: {query}"]
    if quality_signals:
        parts.append(f"Quality signals: {', '.join(quality_signals)}")
        if "event-confirmation-needs-strong-source" in quality_signals:
            parts.append(
                "CRITICAL: This is a person status event query. Previous results lacked strong confirmation. "
                "You MUST generate queries with: 讣告, 逝世, 去世, 官方声明, 公司, 工作室, 团队. "
                "Do NOT use 辟谣, 最新动态, 近况 — these find rumors, not confirmation."
            )
    if failed_attempts:
        lines = []
        for a in failed_attempts:
            line = f"- query={a.query!r}, site={a.site!r}, reason={a.reason!r}"
            if a.source_hint:
                line += f", source_hint={a.source_hint!r}"
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
                            source_hint=str(item.get("source_hint", "")),
                            enable_comments=bool(item.get("enable_comments", False)),
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
