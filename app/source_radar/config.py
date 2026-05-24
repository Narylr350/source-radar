import json
import os
import pathlib


def get_config_path() -> pathlib.Path:
    configured = os.environ.get("SOURCE_RADAR_CONFIG_DIR")
    if configured:
        return pathlib.Path(configured) / "config.json"
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
        if key in {"api_key", "endpoint", "model"} and value
    }


def save_openai_config(
    api_key: str,
    endpoint: str = "https://api.openai.com/",
    model: str = "gpt-4.1-mini",
) -> None:
    path = get_config_path()
    payload = _read_config()
    payload["openai"] = {
        "api_key": api_key,
        "endpoint": endpoint,
        "model": model,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_openai_config() -> None:
    path = get_config_path()
    payload = _read_config()
    payload.pop("openai", None)
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
