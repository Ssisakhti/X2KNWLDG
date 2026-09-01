"""The local read-only HTTP API (Track B, `T-105`-`T-108`).

Importing this package must not import ``fastapi``. ADR 0001 invariant 5 keeps
the core package zero-dependency, and ``tests/test_ui_scaffold`` checks
structurally that nothing in ``x2knwldg`` imports the ``ui`` extra at module
scope. ``create_app`` is therefore resolved lazily: ``from x2knwldg.server
import envelope`` works on a bare core install, and only touching
``create_app`` requires the extra to be present.
"""

from __future__ import annotations

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
