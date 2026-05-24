import re
from typing import Protocol

from .acquisition import (
    AcquisitionProvider,
    AcquisitionRequest,
    AcquisitionResult,
    default_providers,
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
    def __init__(
        self,
        provider: JudgementProvider | None = None,
        acquisition_providers: list[AcquisitionProvider] | None = None,
    ) -> None:
        self.provider = provider or OpenAIResponsesProvider.from_environment()
        providers = acquisition_providers or default_providers()
        self.acquisition_providers = {
            acquisition_provider.provider: acquisition_provider
            for acquisition_provider in providers
        }

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
        acquisition_results: list[AcquisitionResult] = []
        for tool in tools:
            result = self.run_tool(
                tool,
                claim=claim,
                url=url,
                repo=repo,
                html=html,
                github_payload=github_payload,
            )
            acquisition_results.append(result)
            tool_items = result.items
            items.extend(tool_items)
            tool_calls.append(
                {
                    "tool": tool,
                    "items_found": str(len(tool_items)),
                    "status": result.status,
                    "candidates": str(len(result.candidates)),
                    "reason": result.reason,
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
            acquisition=[result.to_trace() for result in acquisition_results],
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
        if "search" in self.acquisition_providers:
            return ["search", *self._ready_bridge_tools()]
        return ["fixture"]

    def _ready_bridge_tools(self) -> list[str]:
        tools: list[str] = []
        for name, provider in self.acquisition_providers.items():
            if getattr(provider, "provider_type", "") != "external-bridge":
                continue
            if not hasattr(provider, "status"):
                continue
            try:
                status = provider.status()
            except Exception:
                continue
            capabilities = status.diagnostics.get("capabilities", "")
            if status.status == "ok" and "search" in capabilities.split(","):
                tools.append(name)
        return tools

    def run_tool(
        self,
        tool: str,
        *,
        claim: str,
        url: str | None,
        repo: str | None,
        html: str | None,
        github_payload: dict[str, object] | None,
    ) -> AcquisitionResult:
        provider = self.acquisition_providers.get(tool)
        if not provider:
            raise ValueError(f"unknown acquisition provider: {tool}")
        if tool in {"web", "official"} and html is not None:
            source_type = "web-page" if tool == "web" else "official-announcement"
            from .adapters import _extract_page

            items = _extract_page(url or "", html, source_type, tool)
            from .acquisition import _items_result

            return _items_result(tool, "builtin-adapter", items)
        if tool == "github" and github_payload is not None:
            from .adapters import collect_github_repo
            from .acquisition import _items_result

            items = collect_github_repo(repo or claim, payload=github_payload)
            return _items_result(tool, "builtin-adapter", items)
        return provider.collect(
            AcquisitionRequest(
                query=claim,
                url=url,
                repo=repo,
            )
        )
