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

The channel is **conditional**. It used to carry no ``ETag``, no
``Last-Modified``, no ``Cache-Control`` and no ``If-Range``, so a ``304`` was
not expressible on the one route that serves megabytes: every re-open of the
Reader re-read the whole transcript, and every ``<video>`` seek re-read the file
from a client that already held most of it. ``/api/openapi.json`` — 71 KB, read
once per session — was the only route in the layer with a validator. See
``conditional.py`` for the comparisons and for why the entity tag this route
sends is a *strong* one; :data:`CACHE_CONTROL` records what a client is
promised about a canonical file.
"""

from __future__ import annotations

import os
import re
import stat as stat_module
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ...adapters.base import MEDIA_TYPES
from ...repository.base import IndexRepository
from ..conditional import entity_tag, http_date, if_modified_since, if_none_match, if_range_matches
from ..deps import repository
from ..envelope import error_body
from ..errors import ApiError, NotFound
from ..head import HEAD_SCOPE_KEY

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
    # Allowlisted, not merely well-formed. The module's own premise is that the
    # index is a rebuildable cache and therefore *not* a trust boundary — which
    # is why `path` is resolved and re-checked — and `media_type` from the same
    # record got only a grammar check, so `text/html` passed. The UI is mounted
    # at `/` on this same origin, so a document served as HTML from `/api/media`
    # would run there. What is allowed is the producer's own table plus the
    # three families a byte channel exists for; see `_is_sendable`.
    if not _is_sendable(_base_type(stated)):
        raise MediaUnavailable(
            "That artifact states a media type this server does not serve; "
            "the index record is damaged."
        )
    return stated


def _base_type(stated: str) -> str:
    """*stated* without its parameters, lowercased — ``text/plain`` for
    ``text/plain; charset=utf-8``."""
    return stated.split(";", 1)[0].strip().lower()


#: Every media type this route will put in a ``Content-Type``, by exact name.
#: ``MEDIA_TYPES`` is the one table that *produces* these values, imported
#: rather than restated so widening the producer widens this; plus the honest
#: answer to "not known".
_SENDABLE_TYPES = frozenset({*MEDIA_TYPES.values(), "application/octet-stream"})

#: Whole families a byte channel exists for. None of them is active content:
#: a browser plays them, and no member of any of the three can script the
#: origin it was served from. ``image/svg+xml`` is the exception that proves
#: the rule, and it is excluded by name below.
_SENDABLE_FAMILIES = ("audio/", "video/", "image/")

#: Excluded from the families above: an SVG is a document with script in it.
_UNSENDABLE_TYPES = frozenset({"image/svg+xml", "image/svg"})


def _is_sendable(base: str) -> bool:
    """Whether *base* — a media type with its parameters already stripped — is
    one this route is willing to name in a ``Content-Type``."""
    if base in _UNSENDABLE_TYPES:
        return False
    return base in _SENDABLE_TYPES or base.startswith(_SENDABLE_FAMILIES)


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


def _open_at(path: Path, start: int) -> BinaryIO:
    """The artifact's bytes, open and positioned, **before** a status is chosen.

    ``_stream`` used to open the file inside the generator — which runs after
    the headers are committed — so a file that had become unreadable between
    the ``stat`` above and the first read produced a ``200`` with a
    ``Content-Length`` no body could satisfy. Fault injection delivered 3 bytes
    under ``Content-Length: 508``, status ``200``, and the Reader's transcript
    panel renders that as a complete transcript: the one thing the
    ``truncated`` flag exists to prevent on the graph side.

    Opened here, a failure is still a *response* — the same
    ``MediaUnavailable`` a missing file gets — because nothing has been sent.
    """
    try:
        handle = path.open("rb")
    except OSError:
        raise MediaUnavailable("That artifact is no longer readable on disk.") from None
    try:
        handle.seek(start)
    except BaseException:
        handle.close()
        raise
    return handle


#: What a client may do with a copy of an artifact.
#:
#: ``no-cache`` does not mean "do not store"; it means "store it, and
#: revalidate before reusing it", which is the only cache directive this route
#: can honour truthfully. A canonical file is rewritten by a re-ingest or by
#: ``apply-bundle``, and neither is on a schedule, so any ``max-age`` would be a
#: guess about when the user next runs the pipeline — and a guess that is wrong
#: serves a stale transcript beside a fresh graph. With an ``ETag`` the
#: revalidation costs one conditional request and a ``304``, which is what the
#: byte channel was paying a full re-read for.
CACHE_CONTROL = "no-cache"


def _regular_file_stat(path: Path) -> os.stat_result:
    """``stat`` for a file this route is willing to open, or a refusal.

    The guard used to be ``if not path.is_file()`` on one line and a bare
    ``path.stat().st_size`` on the next. The bare call is the one that was
    reached when a file went away *between* the two — the same window
    :func:`_open_at` exists for, and the same window ``_resolve`` catches
    ``ValueError`` for (D-173) — and fault injection confirmed both
    ``FileNotFoundError`` and ``PermissionError`` there produced ``500
    {"error": {"code": "internal"}}``. This module's own taxonomy says a record
    whose bytes are gone is ``404 unavailable``; the UI branches on that code,
    and ``internal`` sends it down the "the server is broken" path for an
    artifact the user merely deleted.

    One ``stat`` rather than a ``is_file()`` followed by a ``stat``: the
    membership question and the size are answered by the same syscall, so there
    is no window left between them to lose. ``S_ISREG`` is what ``is_file()``
    asked, so a directory, a FIFO and ``/dev/zero`` are refused exactly as
    before.
    """
    try:
        result = path.stat()
    except OSError:
        # Indexed as available and gone — or unreadable — since. Reported
        # rather than masked with a placeholder, which canvas plan §15 forbids.
        raise MediaUnavailable("That artifact is no longer present on disk.") from None
    if not stat_module.S_ISREG(result.st_mode):
        raise MediaUnavailable("That artifact is no longer present on disk.")
    return result


def _stream(handle: BinaryIO, length: int) -> Iterator[bytes]:
    """*length* bytes from an already-open, already-positioned handle.

    A short read is raised, not ``break``-ed. The status and
    ``Content-Length`` are already on the wire by the time this runs, so there
    is no honest response left to send — and a body that stops early under a
    ``Content-Length`` that promises more is a framing error every HTTP client
    detects, where a silently truncated 200 is one no client can.
    """
    with handle:
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                raise OSError(
                    f"the artifact lost {remaining} of the {length} bytes this "
                    "response promised while it was being sent"
                )
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
    if_none_match_header: str | None = Header(default=None, alias="If-None-Match"),
    if_modified_since_header: str | None = Header(default=None, alias="If-Modified-Since"),
    if_range_header: str | None = Header(default=None, alias="If-Range"),
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
    file_stat = _regular_file_stat(path)
    size = file_stat.st_size
    # A media type is stated, never guessed: `mimetypes` would infer one from
    # the extension, and the schema already says null means "not known". What
    # is stated is now also checked before it becomes a header (D-104).
    media_type = _checked_media_type(record)
    etag = entity_tag(file_stat)
    last_modified = http_date(file_stat.st_mtime)
    # `nosniff`: the type is now allowlisted, so a browser has no reason to
    # look past it — and this route shares an origin with the UI mounted at
    # `/`, where a sniffed type would decide what a document *runs as*.
    headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": CACHE_CONTROL,
    }

    # RFC 9110 §13.2.2 fixes the order, and it is not the order the fields
    # arrive in: the entity tag decides, and `If-Modified-Since` is consulted
    # only when there is no `If-None-Match` — a client that sent both asked the
    # precise question and the imprecise one, and the precise one is the answer.
    # A match here outranks `Range`: the client already holds the whole
    # representation, so there is nothing to send a part of.
    if if_none_match(if_none_match_header, etag) or (
        if_none_match_header is None
        and if_modified_since(if_modified_since_header, file_stat.st_mtime)
    ):
        # No `Content-Length`, and the validators the client will store next
        # time. Starlette omits a body length on a 304 of its own accord; the
        # header dict is passed without one so that stays true if it stops.
        return Response(status_code=304, headers=headers)

    try:
        # `If-Range` guards the range rather than the request: when it does not
        # match, the range is *ignored* and the whole representation is sent
        # (§13.1.5). Evaluated before parsing, so a stale `If-Range` over an
        # unsatisfiable range is a 200 and not a 416 — the client asked for
        # "this range of the thing I already have", and the thing changed.
        span = (
            _parse_range(range_header, size)
            if range_header and if_range_matches(if_range_header, etag, last_modified)
            else None
        )
    except RangeNotSatisfiable as exc:
        # Answered here rather than by the generic handler, because RFC 9110
        # requires a 416 to carry `Content-Range: bytes */size` — the client
        # learns the real length from the refusal and can ask again — and the
        # generic handler renders a body, not headers.
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, str(exc)),
            headers={
                "Content-Range": f"bytes */{exc.size}",
                "Accept-Ranges": "bytes",
                "X-Content-Type-Options": "nosniff",
            },
        )

    if span is None:
        status, start, length = 200, 0, size
        headers["Content-Length"] = str(size)
    else:
        start, end = span
        length = end - start + 1
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(length)

    if request.scope.get(HEAD_SCOPE_KEY):
        # `HEAD` is `GET` without the body (RFC 9110) — *without the body*, and
        # with everything else identical. This branch used to sit above the
        # range arithmetic and throw it away: `HEAD` with `Range: bytes=0-9`
        # answered `200`, `Content-Length: 508` and no `Content-Range` where
        # `GET` answered `206`, `bytes 0-9/508`, `Content-Length: 10`. A player
        # probing with `HEAD Range: bytes=0-1` — which is the discovery this
        # route exists to serve, in `head.py`'s own words — read a `200` and a
        # whole-file length, concluded that ranges were unsupported, and
        # downloaded the entire artifact.
        #
        # Below the arithmetic, `headers` and `status` are already the ones the
        # `GET` would send, so the only difference left is the body: the file is
        # never opened, and discovering a length still costs no read. The scope
        # key is set by `head.HeadAsGet`, which is what routes `HEAD` here at all.
        return Response(status_code=status, media_type=media_type, headers=headers)

    return StreamingResponse(
        _stream(_open_at(path, start), length),
        status_code=status,
        media_type=media_type,
        headers=headers,
    )
