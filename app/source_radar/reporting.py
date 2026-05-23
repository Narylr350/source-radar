import json

from .models import VerifyReport


def render_json(report: VerifyReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: VerifyReport) -> str:
    lines = [
        "# Verification Report",
        "",
        f"Claim: {report.claim}",
        f"Status: {report.status}",
        "",
        "## Evidence",
    ]
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
