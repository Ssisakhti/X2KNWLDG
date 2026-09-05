"""``GET /api/media/{artifact_id}`` — bytes, ranges, and what has no bytes (`T-108`).

The byte channel is the only route that opens a file, so it is where a path
parameter could become a read outside the project. Section 3 is that question
asked directly; the rest of `T-108`'s traversal battery is in
``test_api_hardening``.
"""

from __future__ import annotations

from pathlib import Path

import api_harness as h
import pytest

pytestmark = [h.requires_fastapi]


# --------------------------------------------------------------------------
# 1. The whole artifact
# --------------------------------------------------------------------------


def _artifacts(client) -> list[dict]:
    body = client.get("/api/sources").json()
    out: list[dict] = []
    for source in body["data"]:
        detail = client.get(f"/api/sources/{source['id']}").json()
        out.extend(detail["data"]["artifacts"])
    return out


def _first_local(client) -> dict:
    for artifact in _artifacts(client):
        if artifact.get("path") and artifact.get("available"):
            return artifact
    pytest.fail("the fixtures hold no available local artifact")


def test_a_canonical_file_is_served_byte_for_byte(tmp_path: Path) -> None:
    """The API serves the file as written; it never reformats canonical content.

    Checked against the bytes on disk rather than against a re-serialised
    ``json.dumps``, because "equal as JSON" would pass even if the route had
    reformatted the document — which canvas plan §15 forbids.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        response = client.get(f"/api/media/{artifact['id']}")
        assert response.status_code == 200
        assert response.content == (root / artifact["path"]).read_bytes()
        assert response.headers["accept-ranges"] == "bytes"


def test_the_media_type_is_stated_and_never_guessed(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        for artifact in _artifacts(client):
            if not (artifact.get("path") and artifact.get("available")):
                continue
            response = client.get(f"/api/media/{artifact['id']}")
            expected = artifact.get("media_type") or "application/octet-stream"
            assert response.headers["content-type"].split(";")[0] == expected


def test_a_raw_artifact_is_served_and_stays_immutable(tmp_path: Path) -> None:
    """``raw/`` is readable evidence. It is served, and there is no way to write it.

    ADR 0001 invariant 1: nothing in the UI or API may write to an immutable
    artifact. v1 is read-only, so the check is that no other method is allowed.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        raw = [a for a in _artifacts(client) if a["role"] == "raw" and a.get("path")]
        assert raw, "the fixtures hold no raw artifact"
        artifact = raw[0]
        assert artifact["immutable"] is True
        assert client.get(f"/api/media/{artifact['id']}").status_code == 200
        for method in ("put", "post", "patch", "delete"):
            response = getattr(client, method)(f"/api/media/{artifact['id']}")
            assert response.status_code in (404, 405), f"{method} was not refused"


# --------------------------------------------------------------------------
# 2. What has no bytes
# --------------------------------------------------------------------------


def test_an_external_artifact_has_no_bytes_and_says_so(tmp_path: Path) -> None:
    """A YouTube video answers ``404 unavailable`` and never a placeholder.

    ``503`` would invite a retry, and there will never be bytes here. The client
    uses ``Artifact.url``; canvas plan §15 forbids assuming a local media file.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        external = [a for a in _artifacts(client) if a["role"] == "external"]
        assert external, "the fixtures hold no external artifact"
        for artifact in external:
            assert artifact["path"] is None
            assert artifact["url"]
            h.assert_error(client.get(f"/api/media/{artifact['id']}"), 404, "unavailable")


def test_a_file_deleted_after_indexing_is_reported_not_masked(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        (root / artifact["path"]).unlink()
        h.assert_error(client.get(f"/api/media/{artifact['id']}"), 404, "unavailable")


def test_a_file_that_becomes_unreadable_is_a_refusal_not_a_truncated_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_stream`` opened the file *inside* the generator.

    The generator runs after the headers are committed, so a file that became
    unreadable between the ``stat`` and the first read produced a ``200`` with
    a ``Content-Length`` no body could satisfy — fault injection delivered 3
    bytes under ``Content-Length: 508``, status ``200``. The Reader's
    transcript panel renders that as a complete transcript: the one thing the
    ``truncated`` flag exists to prevent on the graph side. Opened before a
    status is chosen, the failure is still a *response*.
    """
    from x2knwldg.server.routes import media as media_module

    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)

        real_open = Path.open

        def refuse(self: Path, *args: object, **kwargs: object):
            if self.name == Path(artifact["path"]).name:
                raise OSError("the file went away mid-request")
            return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "open", refuse)
        h.assert_error(client.get(f"/api/media/{artifact['id']}"), 404, "unavailable")
        assert media_module.CHUNK > 0  # the module is the one under test


