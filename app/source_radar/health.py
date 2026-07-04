import json
import os
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from .acquisition import (
    AcquisitionProvider,
    AcquisitionRequest,
    ExternalBridgeProvider,
    default_providers,
)
from .adapters import (
    collect_fixture_items,
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from .config import load_provider_config
from .models import HealthReport, HealthStatus, ProbeResult, SourceItem

ADAPTERS = ("fixture", "web", "official", "github")

_BRIDGE_REGISTRY: dict[str, dict[str, object]] = {
    "searxng": {
        "bridge_port": 3004,
        "upstream_url": "http://127.0.0.1:8888",
        "contract_version": "source-radar.bridge.v1",
        "env_var": "SOURCE_RADAR_SEARXNG_ENDPOINT",
        "fix_start": "source-radar engine start searxng",
        "fix_install": "source-radar engine install --searxng",
    },
    "mediacrawler": {
        "bridge_port": 3003,
        "upstream_url": "http://127.0.0.1:18765",
        "contract_version": "source-radar.bridge.v1",
        "env_var": "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT",
        "fix_start": "source-radar engine start mediacrawler",
        "fix_install": "source-radar engine install --community",
    },
}

_PROBE_TIMEOUT = 3
_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


class BridgeHealth:

    @staticmethod
    def resolve(name: str) -> str:
        info = _BRIDGE_REGISTRY.get(name)
        if not info:
            return ""
        env_val = os.environ.get(str(info["env_var"]), "").strip()
        if env_val:
            return env_val.rstrip("/")
        cfg_val = load_provider_config(name).get("endpoint", "").strip()
        if cfg_val:
            return cfg_val.rstrip("/")
        endpoint = f"http://127.0.0.1:{info['bridge_port']}"
        try:
            req = Request(
                f"{endpoint}/health",
                headers={"Accept": "application/json", "User-Agent": _HTTP_USER_AGENT},
            )
            with urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
                if resp.status == 200:
                    return endpoint
        except Exception:
            pass
        return ""

    @staticmethod
    def check(name: str) -> HealthStatus:
        info = _BRIDGE_REGISTRY.get(name)
        if not info:
            return HealthStatus(
                name=name, status="error", reason="unknown-bridge",
                message=f"Unknown bridge: {name}",
            )
        endpoint = BridgeHealth.resolve(name)
        if not endpoint:
            from .backends.installer import EngineInstaller
            from .backends.registry import build_default_registry

            root = os.getcwd()
            source = EngineInstaller(build_default_registry(root), root).resolve_source(name)
            installed = os.path.isdir(str(source.path))
            return HealthStatus(
                name=name,
                status="stopped" if installed else "missing",
                reason="endpoint-unresolved",
                message=f"{name} bridge endpoint is not reachable.",
                fix=str(info["fix_start"]) if installed else str(info["fix_install"]),
                retryable=True,
            )
        try:
            req_m = Request(
                f"{endpoint}/manifest",
                headers={"Accept": "application/json", "User-Agent": _HTTP_USER_AGENT},
            )
            with urlopen(req_m, timeout=_PROBE_TIMEOUT) as resp_m:
                manifest = json.loads(resp_m.read().decode("utf-8"))
            contract = str(manifest.get("contract_version") or "")
            if contract != info["contract_version"]:
                return HealthStatus(
                    name=name, status="error", reason="contract-mismatch",
                    message=f"{name} bridge contract is {contract or 'missing'}, "
                            f"expected {info['contract_version']}.",
                    fix="Upgrade the bridge service.",
                    retryable=False,
                    diagnostics={"contract_version": contract},
                )
            req_h = Request(
                f"{endpoint}/health",
                headers={"Accept": "application/json", "User-Agent": _HTTP_USER_AGENT},
            )
            with urlopen(req_h, timeout=_PROBE_TIMEOUT) as resp_h:
                health = json.loads(resp_h.read().decode("utf-8"))
        except Exception as error:
            return HealthStatus(
                name=name, status="error", reason="service-unreachable",
                message=f"Cannot reach {name} bridge: {error}",
                fix=str(info["fix_start"]),
                retryable=True,
                diagnostics={"error_type": type(error).__name__},
            )
        hs = BridgeHealth._health_from_response(name, health)
        caps: list[str] = []
        for cap in (manifest.get("capabilities") or []):
            if isinstance(cap, dict) and cap.get("name"):
                caps.append(str(cap["name"]))
            elif isinstance(cap, str):
                caps.append(cap)
        diag = dict(hs.diagnostics)
        diag["capabilities"] = ",".join(caps) if caps else diag.get("capabilities", "")
        diag["contract_version"] = str(manifest.get("contract_version") or "")
        return HealthStatus(
            name=hs.name, status=hs.status, reason=hs.reason,
            message=hs.message, fix=hs.fix, retryable=hs.retryable,
            diagnostics=diag,
        )

    @staticmethod
    def classify_searxng(data: dict) -> HealthStatus:
        unresponsive = data.get("unresponsive_engines", []) if isinstance(data, dict) else []
        captcha_engines: list[str] = []
        timeout_engines: list[str] = []
        other_issues: list[str] = []
        for entry in unresponsive:
            if isinstance(entry, list) and len(entry) >= 2:
                engine, reason = entry[0], entry[1]
                if "CAPTCHA" in reason or "captcha" in reason.lower():
                    captcha_engines.append(engine)
                elif "timeout" in reason.lower():
                    timeout_engines.append(engine)
                else:
                    other_issues.append(f"{engine}: {reason}")
        results_count = len(data.get("results", [])) if isinstance(data, dict) else 0
        diagnostics: dict[str, str] = {"results_count": str(results_count)}
        if captcha_engines:
            diagnostics["captcha_engines"] = ", ".join(captcha_engines)
        if timeout_engines:
            diagnostics["timeout_engines"] = ", ".join(timeout_engines)
        if other_issues:
            diagnostics["other_issues"] = "; ".join(other_issues)
        if captcha_engines:
            return HealthStatus(
                name="searxng", status="degraded", reason="captcha-suspended",
                message=f"搜索引擎被 CAPTCHA 暂停: {', '.join(captcha_engines)}。搜索质量可能下降。",
                fix="等待 CAPTCHA 解除（通常 10-30 分钟），或更换 IP，或在 SearXNG settings.yml 中禁用这些引擎",
                diagnostics=diagnostics,
            )
        if timeout_engines:
            return HealthStatus(
                name="searxng", status="degraded", reason="engine-timeout",
                message=f"搜索引擎超时: {', '.join(timeout_engines)}。",
                fix="检查网络连接，或在 SearXNG settings.yml 中增加这些引擎的 timeout",
                diagnostics=diagnostics,
            )
        if other_issues:
            return HealthStatus(
                name="searxng", status="degraded", reason="engine-issues",
                message=f"搜索引擎异常: {'; '.join(other_issues)}",
                diagnostics=diagnostics,
            )
        return HealthStatus(
            name="searxng", status="ok", reason="ready",
            message=f"SearXNG upstream 可访问，JSON 格式已启用，{results_count} 条结果",
            diagnostics=diagnostics,
        )

    @staticmethod
    def classify_mediacrawler(
        response: dict | None, error: Exception | None = None,
        *, api_url: str = "", platforms: str = "", active_platforms: str = "",
    ) -> HealthStatus:
        diag: dict[str, str] = {}
        if api_url:
            diag["api_url"] = api_url
        if platforms:
            diag["platforms"] = platforms
        if active_platforms:
            diag["active_platforms"] = active_platforms
        if error is not None:
            return HealthStatus(
                name="mediacrawler", status="error", reason="service-unreachable",
                message=f"Cannot reach MediaCrawler upstream: {error}",
                fix="Start MediaCrawler WebUI API with `uv run uvicorn api.main:app --port 18765`.",
                retryable=True,
                diagnostics={**diag, "error_type": type(error).__name__},
            )
        if response is None:
            response = {}
        return HealthStatus(
            name="mediacrawler",
            status=str(response.get("status") or "ok"),
            reason="ready",
            message=str(response.get("message") or "MediaCrawler API is reachable."),
            diagnostics=diag,
        )

    @staticmethod
    def _health_from_response(name: str, health: dict) -> HealthStatus:
        raw_status = str(health.get("status") or "ok")
        raw_reason = str(health.get("reason") or "ready")
        raw_message = str(health.get("message") or f"{name} bridge is ready.")
        raw_fix = str(health.get("fix") or "")
        raw_retryable = bool(health.get("retryable", False))
        raw_diag = {str(k): str(v) for k, v in (health.get("diagnostics") or {}).items()}
        if name == "searxng" and raw_status in ("ok", "degraded"):
            diag_data = dict(health.get("diagnostics") or {})
            if "captcha_engines" in raw_diag or "timeout_engines" in raw_diag:
                return HealthStatus(
                    name=name, status=raw_status, reason=raw_reason,
                    message=raw_message, fix=raw_fix, retryable=raw_retryable,
                    diagnostics=raw_diag,
                )
        return HealthStatus(
            name=name, status=raw_status, reason=raw_reason,
            message=raw_message, fix=raw_fix, retryable=raw_retryable,
            diagnostics=raw_diag,
        )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _ok(adapter: str, items: list[SourceItem], checked_at: str) -> ProbeResult:
    first = items[0]
    return ProbeResult(
        adapter=adapter,
        status="ok",
        reason="usable-items",
        message=f"{adapter} adapter returned usable source items.",
        checked_at=checked_at,
        source_type=first.source_type,
        items_found=len(items),
    )


def _no_evidence(adapter: str, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="no-evidence",
        reason="no-usable-items",
        message=f"{adapter} adapter ran but returned no usable source items.",
        checked_at=checked_at,
    )


def _needs_input(adapter: str, reason: str, message: str, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="needs-input",
        reason=reason,
        message=message,
        checked_at=checked_at,
    )


def _error(adapter: str, error: Exception, checked_at: str) -> ProbeResult:
    return ProbeResult(
        adapter=adapter,
        status="error",
        reason=error.__class__.__name__,
        message=str(error),
        checked_at=checked_at,
    )


def _provider_probe(
    provider: AcquisitionProvider,
    *,
    query: str | None,
    url: str | None = None,
    repo: str | None = None,
    checked_at: str,
) -> ProbeResult:
    if isinstance(provider, ExternalBridgeProvider):
        hs = BridgeHealth.check(provider.provider)
        return ProbeResult(
            adapter=provider.provider,
            status=hs.status,
            reason=hs.reason,
            message=hs.message,
            checked_at=checked_at,
            details={
                "provider_type": "external-bridge",
                "candidate_count": "0",
                "fix": hs.fix,
                "retryable": "true" if hs.retryable else "false",
                "warnings": "",
                "evidence_gaps": "",
                **hs.diagnostics,
            },
        )
    try:
        if query is None and url is None and repo is None and hasattr(provider, "status"):
            result = provider.status()
        else:
            result = provider.collect(
                AcquisitionRequest(
                    query=query or "source-radar provider readiness",
                    url=url,
                    repo=repo,
                )
            )
    except Exception as error:
        return _error(provider.provider, error, checked_at)
    return ProbeResult(
        adapter=result.provider,
        status=result.status,
        reason=result.reason,
        message=result.message,
        checked_at=checked_at,
        source_type=result.items[0].source_type if result.items else "",
        items_found=len(result.items),
        details={
            "provider_type": result.provider_type,
            "candidate_count": str(len(result.candidates)),
            "fix": result.fix,
            "retryable": "true" if result.retryable else "false",
            "warnings": "; ".join(result.warnings),
            "evidence_gaps": "; ".join(result.evidence_gaps),
            **result.diagnostics,
        },
    )


def probe_adapter(
    adapter: str,
    *,
    url: str | None = None,
    repo: str | None = None,
    query: str | None = None,
    providers: list[AcquisitionProvider] | None = None,
    html: str | None = None,
    github_payload: dict[str, object] | None = None,
) -> ProbeResult:
    checked_at = _utc_now()
    provider_map = {provider.provider: provider for provider in providers or []}
    if adapter in provider_map:
        return _provider_probe(
            provider_map[adapter],
            query=query,
            url=url,
            repo=repo,
            checked_at=checked_at,
        )
    if adapter not in ADAPTERS:
        return _needs_input(
            adapter,
            "unknown-adapter",
            f"Unknown adapter: {adapter}",
            checked_at,
        )

    try:
        if adapter == "fixture":
            items = collect_fixture_items("source-radar 是本地 CLI")
        elif adapter == "web":
            if not url:
                return _needs_input(
                    adapter,
                    "missing-url",
                    "--url is required to probe the web adapter.",
                    checked_at,
                )
            items = collect_web_page(url, html=html)
        elif adapter == "official":
            if not url:
                return _needs_input(
                    adapter,
                    "missing-url",
                    "--url is required to probe the official adapter.",
                    checked_at,
                )
            items = collect_official_page(url, html=html)
        else:
            if not repo:
                return _needs_input(
                    adapter,
                    "missing-repo",
                    "--repo is required to probe the github adapter.",
                    checked_at,
                )
            items = collect_github_repo(repo, payload=github_payload)
    except Exception as error:
        return _error(adapter, error, checked_at)

    if not items:
        return _no_evidence(adapter, checked_at)
    return _ok(adapter, items, checked_at)


def build_health_report(
    *,
    providers: list[AcquisitionProvider] | None = None,
    provider_query: str | None = None,
) -> HealthReport:
    checked_at = _utc_now()
    selected_providers = providers if providers is not None else default_providers()
    if selected_providers is not None:
        probes = [
            _provider_probe(
                provider,
                query=provider_query,
                checked_at=checked_at,
            )
            for provider in selected_providers
        ]
    else:
        probes = [probe_adapter(adapter) for adapter in ADAPTERS]
    summary: dict[str, str] = {"total": str(len(probes))}
    for probe in probes:
        summary[probe.status] = str(int(summary.get(probe.status, "0")) + 1)
    status = "ok" if all(probe.status == "ok" for probe in probes) else "degraded"
    return HealthReport(
        status=status,
        checked_at=checked_at,
        summary=summary,
        probes=probes,
    )
