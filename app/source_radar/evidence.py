import hashlib
import re

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
        source_fidelity = _source_fidelity(item, raw_excerpt)
        compression = _build_compression(
            summary, raw_excerpt, raw_content_length, raw_content_truncated, source_fidelity,
        )
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


def _source_fidelity(item: SourceItem, raw_excerpt: str) -> str:
    """Classify how much real content the card carries."""
    if item.source_type == "search-result" and not item.raw_content:
        return "snippet_only"
    raw = (item.raw_content or "").strip()
    if raw and len(raw) > len(raw_excerpt):
        return "excerpt"
    if raw:
        return "full_or_long_excerpt"
    return "snippet_only"


def _build_compression(
    summary: str, raw_excerpt: str, raw_content_length: int,
    raw_content_truncated: bool, source_fidelity: str,
) -> dict:
    has_raw = bool(raw_excerpt.strip())
    if source_fidelity == "snippet_only":
        loss_risk = "high"
    elif raw_content_length == 0:
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
        "source_fidelity": source_fidelity,
    }


def _content_hash(item: SourceItem) -> str:
    raw = "\n".join([
        item.source_type, item.title, item.url, item.snippet, item.raw_content or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- Evidence bucketing for source strength classification ---

_BUCKET_PRIORITY = {"official": 0, "mainstream": 1, "platform-account": 2, "community": 3, "community-comment": 4, "noise": 5}

_MAINSTREAM_DOMAINS = (
    "donews.com", "cls.cn", "stcn.com", "china.com.cn", "xinhuanet.com",
    "people.com.cn", "thepaper.cn", "caixin.com", "yicai.com", "jiemian.com",
    "36kr.com", "sina.com.cn", "sohu.com", "163.com", "ifeng.com",
    "cctv.com", "cctv.cn", "chinanews.com", "qq.com",
)

_OFFICIAL_URL_MARKERS = (
    ".gov.cn", "moe.gov.cn", "neea.edu.cn", "eea.", "jyt.", "edu.cn",
)

_COMMUNITY_DOMAINS = (
    "weibo.com", "m.weibo.cn", "bilibili.com", "zhihu.com", "xiaohongshu.com",
    "tieba.baidu.com", "douyin.com",
)


def classify_evidence_bucket(card: EvidenceCard, query: str = "") -> str:
    """Classify an evidence card into a source strength bucket.

    For official/mainstream classification, the card must also be relevant
    to the query (contain entity-related keywords) to avoid false positives
    like unrelated government pages.
    """
    url_lower = (card.url or "").lower()
    title_lower = (card.title or "").lower()
    summary_lower = (card.summary or "").lower()
    text = f"{title_lower} {summary_lower}"

    if card.source_type == "community-comment":
        return "community-comment"

    if card.adapter == "mediacrawler" or card.source_type == "community-post":
        return "community"

    if any(domain in url_lower for domain in _COMMUNITY_DOMAINS):
        return "community"

    # Official / government / company announcements
    has_official_url = any(marker in url_lower for marker in _OFFICIAL_URL_MARKERS)
    has_official_source_type = card.source_type == "official-announcement"

    if has_official_url or has_official_source_type:
        if has_official_source_type:
            return "official"
        if query and _is_relevant_to_query(text, query):
            return "official"
        if not query:
            return "official"

    # Mainstream media
    if any(domain in url_lower for domain in _MAINSTREAM_DOMAINS):
        # Require relevance to query for mainstream media too
        if query and _is_relevant_to_query(text, query):
            return "mainstream"
        if not query:
            return "mainstream"

    return "noise"


def _is_relevant_to_query(text: str, query: str) -> bool:
    """Check if text is relevant to the query (simple keyword overlap)."""
    if not query:
        return True
    stop_words = {"怎么", "如何", "什么", "为什么", "了吗", "了呢", "吧", "呢", "吗",
                  "的", "了", "在", "是", "有", "和", "与", "或", "及", "等"}
    query_tokens = set()
    for token in re.split(r'[\s\-_,，。、?？!！]+', query):
        token = token.strip()
        if len(token) >= 2 and token not in stop_words:
            query_tokens.add(token.lower())
    if not query_tokens:
        return True
    text_lower = text.lower()
    # Check if any query token appears in text (substring match)
    for token in query_tokens:
        if token in text_lower:
            return True
        # For longer tokens, also check substrings of length >= 3
        if len(token) >= 4:
            for i in range(len(token) - 2):
                sub = token[i:i+3]
                if sub not in stop_words and sub in text_lower:
                    return True
    return False


def has_strong_source(cards: list[EvidenceCard], query: str = "") -> bool:
    """Check if any evidence card qualifies as a strong source (official or mainstream)."""
    return any(
        classify_evidence_bucket(c, query) in ("official", "mainstream")
        for c in cards
    )


def sort_evidence_by_strength(cards: list[EvidenceCard], query: str = "") -> list[EvidenceCard]:
    """Sort evidence cards by source strength (strongest first)."""
    return sorted(cards, key=lambda c: _BUCKET_PRIORITY.get(classify_evidence_bucket(c, query), 4))