def test_a_body_that_loses_bytes_mid_stream_does_not_claim_to_be_complete(
    tmp_path: Path,
) -> None:
    """A short read used to ``break``, ending the body under its own
    ``Content-Length`` with a ``200`` already on the wire.

    Raising makes it a framing error every HTTP client detects, where a
    silently truncated ``200`` is one no client can.
    """
    from x2knwldg.server.routes.media import _stream

    payload = tmp_path / "short.json"
    payload.write_bytes(b"1234")

    handle = payload.open("rb")
    with pytest.raises(OSError, match="promised"):
        list(_stream(handle, 508))
    assert handle.closed, "the handle is closed even when the read fails"


def test_a_media_response_forbids_content_type_sniffing(tmp_path: Path) -> None:
    """This route shares an origin with the UI mounted at ``/``."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        response = client.get(f"/api/media/{artifact['id']}")
        assert response.headers["x-content-type-options"] == "nosniff"


def test_an_unknown_id_is_not_found_and_a_malformed_one_is_invalid(tmp_path: Path) -> None:
    """D-020: absent and malformed are different answers."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        h.assert_error(client.get("/api/media/youtube:fixture-pass:nosuchthing"), 404, "not_found")
        h.assert_error(client.get("/api/media/not-a-global-id"), 400, "invalid_id")


# --------------------------------------------------------------------------
# 3. Ranges — RFC 9110
# --------------------------------------------------------------------------


def _sized(client, minimum: int = 64) -> tuple[dict, int]:
    for artifact in _artifacts(client):
        if not (artifact.get("path") and artifact.get("available")):
            continue
        size = int(client.get(f"/api/media/{artifact['id']}").headers["content-length"])
        if size >= minimum:
            return artifact, size
    pytest.fail(f"no fixture artifact is at least {minimum} bytes")


