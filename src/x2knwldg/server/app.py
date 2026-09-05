"""The application factory. Thirteen read-only ``GET`` routes over one repository.

What this file owns: creating the app, holding the repository on
``app.state``, registering the error handlers, and including the routers. What
it deliberately does not own: any route. Each router lives in its own module
under ``routes/`` so that the endpoints could be written concurrently without
contending on one file.

Eleven when Track B froze the surface, and thirteen since `T-254` added the
source graph. The count is written out here rather than left implicit because
it is the number every guard in the layer is asserted against — and it was
still "eleven" in a dozen docstrings for two tasks after it stopped being true.

``docs_url`` is off. The frozen document in ``schemas/api/v1/openapi.json`` is
the contract; a second one generated from the code at runtime would be a second
source of truth, and the one that drifts is always the generated one. The
served ``/api/openapi.json`` reads the frozen file from disk instead.

That route is the **fourteenth** thing this app serves and the one the frozen
document does not declare: a contract cannot list the request for itself
without describing its own retrieval as part of the surface it describes. The
exemption is written down in three places rather than left to be discovered —
the document's own ``description``, this docstring, and
``test_api_hardening.test_the_served_surface_is_exactly_the_frozen_one``, which
walks the real router and compares against ``frozen | {"/api/openapi.json"}``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..repository.base import IndexRepository
from . import errors
from .conditional import if_none_match
from .deps import build_repository
from .envelope import error_body
from .head import HeadAsGet
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


@lru_cache(maxsize=1)
def _frozen_spec_bytes() -> tuple[bytes, str]:
    """The frozen document's bytes and its ``ETag``, read once per process.

    Served as the bytes on disk rather than as a re-serialisation, for the same
    reason ``routes/media.py`` serves a canonical file byte for byte: the
    document a client reads is then the document the tests validate.
    """
    body = _FROZEN_SPEC.read_bytes()
    return body, f'"{hashlib.sha256(body).hexdigest()[:32]}"'


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


def host_name(header: str) -> str:
    """The host a ``Host:`` header names, without its port.

    D-172: Starlette's ``TrustedHostMiddleware`` does
    ``headers.get("host", "").split(":")[0]``, so ``Host: [::1]:8931`` becomes
    ``'['``. The allowlist entries ``"[::1]"`` and ``"::1"`` were therefore
    unreachable dead code and **every** request to an IPv6-bound server was
    ``400`` — including the UI root, at the exact URL ``serve.py`` prints and
    opens in the browser. Two of the three documented ``--host`` values
    produced a UI that answered nothing, and ``localhost`` was one of them,
    because ``getaddrinfo`` returns ``AF_INET6`` first on macOS.

    An IPv6 literal is bracketed in an authority (RFC 3986), so the brackets
    are what separate the address from the port; everything else splits on the
    last colon. Both spellings are accepted for the same address, which is what
    the allowlist already assumed.
    """
    header = header.strip()
    if header.startswith("["):
        closing = header.find("]")
        return header[: closing + 1] if closing != -1 else header
    if header.count(":") > 1:
        # An unbracketed IPv6 literal. Not legal in an authority, but `::1` is
        # in the allowlist and a client that sends it means the address, not an
        # address named `:` with a port.
        return header
    return header.rsplit(":", 1)[0] if ":" in header else header


def _host_variants(name: str) -> set[str]:
    """*name* and its bracketed/unbracketed twin, lower-cased."""
    name = name.strip().lower()
    stripped = name[1:-1] if name.startswith("[") and name.endswith("]") else name
    return {name, stripped, f"[{stripped}]"}


class LoopbackHostMiddleware(BaseHTTPMiddleware):
    """Refuse a rebound name, in the frozen error envelope.

    D-103 put ``TrustedHostMiddleware`` here, and it did the right thing for
    the wrong shape twice over. Besides mis-parsing IPv6 (see :func:`host_name`),
    it is *user* middleware and therefore sits **outside** the exception
    handlers, so its refusal was ``400 text/plain "Invalid host header"`` rather
    than ``ErrorResponse`` — the one thing ``errors.handle_http_exception``
    exists to prevent, in its own words: answering off-contract "would teach a
    client that the envelope is optional".
    """

    def __init__(self, app: Any, allowed_hosts: Sequence[str]) -> None:
        super().__init__(app)
        self._allowed: set[str] = set()
        for name in allowed_hosts:
            self._allowed |= _host_variants(name)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        name = host_name(request.headers.get("host", "")).lower()
        if name not in self._allowed:
            return JSONResponse(
                status_code=400,
                content=error_body(
                    "invalid_request",
                    "This server answers only on the loopback names it was started for.",
                ),
            )
        return await call_next(request)


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
    # a parameter because `serve.serve()` knows what it bound and passes it, and
    # because the tests know what they call; the default is the loopback set and
    # never `*`. The comment used to promise that wiring and there was none:
    # `grep -rn allowed_hosts` returned these lines and nothing else, so the
    # parameter had exactly one value in the whole program and `--host` could
    # not have widened the allowlist if it had ever been allowed to widen.
    app.add_middleware(
        LoopbackHostMiddleware,
        allowed_hosts=list(allowed_hosts if allowed_hosts is not None else LOOPBACK_HOST_NAMES),
    )

    # Before routing: a `HEAD` has to become a `GET` for the router to match it
    # at all. See `head.py` for why this is a middleware rather than thirteen
    # `methods=["GET", "HEAD"]` decorators.
    #
    # Added *after* the host check and therefore **outside** it: Starlette's
    # `add_middleware` inserts at index 0, so the last one added is the
    # outermost, and `app.user_middleware` reads `[HeadAsGet,
    # LoopbackHostMiddleware]`. This comment said the opposite — "after the host
    # check (added above, so it stays the outermost of the two)" — which is a
    # false statement about ordering in the one file where ordering is
    # load-bearing. Nothing depends on which way round these two run (a `HEAD`
    # from a rebound name is refused either way), and that is exactly why the
    # error could sit here: the next pair of middlewares will not be so lucky.
    app.add_middleware(HeadAsGet)

    errors.install(app)
    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    @app.get("/api/openapi.json", include_in_schema=False)
    def frozen_spec(request: Request) -> Any:
        """Serve the frozen contract, not a generated one.

        A client that wants to know what this server promises should read the
        same document the tests validate against.

        Read once and cached, with an ``ETag``. The document is immutable — it
        ships inside the package and the tests fail if the two copies differ by
        a byte — and this used to re-read 51,883 bytes and run a ``json.loads``
        on every request, with no cache and no validator, so a client polling
        the contract paid for it every time and could never be told "unchanged".

        The revalidation itself was then wrong in three ways, because it was an
        ``==`` against the strong tag: a client sending the tag back as weak
        (``W/"a8dd…"``), as a list (``"a8dd…", "x"``), or as ``*`` was answered
        ``200`` and the whole document. RFC 9110 §13.1.2 makes all three a
        match. ``conditional.if_none_match`` is the comparison the specification
        defines, shared with the byte channel so there is one statement of it.
        """
        if not _FROZEN_SPEC.is_file():
            # The frozen envelope, not FastAPI's `{"detail": ...}` — the shape
            # `errors.handle_http_exception`'s own docstring says "would teach
            # a client that the envelope is optional". This was the one
            # response in the package that was not the envelope, and D-084
            # records that this branch was live in every installed wheel, so
            # it was not a theoretical one.
            return JSONResponse(
                status_code=404,
                content=error_body(
                    "not_found",
                    "This installation does not carry the frozen contract document.",
                ),
            )
        body, etag = _frozen_spec_bytes()
        if if_none_match(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers={"ETag": etag})
        return Response(
            content=body,
            media_type="application/json",
            headers={"ETag": etag},
        )

    return app


