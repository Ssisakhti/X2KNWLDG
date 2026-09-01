"""``GET /api/media/{artifact_id}`` — bytes, ranges, and what has no bytes (`T-108`).

The byte channel is the only route that opens a file, so it is where a path
parameter could become a read outside the project. Section 3 is that question
asked directly; the rest of `T-108`'s traversal battery is in
``test_api_hardening``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import api_harness as h

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