def test_a_byte_range_is_answered_with_206_and_a_content_range(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        whole = (root / artifact["path"]).read_bytes()
        response = client.get(f"/api/media/{artifact['id']}", headers={"Range": "bytes=0-9"})
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 0-9/{size}"
        assert response.content == whole[:10]


def test_an_open_ended_range_runs_to_the_last_byte(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        whole = (root / artifact["path"]).read_bytes()
        response = client.get(f"/api/media/{artifact['id']}", headers={"Range": "bytes=10-"})
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 10-{size - 1}/{size}"
        assert response.content == whole[10:]


def test_a_suffix_range_returns_the_final_bytes(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        whole = (root / artifact["path"]).read_bytes()
        response = client.get(f"/api/media/{artifact['id']}", headers={"Range": "bytes=-16"})
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes {size - 16}-{size - 1}/{size}"
        assert response.content == whole[-16:]


def test_an_end_past_the_last_byte_is_clamped_not_refused(tmp_path: Path) -> None:
    """RFC 9110: a last-byte-pos beyond the length is the length minus one."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes=0-{size + 1000}"}
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 0-{size - 1}/{size}"


def test_an_unsatisfiable_range_is_416_and_names_the_real_length(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes={size + 1}-{size + 9}"}
        )
        h.assert_error(response, 416, "invalid_request")
        assert response.headers["content-range"] == f"bytes */{size}"


def test_a_malformed_range_header_is_ignored_rather_than_refused(tmp_path: Path) -> None:
    """RFC 9110: an unparseable Range is ignored and the whole file is served."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        for header in ("bytes=abc-def", "furlongs=0-9", "bytes 0-9", ""):
            response = client.get(f"/api/media/{artifact['id']}", headers={"Range": header})
            assert response.status_code == 200, f"{header!r} was not ignored"
            assert len(response.content) == size


def test_the_ranges_of_one_artifact_reassemble_into_it(tmp_path: Path) -> None:
    """Paging the bytes must equal reading them once. The property, not a case."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client, minimum=200)
        whole = (root / artifact["path"]).read_bytes()
        assembled = b""
        step = 37
        for start in range(0, size, step):
            end = min(start + step - 1, size - 1)
            response = client.get(
                f"/api/media/{artifact['id']}", headers={"Range": f"bytes={start}-{end}"}
            )
            assert response.status_code == 206
            assembled += response.content
        assert assembled == whole


# --------------------------------------------------------------------------
# 4. Both implementations
# --------------------------------------------------------------------------


@h.requires_fts5
def test_both_implementations_serve_the_same_bytes(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    seen: dict[str, bytes] = {}
    for label, client in h.both_clients(root):
        artifact = _first_local(client)
        response = client.get(f"/api/media/{artifact['id']}")
        assert response.status_code == 200, label
        seen[label] = response.content
    assert len(set(seen.values())) == 1, "the two implementations served different bytes"


# --------------------------------------------------------------------------
# 4. D-083 — a Range header longer than `int()` will convert
# --------------------------------------------------------------------------
#
# CPython refuses to convert a decimal string of more than 4300 digits and
# raises `ValueError`, which nothing in `media.py` caught — so a long `Range`
# header answered an undeclared `500` to any unauthenticated client, while 4299
# digits answered `206` correctly. The route declares `200, 206, 400, 404, 416,
# 503` and nothing else. A number that cannot be an offset into the file does
# not need converting exactly: it is simply past the end, which is a `416`.

#: Every status `GET /api/media/{artifact_id}` declares. `500` is not among them.
#: `304` joined the set when the byte channel grew validators — it is declared
#: because it is served, which is the direction this list has to be read in.
DECLARED_MEDIA_STATUSES = {200, 206, 304, 400, 404, 416, 503}


@pytest.mark.parametrize("digits", [4299, 4301, 5000, 20000])
def test_an_enormous_range_start_is_a_416_not_a_500(tmp_path: Path, digits: int) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes={'9' * digits}-"}
        )
        h.assert_error(response, 416, "invalid_request")
        assert response.headers["content-range"] == f"bytes */{size}"


@pytest.mark.parametrize("digits", [4301, 20000])
def test_an_enormous_range_end_still_serves_the_rest(tmp_path: Path, digits: int) -> None:
    """`bytes=0-<enormous>` is satisfiable: the end is clamped to the last byte."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes=0-{'9' * digits}"}
        )
        assert response.status_code == 206, response.status_code
        assert len(response.content) == size


@pytest.mark.parametrize("digits", [4301, 20000])
def test_an_enormous_suffix_range_is_the_whole_file(tmp_path: Path, digits: int) -> None:
    """RFC 9110: a suffix larger than the representation is the whole of it."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes=-{'9' * digits}"}
        )
        assert response.status_code == 206, response.status_code
        assert len(response.content) == size
        assert response.headers["content-range"] == f"bytes 0-{size - 1}/{size}"


def test_no_long_range_header_answers_an_undeclared_status(tmp_path: Path) -> None:
    """The contract drift the defect was, asserted as the property."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, _size = _sized(client)
        headers = [
            f"bytes={'9' * 5000}-",
            f"bytes=0-{'9' * 5000}",
            f"bytes=-{'9' * 5000}",
            f"bytes={'0' * 5000}-{'9' * 5000}",
            f"bytes={'9' * 5000}-{'9' * 5000}",
            f"bytes={'9' * 5000}-0",
            f"bytes=-{'0' * 5000}",
        ]
        for header in headers:
            response = client.get(f"/api/media/{artifact['id']}", headers={"Range": header})
            assert response.status_code in DECLARED_MEDIA_STATUSES, (
                header[:32],
                response.status_code,
            )


def test_a_leading_zero_padded_range_is_read_as_its_value(tmp_path: Path) -> None:
    """The digit-length shortcut must not mistake padding for magnitude."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client, minimum=32)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"Range": f"bytes={'0' * 5000}0-{'0' * 20}9"}
        )
        assert response.status_code == 206, response.status_code
        assert response.headers["content-range"] == f"bytes 0-9/{size}"


# --------------------------------------------------------------------------
# 5. D-104 — a stated media type is checked before it becomes a header
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stated",
    ["tëxt/plåin", "text/plain\r\nX-Injected: 1", "not-a-type", "", "text/plain\nX: 1", "a/" + "b" * 300],
    ids=["non-latin1", "crlf", "no-slash", "empty", "lf", "overlong"],
)
def test_a_media_type_this_server_cannot_send_is_refused(tmp_path: Path, stated: str) -> None:
    """It went into `Content-Type` with no validation at all.

    A value outside latin-1 failed header encoding and answered an undeclared
    `500`; one containing CRLF was placed in the header dict unchecked, with
    only h11's wire-level refusal in the way. Not reachable without index write
    access, which is why it is low — but "something downstream refuses it" is
    not a check this route performed.
    """
    from x2knwldg.server.routes.media import MediaUnavailable, _checked_media_type

    with pytest.raises(MediaUnavailable):
        _checked_media_type({"media_type": stated})


@pytest.mark.parametrize(
    "stated", ["video/mp4", "text/plain; charset=utf-8", "application/octet-stream"]
)
def test_an_ordinary_media_type_is_sent_unchanged(stated: str) -> None:
    from x2knwldg.server.routes.media import _checked_media_type

    assert _checked_media_type({"media_type": stated}) == stated


@pytest.mark.parametrize(
    "stated",
    [
        "text/html",
        "text/html; charset=utf-8",
        "TEXT/HTML",
        "application/xhtml+xml",
        "image/svg+xml",
        "application/javascript",
    ],
)
def test_active_content_is_refused_even_though_it_is_well_formed(stated: str) -> None:
    """The record was syntax-checked, never allowlisted.

    The module's own premise is that the index is a rebuildable cache and so
    *not* a trust boundary — which is why ``path`` is resolved and re-checked —
    and ``media_type`` from the same record got only a grammar check. The UI is
    mounted at ``/`` on this same origin, so a document served as HTML from
    ``/api/media`` would run there.
    """
    from x2knwldg.server.routes.media import MediaUnavailable, _checked_media_type

    with pytest.raises(MediaUnavailable):
        _checked_media_type({"media_type": stated})


def test_every_type_the_index_can_mint_is_sendable() -> None:
    """The allowlist is derived from the producer, so the two cannot drift."""
    from x2knwldg.adapters.base import MEDIA_TYPES
    from x2knwldg.server.routes.media import _checked_media_type

    for produced in MEDIA_TYPES.values():
        assert _checked_media_type({"media_type": produced}) == produced


def test_an_unstated_media_type_is_octet_stream_not_a_refusal() -> None:
    """`null` means "not known", which octet-stream answers honestly.

    Refusal is for a *malformed* value: replacing one the index holds would be
    guessing, and this route states a media type rather than guessing it.
    """
    from x2knwldg.server.routes.media import _checked_media_type

    assert _checked_media_type({"media_type": None}) == "application/octet-stream"
    assert _checked_media_type({}) == "application/octet-stream"


def test_every_served_artifact_answers_a_declared_status(tmp_path: Path) -> None:
    """The property, over the fixtures: 500 is not in the declared set."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        for artifact in _artifacts(client):
            response = client.get(f"/api/media/{artifact['id']}")
            assert response.status_code in DECLARED_MEDIA_STATUSES, (
                artifact["id"],
                response.status_code,
            )


# ---------------------------------------------------------------------------
# Two undeclared responses (D-173)
# ---------------------------------------------------------------------------


def _empty_artifact(root: Path) -> str:
    """Truncate a local artifact to zero bytes and return its id."""
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
    (root / artifact["path"]).write_bytes(b"")
    return str(artifact["id"])


@pytest.mark.parametrize("header", ["bytes=-5", "bytes=-1", "bytes=-9999"])
def test_a_suffix_range_over_a_zero_byte_artifact_is_416(tmp_path: Path, header: str) -> None:
    """RFC 9110: no suffix range is satisfiable against an empty representation.

    The `start >= size` guard was on the explicit-first branch only, so
    `bytes=-5` against a zero-byte artifact returned `(0, -1)` and the route
    answered `206 Content-Range: bytes 0--1/0` — a satisfied range over a
    representation with no bytes to satisfy it. The sibling branch, `bytes=0-`,
    already got this right.
    """
    root = h.project(tmp_path)
    artifact_id = _empty_artifact(root)
    with h.client(h.memory_repository(root)) as client:
        response = client.get(f"/api/media/{artifact_id}", headers={"Range": header})
        h.assert_error(response, 416, "invalid_request")
        assert response.headers["content-range"] == "bytes */0"


def test_an_explicit_range_over_a_zero_byte_artifact_is_still_416(tmp_path: Path) -> None:
    """The branch that was already right, asserted beside the one that was not."""
    root = h.project(tmp_path)
    artifact_id = _empty_artifact(root)
    with h.client(h.memory_repository(root)) as client:
        response = client.get(f"/api/media/{artifact_id}", headers={"Range": "bytes=0-"})
        h.assert_error(response, 416, "invalid_request")


def test_a_zero_byte_artifact_with_no_range_is_an_empty_200(tmp_path: Path) -> None:
    """An empty file is not an error; only a *range* over it is unsatisfiable."""
    root = h.project(tmp_path)
    artifact_id = _empty_artifact(root)
    with h.client(h.memory_repository(root)) as client:
        response = client.get(f"/api/media/{artifact_id}")
        assert response.status_code == 200, response.text
        assert response.content == b""


def test_a_record_path_holding_a_nul_is_a_404_not_a_500(tmp_path: Path) -> None:
    """`Path.resolve()` raises `ValueError`, which is not an `OSError`.

    `posixpath.realpath` catches `OSError` and nothing caught this, so it
    reached `handle_unexpected` as an undeclared `500`. A path that cannot even
    be named is a path this route cannot read — the same answer as every other
    unreadable one.
    """
    from x2knwldg.server.errors import NotFound
    from x2knwldg.server.routes.media import _resolve

    with pytest.raises(NotFound):
        _resolve(tmp_path, "output/run/raw/sour\x00ce.srt")


# ---------------------------------------------------------------------------
# 6. `HEAD` is `GET` without the body — including the range headers
# ---------------------------------------------------------------------------
#
# The `HEAD` branch read the scope key *before* the range arithmetic and threw
# the computed span away, so it always answered `200` with the whole file's
# length and no `Content-Range`. Measured against a 508-byte artifact:
#
#     Range: bytes=0-9   GET=206  bytes 0-9/508      content-length=10
#                        HEAD=200 (no content-range) content-length=508
#     Range: bytes=-5    GET=206  bytes 503-507/508  content-length=5
#                        HEAD=200 (no content-range) content-length=508
#
# RFC 9110 §9.3.2 requires `HEAD` to send the header fields `GET` would have
# sent, and `head.py`'s own docstring names this route as the reason the
# middleware exists: it is "the standard way a player discovers Content-Length
# and Accept-Ranges before it asks for a range". A player probing with `HEAD
# Range: bytes=0-1` read `200` plus the whole length, concluded that ranges were
# unsupported, and downloaded the entire artifact.

#: Header fields a `HEAD` must reproduce from its `GET`. `Date` is excluded
#: because it legitimately differs between two requests.
_MIRRORED_HEADERS = (
    "content-length",
    "content-range",
    "content-type",
    "accept-ranges",
    "etag",
    "last-modified",
    "cache-control",
    "x-content-type-options",
)


@pytest.mark.parametrize(
    "header",
    ["bytes=0-9", "bytes=-5", "bytes=10-", "bytes=0-0"],
)
def test_head_with_a_range_answers_exactly_what_get_answers(tmp_path: Path, header: str) -> None:
    """The defect, as the property it violated: same status, same headers, no body."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        path = f"/api/media/{artifact['id']}"
        head = client.head(path, headers={"Range": header})
        get = client.get(path, headers={"Range": header})

        assert get.status_code == 206, "the fixture range must actually be satisfiable"
        assert head.status_code == get.status_code, header
        for field in _MIRRORED_HEADERS:
            assert head.headers.get(field) == get.headers.get(field), (header, field)
        assert head.headers["content-range"] == get.headers["content-range"]
        assert int(head.headers["content-length"]) < size, "a range is not the whole file"
        assert head.content == b"", "HEAD is GET without the body"


def test_head_with_an_unsatisfiable_range_refuses_as_get_does(tmp_path: Path) -> None:
    """The 416 half of the same rule: a probe must not be told the range is fine."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        path = f"/api/media/{artifact['id']}"
        headers = {"Range": f"bytes={size + 1}-{size + 9}"}
        head = client.head(path, headers=headers)
        get = client.get(path, headers=headers)
        assert head.status_code == get.status_code == 416
        assert head.headers["content-range"] == get.headers["content-range"] == f"bytes */{size}"
        assert head.content == b""


def test_a_head_probe_still_discovers_the_whole_length_without_a_range(tmp_path: Path) -> None:
    """The behaviour the branch was written for, asserted beside the one it broke."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        head = client.head(f"/api/media/{artifact['id']}")
        assert head.status_code == 200
        assert int(head.headers["content-length"]) == size
        assert head.headers["accept-ranges"] == "bytes"
        assert "content-range" not in head.headers
        assert head.content == b""


# ---------------------------------------------------------------------------
# 7. The `stat` between the two guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failure", [FileNotFoundError, PermissionError], ids=lambda e: e.__name__)
def test_a_stat_that_fails_after_the_is_file_check_is_a_404_not_a_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[OSError]
) -> None:
    """``path.stat()`` sat unguarded one line after a guarded ``path.is_file()``.

    ``_open_at`` exists precisely because a file that becomes unreadable between
    the stat and the first read must stay a *response*, and ``_resolve`` catches
    ``ValueError`` for the same reason (D-173). The ``stat`` between the two was
    left bare, so a file that went away — or a directory whose permissions
    changed — in that window produced ``500 {"error": {"code": "internal"}}``
    where this module's own taxonomy defines ``404 unavailable`` for "the record
    exists; the bytes do not". The UI branches on that code, and ``internal``
    sends a deleted artifact down the "the server is broken" path.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        target = Path(artifact["path"]).name
        real_stat = Path.stat

        def refuse(self: Path, *args: object, **kwargs: object):
            if self.name == target:
                raise failure(f"{target} became unreadable mid-request")
            return real_stat(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "stat", refuse)
        h.assert_error(client.get(f"/api/media/{artifact['id']}"), 404, "unavailable")


def test_a_directory_where_an_artifact_should_be_is_still_refused(tmp_path: Path) -> None:
    """The membership check folded into the ``stat`` must keep refusing a non-file.

    ``is_file()`` answered this before; ``S_ISREG`` on the same ``stat_result``
    answers it now, and losing it would turn a corrupted project into a read of
    something that is not an artifact.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        target = root / artifact["path"]
        target.unlink()
        target.mkdir()
        h.assert_error(client.get(f"/api/media/{artifact['id']}"), 404, "unavailable")


# ---------------------------------------------------------------------------
# 8. Conditional requests — the byte channel had none
# ---------------------------------------------------------------------------
#
# No `ETag`, no `Last-Modified`, no `Cache-Control`, no `If-Range`. Every
# `<video>` seek and every re-open of the Reader re-read the artifact in full,
# and a `304` was not expressible on the one route in the layer that serves
# megabytes — while `/api/openapi.json`, 71 KB read once per session, was the
# only route that had a validator at all.


def test_a_served_artifact_carries_the_validators_a_cache_needs(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        response = client.get(f"/api/media/{artifact['id']}")
        etag = response.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"'), f"a strong tag is quoted: {etag}"
        assert not etag.startswith("W/"), "If-Range accepts nothing weaker than a strong tag"
        assert response.headers["cache-control"] == "no-cache"
        from email.utils import parsedate_to_datetime

        assert parsedate_to_datetime(response.headers["last-modified"]) is not None


def test_a_revalidated_artifact_is_304_and_sends_no_bytes(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        first = client.get(f"/api/media/{artifact['id']}")
        etag = first.headers["etag"]
        assert len(first.content) == size

        again = client.get(f"/api/media/{artifact['id']}", headers={"If-None-Match": etag})
        assert again.status_code == 304
        assert again.content == b""
        assert again.headers["etag"] == etag
        assert "content-length" not in again.headers


@pytest.mark.parametrize(
    "form",
    ["strong", "weak", "list", "star"],
)
def test_every_form_of_if_none_match_the_rfc_defines_revalidates(
    tmp_path: Path, form: str
) -> None:
    """§13.1.2: weak comparison, a list, and ``*``.

    A cache is free to store a tag as weak and a client is free to send two of
    them; both must revalidate rather than re-download.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        etag = client.get(f"/api/media/{artifact['id']}").headers["etag"]
        sent = {
            "strong": etag,
            "weak": f"W/{etag}",
            "list": f'"something-else", {etag}',
            "star": "*",
        }[form]
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"If-None-Match": sent}
        )
        assert response.status_code == 304, (form, sent, response.status_code)


