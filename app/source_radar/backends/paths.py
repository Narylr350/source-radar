"""Central backend runtime path helpers."""

from pathlib import Path


def runtime_root(project_root: Path | str = ".") -> Path:
    return Path(project_root) / ".source-radar"


def engine_root(project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "engines"


def engine_source_path(backend_key: str, project_root: Path | str = ".") -> Path:
    name = backend_key.split(".")[-1]
    return engine_root(project_root) / name / "source"


def engine_venv_path(backend_key: str, project_root: Path | str = ".") -> Path:
    name = backend_key.split(".")[-1]
    return engine_root(project_root) / name / "venv"


def pid_path(backend_key: str, project_root: Path | str = ".") -> Path:
    safe_key = backend_key.replace(".", "-")
    return runtime_root(project_root) / "pids" / f"{safe_key}.pid"


def log_path(name: str, project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "logs" / name
