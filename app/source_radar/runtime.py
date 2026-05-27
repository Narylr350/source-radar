import os
import pathlib
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import Request, urlopen

from .bridge import PLATFORM_COOKIE_ENVS, load_local_env


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
        "SOURCE_RADAR_FIRECRAWL_ENDPOINT": os.environ.get("SOURCE_RADAR_FIRECRAWL_ENDPOINT"),
        "SOURCE_RADAR_MEDIACRAWLER_ENDPOINT": os.environ.get("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"),
    }
    processes: list[subprocess.Popen] = []
    try:
        # Auto-start Firecrawl bridge if credentials are configured
        if os.environ.get("FIRECRAWL_API_KEY") or os.environ.get(
            "FIRECRAWL_TRANSPORT"
        ):
            if not _http_ok("http://127.0.0.1:3002/health"):
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "source_radar",
                            "bridge",
                            "firecrawl",
                            "--port",
                            "3002",
                        ],
                        cwd=root_path,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=os.environ.copy(),
                    )
                )
                _wait_http("http://127.0.0.1:3002/health", timeout_seconds=30)
            os.environ["SOURCE_RADAR_FIRECRAWL_ENDPOINT"] = "http://127.0.0.1:3002"

        # Auto-start MediaCrawler if enabled (AI/user decision, not query-based)
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
            processes.append(
                subprocess.Popen(
                    [
                        "uv",
                        "run",
                        "uvicorn",
                        "api.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8080",
                    ],
                    cwd=media_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=os.environ.copy(),
                )
            )
            _wait_http("http://127.0.0.1:8080/api/health", timeout_seconds=45)

        if not _http_ok("http://127.0.0.1:3003/health"):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "source_radar",
                        "bridge",
                        "mediacrawler",
                        "--port",
                        "3003",
                        "--api-url",
                        "http://127.0.0.1:8080",
                        "--platform",
                        ",".join(active_platforms),
                        "--timeout",
                        os.environ.get("MEDIACRAWLER_TIMEOUT", "60"),
                    ],
                    cwd=root_path,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=os.environ.copy(),
                )
            )
            _wait_http("http://127.0.0.1:3003/health", timeout_seconds=45)

        os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"] = "http://127.0.0.1:3003"
        yield
    finally:
        for key, old_value in old_endpoints.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        for process in reversed(processes):
            _stop_process(process)


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


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