def test_a_tag_for_another_representation_is_not_a_match(tmp_path: Path) -> None:
    """The tautology check: revalidation that always answers 304 serves stale bytes."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"If-None-Match": '"not-this-one"'}
        )
        assert response.status_code == 200
        assert len(response.content) == size


def test_if_modified_since_revalidates_and_an_older_date_does_not(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        last_modified = client.get(f"/api/media/{artifact['id']}").headers["last-modified"]

        current = client.get(
            f"/api/media/{artifact['id']}", headers={"If-Modified-Since": last_modified}
        )
        assert current.status_code == 304

        stale = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-Modified-Since": "Mon, 01 Jan 1990 00:00:00 GMT"},
        )
        assert stale.status_code == 200


def test_an_unparseable_if_modified_since_is_ignored_not_refused(tmp_path: Path) -> None:
    """A recipient that cannot understand a date treats the field as absent."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        response = client.get(
            f"/api/media/{artifact['id']}", headers={"If-Modified-Since": "not a date"}
        )
        assert response.status_code == 200


def test_an_entity_tag_outranks_a_modification_date(tmp_path: Path) -> None:
    """§13.2.2: with both present, the precise validator decides."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={
                "If-None-Match": '"not-this-one"',
                "If-Modified-Since": "Mon, 01 Jan 2400 00:00:00 GMT",
            },
        )
        assert response.status_code == 200, "the date must not rescue a failed tag"


def test_a_revalidation_outranks_a_range(tmp_path: Path) -> None:
    """There is no point sending part of a representation the client holds all of."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact = _first_local(client)
        etag = client.get(f"/api/media/{artifact['id']}").headers["etag"]
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-None-Match": etag, "Range": "bytes=0-9"},
        )
        assert response.status_code == 304
        assert response.content == b""


