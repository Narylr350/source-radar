from .models import EvidenceCard, Judgement


def judge_claim(claim: str, evidence: list[EvidenceCard]) -> Judgement:
    if not evidence:
        return Judgement(
            status="no-evidence",
            summary="No fixture evidence was found for this claim.",
            evidence_ids=[],
            gaps=[
                "Add a real adapter or a matching fixture source before "
                "making a credibility judgement."
            ],
        )

    adapters = sorted({card.adapter for card in evidence})
    if adapters == ["fixture"]:
        summary = (
            "Fixture evidence is available. Treat this as a workflow smoke "
            "result, not a final fact judgement."
        )
        gaps = [
            "This first slice uses fixture data only and does not query live sources."
        ]
    else:
        summary = (
            "Collected evidence is available from "
            f"{', '.join(adapters)} sources. Treat this as evidence-grounded "
            "assistance, not a final fact judgement."
        )
        gaps = [
            "M2 collection does not yet run cross-source conflict analysis or LLM review."
        ]

    return Judgement(
        status="evidence-found",
        summary=summary,
        evidence_ids=[card.id for card in evidence],
        gaps=gaps,
    )
