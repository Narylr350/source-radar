"""Backend registry and lifecycle primitives."""

from .lifecycle import BackendLifecycleManager
from .registry import (
    BackendDiagnostics,
    BackendInstall,
    BackendRecord,
    BackendRegistry,
    build_default_registry,
)

__all__ = [
    "BackendDiagnostics",
    "BackendInstall",
    "BackendLifecycleManager",
    "BackendRecord",
    "BackendRegistry",
    "build_default_registry",
]
