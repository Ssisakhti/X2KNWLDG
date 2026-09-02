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

import api_harness as h
import pytest

pytestmark = [h.requires_fastapi]


#: Ids a client can actually put on the wire, each a real technique rather than
#: a variation on one: percent- and double-percent-encoded traversal, an
#: absolute path, a Windows path, a scheme, an encoded NUL, and length.
#:
#: Raw ``..`` and raw control bytes are **not** here, and that is a statement
#: about httpx rather than about the server: it resolves dot-segments and
#: rejects control characters before a request is made, so a test that sent
#: them would be testing the client. They are covered against the real boundary
#: by :func:`test_a_raw_hostile_id_is_refused_at_the_boundary` below, and their
#: encoded forms — which *do* reach the server — are here.
WIRE_HOSTILE_IDS = [
    "..%2f..%2fetc%2fpasswd",
    "..%252f..%252fetc%252fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "%2e%2e/%2e%2e/etc/passwd",
    "....//....//etc/passwd",
    "%2Fetc%2Fpasswd",
    "C:\\Windows\\System32\\config\\SAM",
    "..\\..\\windows\\win.ini",
    "youtube:%2e%2e%2f%2e%2e:passwd",
    "youtube:pass-run:%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "%00",
    "%2e",
    "youtube:pass%00run:metadata",
    "youtube:pass%0arun:metadata",
    "file:%2f%2f%2fetc%2fpasswd",
    "a" * 4096,
    " ",
    "~",
    "~%2f.ssh%2fid_rsa",
    "$HOME",
]

#: Ids that never survive a URL parser, checked one layer in — at the repository
#: boundary, which is where they would arrive if any client did send them.
RAW_HOSTILE_IDS = [
    "..",
    "../../etc/passwd",
    "/etc/passwd",
    "\x00",
    "youtube:pass\x00run:metadata",
    "youtube:pass\nrun:metadata",
    "",
    "..\\..\\windows\\win.ini",
    "a" * 4096,
]

#: Every route that takes an id in its path.
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
@pytest.mark.parametrize("hostile", WIRE_HOSTILE_IDS)
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


@pytest.mark.parametrize("hostile", WIRE_HOSTILE_IDS)
def test_no_hostile_id_ever_returns_file_bytes(served: Path, hostile: str) -> None:
    """The byte channel specifically: nothing outside the project is ever served."""
    with h.client(h.memory_repository(served)) as client:
        response = client.get(f"/api/media/{hostile}")
        assert response.status_code != 200, f"{hostile!r} was served bytes"
        assert b"root:" not in response.content, "a passwd file was served"
        assert b"PRIVATE KEY" not in response.content


@pytest.mark.parametrize("hostile", RAW_HOSTILE_IDS)
def test_a_raw_hostile_id_is_refused_at_the_boundary(served: Path, hostile: str) -> None:
    """The ids a URL parser eats, checked where they would actually land.

    httpx resolves ``..`` and rejects control bytes client-side, so these never
    reach the app over HTTP from *this* client — but "our test client cannot
    express it" is not a security property. The repository is the boundary every
    id crosses, so the refusal is asserted there directly: malformed in, refused
    out, and never a lookup.
    """
    from x2knwldg.repository.base import RepositoryError

    repo = h.memory_repository(served)
    for lookup in (repo.get_entity, repo.get_artifact):
        try:
            result = lookup(hostile)
        except RepositoryError as exc:
            assert exc.code in ("invalid_id", "invalid_request"), exc.code
            assert exc.http_status == 400
        else:
            assert result is None, f"{hostile!r} resolved to {result!r}"


def test_a_dot_segment_is_never_resolved_by_the_server(served: Path) -> None:
    """``..`` must not traverse — checked without letting the client rewrite it.

    httpx normalises ``/api/media/..`` to ``/api`` before sending, so asserting
    on the response would grade the client. The raw path is handed to the ASGI
    app directly instead, which is what a hand-written HTTP client could do.
    """
    from x2knwldg.repository import MemoryRepository
    from x2knwldg.server.app import create_app

    app = create_app(repository=MemoryRepository.from_project(served))
    seen: dict[str, object] = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
        elif message["type"] == "http.response.body":
            seen["body"] = seen.get("body", b"") + message.get("body", b"")

    import asyncio

    for raw in ("/api/media/../../etc/passwd", "/api/entities/..", "/api/media/.."):
        seen.clear()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": raw,
            "raw_path": raw.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        asyncio.run(app(scope, receive, send))
        assert seen["status"] in (400, 404, 405), f"{raw} answered {seen['status']}"
        assert b"root:" not in seen.get("body", b"")


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

    from x2knwldg.server.errors import NotFound
    from x2knwldg.server.routes.media import _resolve

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
# 4. The repository survives being answered from a thread pool
# --------------------------------------------------------------------------


