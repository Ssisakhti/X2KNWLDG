#!/usr/bin/env python
"""Serve the real API for frontend development.

Track C develops against the **real** server rather than a mock. A mock agrees
with whatever the frontend assumed; ``create_app(project_root=...)`` disagrees,
and disagreeing is the whole value of an oracle. `T-104` proved the two
repository implementations answer identically, so a page written against this
server is written against both.

Two modes:

* ``--fixtures`` (the default) copies the committed ``PASS`` / ``PARTIAL`` /
  ``FAIL`` run fixtures into a scratch project outside the repository, builds
  the SQLite index over it, and serves that. Nothing under ``output/`` or
  ``tests/`` is written, and the fixtures themselves are copied rather than
  edited in place because a run's ``raw/`` is immutable evidence.
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
import shutil
import sys
import tempfile
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
PROJECT = WEB.parent
FIXTURES = PROJECT / "tests" / "fixtures" / "runs"
FIXTURE_RUNS = ("pass-run", "partial-run", "fail-run")

sys.path.insert(0, str(PROJECT / "src"))


def build_fixture_project(destination: Path) -> Path:
    """A scratch project holding copies of the committed run fixtures."""
    from x2knwldg.library import rebuild_library

    if destination.exists():
        shutil.rmtree(destination)
    output = destination / "output"
    output.mkdir(parents=True)
    for name in FIXTURE_RUNS:
        shutil.copytree(FIXTURES / name, output / name)
    rebuild_library(output)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8931)
    parser.add_argument("--no-index", action="store_true")
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("this development server binds loopback only")

    if args.project_root is None:
        root = build_fixture_project(Path(tempfile.gettempdir()) / "x2knwldg-web-dev")
        print(f"serving the committed run fixtures from {root}")
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

    print(f"http://{args.host}:{args.port}/api/status")
    uvicorn.run(create_app(project_root=root), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
