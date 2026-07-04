import logging
import os
import pathlib
from contextlib import contextmanager

from .backends.lifecycle import BackendLifecycleManager
from .backends.registry import build_default_registry
from .bridge import PLATFORM_COOKIE_ENVS, load_local_env
from .health import BridgeHealth

_log = logging.getLogger("source_radar.runtime")


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

    old_endpoint = os.environ.get("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT")
    try:
        active_platforms = [
            p for p, env in PLATFORM_COOKIE_ENVS.items() if os.environ.get(env)
        ]
        if active_platforms:
            try:
                manager = BackendLifecycleManager(build_default_registry(root_path), project_root=root_path)
                if manager.ensure_ready("mediacrawler"):
                    endpoint = BridgeHealth.resolve("mediacrawler")
                    if endpoint:
                        os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"] = endpoint
            except Exception as error:
                _log.warning("MediaCrawler lifecycle ensure_ready failed: %s", error)
        yield
    finally:
        if old_endpoint is None:
            os.environ.pop("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT", None)
        else:
            os.environ["SOURCE_RADAR_MEDIACRAWLER_ENDPOINT"] = old_endpoint
