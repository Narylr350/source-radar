import json

from .models import HealthReport, IntegrationAudit, ProbeResult, SynthesisReport, VerifyReport


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
    if report.agent and report.agent.acquisition:
        for acquisition in report.agent.acquisition:
            lines.append(
                f"- {acquisition.provider}: {acquisition.status} "
                f"({acquisition.reason}); candidates: "
                f"{acquisition.candidate_count}; items: {acquisition.items_found}"
            )
    else:
        lines.append("- 未记录采集过程。")
    lines.extend(
        [
            "",
            "## 结果清单",
        ]
    )
    if report.evidence:
        for card in report.evidence[:8]:
            lines.extend(
                [
                    f"- {card.id}: {card.title}",
                    f"  - 类型: {card.source_type}",
                    f"  - Adapter: {card.adapter}",
                    f"  - 链接: {card.url}",
                    f"  - 摘要: {_short_text(card.summary)}",
                ]
            )
        if len(report.evidence) > 8:
            lines.append(f"- 还有 {len(report.evidence) - 8} 条结果，使用 --format json 查看完整证据。")
    else:
        lines.append("- 没有找到证据。")
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
    if report.agent and report.agent.acquisition:
        for acquisition in report.agent.acquisition:
            lines.append(
                f"- {acquisition.provider}: {acquisition.status} "
                f"({acquisition.reason}); candidates: "
                f"{acquisition.candidate_count}; items: {acquisition.items_found}"
            )
    else:
        lines.append("- 未记录采集过程。")
    lines.extend(["", "## 结果清单"])
    if report.evidence:
        for card in report.evidence:
            lines.extend(
                [
                    f"- {card.id}: {card.title}",
                    f"  - 类型: {card.source_type}",
                    f"  - Adapter: {card.adapter}",
                    f"  - 链接: {card.url}",
                    f"  - 摘要: {_short_text(card.summary)}",
                ]
            )
    else:
        lines.append("- 没有找到可分析结果。")
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
