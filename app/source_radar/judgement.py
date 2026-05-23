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

    return Judgement(
        status="evidence-found",
        summary=(
            "Fixture evidence is available. Treat this as a workflow smoke "
            "result, not a final fact judgement."
        ),
        evidence_ids=[card.id for card in evidence],
        gaps=[
            "This first slice uses fixture data only and does not query live sources."
        ],
    )
