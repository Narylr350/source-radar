import logging
import os
import pathlib
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import Request, urlopen

from .bridge import PLATFORM_COOKIE_ENVS, load_local_env

_log = logging.getLogger("source_radar.runtime")


def _background_python(root: pathlib.Path) -> str:
    if sys.platform != "win32":
        return sys.executable
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pyw.exists():
        return str(pyw)
    raise RuntimeError(
        f"找不到后台 Python: {pyw}\n"
        f"请先运行: cd {root} && uv sync"
    )


def _hidden_spawn_opts() -> dict:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW | subprocess.STARTF_USESTDHANDLES
    si.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": si,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }


@contextmanager
def local_services_for_query(
    query: str,
    *,
    enabled: bool,
    root: str | os.PathLike[str] = ".",
):
    if not enabled:
        yield
        return

    root_path = pathlib.Path(root).resolve()
    load_local_env(root_path)

    old_endpoints = {
        "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT": os.environ.get("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"),
    }
    # MediaCrawler API/bridge: long-lived services started detached, survive context exit,
    #   managed via `engine start/stop mediacrawler`
    try:
        # MediaCrawler (long-lived — survives context exit, managed by engine start/stop)
        media_root = root_path / "external" / "MediaCrawler"
        if not media_root.exists():
            yield
            return

        active_platforms = [
            p for p, env in PLATFORM_COOKIE_ENVS.items() if os.environ.get(env)
        ]
        if not active_platforms:
            yield
            return

        if not _http_ok("http://127.0.0.1:8080/api/health"):
            _log.info("MediaCrawler API not running, attempting start...")
            if not _start_service(
                label="MediaCrawler API",
                cmd=[_background_python(media_root), "-m", "uvicorn", "api.main:app",
                     "--host", "127.0.0.1", "--port", "8080"],
                cwd=media_root,
                health_url="http://127.0.0.1:8080/api/health",
                timeout=15,
                retries=1,
            ):
                yield
                return

        if not _http_ok("http://127.0.0.1:3003/health"):
            _log.info("MediaCrawler bridge not running, attempting start...")
            if not _start_service(
                label="MediaCrawler bridge",
                cmd=[_background_python(root_path), "-m", "source_radar", "bridge",
                     "mediacrawler", "--port", "3003",
                     "--api-url", "http://127.0.0.1:8080",
                     "--platform", ",".join(active_platforms),
                     "--timeout", os.environ.get("MEDIACRAWLER_TIMEOUT", "180")],
                cwd=root_path,
                health_url="http://127.0.0.1:3003/health",
                timeout=15,
                retries=1,
            ):
                yield
                return

        os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"] = "http://127.0.0.1:3003"
        yield
    finally:
        for key, old_value in old_endpoints.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _http_ok(url: str) -> bool:
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=3):
            return True
    except Exception:
        return False


def _wait_http(url: str, *, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _http_ok(url):
            return
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for local service: {url}")


def _start_service(
    *,
    label: str,
    cmd: list[str],
    cwd: str,
    health_url: str,
    timeout: int = 15,
    retries: int = 1,
) -> bool:
    """Start a local service with retry. Returns True if healthy, False if all attempts fail."""
    for attempt in range(1 + retries):
        if attempt > 0:
            _log.info("%s retry %d/%d...", label, attempt, retries)
            time.sleep(2)
        try:
            subprocess.Popen(
                cmd,
                cwd=cwd,
                env=os.environ.copy(),
                **_hidden_spawn_opts(),
            )
            _wait_http(health_url, timeout_seconds=timeout)
            _log.info("%s started successfully", label)
            return True
        except RuntimeError:
            _log.warning("%s attempt %d failed", label, attempt + 1)
    _log.warning("%s failed after %d attempts, skipping", label, 1 + retries)
    return False
