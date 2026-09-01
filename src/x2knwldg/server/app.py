"""The application factory. Eleven read-only ``GET`` routes over one repository.

What this file owns: creating the app, holding the repository on
``app.state``, registering the error handlers, and including the routers. What
it deliberately does not own: any route. Each router lives in its own module
under ``routes/`` so that the eleven endpoints could be written concurrently
without contending on one file.

``docs_url`` is off. The frozen document in ``schemas/api/v1/openapi.json`` is
the contract; a second one generated from the code at runtime would be a second
source of truth, and the one that drifts is always the generated one. The
served ``/api/openapi.json`` reads the frozen file from disk instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..repository.base import IndexRepository
from . import errors
from .deps import build_repository
from .routes import ROUTERS

#: ``schemas/api/v1/openapi.json``, relative to the installed package.
_FROZEN_SPEC = Path(__file__).resolve().parents[3] / "schemas" / "api" / "v1" / "openapi.json"


def create_app(
    *,
    project_root: Path | None = None,
    repository: IndexRepository | None = None,
) -> FastAPI:
    """Build the app.

    Exactly one of *project_root* and *repository* is used: pass a repository to
    serve from an already-open one (the tests pass ``MemoryRepository``), or a
    project root to open the SQLite index at it. Passing neither is a
    programming error rather than a default, because "serve the current
    directory" is a decision for the CLI to make explicitly (`T-116`).
    """
    if (project_root is None) == (repository is None):
        raise ValueError("pass exactly one of project_root or repository")

    app = FastAPI(
        title="X2KNWLDG Knowledge Canvas API",
        version="v1",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.repository = repository if repository is not None else build_repository(Path(project_root))
    app.state.project_root = Path(project_root) if project_root is not None else None

    errors.install(app)
    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    @app.get("/api/openapi.json", include_in_schema=False)
    def frozen_spec() -> Any:
        """Serve the frozen contract, not a generated one.

        A client that wants to know what this server promises should read the
        same document the tests validate against.
        """
        if not _FROZEN_SPEC.is_file():
            return JSONResponse(status_code=404, content={"detail": "spec not packaged"})
        return json.loads(_FROZEN_SPEC.read_text(encoding="utf-8"))

    return app