@h.requires_fts5
def test_the_sqlite_reader_answers_from_other_threads(tmp_path: Path) -> None:
    """A server answers from a thread pool, so the reader must tolerate one.

    ``sqlite3`` binds a connection to its creating thread by default. Starlette
    runs sync endpoints in a worker thread, so a repository opened during app
    construction answered *every* request with
    ``503 index_unavailable: SQLite objects created in a thread can only be
    used in that same thread`` — in production under uvicorn, not only under a
    test client. The reader is now opened with the check lifted and every method
    serialised by a lock.

    Asserted with real threads rather than through the client, because the
    client is what hid it: a failure here names the cause, and a 503 in a route
    test names only the symptom.
    """
    import threading

    from x2knwldg.repository import SourceQuery

    repo = h.sqlite_repository(h.project(tmp_path))
    try:
        results: list[object] = []
        errors: list[str] = []

        def ask() -> None:
            try:
                results.append(len(repo.list_sources(SourceQuery()).items))
            except Exception as exc:  # noqa: BLE001 - the failure text is the point
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=ask) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == [], errors
        assert len(results) == 8
        assert len(set(results)) == 1, f"threads disagreed about the library: {results}"
    finally:
        repo.close()


def test_every_endpoint_answers_over_sqlite_not_only_over_memory(tmp_path: Path) -> None:
    """The whole surface, served by the implementation the UI will actually use.

    The thread bug made every SQLite-backed request a 503 while every
    memory-backed one passed, so a suite that reached for the oracle by default
    stayed green with the real server broken. This asks each endpoint for a
    non-503 over SQLite.
    """
    root = h.project(tmp_path)
    with h.client(h.sqlite_repository(root)) as client:
        for response in _every_response(client):
            if response.status_code != 503:
                continue
            body = response.json()
            assert body["error"]["code"] == "index_unavailable"
            pytest.fail(f"an endpoint 503'd over SQLite: {body}")


# --------------------------------------------------------------------------
# 5. The surface itself
# --------------------------------------------------------------------------


def test_the_served_surface_is_exactly_the_frozen_one(served: Path) -> None:
    """Eleven paths, all ``GET``. Not ten, and not twelve."""
    from x2knwldg.repository import MemoryRepository
    from x2knwldg.server.app import create_app

    frozen = set(json.loads(h.OPENAPI_PATH.read_text(encoding="utf-8"))["paths"])
    app = create_app(repository=MemoryRepository.from_project(served))

    # Read from the schema FastAPI generates, not by walking `app.routes`:
    # this version wraps an included router in an `_IncludedRouter` that
    # carries no `.path`, so walking the list found nothing and the test
    # passed vacuously in the direction that mattered — it would have reported
    # every endpoint missing, or, with a laxer assertion, missed a stray one.
    # The generated document is also the right thing to compare: it is what the
    # app says it serves.
    served_paths = set(app.openapi()["paths"])
    assert served_paths == frozen, (
        f"missing: {sorted(frozen - served_paths)}; extra: {sorted(served_paths - frozen)}"
    )


def test_an_empty_id_is_refused_rather_than_serving_the_collection(served: Path) -> None:
    """``/api/sources/`` must not answer with every source.

    Starlette redirects a trailing slash to the collection by default, so a
    request naming *no* source was served *all* of them — the failure mode is a
    200 with real data, which no status-code assertion elsewhere would catch.
    ``/api/sources`` is the only prefix here that is both a collection and the
    parent of item paths, which is why it is the only one that was wrong.
    """
    with h.client(h.memory_repository(served)) as client:
        for path in ("/api/sources/", "/api/entities/", "/api/artifacts/", "/api/media/"):
            response = client.get(path)
            assert response.status_code == 404, f"{path} answered {response.status_code}"
            assert "data" not in response.json()
        assert client.get("/api/sources").status_code == 200


def test_v1_is_read_only(served: Path) -> None:
    """No write reaches any route. ADR 0001 invariant 1, checked over HTTP."""
    with h.client(h.memory_repository(served)) as client:
        for path in ("/api/sources", "/api/status", "/api/graph", "/api/search?q=a"):
            for method in ("post", "put", "patch", "delete"):
                response = getattr(client, method)(path)
                assert response.status_code in (404, 405), f"{method.upper()} {path} was allowed"


