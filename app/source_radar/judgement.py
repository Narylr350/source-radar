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
            confidence="none",
            confidence_reason="没有可用证据，不能形成可信判断。",
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
        **estimate_evidence_confidence(claim, evidence),
    )


def estimate_evidence_confidence(
    claim: str,
    evidence: list[EvidenceCard],
) -> dict[str, str]:
    if not evidence:
        return {
            "confidence": "none",
            "confidence_reason": "没有可用证据，不能形成可信判断。",
        }

    official_count = sum(
        1
        for card in evidence
        if card.source_type == "official-announcement"
        or card.adapter == "official"
        or _looks_official(card.url)
    )
    extracted_count = sum(
        1
        for card in evidence
        if card.source_type != "search-result" and card.summary.strip()
    )
    search_count = sum(1 for card in evidence if card.source_type == "search-result")
    blocked_count = sum(1 for card in evidence if _looks_blocked_or_empty(card))
    current_policy = _looks_current_policy_question(claim)
    public_figure_life_status = _looks_public_figure_life_status_question(claim)
    first_party_death_count = sum(1 for card in evidence if _looks_first_party_death_confirmation(card))

    if current_policy and official_count == 0:
        return {
            "confidence": "low",
            "confidence_reason": "这是当前考试/政策类问题，但证据里没有教育部、考试院或官方课程标准来源。",
        }
    if public_figure_life_status and first_party_death_count:
        return {
            "confidence": "high",
            "confidence_reason": f"人物生死类问题包含 {first_party_death_count} 条一手或疑似一手讣告/官方确认来源。",
        }
    if public_figure_life_status:
        return {
            "confidence": "low",
            "confidence_reason": "这是人物生死类问题，但证据里没有官方账号、公司、家属或工作室等一手确认。",
        }
    if official_count:
        return {
            "confidence": "high",
            "confidence_reason": f"包含 {official_count} 条官方或疑似官方来源，可作为主要依据。",
        }
    if extracted_count >= 3 and blocked_count == 0:
        return {
            "confidence": "medium",
            "confidence_reason": f"有 {extracted_count} 条正文来源可互相参考，但缺少官方锚点。",
        }
    if search_count >= extracted_count:
        return {
            "confidence": "low",
            "confidence_reason": "搜索结果线索占比较高，正文证据不足，容易受 SEO、问答站或二手内容影响。",
        }
    if blocked_count:
        return {
            "confidence": "low",
            "confidence_reason": "部分来源无法访问、为空页或被安全验证拦截，证据质量偏低。",
        }
    return {
        "confidence": "medium",
        "confidence_reason": "有可读正文来源，但缺少更强的一手来源确认。",
    }


def _looks_current_policy_question(claim: str) -> bool:
    keywords = ("今年", "最新", "现在", "高考", "中考", "考试", "政策", "规定", "考纲")
    return any(keyword in claim for keyword in keywords)


def _looks_public_figure_life_status_question(claim: str) -> bool:
    keywords = ("死了吗", "去世", "逝世", "死亡", "病逝", "猝死", "讣告", "还活着", "辟谣")
    return any(keyword in claim for keyword in keywords)


def _looks_first_party_death_confirmation(card: EvidenceCard) -> bool:
    text = f"{card.title}\n{card.summary}".lower()
    first_party_markers = (
        "官方账号",
        "官方社交账号",
        "工作室",
        "公司发布讣告",
        "团队发布讣告",
        "家属发布讣告",
        "讣告",
    )
    death_markers = ("去世", "逝世", "死亡", "病逝", "猝死", "抢救无效")
    return any(marker in text for marker in first_party_markers) and any(
        marker in text for marker in death_markers
    )


def _looks_official(url: str) -> bool:
    lowered = url.lower()
    official_markers = (
        ".gov.cn",
        "moe.gov.cn",
        "neea.edu.cn",
        "eea.",
        "jyt.",
        "edu.cn",
    )
    return any(marker in lowered for marker in official_markers)


def _looks_blocked_or_empty(card: EvidenceCard) -> bool:
    text = f"{card.title}\n{card.summary}".lower()
    markers = (
        "404 not found",
        "安全验证",
        "不能直接访问",
        "enable javascript",
        "access denied",
        "captcha",
    )
    return not card.summary.strip() or any(marker.lower() in text for marker in markers)
