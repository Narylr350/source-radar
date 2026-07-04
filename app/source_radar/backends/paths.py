"""Central backend runtime path helpers."""

from pathlib import Path


def runtime_root(project_root: Path | str = ".") -> Path:
    return Path(project_root) / ".source-radar"


def runtime_dir(project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "runtime"


def engine_root(project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "engines"


def engine_dir(backend_key: str, project_root: Path | str = ".") -> Path:
    name = backend_key.split(".")[-1]
    return engine_root(project_root) / name


def engine_source_path(backend_key: str, project_root: Path | str = ".") -> Path:
    return engine_dir(backend_key, project_root) / "source"


def engine_venv_path(backend_key: str, project_root: Path | str = ".") -> Path:
    return engine_source_path(backend_key, project_root) / ".venv"


def engine_metadata_path(backend_key: str, project_root: Path | str = ".") -> Path:
    return engine_dir(backend_key, project_root) / "metadata.json"


def downloads_root(project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "downloads"


def archive_download_path(filename: str, project_root: Path | str = ".") -> Path:
    return downloads_root(project_root) / "archives" / filename


def download_manifest_path(filename: str, project_root: Path | str = ".") -> Path:
    return downloads_root(project_root) / "manifests" / f"{filename}.json"


def runtime_cache_path(name: str = "acquisition", project_root: Path | str = ".") -> Path:
    return runtime_dir(project_root) / "cache" / name


def session_dir(project_root: Path | str = ".") -> Path:
    return runtime_dir(project_root) / "sessions"


def crawl4ai_runtime_dir(project_root: Path | str = ".") -> Path:
    return runtime_dir(project_root) / "crawl4ai"


def browser_profile_dir(platform: str, project_root: Path | str = ".") -> Path:
    return runtime_dir(project_root) / "browser-profiles" / platform


def pid_path(backend_key: str, project_root: Path | str = ".") -> Path:
    safe_key = backend_key.replace(".", "-")
    return runtime_root(project_root) / "pids" / f"{safe_key}.pid"


def log_path(name: str, project_root: Path | str = ".") -> Path:
    return runtime_root(project_root) / "logs" / name
