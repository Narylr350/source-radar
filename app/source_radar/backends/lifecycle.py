"""Pure lifecycle state transitions for managed backends."""

from __future__ import annotations

from .registry import BackendDiagnostics, BackendRegistry


class BackendLifecycleManager:
    def __init__(self, registry: BackendRegistry):
        self.registry = registry

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
