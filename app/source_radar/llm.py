import json
import os
from urllib.request import Request, urlopen

from .config import load_openai_config
from .judgement import judge_claim
from .models import EvidenceCard, Judgement


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
        payload = {
            "model": self.model,
            "input": _build_prompt(claim, evidence),
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        summary = _extract_output_text(data).strip()
        if not summary:
            summary = "The AI provider returned no text."
        return Judgement(
            status="ai-judged" if evidence else "no-evidence",
            summary=summary,
            evidence_ids=[card.id for card in evidence],
            gaps=[] if evidence else ["No evidence cards were available to the AI."],
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


def _normalize_endpoint(endpoint: str) -> str:
    cleaned = endpoint.rstrip("/")
    if cleaned.endswith("/responses"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/responses"
    return f"{cleaned}/v1/responses"


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
