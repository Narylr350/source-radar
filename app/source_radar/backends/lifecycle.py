"""Pure lifecycle state transitions for managed backends."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from .registry import BackendDiagnostics, BackendRegistry


def _check_http_ready(url: str, timeout: int = 3) -> bool:
    """Check if an HTTP endpoint is responding."""
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _is_disabled(value: str | None) -> bool:
    return value is not None and value.lower() in ("0", "false", "no")


def _autostart_enabled(engine_key: str) -> bool:
    if _is_disabled(os.environ.get("SOURCE_RADAR_BACKEND_AUTOSTART")):
        return False
    if engine_key == "searxng" and _is_disabled(os.environ.get("SOURCE_RADAR_SEARXNG_AUTOSTART")):
        return False
    return True


def _process_output(result: subprocess.CompletedProcess) -> str:
    stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else (result.stderr or "")
    stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else (result.stdout or "")
    detail = (stderr or stdout or f"exit code {result.returncode}").strip()
    return detail[:500]


class BackendLifecycleManager:
    def __init__(self, registry: BackendRegistry):
        self.registry = registry

    def ensure_ready(self, key: str) -> bool:
        """Ensure a backend is ready. If stopped, try to start it.

        Returns True if ready (already was or successfully started).
        Returns False if could not start (cooldown, failure, not installed).
        """
        backend = self.registry.get(key)
        now = time.time()

        # Already ready
        if backend.ready:
            return True

        # In cooldown — don't retry
        if backend.cooling_down_until and now < backend.cooling_down_until:
            return False

        # Check if autostart is enabled
        if not _autostart_enabled(backend.engine_key):
            return False

        # Try to start
        self.mark_starting(key)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "source_radar", "engine", "start", backend.engine_key],
                capture_output=True, timeout=backend.start_budget_seconds or 20,
            )
        except Exception:
            self.record_failure(key, reason="start-failed", message="启动失败",
                                now=now, cooldown_seconds=60)
            return False
        if result.returncode != 0:
            self.record_failure(key, reason="start-failed", message=_process_output(result),
                                now=now, cooldown_seconds=60)
            return False

        # Check if it came up
        # Use BridgeHealth for health check if available, else assume ready
        from ..health import BridgeHealth
        hs = BridgeHealth.check(backend.engine_key)
        if hs.status in ("ok", "degraded"):
            self.mark_ready(key, now=now)
            return True
        else:
            self.record_failure(key, reason="start-timeout", message=f"启动后健康检查失败: {hs.status}",
                                now=now, cooldown_seconds=60)
            return False

    def mark_starting(self, key: str) -> None:
        backend = self.registry.get(key)
        backend.lifecycle_state = "starting"
        backend.status = "starting"
        backend.ready = False

    def mark_warming(self, key: str) -> None:
        backend = self.registry.get(key)
        backend.lifecycle_state = "warming"
        backend.status = "starting"
        backend.ready = False

    def mark_ready(self, key: str, *, now: float) -> None:
        backend = self.registry.get(key)
        backend.lifecycle_state = "ready"
        backend.status = "ready"
        backend.ready = True
        backend.cooling_down_until = None
        backend.diagnostics = BackendDiagnostics()
        if backend.idle_timeout_seconds:
            backend.warm_lease_until = now + backend.idle_timeout_seconds

    def expire_idle(self, *, now: float) -> None:
        for backend in self.registry.all():
            if not backend.ready or backend.warm_lease_until is None:
                continue
            if now <= backend.warm_lease_until:
                continue
            backend.lifecycle_state = "cooling_down"
            backend.status = "stopped"
            backend.ready = False
            backend.diagnostics = BackendDiagnostics(
                reason="idle-timeout",
                message="空闲保温时间已过，等待停止或下次按需启动",
                retryable=True,
            )

    def record_failure(
        self,
        key: str,
        *,
        reason: str,
        message: str,
        fix: str = "",
        now: float,
        cooldown_seconds: int,
    ) -> None:
        backend = self.registry.get(key)
        backend.lifecycle_state = "cooling_down"
        backend.status = "failed"
        backend.ready = False
        backend.cooling_down_until = now + cooldown_seconds
        backend.diagnostics = BackendDiagnostics(
            reason=reason,
            message=message,
            retryable=False,
            fix=fix,
        )
