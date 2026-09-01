"""`T-108` — what the API refuses, across every route at once.

The per-route test files check their own refusals. This one checks the
properties that must hold *everywhere*, because a rule enforced in ten routes
and forgotten in the eleventh is not enforced:

* no path parameter can escape the project root;
* no response body names a host path;
* a malformed id is refused as malformed, never answered as absent;
* every error body is the frozen ``ErrorResponse``, whatever produced it.

Read [ADR 0003](../docs/adr/0003-reject-unsafe-identifiers.md) first: every id
from outside the process goes through a rule that **rejects**. A rewriting
sanitiser must not stand in for one — ``../other`` must fail, not quietly
become ``_other``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import api_harness as h

pytestmark = [h.requires_fastapi]


#: Ids that must never reach a filesystem read. Each is a real technique rather
#: than a variation on one: parent traversal, an absolute path, percent- and
#: double-percent-encoding, a backslash, a NUL, a newline, a URL, and length.
HOSTILE_IDS = [
    "..",
    "../..",
    "../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "..%252f..%252fetc%252fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//etc/passwd",
    "/etc/passwd",
    "/Users/saeid/.ssh/id_rsa",
    "C:\\Windows\\System32\\config\\SAM",
    "..\\..\\windows\\win.ini",
    "youtube:../../etc:passwd",
    "youtube:pass-run:../../../etc/passwd",
    "\x00",
    "youtube:pass\x00run:metadata",
    "youtube:pass\nrun:metadata",
    "file:///etc/passwd",
    "http://example.com/",
    "a" * 4096,
    "",
    " ",
    ".",
    "~",
    "~/.ssh/id_rsa",
    "$HOME",
    "%00",
]

#: Every route that takes an id in its path, and the response that route gives
#: for an id that is well-formed but matches nothing.
ID_ROUTES = [
    "/api/sources/{id}",
    "/api/sources/{id}/entities",
    "/api/sources/{id}/relations",
    "/api/entities/{id}",
    "/api/artifacts/{id}",
    "/api/media/{id}",
    "/api/graph/neighborhood/{id}",
]


@pytest.fixture(scope="module")
def served(tmp_path_factory) -> Path:
    return h.project(tmp_path_factory.mktemp("hardened"))


# --------------------------------------------------------------------------
# 1. No path parameter escapes the project
# --------------------------------------------------------------------------


@pytest.mark.parametrize("template", ID_ROUTES)
@pytest.mark.parametrize("hostile", HOSTILE_IDS)
def test_a_hostile_id_is_refused_and_never_read(served: Path, template: str, hostile: str) -> None:
    """Refused, never served, and never a crash.

    A ``500`` would mean the id reached something that was not expecting it,
    which is the same defect as a traversal even when nothing escaped. A ``200``
    would mean it resolved. Both are failures; the acceptable answers are a
    refusal (``400``), an absence (``404``), or the router never matching the
    path at all.
    """
    with h.client(h.memory_repository(served)) as client:
        response = client.get(template.replace("{id}", hostile))
        assert response.status_code in (400, 404, 405), (
            f"{template} with {hostile!r} answered {response.status_code}"
        )
        assert response.status_code < 500
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
            if "error" in body:
                h.assert_contract("ErrorResponse", body)


@pytest.mark.parametrize("hostile", HOSTILE_IDS)
def test_no_hostile_id_ever_returns_file_bytes(served: Path, hostile: str) -> None:
    """The byte channel specifically: nothing outside the project is ever served."""
    with h.client(h.memory_repository(served)) as client:
        response = client.get(f"/api/media/{hostile}")
        assert response.status_code != 200, f"{hostile!r} was served bytes"
        assert b"root:" not in response.content, "a passwd file was served"
        assert b"PRIVATE KEY" not in response.content


def test_an_indexed_path_pointing_outside_the_root_is_refused(tmp_path: Path) -> None:
    """The index is a cache, and a cache is not a trust boundary.

    A record's ``path`` is project-relative *by schema*, so a path that escapes
    means the index is wrong — corrupted, hand-edited, or written by an older
    bug. The route re-checks anyway, because "it came from our own index" is
    exactly the assumption that turns one bad row into an arbitrary file read.
    """
    root = h.project(tmp_path)
    secret = tmp_path / "outside.txt"
    secret.write_text("this must never be served", encoding="utf-8")

    from x2knwldg.server.routes.media import _resolve
    from x2knwldg.server.errors import NotFound

    resolved_root = root.resolve()
    for escape in ("../outside.txt", "output/../../outside.txt", str(secret), "/etc/passwd"):
        with pytest.raises(NotFound):
            _resolve(resolved_root, escape)


# --------------------------------------------------------------------------
# 2. No response names a host path
# --------------------------------------------------------------------------


def _every_response(client):
    """One call to each of the eleven endpoints, valid and invalid."""
    yield client.get("/api/status")
    yield client.get("/api/sources")
    yield client.get("/api/sources?limit=0")
    yield client.get("/api/sources/nope")
    yield client.get("/api/sources/nope/entities")
    yield client.get("/api/sources/nope/relations")
    yield client.get("/api/entities/nope")
    yield client.get("/api/artifacts/nope")
    yield client.get("/api/media/nope")
    yield client.get("/api/search?q=knowledge")
    yield client.get("/api/search")
    yield client.get("/api/graph")
    yield client.get("/api/graph?depth=9")
    yield client.get("/api/graph/neighborhood/nope")
    yield client.get("/api/nothing-here")


def test_no_response_body_names_a_host_path(served: Path) -> None:
    """D-051 generalised from the one leak that was caught to every boundary.

    ``AdapterError`` named the directory it refused, absolutely, and that string
    reached ``StatusPayload.runs.skipped[].reason`` the moment D-050 served it.
    It was sanitised where it is *recorded*. This asserts the property the fix
    was for, across every route, so the next such string is caught by a test
    rather than by review.
    """
    home = str(Path.home())
    with h.client(h.memory_repository(served)) as client:
        for response in _every_response(client):
            if not response.headers.get("content-type", "").startswith("application/json"):
                continue
            blob = json.dumps(response.json())
            assert str(served) not in blob, f"a body named the project root: {blob[:400]}"
            assert home not in blob, f"a body named the home directory: {blob[:400]}"
            assert "/Users/" not in blob and "/home/" not in blob, blob[:400]
            assert "Traceback" not in blob, f"a traceback reached a body: {blob[:400]}"


def test_no_response_leaks_a_framework_default_body(served: Path) -> None:
    """Every JSON error is the frozen ``ErrorResponse`` — never ``{"detail": ...}``.

    Starlette's default 404 body and FastAPI's default 422 are both shapes the
    frozen document does not describe. Serving one would teach a client that the
    envelope is optional.
    """
    with h.client(h.memory_repository(served)) as client:
        for response in _every_response(client):
            if response.status_code < 400:
                continue
            body = response.json()
            assert set(body) == {"api_version", "schema_version", "error"}, body
            h.assert_contract("ErrorResponse", body)
        assert client.get("/api/sources?limit=abc").status_code == 400, "a 422 escaped"


# --------------------------------------------------------------------------
# 3. Malformed is not absent
# --------------------------------------------------------------------------


def test_a_malformed_id_and_an_unknown_id_get_different_answers(served: Path) -> None:
    """D-020. Collapsing them is what lets a lookup silently read something else."""
    with h.client(h.memory_repository(served)) as client:
        malformed = client.get("/api/entities/not a global id")
        unknown = client.get("/api/entities/youtube:fixture-pass:KU-999999")
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "invalid_id"
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------
# 4. The surface itself
# --------------------------------------------------------------------------


def test_the_served_surface_is_exactly_the_frozen_one(served: Path) -> None:
    """Eleven paths, all ``GET``. Not ten, and not twelve."""
    from x2knwldg.repository import MemoryRepository
    from x2knwldg.server.app import create_app

    frozen = set(json.loads(h.OPENAPI_PATH.read_text(encoding="utf-8"))["paths"])
    app = create_app(repository=MemoryRepository.from_project(served))
    served_paths = {
        route.path
        for route in app.routes
        if hasattr(route, "path") and route.path.startswith("/api/")
    } - {"/api/openapi.json"}
    assert served_paths == frozen, (
        f"missing: {sorted(frozen - served_paths)}; extra: {sorted(served_paths - frozen)}"
    )


def test_v1_is_read_only(served: Path) -> None:
    """No write reaches any route. ADR 0001 invariant 1, checked over HTTP."""
    with h.client(h.memory_repository(served)) as client:
        for path in ("/api/sources", "/api/status", "/api/graph", "/api/search?q=a"):
            for method in ("post", "put", "patch", "delete"):
                response = getattr(client, method)(path)
                assert response.status_code in (404, 405), f"{method.upper()} {path} was allowed"
