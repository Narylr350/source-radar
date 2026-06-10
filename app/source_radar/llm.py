import json
import os
import time as _time
from urllib.error import HTTPError, URLError
from http.client import RemoteDisconnected
from socket import timeout as SocketTimeout
from urllib.request import Request, urlopen

_MAX_RETRIES = int(os.environ.get("SOURCE_RADAR_MAX_RETRIES", "3"))
_REQUEST_TIMEOUT = int(os.environ.get("SOURCE_RADAR_REQUEST_TIMEOUT", "60"))
_RETRY_BACKOFF = (2, 5, 10)
_RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}

from .config import load_openai_config
from .judgement import judge_claim
from .models import EvidenceCard, InformationAnalysis, Judgement


class LocalFallbackProvider:
    status = "not-configured"
    model = "local-fallback"

    def judge(self, claim: str, evidence: list[EvidenceCard]) -> Judgement:
        judgement = judge_claim(claim, evidence)
        return Judgement(
            status=judgement.status,
            summary=judgement.summary,
            evidence_ids=judgement.evidence_ids,
            gaps=[
                "Configure a local AI provider with `source-radar config setup` "
                "or `source-radar config set-openai` to enable built-in AI judgement.",
                *judgement.gaps,
            ],
            confidence=judgement.confidence,
            confidence_reason=judgement.confidence_reason,
        )

    def synthesize(self, query: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
        return _fallback_analysis(query, evidence)


class AIProvider:
    status = "configured"

    def __init__(
        self,
        api_key: str,
        model: str = "",
        endpoint: str = "",
        provider: str = "",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = _resolve_endpoint(endpoint, provider)
        self.provider = provider

    @classmethod
    def from_environment(cls):
        config = load_openai_config()
        api_key = os.environ.get("OPENAI_API_KEY") or config.get("api_key")
        if not api_key:
            return LocalFallbackProvider()
        model = os.environ.get("SOURCE_RADAR_OPENAI_MODEL") or config.get("model", "")
        endpoint = os.environ.get("SOURCE_RADAR_OPENAI_ENDPOINT") or config.get("endpoint", "")
        provider = os.environ.get("SOURCE_RADAR_AI_PROVIDER") or config.get("provider", "")
        return cls(api_key=api_key, model=model, endpoint=endpoint, provider=provider)

    def _headers(self) -> dict[str, str]:
        if self.provider in ("anthropic", "x-api-key"):
            return {"x-api-key": self.api_key, "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def judge(self, claim: str, evidence: list[EvidenceCard],
              session_context: str = "") -> Judgement:
        prompt = _build_prompt(claim, evidence, session_context=session_context)
        data = _call_model(self.endpoint, self._headers(), self.model, prompt)
        summary = _extract_output_text(data).strip()
        if not summary:
            summary = _extract_chat_text(data).strip()
        if not summary:
            summary = "The AI provider returned no text."
        return _judgement_from_text(summary, evidence)

    def synthesize(self, query: str, evidence: list[EvidenceCard],
                   session_context: str = "") -> InformationAnalysis:
        if not evidence:
            return _fallback_analysis(query, evidence)
        prompt = _build_synthesis_prompt(query, evidence, session_context=session_context)
        data = _call_model(self.endpoint, self._headers(), self.model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        if not text:
            return _fallback_analysis(query, evidence)
        return _analysis_from_text(text, evidence)


def _post_json(endpoint: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            request = Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except HTTPError as error:
            last_error = error
            if error.code not in _RETRYABLE_CODES:
                raise
            if attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                _time.sleep(wait)
                continue
            raise
        except (URLError, SocketTimeout, RemoteDisconnected, TimeoutError, OSError) as error:
            last_error = error
            if attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                _time.sleep(wait)
                continue
            raise
    raise last_error  # type: ignore[misc]


def _call_model(endpoint: str, headers: dict, model: str, prompt: str) -> dict[str, object]:
    if endpoint.endswith("/chat/completions"):
        return _post_json(endpoint, headers, _chat_payload(model, prompt))
    try:
        return _post_json(
            endpoint,
            headers,
            {"model": model, "input": prompt},
        )
    except HTTPError as error:
        if error.code not in {400, 404, 405, 501, 502}:
            raise
        return _post_json(
            _chat_completions_endpoint(endpoint),
            headers,
            _chat_payload(model, prompt),
        )


def _build_prompt(claim: str, evidence: list[EvidenceCard],
                  session_context: str = "") -> str:
    evidence_payload = _evidence_payload_with_budget(evidence)
    session_block = ""
    if session_context:
        session_block = f"Session context:\n{session_context}\n\n"
    return (
        "You are source-radar's built-in verification agent. "
        "Judge the user's claim only from the evidence cards. "
        "Cite evidence card IDs, state uncertainty, and do not invent facts. "
        "Use distilled for quick fact/parameter/risk lookup. "
        "Use raw_excerpt for original details, quotes, and contradictions. "
        "Use summary only as a quick overview. "
        "Do not use information not present in summary, raw_excerpt, or distilled.\n\n"
        "Return valid JSON only with these keys: summary, evidence_ids, gaps, "
        "confidence, confidence_reason. summary must be one concise Chinese paragraph. "
        "evidence_ids and gaps must be arrays of short strings. confidence must be "
        "one of high, medium, low, none, unknown and must describe evidence quality, "
        "not model self-confidence. Base confidence on source coverage, first-party "
        "confirmation, platform diversity, repeated reposting, access failures, and "
        "whether key platforms such as Weibo are missing for Chinese breaking news. "
        "If the evidence lacks an official or first-party source for a current policy, "
        "exam, product, release, or public-figure life/death claim, say that the "
        "conclusion is uncertain instead of forcing a yes/no answer.\n\n"
        f"{session_block}"
        f"Claim: {claim}\n"
        f"Evidence cards JSON: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )


def _build_synthesis_prompt(query: str, evidence: list[EvidenceCard],
                            session_context: str = "") -> str:
    evidence_payload = _evidence_payload_with_budget(evidence)
    session_block = ""
    if session_context:
        session_block = f"Session context:\n{session_context}\n\n"
    return (
        "You are source-radar's information synthesis agent. "
        "Answer the user's question by synthesizing the collected search and crawler "
        "results. Focus on what the sources collectively say, repeated patterns, "
        "representative cases, disagreements when present, and noisy or marketing-like "
        "sources. Do not produce a heavy fact-check audit, evidence-gap checklist, or "
        "next-search plan. Cite evidence card IDs.\n\n"
        "Use distilled for quick fact/parameter/risk lookup. "
        "Use raw_excerpt for original details, parameters, caveats, quotes, and contradictions. "
        "Use summary only as a quick overview. "
        "Do not use information not present in summary, raw_excerpt, or distilled.\n\n"
        "Return valid JSON only with these keys: summary, key_points, source_notes, "
        "disagreements, noise_notes. key_points, source_notes, disagreements, and "
        "noise_notes must be arrays of short strings.\n\n"
        f"{session_block}"
        f"Question: {query}\n"
        f"Evidence cards JSON: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )


def _resolve_endpoint(endpoint: str, provider: str) -> str:
    """Resolve the effective API endpoint based on provider protocol."""
    cleaned = endpoint.rstrip("/")
    # If endpoint already points to a specific API path, use as-is
    if any(cleaned.endswith(suffix) for suffix in (
        "/chat/completions", "/responses", "/messages",
        "/generateContent", "/v1", "/v1beta",
    )):
        return cleaned
    # Provider defaults
    if provider == "anthropic":
        return f"{cleaned}/v1/messages"
    if provider == "gemini":
        return f"{cleaned}/v1beta/models"
    # OpenAI-compatible
    return f"{cleaned}/v1/responses"


def _chat_completions_endpoint(endpoint: str) -> str:
    cleaned = endpoint.rstrip("/")
    if cleaned.endswith("/v1/responses"):
        return cleaned[: -len("/responses")] + "/chat/completions"
    if cleaned.endswith("/responses"):
        return cleaned[: -len("/responses")] + "/chat/completions"
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


def _chat_payload(model: str, prompt: str) -> dict[str, object]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }


def _extract_output_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _extract_chat_text(data: dict) -> str:
    parts: list[str] = []
    for choice in data.get("choices", []):
        message = choice.get("message", {})
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def _analysis_from_text(text: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict):
        return InformationAnalysis(
            summary=str(parsed.get("summary") or text),
            key_points=_string_list(parsed.get("key_points")),
            source_notes=_string_list(parsed.get("source_notes")) or _source_notes(evidence),
            disagreements=_string_list(parsed.get("disagreements")),
            noise_notes=_string_list(parsed.get("noise_notes")),
        )
    return InformationAnalysis(
        summary=text,
        key_points=_fallback_key_points(evidence),
        source_notes=_source_notes(evidence),
        disagreements=[],
        noise_notes=_noise_notes(evidence),
    )


def _judgement_from_text(text: str, evidence: list[EvidenceCard]) -> Judgement:
    status = "ai-judged" if evidence else "no-evidence"
    default_gaps = [] if evidence else ["No evidence cards were available to the AI."]
    try:
        parsed = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    summary = str(parsed.get("summary") or text).strip()
    evidence_ids = _known_evidence_ids(parsed.get("evidence_ids"), evidence)
    return Judgement(
        status=status,
        summary=summary or "The AI provider returned no text.",
        evidence_ids=evidence_ids or [card.id for card in evidence],
        gaps=_string_list(parsed.get("gaps")) or default_gaps,
        confidence=_confidence_value(parsed.get("confidence")),
        confidence_reason=str(parsed.get("confidence_reason") or ""),
    )


def _known_evidence_ids(value: object, evidence: list[EvidenceCard]) -> list[str]:
    known = {card.id for card in evidence}
    return [item for item in _string_list(value) if item in known]


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _confidence_value(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "medium", "low", "none", "unknown"}:
        return text
    return "unknown"


def _fallback_analysis(query: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
    if not evidence:
        return InformationAnalysis(
            summary=f"没有找到可综合分析的来源：{query}",
            key_points=[],
            source_notes=[],
            disagreements=[],
            noise_notes=[],
        )
    return InformationAnalysis(
        summary=f"已围绕“{query}”收集 {len(evidence)} 条来源，可先按来源类型和重复出现的观点阅读。",
        key_points=_fallback_key_points(evidence),
        source_notes=_source_notes(evidence),
        disagreements=[],
        noise_notes=_noise_notes(evidence),
    )


def _fallback_key_points(evidence: list[EvidenceCard]) -> list[str]:
    return [
        f"{card.title}: {card.summary[:160]} [{card.id}]"
        for card in evidence[:5]
    ]


def _source_notes(evidence: list[EvidenceCard]) -> list[str]:
    counts: dict[str, int] = {}
    for card in evidence:
        key = card.adapter or card.source_type
        counts[key] = counts.get(key, 0) + 1
    return [f"{name}: {count} 条来源" for name, count in sorted(counts.items())]


def _noise_notes(evidence: list[EvidenceCard]) -> list[str]:
    notes: list[str] = []
    if any(card.source_type == "search-result" for card in evidence):
        notes.append("搜索结果只作为线索，优先看正文抽取和社区原帖。")
    if any(card.adapter in {"trafilatura", "crawl4ai"} for card in evidence):
        notes.append("网页正文已被本地抽取，但仍需留意软文、SEO 和搬运内容。")
    return notes


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


# ── research ──────────────────────────────────────────────────────


def plan_research(endpoint: str, headers: dict, model: str, query: str,
                  ready_tools: list[str], local_services_enabled: bool) -> tuple[dict, str]:
    tools_str = ", ".join(ready_tools) if ready_tools else "search (fallback)"
    local_str = "enabled" if local_services_enabled else "disabled"
    prompt = (
        "You are source-radar's research planner. Do NOT answer the question. "
        "Your ONLY job is to decompose it into research sub-questions and "
        "generate search queries.\n\n"
        "Return valid JSON only:\n"
        '{"research_type": "hardware_tuning|product_research|community_summary|'
        'technical_howto|general", "subquestions": [{"id":"q1","question":"...",'
        '"priority":"high|medium|low","needed_source_types":["official","community",'
        '"benchmark","tutorial"]}], "search_queries":["..."]}\n\n'
        f"Ready tools this run: {tools_str}\n"
        f"Local services (MediaCrawler): {local_str}\n"
        f"User question: {query}"
    )
    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        plan = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(plan, dict):
            return {"research_type": "general", "subquestions": [],
                    "search_queries": [query]}, "json-error"
        sq = plan.get("search_queries", [])
        if not isinstance(sq, list) or not sq:
            return {"research_type": plan.get("research_type", "general"),
                    "subquestions": plan.get("subquestions", []),
                    "search_queries": [query]}, "no-queries"
        return plan, "ok"
    except Exception:
        return {"research_type": "general", "subquestions": [],
                "search_queries": [query]}, "json-error"


def synthesize_research(endpoint: str, headers: dict, model: str,
                        query: str, evidence: list[EvidenceCard],
                        subquestions: list[dict]) -> tuple[dict, str]:
    evidence_payload = _evidence_payload_with_budget(evidence)
    prompt = (
        "You are source-radar's research synthesizer. "
        "Answer by organizing collected sources into a structured research result. "
        "This is NOT a fact-check or claim verification. Your job is to summarize "
        "findings, community consensus, transferability, and risks.\n\n"
        "Use distilled for quick fact/parameter/risk lookup. "
        "Use raw_excerpt for original details, parameters, caveats, and contradictions. "
        "Use summary only as a quick overview. "
        "Do not use information not present in summary, raw_excerpt, or distilled.\n\n"
        "Return valid JSON only:\n"
        '{"conclusion":"...","recommended_steps":["..."],"source_profile":'
        '{"official":N,"review":N,"community":N,"video":N,"unknown":N},'
        '"consensus":"high|medium|low|unclear","transferability":'
        '"high|partial|low|unclear","applicability":'
        '"directly_actionable|good_as_starting_point|reference_only|not_enough",'
        '"risk_level":"low|medium|high|unknown","gaps":["..."],"key_findings":["..."]}\n\n'
        f"Question: {query}\n"
        f"Sub-questions: {json.dumps(subquestions, ensure_ascii=False)}\n"
        f"Evidence cards JSON: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )
    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        parsed = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(parsed, dict):
            return {"conclusion": f"基于 {len(evidence)} 条来源的综合失败",
                    "gaps": ["synthesis returned invalid JSON"]}, "ai-error"
        return parsed, "ok"
    except Exception:
        return {"conclusion": f"基于 {len(evidence)} 条来源的综合失败",
                "gaps": ["synthesis failed"]}, "ai-error"


def evaluate_research_gap(
    endpoint: str, headers: dict, model: str, query: str,
    plan: dict, evidence: list[EvidenceCard],
    rounds: list, executed_rounds: int, max_rounds: int,
) -> tuple[dict, str]:
    subqs = plan.get("subquestions", [])
    evidence_summary = [
        {"id": c.id, "title": c.title, "url": c.url,
         "source_type": c.source_type, "adapter": c.adapter}
        for c in evidence[-15:]  # last 15 cards only
    ]
    round_summary = [
        {"round": r["round"], "evidence_after": r.get("evidence_after_dedupe", 0),
         "queries": [q["query"] for q in r.get("queries", [])]}
        for r in rounds
    ] if rounds else []
    prompt = (
        "You are source-radar's research gap evaluator. "
        "Your job is to check whether high-priority subquestions are clearly "
        "unanswered and the missing information is likely discoverable by search.\n\n"
        "Only continue when a high-priority subquestion is clearly unanswered "
        "AND the missing information is likely discoverable by search.\n"
        "Do NOT continue just to increase source count.\n"
        "Do NOT continue for cosmetic completeness.\n"
        "Do NOT continue if the remaining gap is inherent uncertainty "
        "(silicon lottery, personal experience, unavailable private data, "
        "specific CO values, specific voltages, guaranteed stable timings).\n\n"
        "Return valid JSON only:\n"
        '{"sufficiency":"enough|partial|insufficient",'
        '"covered_subquestions":["q1"],"missing_subquestions":["q2"],'
        '"should_continue":true,"next_queries":[{"subquestion_id":"q2",'
        '"query":"..."}],"reason":"...","stop_reason":null}\n\n'
        f"User question: {query}\n"
        f"Subquestions: {json.dumps(subqs, ensure_ascii=False)}\n"
        f"Evidence count: {len(evidence)}\n"
        f"Executed rounds: {executed_rounds}/{max_rounds}\n"
        f"Round summary: {json.dumps(round_summary, ensure_ascii=False)}\n"
        f"Evidence cards JSON (last 15): {json.dumps(evidence_summary, ensure_ascii=False)}"
    )
    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        parsed = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(parsed, dict):
            return {"should_continue": False, "reason": "evaluator returned invalid JSON"}, "json-error"
        return parsed, "ok"
    except Exception:
        return {"should_continue": False, "reason": "evaluator failed"}, "json-error"


def evaluate_session_relevance(
    endpoint: str, headers: dict, model: str,
    current_query: str,
    recent_records: list[dict],
) -> tuple[dict, str]:
    """AI evaluator for session context relevance.

    Returns (relevance_dict, status_string).
    On failure, returns a fallback dict so callers can degrade gracefully.
    """
    if not recent_records:
        return {"related": False, "relation": "unrelated",
                "reuse_evidence": False, "context_summary": "",
                "ignore_reason": "no-records"}, "ok"
    parts: list[str] = []
    for r in recent_records[-5:]:
        line = f"[{r.get('ts','')}] Q: {r.get('query','')[:150]}\nA: {r.get('answer_summary','')[:200]}"
        tools_used = r.get("tools_used", [])
        if tools_used:
            line += f"\ntools: {', '.join(tools_used[:5])}"
        tools_skipped = r.get("tools_skipped", [])
        if tools_skipped:
            skipped_info = [f"{s.get('tool','')}({s.get('reason','')[:30]})" for s in tools_skipped[:5]]
            line += f"\nskipped: {', '.join(skipped_info)}"
        evidence_refs = r.get("evidence_refs", [])
        if evidence_refs:
            ref_strs = [f"{ref.get('title','')[:30]}|{ref.get('provider','')}" for ref in evidence_refs[:3]]
            line += f"\nevidence: {', '.join(ref_strs)}"
        gaps = r.get("gaps", [])
        if gaps:
            line += f"\ngaps: {', '.join(str(g)[:40] for g in gaps[:3])}"
        parts.append(line)
    history_text = "\n".join(parts)
    prompt = (
        "You are source-radar's session relevance evaluator. "
        "Your job is to decide whether the user's CURRENT query is related "
        "to their recent session history.\n\n"
        "Rules:\n"
        "- related=true if the current query is a clear follow-up "
        '(e.g. starts with 那/这个/刚才/继续/上面, or asks about the same topic).\n'
        "- related=true if the current query and recent history share "
        "the same topic domain (same product, same person, same event).\n"
        "- related=false if the topic has clearly changed.\n"
        "- reuse_evidence=true only if prior evidence is still fresh and relevant. "
        "Judge based on whether evidence_refs URLs and topics match the current query.\n"
        "- If the current query contains real-time keywords "
        "(今天/现在/刚刚/实时/最新/新闻/股价/汇率/天气/比赛/赛程/开奖/价格/优惠/活动/降价), "
        "set reuse_evidence=false even if related=true.\n"
        "- context_summary: summarize the user's follow-up context, main evidence "
        "directions from prior queries, and unresolved gaps. Max 500 chars. "
        "Do NOT include full webpage text, cookies, API keys, or secrets.\n\n"
        "Return valid JSON only:\n"
        '{"related":true/false,"relation":"follow_up|same_topic|unrelated",'
        '"reuse_evidence":true/false,"context_summary":"...","ignore_reason":""}\n\n'
        f"Current query: {current_query}\n\n"
        f"Recent session history:\n{history_text}"
    )
    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        parsed = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(parsed, dict):
            return {"related": False, "relation": "unrelated",
                    "reuse_evidence": False, "context_summary": "",
                    "ignore_reason": "ai-parse-error"}, "json-error"
        return parsed, "ok"
    except Exception:
        return {"related": False, "relation": "unrelated",
                "reuse_evidence": False, "context_summary": "",
                "ignore_reason": "ai-error"}, "ai-error"


def evaluate_collection_sufficiency(
    endpoint: str, headers: dict, model: str,
    mode: str, query: str, available_tools: list[str],
    evidence_summaries: list[dict], tool_history: list[dict],
    session_context: str = "",
) -> tuple[dict, str]:
    verify_rules = ""
    if mode == "verify":
        verify_rules = (
            "\nVERIFY MODE - stricter rules:\n"
            "- Do NOT mark evidence_sufficient=true if ALL evidence is search-result "
            "only (no full-text extraction, no official/primary source, no "
            "multi-source cross-reference).\n"
            "- If evidence is all search-results, prefer continuing with trafilatura "
            "to get full-text extraction.\n"
            "- For current policy, prices, news, product releases, public figure "
            "status, regulations, or announcements: prefer official/primary/reliable "
            "sources.\n"
            "- Be conservative: if no primary source is found, return low confidence "
            "and note the gap rather than pretending certainty.\n"
            "- Do NOT select mediacrawler unless the claim explicitly involves "
            "Chinese community controversy, leaks, platform opinion, or user experience.\n"
            "- After search + trafilatura, if still insufficient, stop and report "
            "low confidence rather than running more tools.\n"
        )
    prompt = (
        "You are source-radar's collection evaluator. Your job is to decide "
        "whether the current evidence is sufficient to answer the question, "
        "and if not, what tool to run next.\n\n"
        "Rules:\n"
        "- next_tool must be from available_tools, or empty if evidence is sufficient.\n"
        "- mediacrawler should only be selected for Chinese community platforms "
        "(小红书/微博/B站/贴吧/抖音/知乎), experience reports, controversies, "
        "reviews, or community opinions. Do NOT select mediacrawler for simple "
        "facts, general web questions, official docs, or programming questions.\n"
        "- crawl4ai should only be selected if pages need JavaScript rendering, "
        "trafilatura extraction failed, or content is dynamic.\n"
        "- trafilatura is for extracting full text from search result URLs.\n"
        "- search is for discovering candidate sources.\n"
        "- Max 3 tools total, max 12 evidence cards.\n"
        "- Do not repeat a tool that has already been run.\n"
        + verify_rules +
        "\nReturn valid JSON only:\n"
        '{"evidence_sufficient":true/false,"confidence":"low|medium|high",'
        '"reason":"...","next_tool":"","next_limit":0,'
        '"skip_tools":[{"tool":"mediacrawler","reason":"不需要中文社区讨论"}],'
        '"gaps":["..."]}\n\n'
        f"Mode: {mode}\n"
        f"Query: {query}\n"
        f"Available tools: {available_tools}\n"
        f"Tool history (already run): {json.dumps(tool_history, ensure_ascii=False)}\n"
        f"Evidence summaries: {json.dumps(evidence_summaries, ensure_ascii=False)}\n"
        + (f"Session context: {session_context}\n" if session_context else "")
    )
    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        parsed = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(parsed, dict):
            return _fallback_eval(available_tools, tool_history), "json-error"
        return parsed, "ok"
    except Exception:
        return _fallback_eval(available_tools, tool_history), "json-error"


def _fallback_eval(available_tools: list[str], history: list[dict]) -> dict:
    """Conservative fallback: search → trafilatura → stop."""
    has_search = any(h.get("tool") == "search" for h in history)
    has_traf = any(h.get("tool") == "trafilatura" for h in history)
    if not has_search:
        return {"evidence_sufficient": False, "confidence": "low",
                "reason": "fallback: start with search", "next_tool": "search",
                "next_limit": 5, "skip_tools": [], "gaps": []}
    if not has_traf and "trafilatura" in available_tools:
        return {"evidence_sufficient": False, "confidence": "low",
                "reason": "fallback: try trafilatura after search",
                "next_tool": "trafilatura", "next_limit": 5,
                "skip_tools": [], "gaps": []}
    return {"evidence_sufficient": True, "confidence": "low",
            "reason": "fallback: stop after search+trafilatura",
            "next_tool": "", "next_limit": 0, "skip_tools": [], "gaps": []}


def compute_source_profile(evidence: list[EvidenceCard]) -> dict[str, int]:
    profile: dict[str, int] = {"official": 0, "review": 0, "community": 0,
                                "video": 0, "unknown": 0}
    for card in evidence:
        st = card.source_type or ""
        if st in ("official-announcement", "official-page"):
            profile["official"] += 1
        elif st in ("community-post", "forum"):
            profile["community"] += 1
        elif st in ("video",):
            profile["video"] += 1
        elif st in ("review",):
            profile["review"] += 1
        else:
            profile["unknown"] += 1
    return profile


def _dedupe_evidence(cards: list[EvidenceCard]) -> list[EvidenceCard]:
    seen_urls: dict[str, int] = {}
    seen_titles: dict[str, int] = {}
    result: list[EvidenceCard] = []
    for card in cards:
        url_key = (card.url or "").rstrip("/")
        title_key = (card.title or "").strip().lower()
        existing_idx = -1
        if url_key:
            existing_idx = seen_urls.get(url_key, -1)
        if existing_idx < 0 and title_key:
            existing_idx = seen_titles.get(title_key, -1)
        if existing_idx >= 0:
            if card.raw_content_length > result[existing_idx].raw_content_length:
                result[existing_idx] = card
            continue
        idx = len(result)
        if url_key:
            seen_urls[url_key] = idx
        if title_key:
            seen_titles[title_key] = idx
        result.append(card)
    return result


def _evidence_card_payload(card: EvidenceCard, raw_excerpt_limit: int = 0) -> dict:
    payload: dict[str, object] = {
        "id": card.id,
        "source_type": card.source_type,
        "title": card.title,
        "url": card.url,
        "summary": card.summary,
        "adapter": card.adapter,
    }
    if card.raw_excerpt:
        if raw_excerpt_limit > 0:
            payload["raw_excerpt"] = card.raw_excerpt[:raw_excerpt_limit]
        else:
            payload["raw_excerpt"] = card.raw_excerpt
    if card.distilled:
        payload["distilled"] = card.distilled
    return payload


def _evidence_payload_with_budget(
    cards: list[EvidenceCard], max_cards: int = 12, max_total_raw_chars: int = 18000,
) -> list[dict]:
    """Build evidence payload with total raw_excerpt character budget."""
    selected = cards[:max_cards]
    total_raw = sum(len(c.raw_excerpt) for c in selected)
    if total_raw <= max_total_raw_chars or not selected:
        return [_evidence_card_payload(c) for c in selected]
    # Over budget: keep first card full, shrink rest
    per_card = max_total_raw_chars // len(selected)
    result = []
    for i, card in enumerate(selected):
        if i == 0:
            result.append(_evidence_card_payload(card))
        else:
            result.append(_evidence_card_payload(card, raw_excerpt_limit=max(per_card, 1000)))
    return result


def distill_evidence_cards(
    endpoint: str, headers: dict, model: str,
    query: str, evidence_cards: list[EvidenceCard], mode: str = "ask",
) -> tuple[list[EvidenceCard], dict]:
    """Optionally distill evidence cards with AI structured extraction.

    Returns (updated_cards, profile_dict).
    On failure, returns original cards with empty distillation_status.
    """
    to_distill = [c for c in evidence_cards if c.raw_excerpt][:12]
    requested_count = len(to_distill)
    if not to_distill:
        return evidence_cards, {"distillation_status": "skipped", "distillation_reason": "no raw_excerpt",
                                "distillation_requested_cards": 0, "distillation_returned_cards": 0}

    mode_rules = ""
    if mode == "verify":
        mode_rules = (
            "\nFor verify mode: also extract supporting and contradicting evidence.\n"
        )
    elif mode == "research":
        mode_rules = (
            "\nFor research mode: focus on parameters, steps, risks, stability tests, "
            "and community consensus.\n"
        )

    cards_input = [
        {"id": c.id, "title": c.title, "url": c.url, "source_type": c.source_type,
         "summary": c.summary[:200], "raw_excerpt": (c.raw_excerpt or "")[:2000]}
        for c in to_distill
    ]
    prompt = (
        "You are source-radar's evidence distiller. "
        "Extract structured facts, parameters, warnings, quotes, and unknowns "
        "from the evidence cards. Do NOT invent information not present in the cards.\n\n"
        "Rules:\n"
        "- Parameters, versions, numbers, paths must be preserved verbatim.\n"
        "- Quotes must be short and close to original wording.\n"
        "- If uncertain, put it in unknowns.\n"
        "- Relevance: high/medium/low based on how directly it answers the query.\n"
        f"{mode_rules}\n"
        "Return valid JSON only:\n"
        '{"cards":[{"id":"ev-001","relevance":"high","facts":["..."],'
        '"parameters":[{"name":"...","value":"...","condition":"..."}],'
        '"warnings":["..."],"contradictions":["..."],"quotes":["..."],"unknowns":["..."]}]}'
        f"\n\nQuery: {query}\n"
        f"Evidence cards: {json.dumps(cards_input, ensure_ascii=False)}"
    )

    try:
        data = _call_model(endpoint, headers, model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        parsed = json.loads(_strip_code_fence(text or "{}"))
        if not isinstance(parsed, dict):
            return evidence_cards, {"distillation_status": "error", "distillation_reason": "invalid json"}

        distill_map: dict[str, dict] = {}
        for item in parsed.get("cards", []):
            if isinstance(item, dict) and item.get("id"):
                distill_map[item["id"]] = item

        updated: list[EvidenceCard] = []
        returned_count = 0
        for card in evidence_cards:
            d = distill_map.get(card.id)
            if d:
                updated.append(_card_with_distilled(card, d))
                returned_count += 1
            else:
                updated.append(card)
        return updated, {
            "distillation_status": "ok", "distillation_reason": "",
            "distillation_requested_cards": requested_count,
            "distillation_returned_cards": returned_count,
        }
    except Exception as e:
        return evidence_cards, {
            "distillation_status": "error", "distillation_reason": str(e)[:100],
            "distillation_requested_cards": requested_count,
            "distillation_returned_cards": 0,
        }


def _card_with_distilled(card: EvidenceCard, distilled: dict) -> EvidenceCard:
    from dataclasses import replace
    compression = dict(card.compression)
    compression["method"] = "mechanical_excerpt+ai_distill"
    compression["ai_distilled"] = True
    return replace(card, distilled=distilled, compression=compression)


def should_distill(evidence_cards: list[EvidenceCard], mode: str, override: str = "auto") -> bool:
    """Decide whether to run AI distillation."""
    if override == "always":
        return True
    if override == "never":
        return False
    # auto
    if mode == "research":
        return True
    total_raw = sum(len(c.raw_excerpt) for c in evidence_cards)
    if total_raw > 4000:
        return True
    if mode == "verify" and len(evidence_cards) > 3:
        return True
    return False