def test_if_range_applies_the_range_when_the_representation_is_unchanged(
    tmp_path: Path,
) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        etag = client.get(f"/api/media/{artifact['id']}").headers["etag"]
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-Range": etag, "Range": "bytes=0-9"},
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 0-9/{size}"


@pytest.mark.parametrize(
    "guard",
    ['"a-different-representation"', "Mon, 01 Jan 1990 00:00:00 GMT"],
    ids=["stale-tag", "stale-date"],
)
def test_a_stale_if_range_sends_the_whole_representation_rather_than_a_part(
    tmp_path: Path, guard: str
) -> None:
    """§13.1.5: an unmatched ``If-Range`` means the ``Range`` is ignored.

    Not refused. The client asked for "this range of the thing I already have",
    and the honest answer to a changed thing is all of it — splicing a fresh
    range onto a stale prefix is how a cache assembles a file that never existed.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-Range": guard, "Range": "bytes=0-9"},
        )
        assert response.status_code == 200, response.status_code
        assert len(response.content) == size
        assert "content-range" not in response.headers


def test_a_weak_tag_never_satisfies_if_range(tmp_path: Path) -> None:
    """Strong comparison only: a weak tag says *equivalent*, not *identical*."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        etag = client.get(f"/api/media/{artifact['id']}").headers["etag"]
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-Range": f"W/{etag}", "Range": "bytes=0-9"},
        )
        assert response.status_code == 200
        assert len(response.content) == size


