"""Turning a refusal into a response, in one place.

``RepositoryError`` already carries ``code`` and ``http_status`` (D-030): the
repository decides what kind of refusal it is and the API renders it. That is
the whole rule here — no route may catch a repository error and pick a
different status for the same refusal, because then the taxonomy would live in
eleven places instead of one.

One thing routes *do* raise themselves, because the repository cannot:
:class:`NotFound` — the repository returns ``None`` for absence rather than
raising (see ``repository/README.md``), so the ``404`` is the route's to make.

D-174: this used to name a second, :class:`Unavailable`, "an artifact whose
record exists but whose file does not". Nothing ever instantiated it, and
``media.py`` — the only route that has that case — defines its own
``MediaUnavailable`` and its own ``RangeNotSatisfiable`` (with a ``size``
attribute the copy here lacked), importing only ``ApiError`` and ``NotFound``.
Both classes and the sentence advertising one of them are gone: a module
docstring that describes a class no caller can reach is a claim about the code
that the code does not make.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..repository.base import RepositoryError
from .envelope import error_body


class ApiError(Exception):
    """A refusal the API itself makes. Mirrors ``RepositoryError``'s shape."""

    code = "internal"
    http_status = 500

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.detail = detail


class NotFound(ApiError):
    """Nothing has that id. Distinct from an id that is *malformed* (D-020)."""

    code = "not_found"
    http_status = 404


def _response(
    code: str,
    message: str,
    status: int,
    detail: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=error_body(code, message, detail),
        headers=dict(headers) if headers else None,
    )


async def handle_repository_error(request: Request, exc: RepositoryError) -> JSONResponse:
    """Render a repository refusal with the status the repository chose.

    ``IndexUnavailable`` carries a ``state`` — *absent* is not *empty*, and a UI
    that cannot tell them apart will present "no sources" as a fact. So the
    state travels in ``detail`` rather than being flattened into the message.
    """
    detail = None
    state = getattr(exc, "state", None)
    if state is not None:
        detail = {"state": state}
    return _response(exc.code, str(exc), exc.http_status, detail)


async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _response(exc.code, str(exc), exc.http_status, exc.detail)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """A parameter outside the contract is a ``400``, not FastAPI's ``422``.

    The frozen document declares ``400`` for a bad request and never ``422``, so
    the default handler would answer with a status the contract does not list
    and a body that is not ``ErrorResponse``. Both are contract violations, and
    both are invisible until something validates the response.

    The offending parameters are named in ``detail`` — a client that sent
    ``limit=900`` should be told which field it was — but only their location
    and message, never the raw input echoed back.
    """
    fields = [
        {"field": ".".join(str(part) for part in err.get("loc", ())), "message": err.get("msg", "")}
        for err in exc.errors()
    ]
    return _response(
        "invalid_request",
        "One or more parameters are outside the contract.",
        400,
        {"fields": fields} if fields else None,
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Framework-raised HTTP errors get the frozen body too.

    An unrouted path is the common one: without this it answers with Starlette's
    ``{"detail": "Not Found"}``, which is not ``ErrorResponse`` and would teach a
    client that the envelope is optional.
    """
    code = "not_found" if exc.status_code == 404 else "invalid_request"
    if exc.status_code >= 500:
        code = "internal"
    # `exc.headers` travels with the body. Starlette builds an `Allow` for a
    # method mismatch and this handler discarded it, so the 405 carried only
    # content-length and content-type — RFC 9110 requires `Allow` on a 405,
    # and a client is left guessing what the path does accept. Any future
    # `HTTPException` with headers — a `Retry-After`, a `WWW-Authenticate` —
    # lost them the same way, so this is read from the exception rather than
    # special-cased for 405.
    return _response(
        code, str(exc.detail), exc.status_code, headers=_with_head(exc.headers)
    )


def _with_head(headers: Mapping[str, str] | None) -> Mapping[str, str] | None:
    """*headers*, with ``HEAD`` named in ``Allow`` wherever ``GET`` is.

    Starlette builds ``Allow`` from the router, and the router only knows about
    ``GET``: :class:`~x2knwldg.server.head.HeadAsGet` rewrites a ``HEAD`` into
    one *before* routing, so ``HEAD`` is answered on every path the header would
    otherwise list as ``GET``-only. ``Allow`` names the methods the **target
    resource** supports (RFC 9110), so a header that omitted it would be
    telling a client that the method it just used successfully is not allowed.
    """
    if headers is None:
        return None
    allow = headers.get("Allow") or headers.get("allow")
    if allow is None:
        return headers
    methods = [method.strip() for method in allow.split(",") if method.strip()]
    if "GET" not in methods or "HEAD" in methods:
        return headers
    updated = dict(headers)
    updated.pop("allow", None)
    updated["Allow"] = ", ".join([*methods, "HEAD"])
    return updated


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen becomes ``internal`` — never a framework traceback.

    A default handler would return the exception's own text, and that text is
    routinely a path. One generic message is the only version of this that
    cannot leak (ADR 0003).
    """
    return _response("internal", "The server could not complete the request.", 500)


def install(app) -> None:
    """Register the three handlers on *app*."""
    app.add_exception_handler(RepositoryError, handle_repository_error)
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected)
