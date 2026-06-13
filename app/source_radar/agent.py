from dataclasses import asdict, dataclass, replace
import logging
import re
import time as _time_module
from collections.abc import Callable
from typing import Protocol

_log = logging.getLogger("source_radar.agent")

from .acquisition import (
    AcquisitionProvider,
    AcquisitionRequest,
    AcquisitionResult,
    default_providers,
)
from .search_planner import call_planner_llm, build_planner_prompt, SearchPlan, SearchAttempt
from .models import QualityAssessment
from .evidence import build_evidence_cards, evidence_input_profile
from .judgement import estimate_evidence_confidence
from .llm import (
    AIProvider,
    _dedupe_evidence,
    compute_source_profile,
    distill_evidence_cards,
    evaluate_collection_sufficiency,
    evaluate_research_gap,
    plan_research,
    should_distill,
    synthesize_research,
)
from .models import (
    AgentTrace,
    CandidateSource,
    EvidenceCard,
    InformationAnalysis,
    Judgement,
    ResearchReport,
    ResearchRound,
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
        session_context: str = "",
        context_used: bool = False,
        session_id: str = "",
        context_records_read: int = 0,
        context_ignore_reason: str = "",
        reused_evidence_count: int = 0,
        distill_evidence: str = "auto",
    ) -> VerifyReport:
        _log.info("verify start: claim=%r, source=%s", claim[:60], source)
        t_verify = _time_module.time()
        use_adaptive = source == "auto" and not url and not repo and isinstance(self.provider, AIProvider)
        if use_adaptive:
            available = self.plan_tools(claim, source="auto", url=None, repo=None)
            items, tool_calls, evidence, acquisition_results, skipped, cache_hit_count, fresh_tool_count = (
                self._adaptive_collect(
                    claim, available=available, progress=progress, mode="verify",
                    session_context=session_context,
                )
            )
            for s in skipped:
                tool_calls.append({"tool": s.get("tool", ""), "skipped": "true",
                                   "reason": s.get("reason", ""),
                                   "skip_reason": s.get("reason", ""),
                                   "decided_by": "collection_evaluator"})
            _progress(progress, f"已构建 {len(evidence)} 张证据卡")
        else:
            available = self.plan_tools(claim, source=source, url=url, repo=repo)
            _progress(progress, f"已规划工具: {', '.join(available)}")
            items: list[SourceItem] = []
            tool_calls: list[dict[str, str]] = []
            acquisition_results: list[AcquisitionResult] = []
            cache_hit_count = 0
            fresh_tool_count = 0
            skipped = []
            for index, tool in enumerate(available, start=1):
                _progress(progress, f"[{index}/{len(available)}] 采集 {tool}")
                t0 = _time_module.time()
                result, cache_hit, cache_key, cache_age = self.run_tool(
                    tool,
                    claim=claim,
                    url=url,
                    repo=repo,
                    html=html,
                    github_payload=github_payload,
                )
                elapsed_ms = str(int((_time_module.time() - t0) * 1000))
                if cache_hit:
                    cache_hit_count += 1
                else:
                    fresh_tool_count += 1
                acquisition_results.append(result)
                tool_items = result.items
                items.extend(tool_items)
                _progress(
                    progress,
                    f"[{index}/{len(available)}] {tool}: {result.status}, "
                    f"{len(result.candidates)} 个候选, {len(tool_items)} 条结果",
                )
                tool_calls.append(
                    {
                        "tool": tool,
                        "items_found": str(len(tool_items)),
                        "status": result.status,
                        "candidates": str(len(result.candidates)),
                        "reason": result.reason,
                        "limit": str(5),
                        "elapsed_ms": elapsed_ms,
                        "cache_hit": str(cache_hit),
                        "cache_key": cache_key,
                        "cache_age_seconds": str(cache_age) if cache_hit else "",
                    }
                )
            evidence = build_evidence_cards(items)
            _progress(progress, f"已构建 {len(evidence)} 张证据卡")
        # Distillation
        distill_profile: dict = {}
        if isinstance(self.provider, AIProvider) and should_distill(evidence, "verify", distill_evidence):
            _progress(progress, "AI 证据提炼中...")
            evidence, distill_profile = distill_evidence_cards(
                self.provider.endpoint, self.provider._headers(), self.provider.model,
                claim, evidence, mode="verify",
            )
        else:
            distill_profile = {"distillation_status": "skipped", "distillation_reason": "not triggered or no AI"}

        ai_status = self.provider.status
        try:
            _progress(progress, f"调用 AI 判断: {self.provider.model}")
            try:
                judgement = self.provider.judge(claim, evidence, session_context=session_context)
            except TypeError:
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
        normalized_skipped = [{"tool": s.get("tool", ""), "reason": s.get("reason", ""),
                               "decided_by": "collection_evaluator"} for s in skipped]
        profile = evidence_input_profile(evidence)
        profile.update(distill_profile)
        trace = AgentTrace(
            mode="agent",
            ai_status=ai_status,
            model=self.provider.model,
            planned_tools=available,
            tool_calls=tool_calls,
            acquisition=[r.to_trace() for r in acquisition_results],
            context_used=context_used,
            session_id=session_id,
            context_records_read=context_records_read,
            context_ignore_reason=context_ignore_reason,
            reused_evidence_count=(reused_evidence_count if context_used else 0),
            fresh_evidence_count=len(evidence),
            actually_used_tools=[tc["tool"] for tc in tool_calls if tc.get("skipped") != "true"],
            skipped_tools=normalized_skipped,
            cache_hit_count=cache_hit_count,
            fresh_tool_count=fresh_tool_count,
            evidence_input_profile=profile,
        )
        _log.info("verify done: status=%s, evidence=%d, elapsed=%.1fs",
                  judgement.status, len(evidence), _time_module.time() - t_verify)
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
        session_context: str = "",
        context_used: bool = False,
        session_id: str = "",
        context_records_read: int = 0,
        context_ignore_reason: str = "",
        reused_evidence_count: int = 0,
        distill_evidence: str = "auto",
    ) -> SynthesisReport:
        _log.info("ask start: query=%r, source=%s", query[:60], source)
        t_ask = _time_module.time()
        use_adaptive = source == "auto" and not url and not repo and isinstance(self.provider, AIProvider)
        if not use_adaptive:
            return self._ask_legacy(
                query, source=source, url=url, repo=repo,
                html=html, github_payload=github_payload, progress=progress,
                session_context=session_context,
                context_used=context_used,
                session_id=session_id,
                context_records_read=context_records_read,
                context_ignore_reason=context_ignore_reason,
                reused_evidence_count=reused_evidence_count,
                distill_evidence=distill_evidence,
            )

        available = self.plan_tools(query, source="auto", url=None, repo=None)
        items, tool_calls, evidence, acquisition_results, skipped, cache_hit_count, fresh_tool_count = (
            self._adaptive_collect(
                query, available=available, progress=progress, mode="ask",
                session_context=session_context,
            )
        )
        for s in skipped:
            tool_calls.append({"tool": s.get("tool", ""), "skipped": "true",
                               "reason": s.get("reason", ""),
                               "skip_reason": s.get("reason", ""),
                               "decided_by": "collection_evaluator"})
        _progress(progress, f"已构建 {len(evidence)} 张证据卡")
        # Distillation
        distill_profile: dict = {}
        if isinstance(self.provider, AIProvider) and should_distill(evidence, "ask", distill_evidence):
            _progress(progress, "AI 证据提炼中...")
            evidence, distill_profile = distill_evidence_cards(
                self.provider.endpoint, self.provider._headers(), self.provider.model,
                query, evidence, mode="ask",
            )
        else:
            distill_profile = {"distillation_status": "skipped", "distillation_reason": "not triggered or no AI"}

        ai_status = self.provider.status
        try:
            _progress(progress, f"调用 AI 综合: {self.provider.model}")
            try:
                analysis = self.provider.synthesize(query, evidence, session_context=session_context)
            except TypeError:
                analysis = self.provider.synthesize(query, evidence)
            _progress(progress, "AI 综合完成")
        except Exception as error:
            ai_status = "error"
            _progress(progress, f"AI 综合失败: {error}")
            analysis = InformationAnalysis(
                summary="The AI provider failed after source collection.",
                key_points=[], source_notes=[], disagreements=[], noise_notes=[str(error)],
            )
        normalized_skipped = [{"tool": s.get("tool", ""), "reason": s.get("reason", ""),
                               "decided_by": "collection_evaluator"} for s in skipped]
        profile = evidence_input_profile(evidence)
        profile.update(distill_profile)
        trace = AgentTrace(
            mode="analysis", ai_status=ai_status, model=self.provider.model,
            planned_tools=available, tool_calls=tool_calls,
            acquisition=[r.to_trace() for r in acquisition_results],
            context_used=context_used,
            session_id=session_id,
            context_records_read=context_records_read,
            context_ignore_reason=context_ignore_reason,
            reused_evidence_count=(reused_evidence_count if context_used else 0),
            fresh_evidence_count=len(evidence),
            actually_used_tools=[tc["tool"] for tc in tool_calls if tc.get("skipped") != "true"],
            skipped_tools=normalized_skipped,
            cache_hit_count=cache_hit_count,
            fresh_tool_count=fresh_tool_count,
            evidence_input_profile=profile,
        )
        status = "analysis-ready" if evidence else "no-evidence"
        _log.info("ask done: status=%s, evidence=%d, elapsed=%.1fs",
                  status, len(evidence), _time_module.time() - t_ask)
        return SynthesisReport(
            query=query,
            status=status,
            evidence=evidence, analysis=analysis, agent=trace,
        )

    def _ask_legacy(
        self, query: str, *, source: str, url: str | None, repo: str | None,
        html: str | None, github_payload: dict[str, object] | None,
        progress: Callable[[str], None] | None,
        session_context: str = "",
        context_used: bool = False,
        session_id: str = "",
        context_records_read: int = 0,
        context_ignore_reason: str = "",
        reused_evidence_count: int = 0,
        distill_evidence: str = "auto",
    ) -> SynthesisReport:
        tools = self.plan_tools(query, source=source, url=url, repo=repo)
        _progress(progress, f"已规划工具: {', '.join(tools)}")
        items: list[SourceItem] = []
        tool_calls: list[dict[str, str]] = []
        acquisition_results: list[AcquisitionResult] = []
        cache_hit_count = 0
        fresh_tool_count = 0
        for index, tool in enumerate(tools, start=1):
            _progress(progress, f"[{index}/{len(tools)}] 采集 {tool}")
            t0 = _time_module.time()
            result, cache_hit, cache_key, cache_age = self.run_tool(
                tool, claim=query, url=url, repo=repo,
                html=html, github_payload=github_payload,
            )
            elapsed_ms = str(int((_time_module.time() - t0) * 1000))
            if cache_hit:
                cache_hit_count += 1
            else:
                fresh_tool_count += 1
            acquisition_results.append(result)
            tool_items = result.items
            items.extend(tool_items)
            _progress(progress, f"[{index}/{len(tools)}] {tool}: {result.status}, "
                      f"{len(result.candidates)} 候选, {len(tool_items)} 条结果")
            tool_calls.append({
                "tool": tool, "items_found": str(len(tool_items)),
                "status": result.status, "candidates": str(len(result.candidates)),
                "reason": result.reason,
                "limit": str(5),
                "elapsed_ms": elapsed_ms,
                "cache_hit": str(cache_hit), "cache_key": cache_key,
                "cache_age_seconds": str(cache_age) if cache_hit else "",
            })
        evidence = build_evidence_cards(items)
        _progress(progress, f"已构建 {len(evidence)} 张证据卡")
        # Distillation
        distill_profile: dict = {}
        if isinstance(self.provider, AIProvider) and should_distill(evidence, "ask", distill_evidence):
            _progress(progress, "AI 证据提炼中...")
            evidence, distill_profile = distill_evidence_cards(
                self.provider.endpoint, self.provider._headers(), self.provider.model,
                query, evidence, mode="ask",
            )
        else:
            distill_profile = {"distillation_status": "skipped", "distillation_reason": "not triggered or no AI"}

        ai_status = self.provider.status
        try:
            _progress(progress, f"调用 AI 综合: {self.provider.model}")
            try:
                analysis = self.provider.synthesize(query, evidence, session_context=session_context)
            except TypeError:
                analysis = self.provider.synthesize(query, evidence)
            _progress(progress, "AI 综合完成")
        except Exception as error:
            ai_status = "error"
            _progress(progress, f"AI 综合失败: {error}")
            analysis = InformationAnalysis(
                summary="The AI provider failed after source collection.",
                key_points=[], source_notes=[], disagreements=[], noise_notes=[str(error)],
            )
        profile = evidence_input_profile(evidence)
        profile.update(distill_profile)
        trace = AgentTrace(
            mode="analysis", ai_status=ai_status, model=self.provider.model,
            planned_tools=tools, tool_calls=tool_calls,
            acquisition=[r.to_trace() for r in acquisition_results],
            context_used=context_used,
            session_id=session_id,
            context_records_read=context_records_read,
            context_ignore_reason=context_ignore_reason,
            reused_evidence_count=(reused_evidence_count if context_used else 0),
            fresh_evidence_count=len(evidence),
            actually_used_tools=[tc["tool"] for tc in tool_calls],
            skipped_tools=[],
            cache_hit_count=cache_hit_count,
            fresh_tool_count=fresh_tool_count,
            evidence_input_profile=profile,
        )
        return SynthesisReport(
            query=query,
            status="analysis-ready" if evidence else "no-evidence",
            evidence=evidence, analysis=analysis, agent=trace,
        )

    def _adaptive_collect(
        self,
        claim: str,
        *,
        available: list[str],
        progress: Callable[[str], None] | None = None,
        mode: str = "ask",
        session_context: str = "",
        max_tools: int = 3,
        evidence_limit: int = 12,
    ) -> tuple[list[SourceItem], list[dict], list[EvidenceCard], list[AcquisitionResult], list[dict], int, int]:
        _ADAPTIVE_TIMEOUT = 180  # seconds — return partial results after this
        _t_start = _time_module.time()
        items: list[SourceItem] = []
        tool_calls: list[dict[str, str]] = []
        ran_tools: list[str] = []
        skipped: list[dict] = []
        acquisition_results: list[AcquisitionResult] = []
        cache_hit_count = 0
        fresh_tool_count = 0

        def _timed_out() -> bool:
            return (_time_module.time() - _t_start) > _ADAPTIVE_TIMEOUT

        # Round 1: AI-planned search (multiple attempts)
        _log.info("adaptive_collect start: claim=%r, mode=%s, available=%s", claim[:60], mode, available)
        search_plan = call_planner_llm(
            self.provider.endpoint, self.provider._headers(), self.provider.model, claim,
        )
        _progress(progress, f"搜索规划: {len(search_plan.attempts)} 个尝试 — {search_plan.strategy_notes[:60]}")

        all_search_candidates: list[CandidateSource] = []
        search_succeeded = False
        last_search_result: AcquisitionResult | None = None

        for attempt in search_plan.attempts:
            progress_parts = [f"采集 search: {attempt.query[:40]}"]
            if attempt.site:
                progress_parts.append(f"site:{attempt.site}")
            if attempt.page > 1:
                progress_parts.append(f"page:{attempt.page}")
            if attempt.source_hint:
                progress_parts.append(f"hint:{attempt.source_hint}")
            _progress(progress, " | ".join(progress_parts))
            t0 = _time_module.time()
            result, cache_hit, cache_key, cache_age = self.run_tool(
                "search", claim=attempt.query, url=None, repo=None, html=None, github_payload=None,
                site=attempt.site or None, page=attempt.page, platform=attempt.platform or None,
            )
            elapsed_s = _time_module.time() - t0
            _log.info("search done: query=%r status=%s items=%d elapsed=%.1fs", attempt.query[:40], result.status, len(result.items), elapsed_s)
            elapsed_ms = str(int(elapsed_s * 1000))
            if cache_hit:
                cache_hit_count += 1
            else:
                fresh_tool_count += 1
            acquisition_results.append(result)
            items.extend(result.items)
            all_search_candidates.extend(result.candidates)
            last_search_result = result
            tool_calls.append({
                "tool": "search", "query": attempt.query, "site": attempt.site,
                "page": str(attempt.page), "platform": attempt.platform,
                "source_hint": attempt.source_hint,
                "items_found": str(len(result.items)),
                "status": result.status, "candidates": str(len(result.candidates)),
                "reason": attempt.reason, "limit": str(5),
                "elapsed_ms": elapsed_ms,
                "cache_hit": str(cache_hit), "cache_key": cache_key,
                "cache_age_seconds": str(cache_age) if cache_hit else "",
            })
            if result.status in ("ok", "no-evidence"):
                search_succeeded = True

            # Auto-downgrade: if site-filtered search returned no results, retry without site
            if attempt.site and result.status == "no-evidence" and not result.candidates:
                _progress(progress, f"site:{attempt.site} 无结果，去掉 site 重搜...")
                fallback_result, fc_hit, fc_key, fc_age = self.run_tool(
                    "search", claim=attempt.query, url=None, repo=None, html=None, github_payload=None,
                    page=attempt.page,
                )
                if fallback_result.candidates:
                    _progress(progress, f"去掉 site 后: {len(fallback_result.candidates)} 候选")
                    acquisition_results.append(fallback_result)
                    items.extend(fallback_result.items)
                    all_search_candidates.extend(fallback_result.candidates)
                    last_search_result = fallback_result
                    tool_calls.append({
                        "tool": "search-fallback", "query": attempt.query, "site": "",
                        "page": str(attempt.page), "source_hint": attempt.source_hint,
                        "items_found": str(len(fallback_result.items)),
                        "status": fallback_result.status,
                        "candidates": str(len(fallback_result.candidates)),
                        "reason": f"site:{attempt.site} returned no results, retried without site",
                        "limit": str(5), "elapsed_ms": "0",
                        "cache_hit": str(fc_hit), "cache_key": fc_key,
                        "cache_age_seconds": str(fc_age) if fc_hit else "",
                    })

        ran_tools.append("search")
        total_candidates = len(all_search_candidates)
        total_items = len(items)
        _progress(progress, f"search: {total_candidates} 候选, {total_items} 条结果 ({len(search_plan.attempts)} 个尝试)")

        # Quality gate: if low quality, retry once with planner
        if last_search_result and last_search_result.quality and last_search_result.quality.score == "low":
            bad_signals = last_search_result.quality.signals
            if any(s in bad_signals for s in ["semantic-mismatch", "no-candidates", "method-answers-missing"]):
                _progress(progress, f"质量低 ({', '.join(bad_signals)})，AI 重新规划搜索...")
                failed_info = [SearchAttempt(
                    query=a.query, site=a.site, reason=a.reason,
                    platform=a.platform, page=a.page,
                ) for a in search_plan.attempts]
                top_results = [
                    {"title": c.title or "", "url": c.url or "", "snippet": (c.snippet or "")[:100]}
                    for c in all_search_candidates[:5]
                ]
                retry_plan = call_planner_llm(
                    self.provider.endpoint, self.provider._headers(), self.provider.model, claim,
                    failed_attempts=failed_info, top_results=top_results,
                    quality_signals=bad_signals,
                )
                for attempt in retry_plan.attempts:
                    progress_parts = [f"重试 search: {attempt.query[:40]}"]
                    if attempt.site:
                        progress_parts.append(f"site:{attempt.site}")
                    if attempt.page > 1:
                        progress_parts.append(f"page:{attempt.page}")
                    _progress(progress, " | ".join(progress_parts))
                    t0 = _time_module.time()
                    result, cache_hit, cache_key, cache_age = self.run_tool(
                        "search", claim=attempt.query, url=None, repo=None, html=None, github_payload=None,
                        site=attempt.site or None, page=attempt.page, platform=attempt.platform or None,
                    )
                    elapsed_s = _time_module.time() - t0
                    if cache_hit:
                        cache_hit_count += 1
                    else:
                        fresh_tool_count += 1
                    acquisition_results.append(result)
                    items.extend(result.items)
                    all_search_candidates.extend(result.candidates)
                    tool_calls.append({
                        "tool": "search-retry", "query": attempt.query, "site": attempt.site,
                        "page": str(attempt.page), "platform": attempt.platform,
                        "items_found": str(len(result.items)),
                        "status": result.status, "candidates": str(len(result.candidates)),
                        "reason": attempt.reason, "limit": str(5),
                        "elapsed_ms": str(int(elapsed_s * 1000)),
                        "cache_hit": str(cache_hit), "cache_key": cache_key,
                        "cache_age_seconds": str(cache_age) if cache_hit else "",
                    })

        evidence = build_evidence_cards(items)
        evidence = _dedupe_evidence(evidence)
        _progress(progress, f"证据卡: {len(evidence)} 张，调用采集评估...")

        # Collect planner's platform intent — these are REQUIRED, not hints
        planner_platforms = list(dict.fromkeys(
            a.platform for a in search_plan.attempts if a.platform
        ))
        # Also collect from retry plan if it ran
        if 'retry_plan' in dir():
            for a in retry_plan.attempts:
                if a.platform and a.platform not in planner_platforms:
                    planner_platforms.append(a.platform)

        # Collect source hints from planner for evaluator
        source_hints = list(dict.fromkeys(
            a.source_hint for a in search_plan.attempts if a.source_hint
        ))
        source_hint_str = ",".join(source_hints) if source_hints else ""

        # Search status: "ok"/"no-evidence" = 成功但无结果; "error" = 网络失败
        search_succeeded = search_succeeded or (last_search_result is not None and last_search_result.status in ("ok", "no-evidence"))

        # Force mediacrawler if planner specified platforms (before evaluator)
        if planner_platforms and "mediacrawler" in available and "mediacrawler" not in ran_tools:
            platform_arg = ",".join(planner_platforms)
            _progress(progress, f"规划指定平台 {platform_arg}，执行社区采集...")
            t0 = _time_module.time()
            result, cache_hit, cache_key, cache_age = self.run_tool(
                "mediacrawler", claim=claim, url=None, repo=None, html=None, github_payload=None,
                limit=5, platform=platform_arg,
            )
            elapsed_s = _time_module.time() - t0
            if cache_hit:
                cache_hit_count += 1
            else:
                fresh_tool_count += 1
            acquisition_results.append(result)
            items.extend(result.items)
            ran_tools.append("mediacrawler")
            tool_calls.append({
                "tool": "mediacrawler", "platform": platform_arg,
                "items_found": str(len(result.items)),
                "status": result.status, "reason": "planner-specified-platforms",
                "limit": str(5), "elapsed_ms": str(int(elapsed_s * 1000)),
                "cache_hit": str(cache_hit), "cache_key": cache_key,
                "cache_age_seconds": str(cache_age) if cache_hit else "",
            })
            evidence = build_evidence_cards(items)
            evidence = _dedupe_evidence(evidence)
            _progress(progress, f"社区采集完成: {len(result.items)} 条, 证据卡: {len(evidence)} 张")

        for _round in range(max_tools - 1):
            if _timed_out():
                _progress(progress, f"采集超时 ({_ADAPTIVE_TIMEOUT}s)，返回已有结果 ({len(evidence)} 张证据)")
                break
            if len(evidence) >= evidence_limit:
                _progress(progress, f"证据已达上限 ({evidence_limit} 张)，停止采集")
                break

            # Fast path: search succeeded but no results → skip AI eval, try trafilatura
            # If search failed (network error), still call AI evaluator
            if search_succeeded and not evidence and "trafilatura" in available and "trafilatura" not in ran_tools:
                _progress(progress, "搜索无结果，直接尝试 trafilatura")
                eval_result = {"next_tool": "trafilatura", "next_limit": 5}
                eval_status = "fast-path"
            else:
                provider = self.provider
                eval_result, eval_status = evaluate_collection_sufficiency(
                    provider.endpoint, provider._headers(), provider.model,
                    mode=mode, query=claim, available_tools=available,
                    evidence_summaries=[{"id": c.id, "title": c.title, "url": c.url,
                                         "source_type": c.source_type, "adapter": c.adapter}
                                        for c in evidence[:10]],
                    tool_history=[{"tool": t, "items": tc["items_found"]}
                                  for t, tc in zip(ran_tools, tool_calls)],
                    session_context=session_context,
                    source_hint=source_hint_str,
                )

            for skip in eval_result.get("skip_tools", []):
                skipped.append(skip)
                _progress(progress, f"跳过 {skip.get('tool','')}: {skip.get('reason','')}")

            # Show evaluator's evidence relevance judgment
            relevant = eval_result.get("relevant_evidence", [])
            irrelevant = eval_result.get("irrelevant_evidence", [])
            if relevant or irrelevant:
                _progress(progress, f"证据判定: {len(relevant)}条相关, {len(irrelevant)}条不相关")
                for e in irrelevant[:3]:
                    _progress(progress, f"  ✗ {e.get('id','')}: {e.get('why','')}")
                # Store judgment in tool_calls for trace
                tool_calls.append({
                    "tool": "evaluator-judgment",
                    "relevant_count": str(len(relevant)),
                    "irrelevant_count": str(len(irrelevant)),
                    "relevant_ids": ",".join(relevant) if isinstance(relevant[0], str) else "",
                    "irrelevant_reasons": "; ".join(
                        f"{e.get('id','')}: {e.get('why','')}" for e in irrelevant[:5]
                    ) if irrelevant else "",
                    "reason": eval_result.get("reason", ""),
                })

            # Code-level guard: skip mediacrawler if search already returned evidence
            # BUT: if search quality is low (semantic-mismatch, no-candidates, method-answers-missing), don't skip
            # because web search results may be irrelevant and community sources might help
            if eval_result.get("next_tool") == "mediacrawler" and evidence and "search" in ran_tools:
                last_quality = last_search_result.quality if last_search_result else None
                if last_quality and last_quality.score == "low":
                    _progress(progress, f"搜索质量低 ({', '.join(last_quality.signals)})，允许 mediacrawler 补充")
                elif "mediacrawler" not in ran_tools and planner_platforms:
                    # Planner specified platforms — already ran above, skip duplicate
                    _progress(progress, "跳过 mediacrawler: 已按规划执行过")
                    eval_result["next_tool"] = ""
                    eval_result["next_limit"] = 0
                else:
                    _progress(progress, "跳过 mediacrawler: 搜索已有结果，中文平台作为显式慢工具")
                    skipped.append({"tool": "mediacrawler", "reason": "search already returned evidence, skip slow tool"})
                    eval_result["next_tool"] = ""
                    eval_result["next_limit"] = 0

            # Method-intent guard: if quality has method-answers-missing, don't waste time on trafilatura
            # Redirect to mediacrawler if available and not yet run
            if eval_result.get("next_tool") == "trafilatura" and "mediacrawler" not in ran_tools and "mediacrawler" in available:
                last_quality = last_search_result.quality if last_search_result else None
                if last_quality and "method-answers-missing" in (last_quality.signals or []):
                    _progress(progress, "方法型查询缺少社区经验，跳过 trafilatura，转向 mediacrawler")
                    eval_result["next_tool"] = "mediacrawler"
                    eval_result["next_limit"] = 5

            if eval_result.get("evidence_sufficient", True):
                # code-level guard: verify mode forces trafilatura if only search results
                if mode == "verify" and _evidence_needs_more(evidence, ran_tools, available):
                    _progress(progress, "verify 严格模式: 仅 search-result，继续 trafilatura")
                    eval_result["next_tool"] = "trafilatura"
                    eval_result["next_limit"] = 5
                else:
                    _progress(progress, f"评估: 证据足够，停止采集 ({eval_result.get('reason','')[:60]})")
                    break

            next_tool = eval_result.get("next_tool", "")
            if not next_tool or next_tool in ran_tools or next_tool not in available:
                _progress(progress, "评估: 无需继续采集")
                break

            next_limit = eval_result.get("next_limit", 5) or 5
            _progress(progress, f"采集 {next_tool}...")
            _log.info("next_tool=%s limit=%d", next_tool, next_limit)
            t0 = _time_module.time()
            platform_arg = None
            if next_tool == "mediacrawler":
                planner_platforms = [a.platform for a in search_plan.attempts if a.platform]
                platform_arg = ",".join(planner_platforms) if planner_platforms else None
            result, cache_hit, cache_key, cache_age = self.run_tool(
                next_tool, claim=claim, url=None, repo=None, html=None, github_payload=None,
                limit=next_limit, platform=platform_arg,
            )
            elapsed_s = _time_module.time() - t0
            _log.info("%s done: status=%s items=%d elapsed=%.1fs", next_tool, result.status, len(result.items), elapsed_s)
            elapsed_ms = str(int(elapsed_s * 1000))
            if cache_hit:
                cache_hit_count += 1
            else:
                fresh_tool_count += 1
            acquisition_results.append(result)
            ran_tools.append(next_tool)
            new_count = len(result.items)
            items.extend(result.items)
            tool_calls.append({
                "tool": next_tool, "items_found": str(new_count),
                "status": result.status, "candidates": str(len(result.candidates)),
                "reason": result.reason, "limit": str(next_limit),
                "elapsed_ms": elapsed_ms,
                "cache_hit": str(cache_hit), "cache_key": cache_key,
                "cache_age_seconds": str(cache_age) if cache_hit else "",
            })
            _progress(progress, f"{next_tool}: {result.status}, 新增 {new_count} 条")
            before_evidence = len(evidence)
            evidence = build_evidence_cards(items)
            evidence = _dedupe_evidence(evidence)
            after_evidence = len(evidence)
            if after_evidence == before_evidence:
                _progress(progress, "无新增证据，停止采集")
                break
            _progress(progress, f"累计证据 {after_evidence} 张")

        return items, tool_calls, evidence, acquisition_results, skipped, cache_hit_count, fresh_tool_count

    def research(
        self,
        query: str,
        *,
        max_rounds: int = 1,
        local_services: bool = False,
        progress: Callable[[str], None] | None = None,
        distill_evidence: str = "auto",
    ) -> ResearchReport:
        if not isinstance(self.provider, AIProvider):
            return ResearchReport(
                query=query, status="ai-error",
                requested_max_rounds=max_rounds,
                gaps=["AI 未配置，research 需要 AI provider"],
            )

        provider = self.provider
        endpoint, headers, model = provider.endpoint, provider._headers(), provider.model
        tools = self.plan_tools(query, source="auto", url=None, repo=None)

        # 1. Plan
        _progress(progress, "规划研究方案...")
        _log.info("research start: query=%r, max_rounds=%d, tools=%s", query, max_rounds, tools)
        t_plan = _time_module.time()
        plan, planner_status = plan_research(
            endpoint, headers, model, query,
            ready_tools=tools, local_services_enabled=local_services,
        )
        search_queries = plan.get("search_queries", [])
        _log.info("plan done: status=%s, queries=%d, elapsed=%.1fs",
                  planner_status, len(search_queries),
                  _time_module.time() - t_plan)
        # Normalize: each item is {"query": "...", "tools": [...]}
        seen: set[str] = set()
        unique_queries: list[dict] = []
        for item in search_queries:
            if isinstance(item, dict):
                q = item.get("query", "").strip()
                t = item.get("tools", ["search", "trafilatura"])
            else:
                q = str(item).strip()
                t = ["search", "trafilatura"]
            if q and q not in seen:
                seen.add(q)
                unique_queries.append({"query": q, "tools": [x for x in t if x in tools]})
        if not unique_queries:
            unique_queries = [{"query": query, "tools": ["search", "trafilatura"]}]
        plan["search_queries"] = unique_queries

        # 2. Collect rounds
        all_evidence: list[EvidenceCard] = []
        all_query_traces: list[dict] = []
        rounds: list[ResearchRound] = []
        round_num = 0
        queries_pool = unique_queries  # list of {"query": "...", "tools": [...]}
        searched_qs: set[str] = set()
        evidence_limit = 40
        status = "research-ready"
        evaluator_fallback = False

        while round_num < max_rounds:
            round_num += 1
            round_items: list[SourceItem] = []
            round_traces: list[dict] = []
            _log.info("round %d start: %d queries", round_num, len(queries_pool))

            for q_entry in queries_pool:
                sq = q_entry["query"]
                query_tools = q_entry.get("tools", ["search", "trafilatura"])
                searched_qs.add(sq)
                q_items: list[SourceItem] = []
                q_candidates = 0
                failures: list[str] = []
                cache_hits = 0
                cache_keys: list[str] = []
                cache_ages: list[int] = []
                _log.info("  query=%r tools=%s", sq[:60], query_tools)
                for tool in query_tools:
                    t0 = _time_module.time()
                    _log.info("  tool=%s query=%r ...", tool, sq[:60])
                    result, cache_hit, cache_key, cache_age = self.run_tool(
                        tool, claim=sq, url=None, repo=None, html=None, github_payload=None,
                    )
                    _log.info("  tool=%s status=%s items=%d elapsed=%.1fs",
                              tool, result.status, len(result.items), _time_module.time() - t0)
                    q_items.extend(result.items)
                    q_candidates += len(result.candidates)
                    if cache_hit:
                        cache_hits += 1
                    if cache_key:
                        cache_keys.append(cache_key)
                    if cache_hit:
                        cache_ages.append(cache_age)
                    if result.status not in ("ok", "items-found", "candidates-found"):
                        failures.append(f"{tool}: {result.reason}")
                round_items.extend(q_items)
                round_traces.append({
                    "query": sq, "providers": query_tools,
                    "candidates": q_candidates,
                    "evidence_count": len(q_items),
                    "failures": failures,
                    "cache_hits": cache_hits,
                    "cache_keys": cache_keys,
                    "cache_age_seconds": max(cache_ages) if cache_hits else "",
                })

            before_dedupe = len(round_items)
            round_items = _dedupe_source_items(round_items)
            round_evidence = build_evidence_cards(round_items)
            round_evidence = _dedupe_evidence(round_evidence)
            after_dedupe = len(round_evidence)
            before_merge = len(all_evidence)
            all_evidence = _dedupe_evidence(all_evidence + round_evidence)
            new_unique = len(all_evidence) - before_merge
            all_query_traces.extend(round_traces)

            rounds.append(ResearchRound(
                round=round_num,
                queries=round_traces,
                evidence_before_dedupe=before_dedupe,
                evidence_after_dedupe=after_dedupe,
            ))

            # Stop conditions
            if round_num >= max_rounds:
                break
            if len(all_evidence) >= evidence_limit:
                break
            if new_unique == 0:
                break  # nothing new after global dedupe

            # v2 Evaluator (only if multi-round enabled)
            if max_rounds <= 1:
                break
            _progress(progress, "评估研究缺口...")
            evaluator, eval_status = evaluate_research_gap(
                endpoint, headers, model, query, plan, all_evidence,
                [{"round": r.round, "evidence_after_dedupe": r.evidence_after_dedupe,
                  "queries": r.queries} for r in rounds],
                round_num, max_rounds,
            )
            if eval_status != "ok":
                evaluator_fallback = True
                break
            next_qs = _filter_next_queries(evaluator, plan, searched_qs)
            should_stop, stop_reason = _research_should_stop(
                round_num, max_rounds, len(all_evidence),
                evaluator, next_qs, new_unique, evidence_limit,
            )
            rounds[-1] = ResearchRound(
                round=round_num,
                queries=round_traces,
                evidence_before_dedupe=before_dedupe,
                evidence_after_dedupe=after_dedupe,
                evaluator={"sufficiency": evaluator.get("sufficiency"),
                          "should_continue": evaluator.get("should_continue"),
                          "next_queries": next_qs,
                          "reason": evaluator.get("reason", ""),
                          "stop_reason": stop_reason},
            )
            if should_stop:
                if stop_reason == "round-limit":
                    status = "round-limit"
                break
            queries_pool = next_qs

        # 3. Distill + Synthesize
        multi_round = max_rounds > 1
        distill_profile: dict = {}
        _log.info("collection done: %d evidence cards, %d rounds", len(all_evidence), round_num)
        if should_distill(all_evidence, "research", distill_evidence):
            _progress(progress, "AI 证据提炼中...")
            t_distill = _time_module.time()
            all_evidence, distill_profile = distill_evidence_cards(
                endpoint, headers, model, query, all_evidence, mode="research",
            )
            _log.info("distill done: elapsed=%.1fs", _time_module.time() - t_distill)
        else:
            distill_profile = {"distillation_status": "skipped", "distillation_reason": "not triggered"}
        _progress(progress, "综合分析中...")
        t_syn = _time_module.time()
        syn, syn_status = synthesize_research(
            endpoint, headers, model, query, all_evidence,
            plan.get("subquestions", []),
        )
        _log.info("synthesize done: status=%s, elapsed=%.1fs", syn_status, _time_module.time() - t_syn)
        raw_profile = syn.get("source_profile", {})
        if not raw_profile:
            raw_profile = compute_source_profile(all_evidence)

        # Status (don't override round-limit set in loop)
        if not all_evidence:
            status = "insufficient-evidence"
        elif syn_status == "ai-error":
            status = "ai-error"
        elif evaluator_fallback:
            status = "evaluator-fallback"
        elif planner_status != "ok":
            status = "planner-fallback"
        elif status != "round-limit" and round_num >= max_rounds and max_rounds > 1:
            status = "partial-evidence" if len(all_evidence) < 3 else "research-ready"
        elif status == "round-limit":
            pass  # preserve round-limit
        else:
            status = "research-ready"

        profile = evidence_input_profile(all_evidence)
        profile.update(distill_profile)
        trace = AgentTrace(
            mode="research",
            ai_status=provider.status,
            model=model,
            planned_tools=tools,
            tool_calls=all_query_traces,
            acquisition=[],
            evidence_input_profile=profile,
        )
        return ResearchReport(
            query=query,
            status=status,
            requested_max_rounds=max_rounds,
            executed_rounds=round_num,
            multi_round_enabled=multi_round,
            plan=plan,
            queries=all_query_traces,
            rounds=rounds,
            evidence_count_before_dedupe=sum(r.evidence_before_dedupe for r in rounds),
            evidence_count=len(all_evidence),
            source_profile=raw_profile,
            consensus=syn.get("consensus", "unclear"),
            transferability=syn.get("transferability", "unclear"),
            applicability=syn.get("applicability", "not_enough"),
            risk_level=syn.get("risk_level", "unknown"),
            gaps=syn.get("gaps", []),
            conclusion=syn.get("conclusion", ""),
            recommended_steps=syn.get("recommended_steps", []),
            key_findings=syn.get("key_findings", []),
            evidence=all_evidence,
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
            tools = ["search"]
            # Add github-search for programming-related queries
            if self._is_programming_query(claim) and "github-search" in self.acquisition_providers:
                tools.append("github-search")
            tools.extend(self._ready_collection_tools(claim))
            return tools
        return ["fixture"]

    def _is_programming_query(self, claim: str) -> bool:
        """Check if query is related to programming/development."""
        keywords = [
            "python", "javascript", "typescript", "react", "vue", "angular", "node",
            "java", "go", "rust", "c++", "cpp", "c#", "ruby", "php", "swift", "kotlin",
            "教程", "示例", "代码", "开源", "library", "framework", "api", "sdk",
            "github", "npm", "pypi", "pip", "npm", "yarn", "cargo",
            "bug", "error", "issue", "fix", "debug", "调试",
            "how to", "怎么", "如何", "实现", "example", "sample",
            "async", "await", "并发", "并行", "multithread", "thread",
            "database", "sql", "mysql", "postgres", "redis", "mongodb",
            "docker", "kubernetes", "k8s", "deploy", "部署",
            "machine learning", "ml", "ai", "deep learning", "深度学习",
            "algorithm", "算法", "data structure", "数据结构",
        ]
        claim_lower = claim.lower()
        return any(kw in claim_lower for kw in keywords)

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
        if name == "mediacrawler":
            return 2
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
        limit: int = 5,
        site: str | None = None,
        page: int = 1,
        platform: str | None = None,
    ) -> tuple[AcquisitionResult, bool, str, int]:
        from .cache import _make_key, _make_provider_signature, get_cached_result, put_cached_result

        provider = self.acquisition_providers.get(tool)
        provider_type = ""
        endpoint_host = ""
        adapter_class = ""
        if provider:
            provider_type = getattr(provider, "provider_type", "")
            adapter_class = type(provider).__name__
            if hasattr(provider, "endpoint"):
                endpoint_host = getattr(provider, "endpoint", "") or ""

        platform = platform or ""

        provider_sig = _make_provider_signature(
            tool, provider_type, endpoint_host, adapter_class,
        )
        cache_query = f"{claim} site:{site}" if site else claim
        cache_key = _make_key(tool, query=cache_query, url=url or "", repo=repo or "",
                              limit=limit, platform=platform, provider_signature=provider_sig)

        # Check cache (skip for html/github_payload passthrough)
        if html is None and github_payload is None:
            cached, cache_age = get_cached_result(
                tool, query=cache_query, url=url or "", repo=repo or "", limit=limit,
                platform=platform, provider_signature=provider_sig,
            )
            if cached is not None:
                try:
                    quality = None
                    raw_q = cached.get("quality")
                    if raw_q and isinstance(raw_q, dict):
                        quality = QualityAssessment(**raw_q)
                    result = AcquisitionResult(
                        provider=cached["provider"],
                        provider_type=cached["provider_type"],
                        status=cached.get("status", "ok"),
                        reason=cached.get("reason", ""),
                        message=cached.get("message", ""),
                        fix=cached.get("fix", ""),
                        retryable=bool(cached.get("retryable", False)),
                        warnings=list(cached.get("warnings", [])),
                        evidence_gaps=list(cached.get("evidence_gaps", [])),
                        diagnostics=dict(cached.get("diagnostics", {})),
                        candidates=[CandidateSource(**c) for c in cached.get("candidates", [])],
                        items=[SourceItem(**i) for i in cached.get("items", [])],
                        quality=quality,
                    )
                    return result, True, cache_key, cache_age
                except Exception:
                    pass  # Corrupt cache entry, fall through to collect

        if not provider:
            raise ValueError(f"unknown acquisition provider: {tool}")
        if tool in {"web", "official"} and html is not None:
            source_type = "web-page" if tool == "web" else "official-announcement"
            from .adapters import _extract_page

            items = _extract_page(url or "", html, source_type, tool)
            from .acquisition import _items_result

            return _items_result(tool, "builtin-adapter", items), False, cache_key, 0
        if tool == "github" and github_payload is not None:
            from .adapters import collect_github_repo
            from .acquisition import _items_result

            items = collect_github_repo(repo or claim, payload=github_payload)
            return _items_result(tool, "builtin-adapter", items), False, cache_key, 0
        platforms_list = platform.split(",") if platform else None
        result = provider.collect(
            AcquisitionRequest(
                query=claim,
                url=url,
                repo=repo,
                limit=limit,
                site=site,
                page=page,
                platforms=platforms_list,
            )
        )
        # Write cache
        cache_payload = {
            "provider": result.provider,
            "provider_type": result.provider_type,
            "status": result.status,
            "reason": result.reason,
            "message": result.message,
            "fix": result.fix,
            "retryable": result.retryable,
            "warnings": result.warnings,
            "evidence_gaps": result.evidence_gaps,
            "diagnostics": result.diagnostics,
            "candidates": [asdict(c) for c in result.candidates],
            "items": [asdict(i) for i in result.items],
            "quality": asdict(result.quality) if result.quality else None,
        }
        # Only cache successful results, not errors/unreachable
        if result.status in ("ok", "items-found", "candidates-found"):
            put_cached_result(tool, cache_payload, query=cache_query, url=url or "",
                              repo=repo or "", limit=limit, platform=platform,
                              provider_signature=provider_sig)
        return result, False, cache_key, 0