def test_a_stale_if_range_over_an_unsatisfiable_range_is_200_not_416(tmp_path: Path) -> None:
    """The guard is evaluated before the range is parsed, so there is no 416 to give."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        response = client.get(
            f"/api/media/{artifact['id']}",
            headers={"If-Range": '"gone"', "Range": f"bytes={size + 99}-{size + 999}"},
        )
        assert response.status_code == 200
        assert len(response.content) == size


def test_a_replaced_file_gets_a_new_entity_tag(tmp_path: Path) -> None:
    """The tag has to change when the bytes do, even at the same length.

    An atomic replace — how this project writes canonical files (D-170) —
    installs a new inode, so the tag changes even on a filesystem whose
    ``st_mtime_ns`` is only second-resolution and even when the replacement is
    exactly as long as what it replaced. A tag that survived that would let a
    client splice new bytes onto a cached range.
    """
    import os

    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        before = client.get(f"/api/media/{artifact['id']}").headers["etag"]

        replacement = tmp_path / "replacement.bin"
        replacement.write_bytes(b"x" * size)
        os.replace(replacement, root / artifact["path"])

        after = client.get(f"/api/media/{artifact['id']}")
        assert after.headers["etag"] != before, "a replaced artifact kept its tag"
        assert after.status_code == 200
        revalidated = client.get(
            f"/api/media/{artifact['id']}", headers={"If-None-Match": before}
        )
        assert revalidated.status_code == 200, "the old tag must not revalidate"


def test_two_distinct_files_never_share_an_entity_tag(tmp_path: Path) -> None:
    """Same length, same second, different files. Only the inode separates them."""
    from x2knwldg.server.conditional import entity_tag

    first = tmp_path / "one.bin"
    second = tmp_path / "two.bin"
    first.write_bytes(b"aaaa")
    second.write_bytes(b"aaaa")
    assert entity_tag(first.stat()) != entity_tag(second.stat())
    assert entity_tag(first.stat()) == entity_tag(first.stat()), "and it is stable"


# ---------------------------------------------------------------------------
# 9. What the byte channel sends is what the document declares
# ---------------------------------------------------------------------------

#: Header fields no operation declares because the transport, not this route,
#: decides them.
_TRANSPORT_HEADERS = {
    "content-type",
    "date",
    "server",
    "connection",
    "transfer-encoding",
}


def test_every_header_the_byte_channel_sends_is_declared(tmp_path: Path) -> None:
    """The spec was the weaker copy of the implementation on three responses.

    ``416`` declared ``content: application/json`` and no headers at all, while
    the route sends the ``Content-Range: bytes */<size>`` RFC 9110 *requires* on
    one, plus ``Accept-Ranges``. ``200`` and ``206`` omitted ``Content-Length``
    and ``X-Content-Type-Options``, both of which the route has always sent. A
    header a client can rely on and the contract does not mention is a promise
    that only the code makes.
    """
    import json as _json

    frozen = _json.loads(h.OPENAPI_PATH.read_text(encoding="utf-8"))
    declared = frozen["paths"]["/api/media/{artifact_id}"]["get"]["responses"]

    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        artifact, size = _sized(client)
        path = f"/api/media/{artifact['id']}"
        etag = client.get(path).headers["etag"]
        answers = [
            client.get(path),
            client.get(path, headers={"Range": "bytes=0-9"}),
            client.get(path, headers={"If-None-Match": etag}),
            client.get(path, headers={"Range": f"bytes={size + 1}-{size + 9}"}),
        ]

    seen = set()
    for response in answers:
        status = str(response.status_code)
        assert status in declared, status
        seen.add(status)
        promised = {name.lower() for name in declared[status].get("headers", {})}
        # On an error envelope the length is the framework's framing of a JSON
        # body, which no response in the document declares. On the byte
        # channel's own 200 and 206 it is a value this route computes and a
        # player relies on, so there it must be declared.
        ignored = set(_TRANSPORT_HEADERS)
        if response.headers.get("content-type", "").startswith("application/json"):
            ignored.add("content-length")
        for name in response.headers:
            if name.lower() in ignored:
                continue
            assert name.lower() in promised, f"{status} sends undeclared {name!r}"
    assert seen == {"200", "206", "304", "416"}, seen