# --------------------------------------------------------------------------
# D-103 — the Host header is checked
# --------------------------------------------------------------------------
#
# There was no validation at all. The bind is correctly loopback-only (ADR 0001
# invariant 9) and there is no CORS middleware, so a page on another origin
# cannot *read* a reply — but DNS rebinding does not need CORS: a name the
# attacker controls, resolved to 127.0.0.1, makes their page **same-origin**
# with this server, and every route is a readable `GET` over the whole
# knowledge base. Binding to loopback stops other machines, not other origins
# on this one.


@pytest.mark.parametrize(
    "host", ["evil.example.com", "rebind.attacker.test", "x2knwldg.attacker.test:8931"]
)
def test_a_rebound_name_is_refused(tmp_path: Path, host: str) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        response = client.get("/api/status", headers={"Host": host})
        assert response.status_code == 400, response.status_code
        # D-172: the status code was the whole of this assertion, so
        # `assert_error`'s contract check never ran on this path — and the
        # refusal came from `TrustedHostMiddleware`, which sits outside the
        # exception handlers and answered `text/plain "Invalid host header"`.
        h.assert_error(response, 400, "invalid_request")


@pytest.mark.parametrize(
    "host",
    ["[::1]", "[::1]:8931", "::1", "[::1]:80"],
    ids=repr,
)
def test_an_ipv6_loopback_name_is_answered(tmp_path: Path, host: str) -> None:
    """D-172: two of the three documented `--host` values answered nothing.

    Starlette's `TrustedHostMiddleware` does
    `headers.get("host", "").split(":")[0]`, so `Host: [::1]:8931` became `'['`.
    The allowlist entries `"[::1]"` and `"::1"` were unreachable dead code and
    every request to an IPv6-bound server was `400` — including the UI root, at
    the exact URL `serve.py` prints and opens in the browser. `localhost` is one
    of the two, because `getaddrinfo(..., AI_PASSIVE)` returns `AF_INET6` first
    on macOS.
    """
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        response = client.get("/api/status", headers={"Host": host})
        assert response.status_code == 200, response.text


def test_the_host_parser_keeps_the_address_and_drops_the_port() -> None:
    from x2knwldg.server.app import host_name

    assert host_name("127.0.0.1:8931") == "127.0.0.1"
    assert host_name("localhost") == "localhost"
    assert host_name("[::1]:8931") == "[::1]"
    assert host_name("[fe80::1]:80") == "[fe80::1]"
    assert host_name("::1") == "::1", "unbracketed, but it is still the address"
    assert host_name("") == ""


def test_every_endpoint_declares_the_statuses_the_host_check_can_produce() -> None:
    """The refusal reaches every path, `/api/status` included."""
    spec = json.loads(h.OPENAPI_PATH.read_text(encoding="utf-8"))
    for path, operations in spec["paths"].items():
        for verb, operation in operations.items():
            declared = set(operation["responses"])
            assert "400" in declared, f"{verb.upper()} {path}"
            assert "500" in declared, f"{verb.upper()} {path}"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.0.0.1:8931", "localhost:8931"])
def test_every_loopback_name_the_cli_accepts_is_answered(tmp_path: Path, host: str) -> None:
    """The allowlist must not refuse the hosts `x2knwldg ui` can bind."""
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        response = client.get("/api/status", headers={"Host": host})
        assert response.status_code == 200, (host, response.status_code)


def test_the_allowlist_is_never_a_wildcard(tmp_path: Path) -> None:
    """A `*` would install the middleware and answer nothing with it."""
    from x2knwldg.server.app import LOOPBACK_HOST_NAMES

    assert "*" not in LOOPBACK_HOST_NAMES
    assert set(LOOPBACK_HOST_NAMES) >= {"localhost", "127.0.0.1"}


def test_the_refusal_happens_before_a_route_reads_the_index(tmp_path: Path) -> None:
    """Installed before the routers, so nothing is looked up for a bad Host."""
    root = h.project(tmp_path)
    repository = h.memory_repository(root)
    with h.client(repository) as client:
        for path in ("/api/status", "/api/sources", "/api/search?q=x", "/api/openapi.json"):
            response = client.get(path, headers={"Host": "evil.example.com"})
            assert response.status_code == 400, (path, response.status_code)
