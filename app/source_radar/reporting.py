import json

from .models import HealthReport, IntegrationAudit, ProbeResult, VerifyReport


def render_json(report: VerifyReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: VerifyReport) -> str:
    lines = [
        "# Verification Report",
        "",
        f"Claim: {report.claim}",
        f"Status: {report.status}",
        "",
        "## Agent",
    ]
    if report.agent:
        lines.extend(
            [
                f"Mode: {report.agent.mode}",
                f"AI Status: {report.agent.ai_status}",
                f"Model: {report.agent.model}",
                "Planned Tools: " + ", ".join(report.agent.planned_tools),
            ]
        )
    else:
        lines.append("No agent trace recorded.")
    lines.extend(
        [
            "",
            "## Source Acquisition",
        ]
    )
    if report.agent and report.agent.acquisition:
        for acquisition in report.agent.acquisition:
            lines.append(
                f"- {acquisition.provider}: {acquisition.status} "
                f"({acquisition.reason}); candidates: "
                f"{acquisition.candidate_count}; items: {acquisition.items_found}"
            )
            for candidate in acquisition.candidates:
                lines.append(f"  - {candidate.title}: {candidate.url}")
    else:
        lines.append("- No source acquisition trace recorded.")
    lines.extend(
        [
            "",
            "## Evidence",
        ]
    )
    if report.evidence:
        for card in report.evidence:
            lines.extend(
                [
                    f"- {card.id}: {card.title}",
                    f"  - Source: {card.source_type}",
                    f"  - URL: {card.url}",
                    f"  - Summary: {card.summary}",
                ]
            )
    else:
        lines.append("- No evidence found.")

    lines.extend(
        [
            "",
            "## Judgement",
            report.judgement.summary,
            "",
            "Evidence IDs: " + (", ".join(report.judgement.evidence_ids) or "none"),
            "",
            "## Evidence Gaps",
        ]
    )
    for gap in report.judgement.gaps:
        lines.append(f"- {gap}")
    return "\n".join(lines)


def render_probe_json(result: ProbeResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def render_health_json(report: HealthReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_probe_markdown(result: ProbeResult) -> str:
    lines = [
        "# Adapter Probe",
        "",
        f"Adapter: {result.adapter}",
        f"Status: {result.status}",
        f"Reason: {result.reason}",
        f"Message: {result.message}",
        f"Checked At: {result.checked_at}",
        f"Items Found: {result.items_found}",
    ]
    if result.source_type:
        lines.append(f"Source Type: {result.source_type}")
    if result.details.get("fix"):
        lines.append(f"Fix: {result.details['fix']}")
    if result.details.get("retryable"):
        lines.append(f"Retryable: {result.details['retryable']}")
    return "\n".join(lines)


def render_health_markdown(report: HealthReport) -> str:
    lines = [
        "# Platform Health",
        "",
        f"Status: {report.status}",
        f"Checked At: {report.checked_at}",
        "",
        "## Summary",
    ]
    for key, value in sorted(report.summary.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Adapters"])
    for probe in report.probes:
        lines.append(f"- {probe.adapter}: {probe.status} ({probe.reason})")
    return "\n".join(lines)


def render_integration_audit_json(audit: IntegrationAudit) -> str:
    return json.dumps(audit.to_dict(), ensure_ascii=False, indent=2)


def render_integration_audit_markdown(audit: IntegrationAudit) -> str:
    lines = [
        "# Integration License Audit",
        "",
        f"Status: {audit.status}",
        "",
        "## Summary",
    ]
    for key, value in sorted(audit.summary.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Integrations"])
    for item in audit.items:
        lines.extend(
            [
                f"- {item.name}: {item.status}",
                f"  - Source: {item.source}",
                f"  - License: {item.license}",
                f"  - Policy: {item.core_policy}",
                f"  - Boundary: {item.boundary}",
                f"  - Notice: {item.notice}",
            ]
        )
    return "\n".join(lines)
