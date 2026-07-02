import json

from .models import HealthReport, IntegrationAudit, ProbeResult, SynthesisReport, VerifyReport


def _render_acquisition(agent) -> list[str]:
    """Shared acquisition trace lines for markdown reports."""
    if agent and agent.acquisition:
        return [
            f"- {acq.provider}: {acq.status} ({acq.reason}); "
            f"candidates: {acq.candidate_count}; items: {acq.items_found}"
            for acq in agent.acquisition
        ]
    return ["- 未记录采集过程。"]


def _render_evidence_list(cards, limit: int = 8) -> list[str]:
    """Shared evidence card list for markdown reports."""
    if not cards:
        return ["- 没有找到证据。"]
    lines: list[str] = []
    for card in cards[:limit]:
        lines.extend([
            f"- {card.id}: {card.title}",
            f"  - 类型: {card.source_type}",
            f"  - Adapter: {card.adapter}",
            f"  - 链接: {card.url}",
            f"  - 摘要: {_short_text(card.summary)}",
        ])
    if len(cards) > limit:
        lines.append(f"- 还有 {len(cards) - limit} 条结果，使用 --format json 查看完整证据。")
    return lines


def render_json(report: VerifyReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: VerifyReport) -> str:
    lines = [
        "# 核验报告",
        "",
        f"问题: {report.claim}",
        f"状态: {report.status}",
        "",
        "## 结论",
        report.judgement.summary,
        "",
        "## 可信度",
        f"{_confidence_label(report.judgement.confidence)}："
        f"{report.judgement.confidence_reason or '未记录可信度原因。'}",
        "",
        "## 依据",
        "证据卡: " + (", ".join(report.judgement.evidence_ids) or "none"),
        "",
        "## 采集过程",
    ]
    if report.agent:
        lines.extend(
            [
                f"- 模式: {report.agent.mode}",
                f"- AI 状态: {report.agent.ai_status}",
                f"- 模型: {report.agent.model}",
                "- 计划工具: " + ", ".join(report.agent.planned_tools),
            ]
        )
    else:
        lines.append("- 未记录 agent trace。")
    lines.extend(_render_acquisition(report.agent))
    lines.extend(
        [
            "",
            "## 结果清单",
        ]
    )
    lines.extend(_render_evidence_list(report.evidence, limit=8))
    if report.judgement.gaps:
        lines.extend(["", "## 证据缺口"])
        for gap in report.judgement.gaps:
            lines.append(f"- {gap}")
    return "\n".join(lines)


def _confidence_label(confidence: str) -> str:
    labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无",
        "unknown": "未知",
    }
    return labels.get(confidence, confidence or "未知")


def render_synthesis_json(report: SynthesisReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_synthesis_markdown(report: SynthesisReport) -> str:
    lines = [
        "# 综合信息分析",
        "",
        f"问题: {report.query}",
        f"状态: {report.status}",
        "",
        "## 采集与分析",
    ]
    if report.agent:
        lines.extend(
            [
                f"模式: {report.agent.mode}",
                f"AI 状态: {report.agent.ai_status}",
                f"模型: {report.agent.model}",
                "计划工具: " + ", ".join(report.agent.planned_tools),
            ]
        )
    else:
        lines.append("未记录 agent trace。")
    lines.extend(
        [
            "",
            "## 综合回答",
            report.analysis.summary,
            "",
            "## 搜索结果要点",
        ]
    )
    _append_list(lines, report.analysis.key_points, "- 暂无可综合的搜索结果。")
    lines.extend(["", "## 来源分布"])
    _append_list(lines, report.analysis.source_notes, "- 暂无来源分布。")
    if report.analysis.disagreements:
        lines.extend(["", "## 分歧/争议"])
        _append_list(lines, report.analysis.disagreements)
    if report.analysis.noise_notes:
        lines.extend(["", "## 噪音提示"])
        _append_list(lines, report.analysis.noise_notes)
    lines.extend(
        [
            "",
            "## 采集过程",
        ]
    )
    lines.extend(_render_acquisition(report.agent))
    lines.extend(["", "## 结果清单"])
    lines.extend(_render_evidence_list(report.evidence, limit=len(report.evidence) if report.evidence else 8))
    return "\n".join(lines)


def _append_list(lines: list[str], items: list[str], empty: str = "- none") -> None:
    if not items:
        lines.append(empty)
        return
    for item in items:
        lines.append(f"- {item}")


def _short_text(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


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
    if result.details.get("warnings"):
        lines.append(f"Warnings: {result.details['warnings']}")
    for diag_key in ("captcha_engines", "timeout_engines", "other_issues"):
        if result.details.get(diag_key):
            lines.append(f"{diag_key}: {result.details[diag_key]}")
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
        line = f"- {probe.adapter}: {probe.status} ({probe.reason})"
        if probe.details.get("fix"):
            line += f" — fix: {probe.details['fix']}"
        lines.append(line)
        if probe.status not in ("ok", "needs-input"):
            for diag_key in ("captcha_engines", "timeout_engines", "other_issues"):
                if probe.details.get(diag_key):
                    lines.append(f"  - {diag_key}: {probe.details[diag_key]}")
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


def render_research_markdown(report) -> str:
    lines = [
        "# 深度研究结果",
        "",
        f"问题: {report.query}",
        f"状态: {report.status}",
        f"执行轮数: {report.executed_rounds}",
        "",
        "## 结论",
        report.conclusion or "未能综合出结论",
        "",
    ]
    if report.recommended_steps:
        lines.append("## 推荐方案 / 操作步骤")
        for step in report.recommended_steps:
            lines.append(f"- {step}")
        lines.append("")
    if report.key_findings:
        lines.append("## 关键发现")
        for f in report.key_findings:
            lines.append(f"- {f}")
        lines.append("")

    lines.append("## 信息来源与适用性")
    sp = report.source_profile or {}
    parts = []
    if sp.get("official"): parts.append(f"官方 {sp['official']} 条")
    if sp.get("review"): parts.append(f"评测 {sp['review']} 条")
    if sp.get("community"): parts.append(f"社区经验 {sp['community']} 条")
    if sp.get("video"): parts.append(f"视频 {sp['video']} 条")
    if sp.get("unknown"): parts.append(f"其他 {sp['unknown']} 条")
    lines.append(f"来源构成: {', '.join(parts) if parts else '无'}")
    lines.append(f"社区一致性: {report.consensus}")
    lines.append(f"可迁移性: {report.transferability}")
    lines.append(f"适用方式: {report.applicability}")
    lines.append("")

    if report.gaps:
        lines.append("## 风险与不确定性")
        for g in report.gaps:
            lines.append(f"- {g}")
        lines.append("")

    if report.risk_level in ("medium", "high") or report.plan.get("research_type") == "hardware_tuning":
        lines.append("这不是保稳方案，只能作为起步参考；最终以你自己的稳定性测试为准。")
        lines.append("")

    if report.evidence:
        lines.append("## 参考来源")
        for card in report.evidence:
            lines.append(f"- **{card.title}**")
            if card.url:
                lines.append(f"  {card.url}")
            lines.append(f"  类型: {card.source_type} | 适配器: {card.adapter}")
            if card.summary:
                lines.append(f"  {card.summary[:160]}")
        lines.append("")

    return "\n".join(lines)
