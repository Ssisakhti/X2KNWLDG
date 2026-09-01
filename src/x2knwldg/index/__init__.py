"""The SQLite index: ``T-101``–``T-104``, behind ``repository.IndexRepository``.

The index is a **rebuildable cache** and nothing else. Canvas plan §5 invariant
5 and ADR 0001 invariant 3 both say it: nothing may exist only here, and
deleting the cache directory must lose no evidence, no canonical knowledge and
no user content. Every number this package reports is reproducible from the
canonical files, so a stale count is a bug rather than an achievement.

Layout, one responsibility each:

* :mod:`~x2knwldg.index.errors` — what the store refuses, in the frozen taxonomy.
* :mod:`~x2knwldg.index.schema` — the DDL and the versioned migrations. The only
  module that writes ``CREATE``.
* :mod:`~x2knwldg.index.scanner` — discovery, per-run digests, incremental
  change detection, and the build lifecycle. The only module that writes rows.
* :mod:`~x2knwldg.index.search` — the FTS5 candidate retrieval behind
  ``query.rank_documents``.
* :mod:`~x2knwldg.index.repository` — ``SqliteRepository``, the ten protocol
  methods. Writes nothing at all (ADR 0002 invariant 2).

Stdlib only: ``sqlite3`` ships with Python, so this package runs on a bare core
install and its tests run in the zero-dependency CI job (ADR 0001 invariant 5).
"""

from __future__ import annotations

from .errors import Fts5Unavailable, IndexCorrupt, SchemaTooNew, StoreError
from .repository import SearchCandidates, SqliteRepository
from .scanner import ScanReport, build_index, refresh_index
from .schema import (
    DATABASE_DIRNAME,
    DATABASE_FILENAME,
    MIGRATIONS,
    SCHEMA_VERSION,
    connect,
    database_path,
    has_fts5,
    migrate,
    require_fts5,
    schema_version,
)
from .search import (
    HIT_TYPES,
    KNOWLEDGE_UNIT_HIT,
    TRANSCRIPT_CAPTION_HIT,
    Candidates,
    IndexReport,
    as_api_hit,
    clear_source_documents,
    document_indexer,
    index_documents,
    search_candidates,
    search_retrieval,
    unreadable_sources,
)

__all__ = [
    "DATABASE_DIRNAME",
    "DATABASE_FILENAME",
    "HIT_TYPES",
    "KNOWLEDGE_UNIT_HIT",
    "MIGRATIONS",
    "SCHEMA_VERSION",
    "TRANSCRIPT_CAPTION_HIT",
    "Candidates",
    "Fts5Unavailable",
    "IndexCorrupt",
    "IndexReport",
    "ScanReport",
    "SchemaTooNew",
    "SearchCandidates",
    "SqliteRepository",
    "StoreError",
    "as_api_hit",
    "build_index",
    "clear_source_documents",
    "connect",
    "database_path",
    "document_indexer",
    "has_fts5",
    "index_documents",
    "migrate",
    "refresh_index",
    "require_fts5",
    "schema_version",
    "search_candidates",
    "search_retrieval",
    "unreadable_sources",
]
