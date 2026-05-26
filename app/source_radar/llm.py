import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
        )

    def synthesize(self, query: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
        return _fallback_analysis(query, evidence)


class OpenAIResponsesProvider:
    status = "configured"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        endpoint: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    @classmethod
    def from_environment(cls):
        config = load_openai_config()
        api_key = os.environ.get("OPENAI_API_KEY") or config.get("api_key")
        if not api_key:
            return LocalFallbackProvider()
        model = os.environ.get(
            "SOURCE_RADAR_OPENAI_MODEL",
            config.get("model", "gpt-4.1-mini"),
        )
        endpoint = os.environ.get(
            "SOURCE_RADAR_OPENAI_ENDPOINT",
            config.get("endpoint", "https://api.openai.com/v1/responses"),
        )
        return cls(api_key=api_key, model=model, endpoint=_normalize_endpoint(endpoint))

    def judge(self, claim: str, evidence: list[EvidenceCard]) -> Judgement:
        prompt = _build_prompt(claim, evidence)
        if self.endpoint.endswith("/chat/completions"):
            data = _post_json(self.endpoint, self.api_key, _chat_payload(self.model, prompt))
        else:
            try:
                data = _post_json(
                    self.endpoint,
                    self.api_key,
                    {
                        "model": self.model,
                        "input": prompt,
                    },
                )
            except HTTPError as error:
                if error.code not in {400, 404, 405, 501, 502}:
                    raise
                data = _post_json(
                    _chat_completions_endpoint(self.endpoint),
                    self.api_key,
                    _chat_payload(self.model, prompt),
                )
        summary = _extract_output_text(data).strip()
        if not summary:
            summary = _extract_chat_text(data).strip()
        if not summary:
            summary = "The AI provider returned no text."
        return Judgement(
            status="ai-judged" if evidence else "no-evidence",
            summary=summary,
            evidence_ids=[card.id for card in evidence],
            gaps=[] if evidence else ["No evidence cards were available to the AI."],
        )

    def synthesize(self, query: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
        prompt = _build_synthesis_prompt(query, evidence)
        data = _call_model(self.endpoint, self.api_key, self.model, prompt)
        text = _extract_output_text(data).strip() or _extract_chat_text(data).strip()
        if not text:
            return _fallback_analysis(query, evidence)
        return _analysis_from_text(text, evidence)


def _post_json(endpoint: str, api_key: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _call_model(endpoint: str, api_key: str, model: str, prompt: str) -> dict[str, object]:
    if endpoint.endswith("/chat/completions"):
        return _post_json(endpoint, api_key, _chat_payload(model, prompt))
    try:
        return _post_json(
            endpoint,
            api_key,
            {
                "model": model,
                "input": prompt,
            },
        )
    except HTTPError as error:
        if error.code not in {400, 404, 405, 501, 502}:
            raise
        return _post_json(
            _chat_completions_endpoint(endpoint),
            api_key,
            _chat_payload(model, prompt),
        )


def _build_prompt(claim: str, evidence: list[EvidenceCard]) -> str:
    evidence_payload = [
        {
            "id": card.id,
            "source_type": card.source_type,
            "title": card.title,
            "url": card.url,
            "summary": card.summary,
            "adapter": card.adapter,
        }
        for card in evidence
    ]
    return (
        "You are source-radar's built-in verification agent. "
        "Judge the user's claim only from the evidence cards. "
        "Cite evidence card IDs, state uncertainty, and do not invent facts.\n\n"
        f"Claim: {claim}\n"
        f"Evidence cards JSON: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )


def _build_synthesis_prompt(query: str, evidence: list[EvidenceCard]) -> str:
    evidence_payload = [
        {
            "id": card.id,
            "source_type": card.source_type,
            "title": card.title,
            "url": card.url,
            "summary": card.summary,
            "adapter": card.adapter,
        }
        for card in evidence
    ]
    return (
        "You are source-radar's information synthesis agent. "
        "Answer the user's question by synthesizing the collected search and crawler "
        "results. Focus on what the sources collectively say, repeated patterns, "
        "representative cases, disagreements when present, and noisy or marketing-like "
        "sources. Do not produce a heavy fact-check audit, evidence-gap checklist, or "
        "next-search plan. Cite evidence card IDs.\n\n"
        "Return valid JSON only with these keys: summary, key_points, source_notes, "
        "disagreements, noise_notes. key_points, source_notes, disagreements, and "
        "noise_notes must be arrays of short strings.\n\n"
        f"Question: {query}\n"
        f"Evidence cards JSON: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )


def _normalize_endpoint(endpoint: str) -> str:
    cleaned = endpoint.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    if cleaned.endswith("/responses"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/responses"
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
