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
    IntegrationRecord(
        name="firecrawl",
        source="external-project",
        license="AGPL-3.0",
        core_policy="bridge-or-api-only",
        status="restricted",
        boundary=(
            "Firecrawl source must not be copied into the Apache-2.0 core; "
            "use an API, local service, or independent compatible bridge."
        ),
        notice="Record service URL/version and AGPL boundary before enabling.",
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
    items = [
        IntegrationRecord(
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
        for item in list_integrations()
    ]
    return IntegrationAudit(
        status="disabled",
        summary={"total": str(len(items)), "disabled": str(len(items))},
        items=items,
    )