def _evidence_needs_more(evidence: list[EvidenceCard], ran_tools: list[str],
                         available: list[str]) -> bool:
    """Code-level guard: force trafilatura if all evidence is search-result type."""
    if not evidence:
        return False
    all_search = all(
        getattr(c, "source_type", "") == "search-result" for c in evidence
    )
    if not all_search:
        return False
    if "trafilatura" not in available:
        return False
    if "trafilatura" in ran_tools:
        return False
    return True


def _filter_next_queries(evaluator_result: dict, plan: dict, searched: set[str]) -> list[dict]:
    """Code-level filter: only keep queries bound to actual missing subquestions."""
    missing_ids = set(evaluator_result.get("missing_subquestions", []))
    plan_ids = {sq["id"] for sq in plan.get("subquestions", []) if "id" in sq}
    if not missing_ids or not plan_ids:
        return []
    valid: list[dict] = []
    seen_next: set[str] = set()
    for nq in evaluator_result.get("next_queries", []):
        if not isinstance(nq, dict):
            continue
        sid = nq.get("subquestion_id", "")
        q_text = (nq.get("query", "") or "").strip()
        if not q_text:
            continue
        if sid not in missing_ids:
            continue
        if sid not in plan_ids:
            continue
        if q_text in searched:
            continue
        if q_text in seen_next:
            continue
        seen_next.add(q_text)
        valid.append({"query": q_text, "tools": ["search", "trafilatura"]})
    return valid


def _research_should_stop(
    round_num: int, max_rounds: int, evidence_count: int,
    evaluator: dict, next_queries: list[str], new_evidence: int,
    evidence_limit: int = 40,
) -> tuple[bool, str]:
    if round_num >= max_rounds:
        return True, "round-limit"
    if not evaluator.get("should_continue", False):
        return True, evaluator.get("stop_reason") or "evaluator-stopped"
    if not next_queries:
        return True, "no-valid-next-queries"
    if new_evidence == 0:
        return True, "no-new-evidence"
    if evidence_count >= evidence_limit:
        return True, "evidence-limit"
    return False, ""


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
