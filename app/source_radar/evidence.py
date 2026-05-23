import hashlib

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
                adapter=item.adapter,
                retrieved_at=item.retrieved_at,
                content_hash=_content_hash(item),
                metadata=item.metadata,
            )
        )
    return cards


def _content_hash(item: SourceItem) -> str:
    raw = "\n".join([item.source_type, item.title, item.url, item.snippet])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
