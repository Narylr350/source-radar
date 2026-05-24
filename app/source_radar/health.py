from datetime import UTC, datetime

from .acquisition import (
    AcquisitionProvider,
    AcquisitionRequest,
    default_providers,
)
from .adapters import (
    collect_fixture_items,
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from .models import HealthReport, ProbeResult, SourceItem


ADAPTERS = ("fixture", "web", "official", "github")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _ok(adapter: str, items: list[SourceItem], checked_at: str) -> ProbeResult:
    first = items[0]
    return ProbeResult(
        adapter=adapter,
        status="ok",
        reason="usable-items",
        message=f"{adapter} adapter returned usable source items.",
        checked_at=checked_at,
        source_type=first.source_type,
        items_found=len(items),
    )


def _no_evidence(adapter: str, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="no-evidence",
        reason="no-usable-items",
        message=f"{adapter} adapter ran but returned no usable source items.",
        checked_at=checked_at,
    )


def _needs_input(adapter: str, reason: str, message: str, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="needs-input",
        reason=reason,
        message=message,
        checked_at=checked_at,
    )


def _error(adapter: str, error: Exception, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="error",
        reason=error.__class__.__name__,
        message=str(error),
        checked_at=checked_at,
    )


def _provider_probe(
    provider: AcquisitionProvider,
    *,
    query: str | None,
    url: str | None = None,
    repo: str | None = None,
    checked_at: str,
) -> ProbeResult:
    try:
        if query is None and url is None and repo is None and hasattr(provider, "status"):
            result = provider.status()
        else:
            result = provider.collect(
                AcquisitionRequest(
                    query=query or "source-radar provider readiness",
                    url=url,
                    repo=repo,
                )
            )
    except Exception as error:
        return _error(provider.provider, error, checked_at)
    return ProbeResult(
        adapter=result.provider,
        status=result.status,
        reason=result.reason,
        message=result.message,
        checked_at=checked_at,
        source_type=result.items[0].source_type if result.items else "",
        items_found=len(result.items),
        details={
            "provider_type": result.provider_type,
            "candidate_count": str(len(result.candidates)),
        },
    )


def probe_adapter(
    adapter: str,
    *,
    url: str | None = None,
    repo: str | None = None,
    query: str | None = None,
    providers: list[AcquisitionProvider] | None = None,
    html: str | None = None,
    github_payload: dict[str, object] | None = None,
) -> ProbeResult:
    checked_at = _utc_now()
    provider_map = {provider.provider: provider for provider in providers or []}
    if adapter in provider_map:
        return _provider_probe(
            provider_map[adapter],
            query=query,
            url=url,
            repo=repo,
            checked_at=checked_at,
        )
    if adapter not in ADAPTERS:
        return _needs_input(
            adapter,
            "unknown-adapter",
            f"Unknown adapter: {adapter}",
            checked_at,
        )

    try:
        if adapter == "fixture":
            items = collect_fixture_items("source-radar 是本地 CLI")
        elif adapter == "web":
            if not url:
                return _needs_input(
                    adapter,
                    "missing-url",
                    "--url is required to probe the web adapter.",
                    checked_at,
                )
            items = collect_web_page(url, html=html)
        elif adapter == "official":
            if not url:
                return _needs_input(
                    adapter,
                    "missing-url",
                    "--url is required to probe the official adapter.",
                    checked_at,
                )
            items = collect_official_page(url, html=html)
        else:
            if not repo:
                return _needs_input(
                    adapter,
                    "missing-repo",
                    "--repo is required to probe the github adapter.",
                    checked_at,
                )
            items = collect_github_repo(repo, payload=github_payload)
    except Exception as error:
        return _error(adapter, error, checked_at)

    if not items:
        return _no_evidence(adapter, checked_at)
    return _ok(adapter, items, checked_at)


def build_health_report(
    *,
    providers: list[AcquisitionProvider] | None = None,
    provider_query: str | None = None,
) -> HealthReport:
    checked_at = _utc_now()
    selected_providers = providers if providers is not None else default_providers()
    if selected_providers is not None:
        probes = [
            _provider_probe(
                provider,
                query=provider_query,
                checked_at=checked_at,
            )
            for provider in selected_providers
        ]
    else:
        probes = [probe_adapter(adapter) for adapter in ADAPTERS]
    summary: dict[str, str] = {"total": str(len(probes))}
    for probe in probes:
        summary[probe.status] = str(int(summary.get(probe.status, "0")) + 1)
    status = "ok" if all(probe.status == "ok" for probe in probes) else "degraded"
    return HealthReport(
        status=status,
        checked_at=checked_at,
        summary=summary,
        probes=probes,
    )
