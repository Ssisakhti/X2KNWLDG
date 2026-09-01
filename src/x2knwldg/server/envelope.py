"""The frozen response envelope, and nothing that needs a web framework.

Every ``200`` body in ``schemas/api/v1/openapi.json`` is ``{api_version,
schema_version, data}``, plus ``page`` on the six paged endpoints and ``query``
on search. Every error body is ``{api_version, schema_version, error}``. Those
two shapes are built here, once, so eleven routes cannot disagree about the
envelope they share.

Stdlib only, deliberately. The envelope is the part of the API that the CLI's
`--json` output and a future non-HTTP transport would also want, and it is the
part worth testing on a bare core install where `fastapi` is absent (`T-009`).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: ``ApiVersion`` — a const in the frozen document. A breaking change becomes
#: ``schemas/api/v2/`` and a ``/api/v2/`` prefix, leaving these paths on v1
#: (D-026), so this string is fixed for the life of ``schemas/api/v1/``.
API_VERSION = "v1"

#: ``common.schema.json#/$defs/schemaVersion`` — the *record* model version,
#: bumped only by a new ``schemas/<version>/`` directory. Deliberately separate
#: from :data:`API_VERSION`: the surface and the records it carries version
#: independently, and collapsing them would force a v2 API to reissue v1
#: records under a new number they did not change under.
SCHEMA_VERSION = "1.0"

#: The closed ``ErrorCode`` vocabulary. Listed here so a typo in a route is a
#: failing assertion rather than a body that quietly violates the contract.
ERROR_CODES = (
    "invalid_id",
    "invalid_request",
    "not_found",
    "unavailable",
    "index_unavailable",
    "internal",
)

#: ``ErrorBody.message`` is ``maxLength: 1024`` in the frozen document.
MAX_MESSAGE = 1024

#: What replaces the tail of a message that would exceed it. Counted against
#: the limit, so the result is never 1024 *plus* a marker.
_ELLIPSIS = "… (truncated)"


def _fit(message: str) -> str:
    """Bound a message to what ``ErrorBody`` allows.

    The refusals that need this are the ones that quote the input back: an id
    of a few thousand characters is correctly refused, and the repository names
    it in the message, so the *body* then violated the very contract the refusal
    was enforcing. Found by the traversal battery's over-long id, which is the
    only hostile input whose damage is to the response rather than to the read.

    Truncated here rather than in the repository: its message is also a log line
    and a CLI string, where the full id is worth having. 1024 characters is an
    HTTP concern, so it is enforced at the HTTP boundary.
    """
    if len(message) <= MAX_MESSAGE:
        return message
    return message[: MAX_MESSAGE - len(_ELLIPSIS)] + _ELLIPSIS


def envelope(data: Any, **extra: Any) -> dict[str, Any]:
    """``{api_version, schema_version, data}``, plus whatever the shape adds.

    ``extra`` carries ``page`` and search's ``query``. It is keyword-only and
    unvalidated on purpose: ``additionalProperties: false`` in the frozen
    document is what rejects a stray key, and the contract tests run every
    response through it. A second check here would be a second rule.
    """
    body: dict[str, Any] = {
        "api_version": API_VERSION,
        "schema_version": SCHEMA_VERSION,
        "data": data,
    }
    body.update(extra)
    return body


def paged(items: Sequence[Mapping[str, Any]], page_info: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """A list response: the envelope with ``data`` an array and ``page`` beside it.

    ``page_info`` comes from ``Page.page_info()`` / ``GraphPage.page_info()``
    verbatim — the repository decides what a page is, and the API reports it.
    """
    return envelope(list(items), page=dict(page_info), **extra)


def error_body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    """``{api_version, schema_version, error}``.

    ``detail`` is omitted rather than sent as ``null`` when there is none:
    ``ErrorBody`` marks it optional, and an absent key says "no structured
    context" without inviting a client to render an empty one.

    The caller is responsible for a *message* that names what was wrong with the
    request and never a host path (D-030, ADR 0003). D-051 sanitises the one
    source of host paths that reaches a body — the reason a run was skipped — at
    the point it is recorded, so nothing here has to re-sanitise it.
    """
    if code not in ERROR_CODES:
        raise ValueError(f"error code must be one of {', '.join(ERROR_CODES)}, got {code!r}")
    error: dict[str, Any] = {"code": code, "message": _fit(message)}
    if detail is not None:
        error["detail"] = detail
    return {
        "api_version": API_VERSION,
        "schema_version": SCHEMA_VERSION,
        "error": error,
    }
