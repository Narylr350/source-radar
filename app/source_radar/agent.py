from dataclasses import replace
import re
from collections.abc import Callable
from typing import Protocol

from .acquisition import (
    AcquisitionProvider,
    AcquisitionRequest,
    AcquisitionResult,
    default_providers,
)
from .evidence import build_evidence_cards
from .judgement import estimate_evidence_confidence
from .llm import (
    AIProvider,
    compute_source_profile,
    plan_research,
    synthesize_research,
    _dedupe_evidence,
)
from .models import (
    AgentTrace,
    EvidenceCard,
    InformationAnalysis,
    Judgement,
    ResearchReport,
    SourceItem,
    SynthesisReport,
    VerifyReport,
)


class JudgementProvider(Protocol):
    status: str
    model: str

    def judge(self, claim: str, evidence: list[EvidenceCard]) -> Judgement:
        ...

    def synthesize(self, query: str, evidence: list[EvidenceCard]) -> InformationAnalysis:
        ...


class VerificationAgent:
    def __init__(
        self,
        provider: JudgementProvider | None = None,
        acquisition_providers: list[AcquisitionProvider] | None = None,
    ) -> None:
        self.provider = provider or AIProvider.from_environment()
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
        progress: Callable[[str], None] | None = None,
    ) -> VerifyReport:
        tools = self.plan_tools(claim, source=source, url=url, repo=repo)
        _progress(progress, f"已规划工具: {', '.join(tools)}")
        items: list[SourceItem] = []
        tool_calls: list[dict[str, str]] = []
        acquisition_results: list[AcquisitionResult] = []
        for index, tool in enumerate(tools, start=1):
            _progress(progress, f"[{index}/{len(tools)}] 采集 {tool}")
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
            _progress(
                progress,
                f"[{index}/{len(tools)}] {tool}: {result.status}, "
                f"{len(result.candidates)} 个候选, {len(tool_items)} 条结果",
            )
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
        _progress(progress, f"已压缩为 {len(evidence)} 张证据卡")
        ai_status = self.provider.status
        try:
            _progress(progress, f"调用 AI 判断: {self.provider.model}")
            judgement = self.provider.judge(claim, evidence)
            confidence = estimate_evidence_confidence(claim, evidence)
            if judgement.confidence == "unknown":
                judgement = replace(judgement, **confidence)
            elif not judgement.confidence_reason:
                judgement = replace(
                    judgement,
                    confidence_reason=confidence["confidence_reason"],
                )
            _progress(progress, f"AI 判断完成: {judgement.status}")
        except Exception as error:
            ai_status = "error"
            _progress(progress, f"AI 判断失败: {error}")
            judgement = Judgement(
                status="ai-error",
                summary="The AI provider failed after evidence collection.",
                evidence_ids=[card.id for card in evidence],
                gaps=[str(error)],
                **estimate_evidence_confidence(claim, evidence),
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

    def ask(
        self,
        query: str,
        *,
        source: str = "auto",
        url: str | None = None,
        repo: str | None = None,
        html: str | None = None,
        github_payload: dict[str, object] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> SynthesisReport:
        tools = self.plan_tools(query, source=source, url=url, repo=repo)
        _progress(progress, f"已规划工具: {', '.join(tools)}")
        items: list[SourceItem] = []
        tool_calls: list[dict[str, str]] = []
        acquisition_results: list[AcquisitionResult] = []
        for index, tool in enumerate(tools, start=1):
            _progress(progress, f"[{index}/{len(tools)}] 采集 {tool}")
            result = self.run_tool(
                tool,
                claim=query,
                url=url,
                repo=repo,
                html=html,
                github_payload=github_payload,
            )
            acquisition_results.append(result)
            tool_items = result.items
            items.extend(tool_items)
            _progress(
                progress,
                f"[{index}/{len(tools)}] {tool}: {result.status}, "
                f"{len(result.candidates)} 个候选, {len(tool_items)} 条结果",
            )
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
        _progress(progress, f"已压缩为 {len(evidence)} 张证据卡")
        ai_status = self.provider.status
        try:
            _progress(progress, f"调用 AI 综合: {self.provider.model}")
            analysis = self.provider.synthesize(query, evidence)
            _progress(progress, "AI 综合完成")
        except Exception as error:
            ai_status = "error"
            _progress(progress, f"AI 综合失败: {error}")
            analysis = InformationAnalysis(
                summary="The AI provider failed after source collection.",
                key_points=[],
                source_notes=[],
                disagreements=[],
                noise_notes=[str(error)],
            )
        trace = AgentTrace(
            mode="analysis",
            ai_status=ai_status,
            model=self.provider.model,
            planned_tools=tools,
            tool_calls=tool_calls,
            acquisition=[result.to_trace() for result in acquisition_results],
        )
        return SynthesisReport(
            query=query,
            status=(
                "analysis-ready"
                if evidence and ai_status != "error"
                else "no-evidence"
                if not evidence
                else "ai-error"
            ),
            evidence=evidence,
            analysis=analysis,
            agent=trace,
        )

    def research(
        self,
        query: str,
        *,
        max_rounds: int = 1,
        progress: Callable[[str], None] | None = None,
    ) -> ResearchReport:
        if not isinstance(self.provider, AIProvider):
            return ResearchReport(
                query=query, status="ai-error",
                requested_max_rounds=max_rounds, executed_rounds=0,
                multi_round_enabled=False, plan={}, queries=[],
                evidence_count_before_dedupe=0, evidence_count=0,
                source_profile={}, consensus="unclear", transferability="unclear",
                applicability="not_enough", risk_level="unknown",
                gaps=["AI 未配置，research 需要 AI provider"], conclusion="",
                recommended_steps=[], key_findings=[], evidence=[], agent=None,
            )

        provider = self.provider
        endpoint, headers, model = provider.endpoint, provider._headers(), provider.model

        # 1. Plan
        _progress(progress, "规划研究方案...")
        plan = plan_research(
            endpoint, headers, model, query,
            _provider_capabilities_summary(),
        )
        search_queries = plan.get("search_queries", [query])
        # Dedupe queries
        seen: set[str] = set()
        unique_queries: list[str] = []
        for q in search_queries:
            stripped = q.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_queries.append(stripped)
        if not unique_queries:
            unique_queries = [query]
        plan["search_queries"] = unique_queries
        planner_status = "ok" if plan.get("subquestions") else "fallback"

        # 2. Collect
        tools = self.plan_tools(query, source="auto")
        all_items: list[SourceItem] = []
        query_traces: list[dict] = []
        for sq in unique_queries:
            q_items: list[SourceItem] = []
            failures: list[str] = []
            for tool in tools:
                result = self.run_tool(tool, claim=sq, url=None, repo=None,
                                       html=None, github_payload=None)
                q_items.extend(result.items)
                if result.status not in ("ok", "items-found", "candidates-found"):
                    failures.append(f"{tool}: {result.reason}")
            all_items.extend(q_items)
            query_traces.append({
                "query": sq, "providers": tools,
                "candidates": len(q_items),
                "evidence_count": len(q_items),
                "failures": failures,
            })

        # 3. Dedupe
        evidence_before = len(all_items)
        all_items_deduped = _dedupe_source_items(all_items)
        evidence = build_evidence_cards(all_items_deduped)
        evidence = _dedupe_evidence(evidence)

        # 4. Synthesize
        _progress(progress, "综合分析中...")
        syn = synthesize_research(
            endpoint, headers, model, query, evidence,
            plan.get("subquestions", []),
        )
        raw_profile = syn.get("source_profile", {})
        if not raw_profile:
            raw_profile = compute_source_profile(evidence)

        trace = AgentTrace(
            mode="research",
            ai_status=provider.status,
            model=model,
            planned_tools=tools,
            tool_calls=query_traces,
            acquisition=[],
        )

        return ResearchReport(
            query=query,
            status="research-ready" if evidence else "insufficient-evidence",
            requested_max_rounds=max_rounds,
            executed_rounds=1,
            multi_round_enabled=False,
            plan=plan,
            queries=query_traces,
            evidence_count_before_dedupe=evidence_before,
            evidence_count=len(evidence),
            source_profile=raw_profile,
            consensus=syn.get("consensus", "unclear"),
            transferability=syn.get("transferability", "unclear"),
            applicability=syn.get("applicability", "not_enough"),
            risk_level=syn.get("risk_level", "unknown"),
            gaps=syn.get("gaps", []),
            conclusion=syn.get("conclusion", ""),
            recommended_steps=syn.get("recommended_steps", []),
            key_findings=syn.get("key_findings", []),
            evidence=evidence,
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
            return ["search", *self._ready_collection_tools(claim)]
        return ["fixture"]

    def _ready_collection_tools(self, claim: str) -> list[str]:
        tools: list[tuple[int, str]] = []
        for name, provider in self.acquisition_providers.items():
            provider_type = getattr(provider, "provider_type", "")
            if provider_type not in {"external-bridge", "generic-crawler"}:
                continue
            if not hasattr(provider, "status"):
                continue
            try:
                status = provider.status()
            except Exception:
                continue
            capabilities = status.diagnostics.get("capabilities", "")
            if status.status != "ok":
                continue
            if provider_type == "generic-crawler":
                tools.append((self._collection_priority(name, status, claim), name))
            elif "search" in capabilities.split(","):
                tools.append((self._collection_priority(name, status, claim), name))
        return [name for _, name in sorted(tools)]

    def _collection_priority(self, name: str, status: AcquisitionResult, claim: str) -> int:
        # Neutral priority: all ready providers have equal weight.
        # AI/user chooses sources via --local-services, not keyword matching.
        if name == "trafilatura":
            return 0
        if name == "crawl4ai":
            return 1
        if name == "firecrawl":
            return 2
        if name == "mediacrawler":
            return 3
        return 1

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


def _provider_capabilities_summary() -> str:
    providers = default_providers()
    names = [p.provider for p in providers]
    return f"search, trafilatura, crawl4ai, mediacrawler ({', '.join(names)})"


def _dedupe_source_items(items: list[SourceItem]) -> list[SourceItem]:
    seen_urls: set[str] = set()
    result: list[SourceItem] = []
    for item in items:
        key = (item.url or "").rstrip("/")
        if key and key in seen_urls:
            continue
        if key:
            seen_urls.add(key)
        result.append(item)
    return result


def _progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
