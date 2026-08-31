"""The index repository — the Track A ↔ Track B seam (``T-007``).

The API asks a repository for pages of v1 records; the indexer answers. Neither
knows anything else about the other.

    from pathlib import Path
    from x2knwldg.repository import MemoryRepository, SourceQuery

    repo = MemoryRepository.from_project(Path.cwd())
    page = repo.list_sources(SourceQuery(limit=20, status="PASS"))
    page.items        # Source records, exactly as the adapters produce them
    page.page_info()  # {"limit": 20, "next_cursor": ..., "total": ...}

:mod:`base` holds the contract — the queries, the results, the error taxonomy of
D-030, and the shared cursor encoding. :mod:`memory` holds the reference
implementation over ``adapters.adapt_project``. ``T-101``–``T-104`` add a SQLite
implementation beside it; ``T-105``–``T-108`` call the interface and neither
know nor care which one is behind it.
"""

from __future__ import annotations

from .base import (
    DEFAULT_LIMIT,
    ENTITY_KINDS,
    FILTERABLE_STATUSES,
    INDEX_STATES,
    MAX_CURSOR_LENGTH,
    MAX_DEPTH,
    MAX_LIMIT,
    MAX_QUERY_LENGTH,
    MIN_DEPTH,
    MIN_LIMIT,
    ORDER_KEYS,
    PROVENANCE_CLASSES,
    READY,
    RELATION_VOCABULARIES,
    EntityQuery,
    GraphPage,
    GraphQuery,
    IndexRepository,
    IndexStatus,
    IndexUnavailable,
    InvalidId,
    InvalidQuery,
    Neighborhood,
    NeighborhoodQuery,
    Page,
    PagedQuery,
    RelationQuery,
    RepositoryError,
    SearchQuery,
    SourceDetail,
    SourceQuery,
    decode_cursor,
    encode_cursor,
    entity_belongs_to_source,
    keyset_page,
    matches_entity,
    matches_relation,
    matches_source,
    order_key,
    query_fingerprint,
    record_copy,
    relation_belongs_to_source,
    sort_records,
)
from .memory import MemoryRepository

__all__ = [
    "DEFAULT_LIMIT",
    "ENTITY_KINDS",
    "FILTERABLE_STATUSES",
    "INDEX_STATES",
    "MAX_CURSOR_LENGTH",
    "MAX_DEPTH",
    "MAX_LIMIT",
    "MAX_QUERY_LENGTH",
    "MIN_DEPTH",
    "MIN_LIMIT",
    "ORDER_KEYS",
    "PROVENANCE_CLASSES",
    "READY",
    "RELATION_VOCABULARIES",
    "EntityQuery",
    "GraphPage",
    "GraphQuery",
    "IndexRepository",
    "IndexStatus",
    "IndexUnavailable",
    "InvalidId",
    "InvalidQuery",
    "MemoryRepository",
    "Neighborhood",
    "NeighborhoodQuery",
    "Page",
    "PagedQuery",
    "RelationQuery",
    "RepositoryError",
    "SearchQuery",
    "SourceDetail",
    "SourceQuery",
    "decode_cursor",
    "encode_cursor",
    "entity_belongs_to_source",
    "keyset_page",
    "matches_entity",
    "matches_relation",
    "matches_source",
    "order_key",
    "query_fingerprint",
    "record_copy",
    "relation_belongs_to_source",
    "sort_records",
]
