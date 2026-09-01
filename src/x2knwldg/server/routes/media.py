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
from pathlib import Path
from typing import Any, Iterator

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
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        # Not reported in detail: which path was refused, and where the root
        # is, are both facts about the host filesystem (ADR 0003).
        raise NotFound("That artifact has no readable local path.")
    return candidate


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
        # `bytes=-N` — the final N bytes.
        length = int(last)
        if length == 0:
            raise RangeNotSatisfiable("A suffix range of zero bytes is not satisfiable.", size)
        return (max(0, size - length), size - 1)
    start = int(first)
    end = int(last) if last else size - 1
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
    # the extension, and the schema already says null means "not known".
    media_type = record.get("media_type") or "application/octet-stream"
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
