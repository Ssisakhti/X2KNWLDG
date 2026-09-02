"""`T-116` — binding, serving, and the two halves of the surface.

`tests/test_ui_scaffold.py` covers the argument refusals and stops at
``UI_NOT_BUILT`` on purpose: nothing there may start a server. This file is the
other half. It binds real sockets on ephemeral ports and builds the real app,
because the properties worth asserting here are the ones a mock cannot have --
that the port in the printed URL is the port the kernel actually gave us, and
that the static mount cannot serve a file outside ``web/dist``.

The socket and asset-location tests are stdlib-only and run everywhere,
including on a bare core install. Only the tests that build the app need the
``ui`` extra, and they skip without it (`T-009`).
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import api_harness as h
from x2knwldg import cli
from x2knwldg.server import serve as ui


# ---------------------------------------------------------------------------
# Locating the built frontend
# ---------------------------------------------------------------------------


def test_a_project_with_no_web_directory_has_no_assets(tmp_path: Path) -> None:
    assert ui.assets_dir(tmp_path) is None


def test_an_empty_dist_directory_is_not_a_built_frontend(tmp_path: Path) -> None:
    """A failed or interrupted `npm run build` leaves a directory behind.

    Serving it would answer the browser with a blank page rather than telling
    the user to build, which is the whole reason `UI_NOT_BUILT` exists.
    """
    (tmp_path / "web" / "dist").mkdir(parents=True)
    assert ui.assets_dir(tmp_path) is None


def test_dist_with_an_index_is_the_built_frontend(tmp_path: Path) -> None:
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    assert ui.assets_dir(tmp_path) == dist


# ---------------------------------------------------------------------------
# The bind happens before the URL exists
# ---------------------------------------------------------------------------


def test_an_omitted_port_is_chosen_by_the_os_and_reported() -> None:
    """`--port` is optional so the OS may pick; the pick is knowable only after.

    This is the whole reason the socket is bound in the CLI rather than handed
    to `uvicorn` as a host/port pair: a URL printed before the bind would name
    port `0`.
    """
    sock, listening = ui.bind("127.0.0.1", None)
    try:
        assert listening.port != 0
        assert listening.port == sock.getsockname()[1]
        assert listening.url == f"http://127.0.0.1:{listening.port}/"
    finally:
        sock.close()


def test_an_explicit_port_is_the_port_bound() -> None:
    probe, chosen = ui.bind("127.0.0.1", None)
    port = chosen.port
    probe.close()

    sock, listening = ui.bind("127.0.0.1", port)
    try:
        assert listening.port == port
    finally:
        sock.close()


def test_a_port_already_in_use_is_refused_rather_than_silently_shared() -> None:
    """``SO_REUSEPORT`` is deliberately not set.

    With it, a second ``x2knwldg ui`` would bind the same port and the kernel
    would split requests between two servers -- a confusing failure rather than
    a convenience. The second bind must raise instead.
    """
    first, listening = ui.bind("127.0.0.1", None)
    try:
        with pytest.raises(OSError):
            ui.bind("127.0.0.1", listening.port)
    finally:
        first.close()


def test_a_failed_bind_leaks_no_socket() -> None:
    first, listening = ui.bind("127.0.0.1", None)
    try:
        with pytest.raises(OSError):
            ui.bind("127.0.0.1", listening.port)
        # The refusal above must have closed its own socket rather than leaving
        # a dangling descriptor; binding once more still fails for the same
        # reason, not for a new one about file descriptors.
        with pytest.raises(OSError):
            ui.bind("127.0.0.1", listening.port)
    finally:
        first.close()


@pytest.mark.parametrize("host", sorted(cli.LOOPBACK_HOSTS))
def test_every_accepted_loopback_host_can_actually_be_bound(host: str) -> None:
    """The three names `cli.LOOPBACK_HOSTS` accepts must resolve and bind.

    ``::1`` needs a different address family from ``127.0.0.1``, and
    ``localhost`` may be either. Hard-coding ``AF_INET`` would have made one of
    the three accepted-but-unusable.
    """
    try:
        sock, listening = ui.bind(host, None)
    except OSError as exc:  # pragma: no cover - IPv6-less machine
        pytest.skip(f"{host} is not bindable here: {exc}")
    try:
        assert listening.port != 0
    finally:
        sock.close()


def test_an_ipv6_url_brackets_the_host() -> None:
    """`http://::1:8000/` is not a URL. A browser would not open it."""
    assert ui.Listening(host="::1", port=8000).url == "http://[::1]:8000/"
    assert ui.Listening(host="127.0.0.1", port=8000).url == "http://127.0.0.1:8000/"


# ---------------------------------------------------------------------------
# The served surface: API beneath, frontend at the root
# ---------------------------------------------------------------------------


@pytest.fixture
def served(tmp_path: Path):
    """A real project with a real (tiny) built frontend, as one app.

    The skip lives here rather than on the module, so the socket and
    asset-location tests above -- which are stdlib-only and are exactly the
    ones that would catch `bind` breaking -- still run on a bare core install.
    """
    pytest.importorskip("fastapi", reason="the API layer is the `ui` extra")
    root = h.project(tmp_path / "p", *h.ALL_FIXTURES)
    dist = root / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>canvas</title>", encoding="utf-8")
    (dist / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    (root / "secret.txt").write_text("not part of the frontend", encoding="utf-8")

    from fastapi.testclient import TestClient

    from x2knwldg.index.scanner import refresh_index

    refresh_index(root)
    app = ui.build_app(root, dist)
    with TestClient(app) as client:
        yield root, client


def test_the_root_serves_the_built_index(served) -> None:
    _root, client = served
    response = client.get("/")
    assert response.status_code == 200
    assert "canvas" in response.text


def test_a_built_asset_is_served(served) -> None:
    _root, client = served
    assert client.get("/app.js").status_code == 200


def test_the_api_is_still_underneath(served) -> None:
    """The static mount is added last, so it catches only what no route claimed.

    Mounting at ``/`` is the one arrangement that could have swallowed the
    eleven endpoints, so it is asserted rather than assumed.
    """
    _root, client = served
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["data"]["index"]["state"] == "ready"
    assert client.get("/api/sources").status_code == 200


def test_the_api_error_taxonomy_survives_the_mount(served) -> None:
    """D-020's distinction must not collapse into the static mount's 404.

    A malformed id is still `400 invalid_id`; the static handler would have
    made it a flat 404 with no code, and the UI could no longer tell a bad
    address from an absent one.
    """
    _root, client = served
    response = client.get("/api/sources/not-an-id")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_id"


def _raw_request(app, raw: str) -> tuple[int, bytes]:
    """Hand *raw* to the ASGI app verbatim, bypassing the client's normaliser.

    The lesson `T-108` recorded, applied to the other half of the surface:
    httpx resolves ``..`` before a request leaves, so ``client.get("/../x")``
    asserts on a path the app never saw and grades the client instead. A
    hand-written HTTP client is under no such obligation, so the escape has to
    be attempted the way one would attempt it.
    """
    import asyncio

    seen: dict[str, object] = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
        elif message["type"] == "http.response.body":
            seen["body"] = seen.get("body", b"") + message.get("body", b"")

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
    return int(seen["status"]), bytes(seen.get("body", b""))


@pytest.mark.parametrize(
    "raw",
    [
        "/../secret.txt",
        "/../../etc/passwd",
        "/./../secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/app.js/../../secret.txt",
        "/....//secret.txt",
    ],
)
def test_the_static_mount_serves_nothing_outside_the_built_frontend(
    served, raw: str, tmp_path: Path
) -> None:
    """Canvas plan section 8.3 step 5, for the assets half of the surface.

    `T-108` enforces the same rule for canonical bytes against the project
    root. Here the boundary is ``web/dist``: ``secret.txt`` sits in the project
    root, which is *outside* it, so reaching it is an escape even though it
    never leaves the project. The raw path goes straight to the ASGI app, so
    what is graded is the mount rather than httpx.
    """
    root, _client = served
    app = ui.build_app(root, root / "web" / "dist")
    status, body = _raw_request(app, raw)
    assert status in {400, 403, 404}, f"{raw} answered {status}"
    assert b"not part of the frontend" not in body
    assert b"root:" not in body


def test_the_traversal_probe_can_actually_reach_the_mount(served) -> None:
    """The battery above, checked -- it must fail for the right reason.

    Every hostile path answering 404 proves nothing if the probe never reaches
    the static mount at all. A benign path through the same code path must come
    back 200, or the assertions above are satisfied by a broken harness.
    """
    root, _client = served
    app = ui.build_app(root, root / "web" / "dist")
    status, body = _raw_request(app, "/app.js")
    assert status == 200, "the probe never reached the mount; the battery proves nothing"
    assert b"export const x" in body


def test_the_frozen_api_document_is_unchanged_by_the_mount(served, tmp_path: Path) -> None:
    """`create_app` is left exactly as Track B froze it.

    The mount is added to the returned app, so the generated document must
    still equal the frozen one -- otherwise
    `test_the_served_surface_is_exactly_the_frozen_one` and this command would
    disagree about what is served.
    """
    _root, client = served
    served_doc = client.get("/api/openapi.json").json()
    frozen = json.loads(h.OPENAPI_PATH.read_text(encoding="utf-8"))
    assert served_doc["paths"].keys() == frozen["paths"].keys()


# ---------------------------------------------------------------------------
# The index the *command* builds is the one the user searches
# ---------------------------------------------------------------------------


def test_the_command_builds_a_searchable_index(tmp_path: Path, monkeypatch) -> None:
    """`/api/search` must answer over the index `x2knwldg ui` actually builds.

    This is a regression test with a story. `refresh_index` takes an optional
    ``index_documents`` hook, and *without* it the scan still produces a
    complete and correct index of sources, artifacts, entities and relations --
    only the ``documents`` table and the FTS5 corpus stay empty. So the UI came
    up, the library listed every source, the reader opened, the counts were
    right, and `/api/search` answered `0` for every query ever typed.

    Nothing in the suite caught it, and the reason is worth keeping: every
    other caller in the tree -- `search.build_searchable_index`, the harness,
    the equivalence tests -- passes ``index_documents=document_indexer(root)``
    itself. They prove the indexer works. None of them could prove the *CLI*
    asks for it. This test goes through `cli.main` for exactly that reason.
    """
    pytest.importorskip("fastapi", reason="the API layer is the `ui` extra")

    from fastapi.testclient import TestClient

    from x2knwldg.server.deps import build_repository

    root = h.project(tmp_path / "p", *h.ALL_FIXTURES)
    dist = root / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")

    # Serve is replaced by a no-op that closes the socket the command bound,
    # so the command runs to completion instead of serving the test suite.
    served: dict[str, object] = {}

    def capture(*, project_root, assets, sock, listening, open_browser):
        served["listening"] = listening
        sock.close()

    monkeypatch.setattr(ui, "serve", capture)
    monkeypatch.setattr(cli, "_missing_ui_dependencies", lambda: [])
    assert cli.main(["ui", "--root", str(root), "--no-open"]) == cli.EXIT_OK
    assert served, "the command never reached the serving step"

    repository = build_repository(root)
    try:
        from x2knwldg.server.app import create_app

        with TestClient(create_app(repository=repository)) as client:
            response = client.get("/api/search", params={"q": "evidence"})
            assert response.status_code == 200
            body = response.json()
            assert body["page"]["total"] > 0, (
                "the command built an index whose search corpus is empty; "
                "`refresh_index` was called without `index_documents`"
            )
            assert body["data"], body
    finally:
        close = getattr(repository, "close", None)
        if close is not None:
            close()
