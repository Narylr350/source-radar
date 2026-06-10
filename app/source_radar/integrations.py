from .config import load_provider_configs
from .models import IntegrationAudit, IntegrationRecord


INTEGRATIONS = [
    IntegrationRecord(
        name="mediacrawler",
        source="external-project",
        license="Non-commercial learning/research",
        core_policy="external-only",
        status="restricted",
        boundary=(
            "MediaCrawler must not be vendored into the Apache-2.0 core; "
            "users may wire a local external dependency or bridge."
        ),
        notice="Record user-provided local dependency details before enabling.",
    ),
]


def list_integrations() -> list[IntegrationRecord]:
    return INTEGRATIONS


def audit_integrations() -> IntegrationAudit:
    items = list_integrations()
    summary: dict[str, str] = {"total": str(len(items))}
    for item in items:
        summary[item.status] = str(int(summary.get(item.status, "0")) + 1)
    status = "ok" if summary.get("restricted", "0") == "0" else "restricted"
    return IntegrationAudit(status=status, summary=summary, items=items)


def build_integration_status_report() -> IntegrationAudit:
    provider_configs = load_provider_configs()
    items = [_status_record(item, provider_configs.get(item.name, {})) for item in list_integrations()]
    summary: dict[str, str] = {"total": str(len(items))}
    for item in items:
        summary[item.status] = str(int(summary.get(item.status, "0")) + 1)
    status = "disabled"
    if summary.get("configured") == str(len(items)):
        status = "configured"
    elif summary.get("configured"):
        status = "partial"
    return IntegrationAudit(
        status=status,
        summary=summary,
        items=items,
    )


def _status_record(item: IntegrationRecord, config: dict[str, str]) -> IntegrationRecord:
    configured = (
        config.get("enabled", "true") != "false"
        and bool(config.get("endpoint") or config.get("command"))
    )
    if configured:
        return IntegrationRecord(
            name=item.name,
            source=item.source,
            license=item.license,
            core_policy=item.core_policy,
            status="configured",
            boundary=item.boundary,
            notice=(
                "Optional bridge is configured locally; keep the external "
                "dependency outside the Apache-2.0 core."
            ),
        )
    return IntegrationRecord(
        name=item.name,
        source=item.source,
        license=item.license,
        core_policy=item.core_policy,
        status="disabled",
        boundary=item.boundary,
        notice=(
            "Optional bridge is not enabled by default; configure an "
            "external dependency, API, or local service before use."
        ),
    )
