from datetime import UTC, datetime

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


def probe_adapter(
    adapter: str,
    *,
    url: str | None = None,
    repo: str | None = None,
    html: str | None = None,
    github_payload: dict[str, object] | None = None,
) -> ProbeResult:
    checked_at = _utc_now()
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


def build_health_report() -> HealthReport:
    checked_at = _utc_now()
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
