"""``GET /api/media/{artifact_id}`` — the byte channel, and the path rules for it.

This is the only route that opens a file, so it is the only one where a path can
escape the project. Two independent checks stand between a path parameter and a
read, and neither is a rewrite:

1. The id goes to the repository, which rejects a malformed one (`InvalidId`,
   D-020). Nothing is read until it comes back with a record.
2. The record's ``path`` is **project-relative by schema** (risk R15), and is
   still resolved and re-checked against the project root before it is opened.
   A path is trusted because it was verified, not because of where it came
   from: the index is a rebuildable cache, and a cache is not a trust boundary.

The file is served as written. Canonical JSON and the Markdown report go out
byte for byte — the API never reinterprets, reformats, or summarises canonical
content (canvas plan §15).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ...repository.base import IndexRepository
from ..deps import repository
from ..envelope import error_body
from ..errors import ApiError, NotFound

router = APIRouter(tags=["artifacts"])

#: Bytes per read. Large enough that a video does not cost thousands of
#: syscalls, small enough that one request does not hold a megabyte per chunk.
CHUNK = 64 * 1024

#: A single byte range. Multi-range requests are answered with the whole file,
#: which RFC 9110 permits: `multipart/byteranges` buys nothing for a local
#: viewer and is a parser this does not need to own.
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class MediaUnavailable(ApiError):
    """The record exists; the bytes do not.

    ``404`` rather than the ``503`` that ``errors.Unavailable`` carries, because
    the frozen document says so for this endpoint: an `external` artifact — a
    YouTube video — is *permanently* without local bytes, and ``503`` would
    invite a client to retry something that will never succeed. The client uses
    ``Artifact.url`` instead, and never assumes a local media file exists.
    """

    code = "unavailable"
    http_status = 404


class RangeNotSatisfiable(ApiError):
    code = "invalid_request"
    http_status = 416

    def __init__(self, message: str, size: int) -> None:
        super().__init__(message)
        self.size = size


def _project_root(request: Request, repo: IndexRepository) -> Path:
    """The root every artifact path must resolve inside.

    Taken from the repository rather than the app: the repository is what read
    the records, so its root is the one the paths in them are relative to.
    """
    root = getattr(repo, "project_root", None) or request.app.state.project_root
    if root is None:
        raise ApiError("The server was not configured with a project root.")
    return Path(root).expanduser().resolve()


def _resolve(root: Path, relative: str) -> Path:
    """Resolve a project-relative artifact path, refusing every escape.

    The same rule as :func:`pipeline.resolve_run_dir`, applied to a path rather
    than an id: reject, never rewrite. ``..`` must fail, not quietly become
    something inside the root.
    """
    if not relative or Path(relative).is_absolute():
        raise NotFound("That artifact has no readable local path.")
    try:
        candidate = (root / relative).resolve()
    except ValueError:
        # D-173: a NUL in a record's `path` makes `resolve()` raise
        # `ValueError: embedded null character`, which is **not** an `OSError`,
        # so `posixpath.realpath`'s own handler does not catch it and neither
        # did anything here. It reached `handle_unexpected` as an undeclared
        # `500`. A path that cannot be named is a path this route cannot read,
        # which is the same answer as every other unreadable one.
        raise NotFound("That artifact has no readable local path.") from None
    if root != candidate and root not in candidate.parents:
        # Not reported in detail: which path was refused, and where the root
        # is, are both facts about the host filesystem (ADR 0003).
        raise NotFound("That artifact has no readable local path.")
    return candidate


#: A media type this route is willing to put in a header: ``type/subtype``
#: with optional parameters, ASCII only, no control characters.
#:
#: Defect D-104: ``record["media_type"]`` went into the ``Content-Type`` header
#: with no validation at all. A value outside latin-1 (``"tëxt/plåin"``) failed
#: header encoding and answered an undeclared ``500``; one containing CRLF was
#: placed in the header dict unchecked, and only h11's own wire-level refusal
#: stood between that and a split response. Neither is reachable without index
#: write access, which is why it is a low finding and not a high one — but the
#: route performed no validation of its own, and "something else refuses it
#: downstream" is not a check.
_MEDIA_TYPE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+/[!#$%&'*+.^_`|~0-9A-Za-z-]+"
                         r"(?:\s*;\s*[!#$%&'*+.^_`|~0-9A-Za-z-]+=[^\x00-\x1f\x7f;]*)*$")


def _checked_media_type(record: Mapping[str, Any]) -> str:
    """The artifact's stated media type, or a refusal naming why it cannot be sent.

    Refused rather than replaced with ``application/octet-stream`` (D-104): the
    comment two lines below says a media type is *stated, never guessed*, and
    substituting one for a value the index holds would be guessing on behalf of
    a damaged record. ``null`` is different — the schema says it means "not
    known", and octet-stream is the honest answer to that.
    """
    stated = record.get("media_type")
    if stated is None:
        return "application/octet-stream"
    if not isinstance(stated, str) or not _MEDIA_TYPE.match(stated) or len(stated) > 255:
        raise MediaUnavailable(
            "That artifact states a media type this server cannot send; "
            "the index record is damaged."
        )
    return stated


def _byte_count(digits: str, size: int) -> int:
    """A Range header's digits as an int, without tripping ``int()``'s limit.

    Defect D-083: CPython refuses to convert a decimal string of more than
    4300 digits and raises ``ValueError``, which nothing in this module caught
    — so ``Range: bytes=<5000 nines>-`` answered an undeclared ``500`` to any
    unauthenticated client, while 4299 digits answered ``206`` correctly. The
    route declares ``200, 206, 400, 404, 416, 503`` and nothing else.

    A number that cannot be an offset into a file of *size* bytes does not need
    to be converted exactly — it is simply larger, and the satisfiability
    checks below already know what to do with that. So a digit string longer
    than *size* has digits is answered with ``size + 1``, which is past the end
    by construction, and no conversion of more than a few characters is ever
    attempted.
    """
    stripped = digits.lstrip("0") or "0"
    if len(stripped) > len(str(size)):
        return size + 1
    return int(stripped)


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """``(start, end)`` inclusive, or ``None`` to serve the whole file.

    A malformed header is ``None``, not an error: RFC 9110 says a recipient that
    cannot understand a Range header must ignore it and serve the whole
    representation. Only a *well-formed but unsatisfiable* range is a ``416``.
    """
    match = _RANGE.match(header.strip())
    if match is None:
        return None
    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if not first:
        # `bytes=-N` — the final N bytes. An N larger than the file is the whole
        # file, which is what RFC 9110 asks for.
        length = _byte_count(last, size)
        if length == 0 or size == 0:
            # D-173: the `size == 0` half was missing, and the `start >= size`
            # guard below is on the explicit-first branch only. So `bytes=-5`
            # against a zero-byte artifact returned `(0, -1)` and the route
            # answered `206 Content-Range: bytes 0--1/0` — a satisfied range
            # over a representation that has no bytes to satisfy it. RFC 9110
            # requires `416` with `Content-Range: bytes */0`, which is what the
            # sibling branch already did for `bytes=0-`.
            raise RangeNotSatisfiable("A suffix range of zero bytes is not satisfiable.", size)
        return (max(0, size - length), size - 1)
    start = _byte_count(first, size)
    end = _byte_count(last, size) if last else size - 1
    if start >= size or end < start:
        raise RangeNotSatisfiable(f"Range is outside the artifact's {size} bytes.", size)
    return (start, min(end, size - 1))


def _stream(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get(
    "/media/{artifact_id}",
    summary="The bytes of one artifact",
    response_class=Response,
)
def get_artifact_media(
    artifact_id: str,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    repo: IndexRepository = Depends(repository),
) -> Response:
    record = repo.get_artifact(artifact_id)
    if record is None:
        raise NotFound(f"No artifact has id {artifact_id!r}.")

    if record.get("role") == "external" or record.get("path") is None:
        raise MediaUnavailable("That artifact has no local bytes; use its url instead.")
    if not record.get("available", False):
        raise MediaUnavailable("That artifact was not present when the index was built.")

    path = _resolve(_project_root(request, repo), str(record["path"]))
    if not path.is_file():
        # Indexed as available and gone since. Reported rather than masked with
        # a placeholder, which canvas plan §15 forbids.
        raise MediaUnavailable("That artifact is no longer present on disk.")

    size = path.stat().st_size
    # A media type is stated, never guessed: `mimetypes` would infer one from
    # the extension, and the schema already says null means "not known". What
    # is stated is now also checked before it becomes a header (D-104).
    media_type = _checked_media_type(record)
    headers = {"Accept-Ranges": "bytes"}

    try:
        span = _parse_range(range_header, size) if range_header else None
    except RangeNotSatisfiable as exc:
        # Answered here rather than by the generic handler, because RFC 9110
        # requires a 416 to carry `Content-Range: bytes */size` — the client
        # learns the real length from the refusal and can ask again — and the
        # generic handler renders a body, not headers.
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, str(exc)),
            headers={"Content-Range": f"bytes */{exc.size}", "Accept-Ranges": "bytes"},
        )
    if span is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(
            _stream(path, 0, size), media_type=media_type, headers=headers
        )

    start, end = span
    length = end - start + 1
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        _stream(path, start, length), status_code=206, media_type=media_type, headers=headers
    )
