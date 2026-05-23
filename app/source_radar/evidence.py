from .models import EvidenceCard, SourceItem


def build_evidence_cards(items: list[SourceItem]) -> list[EvidenceCard]:
    cards = []
    for index, item in enumerate(items, start=1):
        cards.append(
            EvidenceCard(
                id=f"ev-{index:03d}",
                source_type=item.source_type,
                title=item.title,
                url=item.url,
                summary=item.snippet,
            )
        )
    return cards
