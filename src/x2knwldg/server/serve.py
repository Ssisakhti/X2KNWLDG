"""Bind, serve, and open the local Knowledge Canvas (`T-116`).

This module exists inside ``server/`` rather than in ``cli.py`` because of
D-055: nothing outside this package may import the ``ui`` extra, and serving
needs ``uvicorn`` and ``starlette``. ``cli.py`` reaches this lazily, inside its
own dispatch branch, so a bare core install still imports the CLI without the
framework present.

The three steps of canvas plan section 8.3 that `T-008` could not do -- run the
service on loopback, open the browser, and expose nothing outside the project
root -- are here. The two it could, resolving the root and refusing a
non-loopback bind, stay in ``cli.py`` where the refusals already were.

**The socket is bound before anything is printed or opened.** ``--port`` is
optional precisely so the OS can choose a free one, and a port chosen at bind
time is not knowable in advance; binding first is also what makes "never print
a URL it is not listening on" true rather than intended. A port already in use
therefore fails as a refusal, before a browser opens on a URL nothing answers.
"""

from __future__ import annotations

import socket
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Where `npm run build` writes, relative to the project root. Not configurable:
#: `web/` is one directory in one repository, and a flag for it would be a
#: second place the layout is stated.
ASSETS_SUBPATH = ("web", "dist")

#: The file whose presence means the frontend was actually built. A `web/dist/`
#: left behind by a failed or interrupted build can exist and be useless, and an
#: empty directory served as a UI is a blank page rather than an error.
ASSETS_ENTRY = "index.html"


@dataclass(frozen=True)
class Listening:
    """Where the server is actually bound, once it is."""

    host: str
    port: int

    @property
    def url(self) -> str:
        # A bare IPv6 address needs brackets in a URL, and `::1` is one of the
        # three accepted loopback hosts.
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/"


def assets_dir(project_root: Path) -> Path | None:
    """The built frontend under *project_root*, or ``None`` if it is not built.

    Returning ``None`` rather than raising: "the UI has not been built" is a
    *next step* for the caller to report with its own exit code, not an error
    in the sense that a corrupt canonical file is one.
    """
    candidate = Path(project_root).joinpath(*ASSETS_SUBPATH)
    return candidate if (candidate / ASSETS_ENTRY).is_file() else None


def bind(host: str, port: int | None) -> tuple[socket.socket, Listening]:
    """A listening socket on *host*, and the address it actually reached.

    The caller has already refused a non-loopback *host* (ADR 0001 invariant 9);
    this resolves it rather than re-deciding it. ``getaddrinfo`` is what makes
    ``localhost`` and ``::1`` work without a hard-coded family: `localhost`
    resolves to whichever of IPv4/IPv6 this machine actually has.

    ``SO_REUSEADDR`` is set so a restart does not have to wait out `TIME_WAIT`.
    ``SO_REUSEPORT`` is deliberately **not** set: it would let a second
    ``x2knwldg ui`` bind the same port silently and split requests between two
    servers, which is a confusing failure rather than a convenience.
    """
    candidates = socket.getaddrinfo(
        host, port or 0, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )
    if not candidates:  # pragma: no cover - getaddrinfo raises instead
        raise OSError(f"could not resolve {host!r}")
    family, socktype, proto, _canonname, sockaddr = candidates[0]
    sock = socket.socket(family, socktype, proto)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(sockaddr)
        sock.listen(128)
    except OSError:
        sock.close()
        raise
    bound_host, bound_port = sock.getsockname()[:2]
    return sock, Listening(host=bound_host, port=bound_port)


def build_app(
    project_root: Path, assets: Path, *, allowed_hosts: Sequence[str] | None = None
) -> Any:
    """The API, with the built frontend mounted beneath it.

    ``create_app`` is left exactly as Track B froze it -- the mount happens
    *after*, on the returned app, so the generated OpenAPI document is
    unchanged and `test_the_served_surface_is_exactly_the_frozen_one` still
    compares like with like.

    Order matters: the thirteen ``/api`` routes are registered by ``create_app``
    and the static mount is added last, so it can only ever catch what no API
    route claimed. ``html=True`` serves ``index.html`` for the root, which is
    all the frontend needs -- D-060 chose hash routing precisely so no
    SPA-fallback rewrite rule is required here.

    ``StaticFiles`` resolves every request against *assets* and refuses to
    escape it, which is canvas plan section 8.3 step 5 for this half of the
    surface; the byte channel enforces the same rule for canonical files
    against the project root (`T-108`).

    *allowed_hosts* is forwarded rather than dropped. ``create_app``'s own
    comment said the parameter exists "because ``serve.py`` knows what it
    bound", and ``serve.py`` did not pass it: every caller in the program took
    the default, so the D-103 allowlist was a constant with a parameter drawn
    around it. ``None`` still means the loopback set, so nothing changes for a
    caller that has nothing to add -- `test_ui_serving` is one.
    """
    from fastapi.staticfiles import StaticFiles

    from .app import create_app

    app = create_app(project_root=Path(project_root), allowed_hosts=allowed_hosts)
    app.mount("/", StaticFiles(directory=str(assets), html=True), name="ui")
    return app


def serve(
    *,
    project_root: Path,
    assets: Path,
    sock: socket.socket,
    listening: Listening,
    open_browser: bool,
) -> None:
    """Serve until interrupted, on an already-bound *sock*.

    The socket arrives bound and listening, so the browser can be opened before
    ``uvicorn`` starts without racing it: the connection queues in the kernel
    and is accepted as soon as the loop runs. That avoids a background thread
    whose only job would be to guess when the server is ready.

    **The address it actually bound is in the D-103 allowlist**, which is the
    wiring ``app.create_app``'s comment described and nobody had written. The
    loopback names stay in it beside that address, and both halves are load
    bearing:

    * ``bind()`` resolves the *name* the user typed, so ``--host localhost``
      produces ``Listening(host='127.0.0.1')`` or ``'::1'`` depending on what
      ``getaddrinfo`` returns first. An allowlist of the bound address alone
      would answer ``400`` to ``http://localhost:8931/`` -- the URL the user
      asked for -- which is D-172's failure with a different cause.
    * The bound address is added because it is the one fact only this function
      has. Today ``cli.py`` refuses every non-loopback ``--host``, so the union
      is the loopback set; if that refusal is ever relaxed for a LAN address,
      the allowlist widens with the bind instead of silently refusing it.
    """
    import uvicorn

    from .app import LOOPBACK_HOST_NAMES

    app = build_app(
        project_root, assets, allowed_hosts=[listening.host, *LOOPBACK_HOST_NAMES]
    )
    config = uvicorn.Config(app, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    if open_browser:
        # A failure here must not take the server down with it: a headless
        # machine has no browser to open, and that is not a reason to refuse to
        # serve. The URL has already been printed, so the user can open it.
        try:
            webbrowser.open(listening.url)
        except Exception:  # pragma: no cover - platform dependent
            pass
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
