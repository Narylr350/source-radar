import hashlib

from .models import EvidenceCard, SourceItem

SUMMARY_MAX_CHARS = 500
RAW_EXCERPT_MAX_CHARS = 3000


def build_evidence_cards(items: list[SourceItem]) -> list[EvidenceCard]:
    cards = []
    for index, item in enumerate(items, start=1):
        summary = _build_summary(item)
        raw_excerpt = _build_raw_excerpt(item)
        raw_content_length = _resolve_raw_content_length(item)
        raw_content_truncated = _resolve_raw_content_truncated(item, raw_excerpt)
        compression = _build_compression(summary, raw_excerpt, raw_content_length, raw_content_truncated)
        cards.append(
            EvidenceCard(
                id=f"ev-{index:03d}",
                source_type=item.source_type,
                title=item.title,
                url=item.url,
                summary=summary,
                adapter=item.adapter,
                retrieved_at=item.retrieved_at,
                content_hash=_content_hash(item),
                metadata=item.metadata,
                raw_excerpt=raw_excerpt,
                raw_content_length=raw_content_length,
                raw_content_truncated=raw_content_truncated,
                compression=compression,
            )
        )
    return cards


def evidence_input_profile(cards: list[EvidenceCard]) -> dict:
    cards_with_raw = sum(1 for c in cards if c.raw_excerpt)
    total_summary = sum(len(c.summary) for c in cards)
    total_raw = sum(len(c.raw_excerpt) for c in cards)
    truncated = sum(1 for c in cards if c.raw_content_truncated)
    distilled = sum(1 for c in cards if c.distilled)
    return {
        "evidence_count": len(cards),
        "cards_with_raw_excerpt": cards_with_raw,
        "total_summary_chars": total_summary,
        "total_raw_excerpt_chars": total_raw,
        "truncated_cards": truncated,
        "distilled_cards": distilled,
    }


def _build_summary(item: SourceItem) -> str:
    snippet = (item.snippet or "").strip()
    if snippet:
        return snippet[:SUMMARY_MAX_CHARS]
    raw = (item.raw_content or "").strip()
    if raw:
        return " ".join(raw.split())[:SUMMARY_MAX_CHARS]
    return ""


def _build_raw_excerpt(item: SourceItem) -> str:
    raw = (item.raw_content or "").strip()
    if raw:
        return " ".join(raw.split())[:RAW_EXCERPT_MAX_CHARS]
    snippet = (item.snippet or "").strip()
    if snippet:
        return snippet[:RAW_EXCERPT_MAX_CHARS]
    return ""


def _resolve_raw_content_length(item: SourceItem) -> int:
    if item.raw_content_length:
        return item.raw_content_length
    raw = item.raw_content or item.snippet or ""
    return len(raw)


def _resolve_raw_content_truncated(item: SourceItem, raw_excerpt: str) -> bool:
    if item.raw_content_truncated:
        return True
    raw_len = _resolve_raw_content_length(item)
    return raw_len > RAW_EXCERPT_MAX_CHARS


def _build_compression(
    summary: str, raw_excerpt: str, raw_content_length: int, raw_content_truncated: bool,
) -> dict:
    has_raw = bool(raw_excerpt.strip())
    if raw_content_length == 0:
        loss_risk = "high"
    elif not has_raw:
        loss_risk = "high"
    elif raw_content_truncated:
        loss_risk = "medium"
    else:
        loss_risk = "low"
    return {
        "method": "mechanical_excerpt",
        "summary_chars": len(summary),
        "raw_excerpt_chars": len(raw_excerpt),
        "raw_content_length": raw_content_length,
        "raw_content_truncated": raw_content_truncated,
        "ai_distilled": False,
        "loss_risk": loss_risk,
    }


def _content_hash(item: SourceItem) -> str:
    raw = "\n".join([item.source_type, item.title, item.url, item.snippet])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
