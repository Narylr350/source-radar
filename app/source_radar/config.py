import json
import logging
import logging.handlers
import os
import pathlib
import urllib.request
from typing import Optional


def fetch_models(endpoint: str, api_key: str, timeout: int = 10) -> list[str]:
    """Fetch available model IDs from an OpenAI-compatible /v1/models endpoint."""
    url = endpoint.rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode())
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid:
                models.append(mid)
        return sorted(models)
    except Exception:
        return []


def test_openai_config(format: str = "text") -> str:
    """Test the configured AI endpoint and return a status message."""
    cfg = load_openai_config()
    if not cfg.get("api_key"):
        if format == "json":
            return json.dumps({
                "status": "not-configured",
                "message": "AI 未配置",
                "available_models": [], "model_count": 0,
            })
        return "AI 未配置。运行: source-radar config setup"
    endpoint = cfg.get("endpoint", "")
    api_key = cfg["api_key"]
    model = cfg.get("model", "")

    url = endpoint.rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        model_ids = [m.get("id", "") for m in data.get("data", [])]
        if format == "json":
            return json.dumps({
                "status": "ok",
                "endpoint": endpoint,
                "current_model": model,
                "current_model_in_list": model in model_ids,
                "available_models": model_ids,
                "model_count": len(model_ids),
            }, ensure_ascii=False)
        lines = [
            f"OK 端点: {endpoint}",
            f"   可用模型: {len(model_ids)} 个",
        ]
        if model:
            if model in model_ids:
                lines.append(f"   当前模型: {model} (在列表中)")
            else:
                lines.append(f"   当前模型: {model} (不在列表中，可能不可用)")
        return "\n".join(lines)
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 401:
            detail = "API key 错误或未授权"
        elif code == 404:
            detail = "endpoint 路径不对或 /v1/models 不支持"
        elif code == 403:
            detail = "访问被拒绝 (403)，检查 API key 权限"
        else:
            detail = f"HTTP {code}"
        if format == "json":
            return json.dumps({
                "status": "error", "code": code, "message": detail,
                "available_models": [], "model_count": 0,
            })
        return f"FAIL {endpoint}: {detail}"
    except OSError as e:
        if format == "json":
            return json.dumps({
                "status": "error", "message": f"连接失败: {e}",
                "available_models": [], "model_count": 0,
            })
        return f"FAIL {endpoint}: 连接失败 - 检查 endpoint 地址和网络\n  {e}"
    except Exception as e:
        if format == "json":
            return json.dumps({
                "status": "error", "message": str(e),
                "available_models": [], "model_count": 0,
            })
        return f"FAIL {endpoint}: {e}"


# ── Logging ────────────────────────────────────────────────────────

_LOG_DEFAULTS = {
    "enabled": False,
    "level": "INFO",
    "max_bytes": 1048576,  # 1MB
    "backup_count": 3,
}


def load_logging_config() -> dict[str, object]:
    payload = _read_config()
    cfg = payload.get("logging", {})
    if not isinstance(cfg, dict):
        return dict(_LOG_DEFAULTS)
    return {**_LOG_DEFAULTS, **{k: v for k, v in cfg.items() if k in _LOG_DEFAULTS}}


def save_logging_config(enabled: bool = True, level: str = "", max_bytes: int = 0, backup_count: int = 0) -> None:
    path = get_config_path()
    payload = _read_config()
    cfg = payload.get("logging", {})
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["enabled"] = enabled
    if level:
        cfg["level"] = level
    if max_bytes:
        cfg["max_bytes"] = max_bytes
    if backup_count:
        cfg["backup_count"] = backup_count
    payload["logging"] = cfg
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _restrict_permissions(path)


def setup_logging() -> None:
    """Setup logging from config.json, env vars override."""
    cfg = load_logging_config()
    enabled = os.environ.get("SOURCE_RADAR_LOG_LEVEL") or cfg.get("enabled", False)
    if not enabled:
        return
    level = os.environ.get("SOURCE_RADAR_LOG_LEVEL") or str(cfg.get("level", "INFO"))
    max_bytes = int(os.environ.get("SOURCE_RADAR_LOG_MAX_BYTES", str(cfg.get("max_bytes", 524288))))
    backup_count = int(os.environ.get("SOURCE_RADAR_LOG_BACKUP_COUNT", str(cfg.get("backup_count", 3))))
    log_dir = pathlib.Path.cwd() / ".source-radar"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "source-radar.log"
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger("source_radar")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)


def get_config_path() -> pathlib.Path:
    configured = os.environ.get("SOURCE_RADAR_CONFIG_DIR")
    if configured:
        return pathlib.Path(configured) / "config.json"
    # Project-local .source-radar takes priority
    local = pathlib.Path.cwd() / ".source-radar" / "config.json"
    if local.exists():
        return local
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        if root:
            return pathlib.Path(root) / "source-radar" / "config.json"
    return pathlib.Path.home() / ".config" / "source-radar" / "config.json"


def load_openai_config() -> dict[str, str]:
    payload = _read_config()
    openai = payload.get("openai", {})
    if not isinstance(openai, dict):
        return {}
    return {
        key: str(value)
        for key, value in openai.items()
        if key in {"api_key", "endpoint", "model", "provider"} and value
    }


def save_openai_config(
    api_key: str,
    endpoint: str = "",
    model: str = "",
    provider: str = "",
) -> None:
    path = get_config_path()
    payload = _read_config()
    payload["openai"] = {
        "api_key": api_key,
        "endpoint": endpoint,
        "model": model,
        "provider": provider,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _restrict_permissions(path)


def _restrict_permissions(path: pathlib.Path) -> None:
    """Set file permissions to owner-only (600) on Unix-like systems."""
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass


def clear_openai_config() -> None:
    path = get_config_path()
    payload = _read_config()
    payload.pop("openai", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_provider_config(name: str) -> dict[str, str]:
    payload = _read_config()
    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    provider = providers.get(name, {})
    if not isinstance(provider, dict):
        return {}
    return {
        key: _string_value(value)
        for key, value in provider.items()
        if key in {"endpoint", "command", "enabled"} and value not in {"", None}
    }


def load_provider_configs() -> dict[str, dict[str, str]]:
    payload = _read_config()
    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    return {
        str(name): load_provider_config(str(name))
        for name in providers
        if load_provider_config(str(name))
    }


def save_provider_config(
    name: str,
    *,
    endpoint: str = "",
    command: str = "",
    enabled: bool = True,
) -> None:
    path = get_config_path()
    payload = _read_config()
    providers = payload.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        payload["providers"] = providers
    providers[name] = {
        "endpoint": endpoint,
        "command": command,
        "enabled": "true" if enabled else "false",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_provider_config(name: str) -> None:
    path = get_config_path()
    payload = _read_config()
    providers = payload.get("providers", {})
    if isinstance(providers, dict):
        providers.pop(name, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_config() -> dict[str, object]:
    try:
        path = get_config_path()
    except RuntimeError:
        return {}
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _string_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
