import os
import pathlib
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import Request, urlopen

from .bridge import PLATFORM_COOKIE_ENVS, load_local_env


COMMUNITY_KEYWORDS = (
    "小红书",
    "b站",
    "bilibili",
    "微博",
    "贴吧",
    "抖音",
    "经验",
    "翻车",
    "实测",
    "案例",
    "观点",
    "死了吗",
    "去世",
    "逝世",
    "死亡",
    "讣告",
    "辟谣",
    "热搜",
    "网传",
    "爆料",
    "回应",
)


def wants_community_sources(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in COMMUNITY_KEYWORDS)


@contextmanager
def local_services_for_query(
    query: str,
    *,
    enabled: bool,
    root: str | os.PathLike[str] = ".",
):
    if not enabled or not wants_community_sources(query):
        yield
        return

    root_path = pathlib.Path(root).resolve()
    media_root = root_path / "external" / "MediaCrawler"
    if not media_root.exists():
        yield
        return

    load_local_env(root_path)
    active_platforms = [p for p, env in PLATFORM_COOKIE_ENVS.items() if os.environ.get(env)]
    if not active_platforms:
        yield
        return

    old_endpoint = os.environ.get("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT")
    processes: list[subprocess.Popen] = []
    try:
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
        if old_endpoint is None:
            os.environ.pop("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT", None)
        else:
            os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"] = old_endpoint
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
