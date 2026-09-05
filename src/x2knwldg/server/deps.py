"""What a request is answered from: one repository, resolved once per app.

The API talks to :class:`~x2knwldg.repository.base.IndexRepository` and to
nothing else. It never reads ``output/`` directly, never opens the SQLite file,
and never imports the adapters — that is the seam ADR 0002 fixes, and it is why
Track B did not have to wait for Track A.

``SqliteRepository`` in production, ``MemoryRepository`` as the test oracle.
They answer the same ten methods with zero page-for-page differences (`T-104`),
so a route written against either is written against both.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from ..repository.base import IndexRepository


def repository(request: Request) -> IndexRepository:
    """The repository this app serves from.

    Held on ``app.state`` rather than resolved per request: opening the index is
    a file operation, and doing it thirteen times a page-load would turn a cache
    into a cost. It also keeps cursors coherent — ``encode_cursor`` signs with a
    per-process key, so tokens are only interchangeable within one process
    anyway.
    """
    return request.app.state.repository


def build_repository(project_root: Path) -> IndexRepository:
    """Open the SQLite index at *project_root*, with FTS5 retrieval wired in.

    Imported here rather than at module scope so that ``x2knwldg.server`` can be
    imported — and its envelope tested — without pulling the index package in.

    An absent index is **not** an error: ``SqliteRepository.open`` returns a
    repository whose ``status()`` reports ``absent`` and whose other methods
    refuse with ``index_unavailable``. That is the honest answer for a project
    that has never been indexed, and the UI needs to be able to say it.
    """
    from ..index.repository import SqliteRepository
    from ..index.search import search_retrieval

    return SqliteRepository.open(Path(project_root), search=search_retrieval)
