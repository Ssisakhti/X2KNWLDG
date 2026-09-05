#!/usr/bin/env python
"""Serve the real API for frontend development.

Track C develops against the **real** server rather than a mock. A mock agrees
with whatever the frontend assumed; ``create_app(project_root=...)`` disagrees,
and disagreeing is the whole value of an oracle. `T-104` proved the two
repository implementations answer identically, so a page written against this
server is written against both.

Two modes:

* ``--fixtures`` (the default) copies committed run fixtures into a scratch
  project outside the repository, builds the SQLite index over it, and serves
  that. Nothing under ``output/`` or ``tests/`` is written, and the fixtures
  themselves are copied rather than edited in place because a run's ``raw/`` is
  immutable evidence.

  The set it copies is ``tests/source_map_corpus.py``'s, and that is a `T-257`
  decision rather than an accident (D-281). The browser gate walks **two** Maps
  over one served library now, and the Source Map's three record families -- a
  source node, a readable brief, an accepted cross-source relation -- exist in
  no smaller committed set: over the three ``PASS``/``PARTIAL``/``FAIL`` runs
  alone, ``/api/source-graph`` answers three nodes, no brief and no relation, so
  every Source Map clause the gate exists to check would have nothing to walk.
  The corpus is a strict superset of those three runs plus one Twitter run, and
  it is *built from the committed runs' own bytes* -- real unit ids, real
  digests -- rather than written here.

  What that costs is stated rather than left implied. The Knowledge Map's
  forty-seven scenarios now walk a library one run larger than the one `T-209`
  recorded. They pass unchanged, because every number they assert on is read
  back out of the payload the page was answered with rather than typed into a
  test -- which is the property ``gate.ts`` was written for, and, over a library
  that now carries briefs and source relations, is also the browser end of
  D-249: the source layer reached the server without moving anything the
  Knowledge Map draws.
* ``--project-root PATH`` serves an existing project, so the UI can be
  developed against real ingested sources.

``--no-index`` skips the build, which is how the ``absent`` index state --
``503 index_unavailable`` on every endpoint but ``/api/status`` -- is reached
deliberately. A UI that cannot tell an unbuilt index from an empty library is
broken in exactly the way D-030 added that code to prevent, so it must be easy
to look at.

This binds loopback only (ADR 0001 invariant 9) and is a development tool: the
shipped command is ``x2knwldg ui`` (`T-116`).
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
PROJECT = WEB.parent

sys.path.insert(0, str(PROJECT / "src"))
# ``tests/`` is on the path for ``source_map_corpus`` alone, which is where the
# five-record-family fixture project is already defined and generated from the
# committed runs' own bytes. Copying its ``LAYOUT`` into this script would be a
# second corpus that can drift from the one every Python test asserts against.
sys.path.insert(0, str(PROJECT / "tests"))


def _scratch_root() -> Path:
    """A scratch project directory this user owns.

    ``Path(tempfile.gettempdir()) / "x2knwldg-web-dev"`` is a predictable path
    in a world-writable directory, and the caller ``rmtree``s it before use.
    ``mkdtemp`` inside a per-user parent gives the same convenience — one
    place to look, reused across runs by the newest-first search below —
    without a name another user can occupy first.
    """
    parent = Path(tempfile.gettempdir()) / f"x2knwldg-web-dev-{os.getuid()}"
    parent.mkdir(mode=0o700, exist_ok=True)
    if parent.owner() != getpass.getuser():  # pragma: no cover - hostile host
        raise SystemExit(f"{parent} is not owned by this user; refusing to use it")
    return parent / "project"


def build_fixture_project(destination: Path) -> Path:
    """A scratch project holding copies of the committed run fixtures.

    All five record families, because the gate walks two Maps: four runs across
    both media, three gated briefs, one accepted cross-source relation, and one
    run with no brief at all -- which is the ``unavailable`` state and a normal
    condition rather than a shortfall.
    """
    import source_map_corpus

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    source_map_corpus.build(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # D-186: `--fixtures` is named in this module's own docstring, in
    # `web/src/map/README.md` as a copy-pasteable command, and in a CI comment —
    # and argparse had never heard of it, so every one of those exited `2`. It
    # is the explicit spelling of the default, and mutually exclusive with
    # `--project-root` so "serve the fixtures *and* this project" is refused
    # rather than silently resolved one way.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixtures", action="store_true")
    mode.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8931)
    parser.add_argument("--no-index", action="store_true")
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("this development server binds loopback only")

    if args.project_root is None:
        # A per-user scratch root, not a fixed `/tmp/x2knwldg-web-dev`. The
        # fixed name is predictable and `build_fixture_project` starts by
        # `rmtree`-ing it, so on a shared machine another user could
        # pre-create it — or be handed it. `mkdtemp` under a per-user parent
        # keeps the path stable enough to find and owned by whoever ran this.
        root = build_fixture_project(_scratch_root())
        print(f"serving the committed source-map fixture corpus from {root}")
    else:
        root = args.project_root.expanduser().resolve()
        print(f"serving {root}")

    import uvicorn

    from x2knwldg.server.app import create_app

    if not args.no_index:
        from x2knwldg.index.scanner import build_index
        from x2knwldg.index.search import document_indexer

        build_index(root, index_documents=document_indexer(root))
    else:
        print("no index built: every endpoint but /api/status will answer 503 index_unavailable")

    # `serve.Listening.url` is the project's one statement of this rule; a
    # second copy printed `http://::1:8931/api/status`, which no browser can
    # parse. Reused rather than restated.
    from x2knwldg.server.serve import Listening

    listening = Listening(host=args.host, port=args.port)
    print(f"{listening.url.rstrip('/')}/api/status")
    uvicorn.run(create_app(project_root=root), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
