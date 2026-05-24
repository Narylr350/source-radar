import re
from typing import Protocol

from .adapters import (
    collect_fixture_items,
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from .evidence import build_evidence_cards
from .llm import OpenAIResponsesProvider
from .models import AgentTrace, EvidenceCard, Judgement, SourceItem, VerifyReport


class JudgementProvider(Protocol):
    status: str
    model: str

    def judge(self, claim: str, evidence: list[EvidenceCard]) -> Judgement:
        ...


class VerificationAgent:
    def __init__(self, provider: JudgementProvider | None = None) -> None:
        self.provider = provider or OpenAIResponsesProvider.from_environment()

    def verify(
        self,
        claim: str,
        *,
        source: str = "auto",
        url: str | None = None,
        repo: str | None = None,
        html: str | None = None,
        github_payload: dict[str, object] | None = None,
    ) -> VerifyReport:
        tools = self.plan_tools(claim, source=source, url=url, repo=repo)
        items: list[SourceItem] = []
        tool_calls: list[dict[str, str]] = []
        for tool in tools:
            tool_items = self.run_tool(
                tool,
                claim=claim,
                url=url,
                repo=repo,
                html=html,
                github_payload=github_payload,
            )
            items.extend(tool_items)
            tool_calls.append(
                {
                    "tool": tool,
                    "items_found": str(len(tool_items)),
                    "status": "ok" if tool_items else "no-evidence",
                }
            )

        evidence = build_evidence_cards(items)
        ai_status = self.provider.status
        try:
            judgement = self.provider.judge(claim, evidence)
        except Exception as error:
            ai_status = "error"
            judgement = Judgement(
                status="ai-error",
                summary="The AI provider failed after evidence collection.",
                evidence_ids=[card.id for card in evidence],
                gaps=[str(error)],
            )
        trace = AgentTrace(
            mode="agent",
            ai_status=ai_status,
            model=self.provider.model,
            planned_tools=tools,
            tool_calls=tool_calls,
        )
        return VerifyReport(
            claim=claim,
            status=judgement.status,
            evidence=evidence,
            judgement=judgement,
            agent=trace,
        )

    def plan_tools(
        self,
        claim: str,
        *,
        source: str,
        url: str | None,
        repo: str | None,
    ) -> list[str]:
        if source != "auto":
            return [source]
        if url:
            return ["web"]
        target_repo = repo or claim
        if re.fullmatch(r"[^/\s]+/[^/\s]+", target_repo.strip()):
            return ["github"]
        if "source-radar" in claim.lower() or "本地 cli" in claim.lower():
            return ["fixture"]
        return ["fixture"]

    def run_tool(
        self,
        tool: str,
        *,
        claim: str,
        url: str | None,
        repo: str | None,
        html: str | None,
        github_payload: dict[str, object] | None,
    ) -> list[SourceItem]:
        if tool == "web":
            if not url:
                raise ValueError("--url is required when the agent uses the web tool")
            return collect_web_page(url, html=html)
        if tool == "official":
            if not url:
                raise ValueError("--url is required when the agent uses the official tool")
            return collect_official_page(url, html=html)
        if tool == "github":
            target_repo = repo or claim
            return collect_github_repo(target_repo, payload=github_payload)
        return collect_fixture_items(claim)
