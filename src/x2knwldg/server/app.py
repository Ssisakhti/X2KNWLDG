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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..repository.base import IndexRepository
from . import errors
from .deps import build_repository
from .routes import ROUTERS

#: The frozen contract, shipped **inside** the package.
#:
#: Defect D-084: this was ``parents[3] / "schemas" / "api" / "v1"``, documented
#: as "relative to the installed package" and in fact relative to a repo
#: checkout — and there was no ``[tool.setuptools.package-data]`` and no
#: ``MANIFEST.in``, so no wheel carried the file at all. ``GET
#: /api/openapi.json`` was therefore permanently ``404 {"detail": "spec not
#: packaged"}`` in every installed package, and CI could not see it: the `ui`
#: job installs with ``-e``, and the non-editable job has no fastapi and never
#: touches the route.
#:
#: ``schemas/api/v1/openapi.json`` stays the authored contract that the tests
#: and ``tools/generate_api_types.py`` read. This is a committed copy of it,
#: next to the module that serves it so both layouts resolve — the same
#: arrangement as the generated ``types.d.ts``, and guarded the same way, by a
#: test that fails when the two differ by a byte.
_FROZEN_SPEC = Path(__file__).resolve().parent / "openapi.json"


#: Host header values this server answers to.
#:
#: Defect D-103: there was no ``Host`` validation at all. The bind is correctly
#: loopback-only (ADR 0001 invariant 9) and there is no CORS middleware, so a
#: page on another origin cannot *read* a reply — but DNS rebinding does not
#: need CORS: a name the attacker controls, resolved to ``127.0.0.1``, makes
#: their page **same-origin** with this server, and every route is a readable
#: ``GET`` over the whole knowledge base. Binding to loopback stops other
#: machines, not other origins on this one.
#:
#: An allowlist rather than a check that the name resolves to loopback: the
#: resolution is the attacker's to control, and the set of names this server is
#: reachable at is small and knowable.
LOOPBACK_HOST_NAMES = ("localhost", "127.0.0.1", "[::1]", "::1")


def create_app(
    *,
    project_root: Path | None = None,
    repository: IndexRepository | None = None,
    allowed_hosts: Sequence[str] | None = None,
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
        # Starlette redirects `/api/sources/` to `/api/sources` by default, so
        # an **empty** source id answered 200 with a page of every source — a
        # request that names no source being served all of them. `/api/sources`
        # is the one prefix here that is both a collection and the parent of
        # item paths, so it is the one place the default is wrong; an empty id
        # is now a 404. Set on the app because `include_router` nests the
        # router's own setting and ignores it (FastAPI 0.141).
        redirect_slashes=False,
    )
    # Narrowed once, rather than twice: the exclusive-or above already decided
    # which of the two arrived, and repeating `is not None` per use is what let
    # `Path(project_root)` be written where `project_root` may be `None`.
    root = Path(project_root) if project_root is not None else None
    if repository is None:
        # `root` is not `None` here: the exclusive-or above is what guarantees
        # it, and this is where that guarantee is spent.
        assert root is not None
        repository = build_repository(root)
    app.state.repository = repository
    app.state.project_root = root

    # D-103. Installed before the routers so a rebound name is refused at the
    # boundary rather than after a route has read the index. `allowed_hosts` is
    # a parameter because `serve.py` knows what it bound and the tests know
    # what they call; the default is the loopback set and never `*`.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(allowed_hosts if allowed_hosts is not None else LOOPBACK_HOST_NAMES),
    )

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
