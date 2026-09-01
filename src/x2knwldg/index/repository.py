"""``SqliteRepository`` — the frozen seam, answered from the SQLite index (``T-101``).

:class:`~x2knwldg.repository.base.IndexRepository` has ten methods and eleven
endpoints, and this module implements exactly those ten. ADR 0002 invariant 3:
no implementation widens the interface. An endpoint that needs something the
protocol cannot express is a contract change first and a method here second.

Everything below follows from five commitments, and each one closes a defect
that would otherwise be invisible until it had already produced a wrong answer.

**This class is a reader.** ADR 0002 invariant 2. It never writes a canonical
file, never recomputes a status, never supplies a value the canonical files
lack — and never writes to the database at all, not even a cached count or a
touched timestamp. ``status()`` reports what the store *says*; a stale number is
the scanner's bug to fix, not this module's to paper over. Nothing here creates
a database either: :meth:`SqliteRepository.open` on a project with no index
returns a repository that reports ``absent`` honestly rather than an empty index
that claims to be built (D-030).

**The Python predicates are the filters; the columns only narrow.** ADR 0002
invariant 5, verbatim: ``matches_entity``, ``matches_relation``,
``matches_source`` and ``relation_belongs_to_source`` "are the definition of
each filter. Where a SQL ``WHERE`` clause disagrees with them, they are right."
So every row this module hands out has been through the seam's own predicate,
and the extracted columns of :mod:`~x2knwldg.index.schema` are confined to two
places that only ever *widen* a candidate set: :func:`_narrow`, and the
``from_id`` / ``to_id`` seek a neighborhood walks. ``min_confidence`` is the sharp case and it is sharp in *both*
directions: ``matches_entity`` fails a missing or non-numeric confidence on
purpose ("a unit that states no confidence is not confident enough"), while a
bare ``WHERE confidence >= 0.5`` drops a ``NULL`` silently and — because a
non-numeric value lands in a ``REAL`` column with TEXT affinity, and SQLite
sorts TEXT above every number — *returns* a row whose confidence is the string
``"high"``. Neither answer is the seam's. There is therefore no narrowing on
``confidence`` at all, and none on a relation's ``source_id`` either: that
filter is a disjunction over two endpoint prefixes (D-034/D-041), and the
schema's own comment says the disjunction stays in Python.

**Paging is a seek plus the shared arithmetic, never a materialised list.**
:func:`~x2knwldg.repository.base.page_from_window` *is* the cursor arithmetic —
the probe row, the cut, the next token — so this implementation and
``MemoryRepository`` mint the same token for the same position, which is what
makes ``T-104`` a page-for-page comparison rather than a second implementation
of the comparison. ``keyset_page`` is deliberately **not** called: it
materialises the whole collection, which is the cost this index exists to
remove. Because the filters run in Python *after* the seek, a fetch can come up
short of a full page, so :meth:`SqliteRepository._records_after` widens and
re-seeks until it has ``limit + 1`` matching records or the table is exhausted.
That same loop covers the other way a window can be too small: a cursor whose
order key was too long for the contract's 512 characters carries a 200-character
*prefix* plus a digest of the whole key (``Cursor``), the seek bound is then a
partial id several rows may share, and ``Cursor.tail`` refuses a position it
cannot find in the window it is given. An ``IndexedRelation.id`` is 1300
characters by schema, so that path is real rather than theoretical, and a walk
that broke there would break only on long ids.

**The graph and the neighborhood inherit their rules and never re-derive them.**
ADR 0004 invariant 1: neither endpoint may grow a second rule for membership,
"in Python or in SQL". :func:`~x2knwldg.repository.base.graph_nodes` decides
which entities a graph is drawn over and :func:`relation_belongs_to_source`
decides which relations belong to a source, so both are *called* here rather
than expressed as a join. A naive join on ``relations.source_id`` would lose
every ``expresses_concept`` edge, because ``adapt_library`` produces them and
they name no run — over the real sample, 118 edges against a lossy 101.

**Records handed out are copies, without a copy being made.** ADR 0002
invariant 6 is satisfied *inherently* here: every record is parsed fresh from
its stored JSON on every call, so no caller can reach a stored dict and there is
nothing to deep-copy. Adding a defensive :func:`record_copy` on top would be
duplicated work claiming to be a guarantee.

Stdlib only, Python 3.10 floor. Nothing reads ``Connection.autocommit`` (3.12)
or ``sqlite3.version`` (removed in 3.14).
"""

from __future__ import annotations

import json
import functools
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from .. import ids
from ..adapters import ADAPTERS, LIBRARY_DIR_NAME
from ..repository import (
    INDEX_STATES,
    READY,
    Cursor,
    EntityQuery,
    GraphPage,
    GraphQuery,
    IndexStatus,
    IndexUnavailable,
    InvalidId,
    InvalidQuery,
    Neighborhood,
    NeighborhoodQuery,
    Page,
    PagedQuery,
    RelationQuery,
    SearchQuery,
    SourceDetail,
    SourceQuery,
    encode_cursor,
    graph_nodes,
    key_digest,
    matches_entity,
    matches_relation,
    matches_source,
    order_key,
    page_from_window,
    record_copy,
)
from . import schema
from .errors import SchemaTooNew, StoreError

__all__ = ["SearchCandidates", "SqliteRepository"]

#: The table each record family lives in. The keys are
#: ``repository.ORDER_KEYS``' models, so a model with no table here is a model
#: this store does not hold — and never a table name built from a caller's
#: string: every ``SELECT`` below interpolates only these values.
_TABLES: Mapping[str, str] = {
    "source": "sources",
    "artifact": "artifacts",
    "entity_ref": "entities",
    "indexed_relation": "relations",
}

#: Rows per continuation seek, once a page has already been asked for. The first
#: seek of a page is exactly ``limit + 1`` rows (``limit + 2`` when resuming,
#: because ``identity >= bound`` returns the boundary row that ``Cursor.tail``
#: drops); a Python predicate that thins the result then costs one round trip per
#: this many rows rather than one per row.
_SCAN_BATCH = 256

#: How many ids go into one ``IN (…)`` list. Well under ``SQLITE_MAX_VARIABLE_
#: NUMBER``, which is 999 on the builds Python has historically shipped.
_IN_CHUNK = 400


# --------------------------------------------------------------------------
# 1. The search seam — the one thing this module does not implement
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchCandidates:
    """What FTS5 retrieval owes :meth:`SqliteRepository.search`.

    ``hits`` are the frozen result dicts of D-028, already ranked — the
    ``documents.hit`` column stores that shape whole, so no field is rebuilt on
    the way out and the two hit shapes cannot drift.

    ``complete`` is ``False`` when some indexed source could not contribute its
    documents. ``MemoryRepository`` reports the same distinction by returning
    ``total=None``: hits for an unreadable source are not zero, they are
    unknown, and a count must not report unknown as none.
    """

    hits: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    complete: bool = True


#: The retrieval callable :meth:`SqliteRepository.search` pages over.
SearchRetrieval = Callable[[sqlite3.Connection, SearchQuery], SearchCandidates]


# --------------------------------------------------------------------------
# 2. The repository
# --------------------------------------------------------------------------


def _serialized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Hold the repository's lock for the whole of *method*.

    ``SqliteRepository`` opens its connection with the same-thread check lifted,
    because a web server answers from a thread pool and would otherwise fail
    every request with *"SQLite objects created in a thread can only be used in
    that same thread"* — a 503 on every endpoint, in production, not only in a
    test.

    Lifting that check is only safe if something else serialises access, and
    this is that something. The lock is taken around the whole public method
    rather than around each ``execute``: a method like :meth:`graph` runs
    several statements whose results must describe one consistent state, and a
    lock released between them would let a rebuild land in the middle and
    return edges whose nodes are no longer there.

    Re-entrant, because the methods call each other — ``neighborhood`` runs
    ``graph``'s machinery, and a plain ``Lock`` would deadlock on the second
    acquisition in the same thread.
    """

    @functools.wraps(method)
    def guarded(self: "SqliteRepository", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


class SqliteRepository:
    """Every v1 record for a project, answered from the SQLite index.

    >>> repo = SqliteRepository.open(project_root)          # doctest: +SKIP
    >>> repo.status().state                                  # doctest: +SKIP
    'ready'

    The connection may be ``None``, which is how "there is no index" is carried:
    :meth:`status` answers ``absent`` and every other method raises
    :class:`~x2knwldg.repository.base.IndexUnavailable`.
    """

    def __init__(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        project_root: Path | None = None,
        search: SearchRetrieval | None = None,
    ) -> None:
        self._connection = connection
        #: Serialises access to the connection. See :func:`_serialized`.
        self._lock = threading.RLock()
        #: The project this index is a cache for. Recorded, never joined onto:
        #: no id reaches a path here (D-042, ADR 0003).
        self.project_root = (
            None if project_root is None else Path(project_root).expanduser().resolve()
        )
        self._search = search

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        project_root: Path,
        *,
        search: SearchRetrieval | None = None,
    ) -> "SqliteRepository":
        """Open the index of *project_root*, or report that there is none.

        Nothing is created. ``schema.connect(create=False)`` is what makes "no
        index yet" distinguishable from "an index I just made empty", and the
        difference is the whole reason ``absent`` is a state rather than an
        error (D-030).

        A database written by a **newer** schema is refused rather than read. A
        forward-only migration list can say what version 4 did to 3; it cannot
        say what 5 did, so answering from it would mean answering from a schema
        this code does not understand. The index is a rebuildable cache, so
        deleting it is always the fix (ADR 0001 invariant 3).
        """
        path = schema.database_path(Path(project_root))
        try:
            # The reader is opened multithreaded because a web server answers
            # from a thread pool; every method is serialised by `_serialized`,
            # which is what makes lifting the driver's check safe.
            connection = schema.connect(path, create=False, multithreaded=True)
        except FileNotFoundError:
            return cls(None, project_root=project_root, search=search)
        try:
            version = schema.schema_version(connection)
        except sqlite3.DatabaseError:
            # A file that is not a database is an index in `error`, which
            # `status()` reports and every other method refuses. Not raised
            # here: a reader that cannot be constructed cannot say why.
            return cls(connection, project_root=project_root, search=search)
        if version > schema.SCHEMA_VERSION:
            connection.close()
            raise SchemaTooNew(
                f"the index was written at schema version {version}, but this code "
                f"knows only up to {schema.SCHEMA_VERSION}. Delete the cache "
                "directory and rebuild — it holds nothing that is not derivable "
                "from the canonical files."
            )
        return cls(connection, project_root=project_root, search=search)

    @_serialized
    def close(self) -> None:
        """Release the connection. Reading is all this class ever did with it."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # State — the one question that is answered in every state
    # ------------------------------------------------------------------

    def _index_state(self) -> tuple[str, str | None, str | None]:
        """``(state, built_at, message)`` as the store itself reports them.

        Read on every call rather than cached at construction: a build writes
        ``building`` and then ``ready``, and a repository that cached the first
        answer would keep reporting a finished index as unbuilt.
        """
        if self._connection is None:
            return "absent", None, None
        try:
            if not self._has_state_table():
                # A file that exists but carries no state table has had no build
                # recorded, which is the same answer as a file that does not
                # exist: absent, not empty. Reporting `error` for the *less*
                # built of two databases would make the state machine
                # non-monotone, and a UI reads `error` as damage.
                return "absent", None, None
            row = self._query(
                "SELECT state, built_at, message FROM index_state WHERE id = 1"
            ).fetchone()
        except StoreError as exc:
            # The file is there and the read failed: a corrupt or unreadable
            # database. `error` is the honest state, and `status()` still
            # answers — which is the whole reason it is a state and not an
            # exception (D-030).
            return "error", None, str(exc)
        if row is None:
            # A migrated database that no build has ever claimed. Same answer,
            # same reason: there is no index here yet, only the shape of one.
            return "absent", None, None
        state = row["state"]
        if state not in INDEX_STATES:
            return (
                "error",
                row["built_at"],
                f"the index reports state {state!r}, which is not one of "
                f"{', '.join(INDEX_STATES)}",
            )
        return state, row["built_at"], row["message"]

    def _has_state_table(self) -> bool:
        """Whether a build could ever have recorded a state here."""
        row = self._query(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'index_state'"
        ).fetchone()
        return row is not None

    def _require_ready(self) -> sqlite3.Connection:
        """The connection, or the reason there is no answer to be had."""
        state, _, message = self._index_state()
        if state != READY or self._connection is None:
            raise IndexUnavailable(
                message or f"the index is {state}, so it cannot answer", state=state
            )
        return self._connection

    @_serialized
    def status(self) -> IndexStatus:
        """What the index is. Answers in every state, including ``error``.

        Every number is read from the store; none is derived from a canonical
        file, and none is invented. ``counts`` and ``sources_by_status`` are left
        **empty** for a database that cannot be read, because the payload renders
        an absent count as ``0`` and an unknown count is not zero.
        """
        state, built_at, _ = self._index_state()
        version: int | None = None
        counts: dict[str, int] = {}
        tally: dict[str, int] = {}
        runs: dict[str, Any] | None = None
        if self._connection is not None:
            try:
                version = schema.schema_version(self._connection)
                counts = self._counts()
                tally = self._status_tally()
                runs = self._runs_seen()
            except (StoreError, sqlite3.DatabaseError):
                counts, tally, runs = {}, {}, None
        return IndexStatus(
            state=state,
            built_at=built_at,
            index_version=version,
            counts=counts,
            sources_by_status=tally,
            runs=runs,
            adapters=[
                {"name": adapter.source_type, "version": adapter.version}
                for adapter in sorted(ADAPTERS.values(), key=lambda cls: cls.source_type)
            ],
        )

    def _runs_seen(self) -> dict[str, Any]:
        """What the last scan found on disk, and what it could not index (D-050).

        A run directory that produced no ``Source`` is in no page and in no
        count, so without this the only honest reading of ``counts.sources`` is
        "at most this many" — and nothing said so. The scanner already records
        both tiers in its ``runs`` table; this reads them back rather than
        re-deriving anything, so the number cannot disagree with the build that
        produced it.

        A skipped run is **named**, not merely counted: "one run was skipped" is
        not actionable and "this directory, for this reason" is.

        The library fragment is excluded. It keeps a ``runs`` row of its own so
        a ``rebuild_library`` that moved no run still re-derives it, and that row
        carries no ``source_id`` because the library is not an ingested source
        (D-016) — so counting it would both inflate ``discovered`` past the
        number of run directories on disk and report the library as a failure
        every time it succeeded. It is identified by its directory name, which
        is safe because ``run_dirs`` refuses that name as a run.
        """
        rows = self._query(
            "SELECT canonical_dir, source_id, skipped_reason FROM runs "
            "ORDER BY canonical_dir"
        ).fetchall()
        runs = [
            row
            for row in rows
            if PurePosixPath(row["canonical_dir"]).name != LIBRARY_DIR_NAME
        ]
        skipped = [
            {
                "relative_path": row["canonical_dir"],
                # The contract requires a non-empty reason. A row with none is
                # a scanner bug rather than a run's fault, and saying so beats
                # emitting an empty string the schema would reject.
                "reason": row["skipped_reason"] or "skipped for a reason the index did not record",
            }
            for row in runs
            if row["source_id"] is None
        ]
        return {
            "discovered": len(runs),
            "indexed": len(runs) - len(skipped),
            "skipped": skipped,
        }

    def _counts(self) -> dict[str, int]:
        """One ``COUNT(*)`` per family. No filter, so no predicate is owed."""
        return {
            "sources": self._count_all("sources"),
            "artifacts": self._count_all("artifacts"),
            "entities": self._count_all("entities"),
            "relations": self._count_all("relations"),
        }

    def _status_tally(self) -> dict[str, int]:
        """Every source's ``status.overall``, tallied.

        Read out of the stored record rather than off the ``status_overall``
        column: the column is a narrowing index (schema §"The extracted columns
        are not the filters"), and a tally is an answer. A non-string overall —
        absent, or a shape no validator wrote — is ``UNKNOWN``, which is a real
        answer about a run rather than the absence of one.
        """
        tally: dict[str, int] = {}
        for record in self._records_after("source", start=None, page=_SCAN_BATCH):
            value = record.get("status")
            overall = value.get("overall") if isinstance(value, Mapping) else None
            key = overall if isinstance(overall, str) else "UNKNOWN"
            tally[key] = tally.get(key, 0) + 1
        return tally

    # ------------------------------------------------------------------
    # Sources and artifacts
    # ------------------------------------------------------------------

    @_serialized
    def list_sources(self, query: SourceQuery) -> Page:
        """``GET /api/sources``."""
        self._require_ready()
        narrow, params = _narrow(
            ("source_type", query.source_type), ("status_overall", query.status)
        )
        return self._page(
            "source",
            query,
            lambda record: matches_source(record, query),
            narrow=narrow,
            params=params,
        )

    @_serialized
    def get_source(self, source_id: str) -> SourceDetail | None:
        """``GET /api/sources/{source_id}``, with the artifacts the source owns."""
        self._require_ready()
        wanted = _source_id(source_id)
        record = self._one("source", wanted)
        if record is None:
            return None
        # The column narrows; the record decides. Ordered by the pair the whole
        # index pages by, so a source's artifacts arrive in the same order a
        # walk of /api/sources/{id} would produce them in.
        narrow, params = _narrow(("source_id", record.get("id")))
        artifacts = [
            artifact
            for artifact in self._records_after(
                "artifact", start=None, narrow=narrow, params=params, page=_SCAN_BATCH
            )
            if artifact.get("source_id") == record.get("id")
        ]
        return SourceDetail(source=record, artifacts=artifacts)

    @_serialized
    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """``GET /api/artifacts/{artifact_id}`` and ``GET /api/media/{artifact_id}``.

        One method for two endpoints. The record carries ``path`` — already
        proven project-relative by ``adapters.project_relative`` — and
        ``available``; serving bytes is ``T-108``'s, and a repository that
        streamed files would put path safety in two places (risk R14).
        """
        self._require_ready()
        return self._one("artifact", _global_id(artifact_id, "artifact_id"))

    # ------------------------------------------------------------------
    # Entities and relations
    # ------------------------------------------------------------------

    @_serialized
    def list_entities(self, query: EntityQuery) -> Page:
        """``GET /api/sources/{source_id}/entities``.

        An unknown ``source_id`` yields an empty page with ``total=0``. Telling
        "no such source" from "a source with no entities" is
        :meth:`get_source`'s job, so the same question is not answered twice.

        ``min_confidence`` is **not** narrowed in SQL. See this module's
        docstring: a bare ``>=`` disagrees with ``matches_entity`` in both
        directions, and the predicate is the specification.
        """
        self._require_ready()
        narrow, params = _narrow(
            ("source_id", query.source_id),
            ("provenance_class", query.provenance_class),
            ("kind", query.kind),
        )
        return self._page(
            "entity_ref",
            query,
            lambda record: matches_entity(record, query),
            narrow=narrow,
            params=params,
        )

    @_serialized
    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """``GET /api/entities/{entity_id}``, or ``None``."""
        self._require_ready()
        return self._one("entity_ref", _global_id(entity_id, "entity_id"))

    @_serialized
    def list_relations(self, query: RelationQuery) -> Page:
        """``GET /api/sources/{source_id}/relations``.

        ``source_id`` is not narrowed in SQL. ``relation_belongs_to_source`` has
        two disjuncts and the second one is load-bearing: the library's
        ``expresses_concept`` edges carry ``source_id: null`` because
        ``adapt_library`` produces them and they are cross-source (D-025), and
        they are still the edges connecting a source to the concepts it
        expresses. A join on ``source_id`` would hide the source's own links —
        118 edges against 101 over the real sample.
        """
        self._require_ready()
        narrow, params = _narrow(("relation_vocabulary", query.relation_vocabulary))
        return self._page(
            "indexed_relation",
            query,
            lambda record: matches_relation(record, query),
            narrow=narrow,
            params=params,
        )

    # ------------------------------------------------------------------
    # Search — offset paging over injected retrieval
    # ------------------------------------------------------------------

    @_serialized
    def search(self, query: SearchQuery) -> Page:
        """``GET /api/search`` — a page of the two hit shapes of D-028.

        The cursor is an **offset**, not a key: a relevance rank is not a stable
        order to key off, and there is no total order over hits to page by. It
        is authenticated like every other cursor, so the offset that indexes the
        ranked list is one this repository issued rather than one a caller minted.

        A well-formed ``source_id`` naming no indexed source has nothing to
        search: an empty page with ``total=0``, because zero here is a fact
        rather than an absent count.

        Retrieval itself is :meth:`_candidates` and lives in
        :mod:`x2knwldg.index.search` (``T-103``). Everything the page shape owes
        — the offset, the window, the probe, the token, the unknown total — is
        here, so the two implementations page identically once retrieval is
        wired.
        """
        self._require_ready()
        offset = _offset(query)
        if query.source_id is not None and self._one("source", query.source_id) is None:
            return Page(items=[], limit=query.limit, next_cursor=None, total=0)
        found = self._candidates(query)
        ranked = list(found.hits)
        window = [record_copy(hit) for hit in ranked[offset : offset + query.limit]]
        exhausted = len(ranked) <= offset + query.limit
        next_cursor = (
            None
            if exhausted or not window
            else _encode_offset(query, offset + query.limit)
        )
        return Page(
            items=window,
            limit=query.limit,
            next_cursor=next_cursor,
            total=len(ranked) if found.complete else None,
        )

    def _candidates(self, query: SearchQuery) -> SearchCandidates:
        """The ranked hits for *query* — the one seam this module leaves open.

        FTS5 candidate retrieval is ``T-103``'s
        ``x2knwldg.index.search.search_candidates``, which owns the two
        external-content indexes ``schema.py`` declares and the rescoring that
        reproduces ``query.rank_documents``' order. Wiring is a one-liner:
        ``SqliteRepository.open(root, search=search_candidates)``. Until then
        this is the only method of the ten that cannot answer, and it says so
        rather than returning an empty page — a search that silently found
        nothing would be indistinguishable from a library with no matches.
        """
        if self._search is None:
            raise NotImplementedError(
                "search retrieval is not wired: pass "
                "x2knwldg.index.search.search_candidates as "
                "SqliteRepository(search=…) (T-103)"
            )
        connection = self._connection
        if connection is None:  # pragma: no cover - _require_ready got here first
            raise StoreError("the index cannot be read: there is no connection")
        return self._search(connection, query)

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    @_serialized
    def graph(self, query: GraphQuery) -> GraphPage:
        """``GET /api/graph`` — a page of nodes, with the edges among them.

        A page of **nodes**, not of edges: paging over edges would silently drop
        an entity that has no relations, and a full walk must show every entity
        exactly once. An edge is included when it matches the query, when both
        endpoints are nodes of this graph, and when at least one of them is on
        *this* page — requiring both keeps the page renderable, because a Map
        that draws an edge to a node it will not show is asserting a node that
        does not exist (D-035).

        Which nodes a source's graph is drawn over is
        :func:`~x2knwldg.repository.base.graph_nodes`' decision, called here
        rather than restated as a join. ADR 0004 invariant 1 forbids a second
        rule for it "in Python or in SQL", and the first attempt at one made
        ``/api/graph?source_id=X`` and ``/api/sources/X/relations`` disagree
        about a fact.

        This is the one method that materialises its collection, and it is not an
        oversight: ``graph_nodes`` is defined over the whole entity and relation
        set — a node belongs when *some* relation names it — so no seek can
        decide membership one page at a time.

        ``truncated`` is about the *graph*, not about the cursor: a last page
        with no ``next_cursor`` is still a slice of a larger graph.
        """
        self._require_ready()
        node_narrow, node_params = _narrow(
            ("provenance_class", query.provenance_class)
        )
        edge_narrow, edge_params = _narrow(
            ("relation_vocabulary", query.relation_vocabulary)
        )
        entities = list(
            self._records_after(
                "entity_ref",
                start=None,
                narrow=node_narrow,
                params=node_params,
                page=_SCAN_BATCH,
            )
        )
        relations = list(
            self._records_after(
                "indexed_relation",
                start=None,
                narrow=edge_narrow,
                params=edge_params,
                page=_SCAN_BATCH,
            )
        )
        nodes = graph_nodes(entities, relations, query)

        start = query.start()
        window = (
            list(nodes)
            if start is None
            else start.tail(nodes, _keyed("entity_ref"))
        )
        page = page_from_window(
            window[: query.limit + 1], query, "entity_ref", total=len(nodes)
        )

        visible = {node.get("global_id") for node in nodes}
        on_page = {node.get("global_id") for node in page.items}
        edges = [
            relation
            for relation in relations
            if matches_relation(relation, query)
            and relation.get("from_id") in visible
            and relation.get("to_id") in visible
            and (relation.get("from_id") in on_page or relation.get("to_id") in on_page)
        ]
        return GraphPage(
            nodes=page.items,
            edges=edges,
            truncated=len(page.items) < len(nodes),
            limit=page.limit,
            next_cursor=page.next_cursor,
            total=page.total,
        )

    @_serialized
    def neighborhood(self, query: NeighborhoodQuery) -> Neighborhood | None:
        """``GET /api/graph/neighborhood/{entity_id}``, or ``None`` for an unknown center.

        A breadth-first walk of ``depth`` rounds over the same adjacency both
        directions of an edge imply, taking each round's new nodes in sorted
        order so two implementations collect the same set when ``limit`` cuts it.
        The ``from_id`` / ``to_id`` indexes of ``schema.py`` are what make each
        round a seek rather than a scan; the edge filter is still
        :func:`matches_relation`.

        ``truncated`` reports the **limit** cutting the walk short, never the
        depth: a depth bound is what the client asked for, while a limit bound is
        the server declining to answer it in full.
        """
        self._require_ready()
        center = self._one("entity_ref", query.entity_id)
        if center is None:
            return None
        edge_filter = _vocabulary_filter(query)

        collected: dict[str, dict[str, Any]] = {str(center.get("global_id")): center}
        frontier = [str(center.get("global_id"))]
        truncated = False
        for _ in range(query.depth):
            neighbours: set[str] = set()
            for relation in self._relations_touching(frontier):
                if not matches_relation(relation, edge_filter):
                    continue
                for endpoint in (relation.get("from_id"), relation.get("to_id")):
                    if isinstance(endpoint, str) and endpoint not in collected:
                        neighbours.add(endpoint)
            found = self._many("entity_ref", sorted(neighbours))
            frontier = []
            for node_id in sorted(neighbours):
                entity = found.get(node_id)
                if entity is None:
                    # A dangling endpoint. Nothing is invented for it: the node
                    # is simply not there to walk to.
                    continue
                if len(collected) >= query.limit:
                    truncated = True
                    break
                collected[node_id] = entity
                frontier.append(node_id)
            if truncated or not frontier:
                break

        # Every edge with both endpoints collected touches a collected node, so
        # the adjacency seek is the whole candidate set — and it returns them in
        # the order the whole index pages by, which is the order a walk of
        # /api/sources/{id}/relations would show them in.
        edges = [
            relation
            for relation in self._relations_touching(collected)
            if matches_relation(relation, edge_filter)
            and relation.get("from_id") in collected
            and relation.get("to_id") in collected
        ]
        return Neighborhood(
            center_id=str(center.get("global_id")),
            depth=query.depth,
            nodes=[collected[key] for key in sorted(collected)],
            edges=edges,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # 3. Paging — the seek, the short-page loop, and the shared arithmetic
    # ------------------------------------------------------------------

    def _page(
        self,
        model: str,
        query: PagedQuery,
        predicate: Callable[[Mapping[str, Any]], bool],
        *,
        narrow: Sequence[str] = (),
        params: Sequence[Any] = (),
    ) -> Page:
        """One page of *model*: seek, filter in Python, hand to the shared cut.

        At most ``limit + 1`` records reach
        :func:`~x2knwldg.repository.base.page_from_window`; the extra one is the
        probe that decides whether a next cursor exists, and it is never
        returned.
        """
        wanted = query.limit + 1
        window: list[dict[str, Any]] = []
        for record in self._records_after(
            model, start=query.start(), narrow=narrow, params=params, page=wanted
        ):
            if predicate(record):
                window.append(record)
                if len(window) == wanted:
                    break
        return page_from_window(
            window,
            query,
            model,
            total=self._total(model, query, predicate, narrow, params),
        )

    def _total(
        self,
        model: str,
        query: PagedQuery,
        predicate: Callable[[Mapping[str, Any]], bool],
        narrow: Sequence[str],
        params: Sequence[Any],
    ) -> int:
        """How many records the query matches, counted rather than estimated.

        ``total`` is the same on every page of a walk, and ``None`` would mean
        *unknown* — never zero. A query with no filters at all is exactly a
        ``COUNT(*)``; any other is counted through the seam's own predicate,
        because a narrowing clause is a superset of its filter by construction
        and counting the superset would over-report.
        """
        if all(value is None for value in query.filters().values()):
            return self._count_all(_TABLES[model])
        return sum(
            1
            for record in self._records_after(
                model, start=None, narrow=narrow, params=params, page=_SCAN_BATCH
            )
            if predicate(record)
        )

    def _records_after(
        self,
        model: str,
        *,
        start: Cursor | None,
        narrow: Sequence[str] = (),
        params: Sequence[Any] = (),
        page: int = _SCAN_BATCH,
    ) -> Iterator[dict[str, Any]]:
        """Every stored record of *model* after *start*, in the one total order.

        Lazy on purpose: a caller that has filled its page stops iterating, and
        the seek that would have followed is never issued.

        Three things make this exact rather than approximate.

        *The order is total.* ``ORDER BY identity, digest`` reproduces
        ``sort_records``' order over ``order_key``, whose separator is a NUL byte
        — which is why the schema stores the two components as two columns and
        never the concatenation. NUL sorts below every character an id may
        contain, so ordering the pair and ordering the joined key agree.

        *The resume is exact.* ``identity >= bound`` returns a superset of the
        tail, and ``Cursor.tail`` trims it to the position itself. One extra row
        is fetched because the boundary row comes back with the tail and is
        dropped.

        *A prefix cursor is found before it is trusted.* When an order key was
        too long for the contract's 512 characters the cursor carries 200
        characters of it plus a digest of the whole, so the seek bound is a
        partial id that several rows may share, and ``Cursor.tail`` **raises**
        for a position it cannot see in its window. An ``IndexedRelation.id`` is
        1300 characters by schema, so the fetch is widened until that row is in
        hand — or until the table is exhausted, when the refusal is the honest
        answer: the record this cursor names really is gone.

        After the first seek the bound is strictly greater than the last row
        *fetched*, and ``identity`` is the ``PRIMARY KEY``, so no row is repeated
        and none is skipped however many times a Python predicate empties a
        batch.
        """
        table = _TABLES[model]
        clauses, args = list(narrow), list(params)
        batch = max(page, _SCAN_BATCH)

        if start is None:
            size = page
            rows = self._select(table, clauses, args, size)
            window = self._parse(rows, table)
        else:
            seek = [*clauses, "identity >= ?"]
            seek_args = [*args, start.identity_bound]
            size = page + 1
            rows = self._select(table, seek, seek_args, size)
            window = self._parse(rows, table)
            while (
                start.digest is not None
                and len(rows) == size
                and not _names(window, model, start.digest)
            ):
                size += batch
                rows = self._select(table, seek, seek_args, size)
                window = self._parse(rows, table)
            window = start.tail(window, _keyed(model))

        while True:
            exhausted = len(rows) < size
            bound = rows[-1]["identity"] if rows else None
            yield from window
            if exhausted or bound is None:
                return
            size = batch
            rows = self._select(table, [*clauses, "identity > ?"], [*args, bound], size)
            window = self._parse(rows, table)

    # ------------------------------------------------------------------
    # 4. Reads — every one of them parameterised
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run *sql*, or report that the store failed rather than the request.

        A ``sqlite3`` failure is the index's problem, not the caller's, so it
        becomes :class:`~x2knwldg.index.errors.StoreError` — ``internal``/500 in
        the D-030 taxonomy — instead of surfacing a driver exception no route
        has a branch for.
        """
        connection = self._connection
        if connection is None:
            raise StoreError("the index cannot be read: there is no database")
        try:
            return connection.execute(sql, tuple(params))
        except sqlite3.DatabaseError as exc:
            raise StoreError(f"the index cannot be read: {exc}") from exc

    def _select(
        self, table: str, clauses: Sequence[str], params: Sequence[Any], limit: int
    ) -> list[sqlite3.Row]:
        """``limit`` rows of *table* in key order, after *clauses*.

        *table* is a value of :data:`_TABLES` and the clauses are literals from
        :func:`_narrow` and :meth:`_records_after`; every caller-supplied value
        travels as a parameter.
        """
        sql = (
            f"SELECT identity, digest, doc FROM {table}{_where(clauses)} "
            "ORDER BY identity, digest LIMIT ?"
        )
        return self._query(sql, [*params, limit]).fetchall()

    def _count_all(self, table: str) -> int:
        row = self._query(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row is not None else 0

    def _parse(self, rows: Iterable[sqlite3.Row], table: str) -> list[dict[str, Any]]:
        """The stored records of *rows*, parsed fresh.

        Fresh per call is what makes ADR 0002 invariant 6 free: no caller can
        reach a dict this repository also holds, so there is nothing to copy
        defensively.
        """
        return [self._document(row, table) for row in rows]

    def _document(self, row: sqlite3.Row, table: str) -> dict[str, Any]:
        try:
            record = json.loads(row["doc"])
        except (TypeError, ValueError) as exc:
            raise StoreError(
                f"{table} row {row['identity']!r} does not hold a readable record"
            ) from exc
        if not isinstance(record, dict):
            raise StoreError(
                f"{table} row {row['identity']!r} holds a "
                f"{type(record).__name__}, not a record"
            )
        return record

    def _one(self, model: str, key: str) -> dict[str, Any] | None:
        """The record of *model* addressed by *key*, or ``None``.

        Absence is a return value; the id was proved well formed before this was
        called (D-020).
        """
        row = self._query(
            f"SELECT identity, digest, doc FROM {_TABLES[model]} WHERE identity = ?",
            (key,),
        ).fetchone()
        return None if row is None else self._document(row, _TABLES[model])

    def _many(self, model: str, keys: Sequence[str]) -> dict[str, dict[str, Any]]:
        """The records of *model* for *keys*, by id. Missing keys are absent."""
        table = _TABLES[model]
        found: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(keys):
            placeholders = ", ".join("?" * len(chunk))
            rows = self._query(
                f"SELECT identity, digest, doc FROM {table} "
                f"WHERE identity IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                found[row["identity"]] = self._document(row, table)
        return found

    def _relations_touching(self, node_ids: Iterable[str]) -> list[dict[str, Any]]:
        """Every stored relation naming one of *node_ids*, in key order.

        Both directions, because an edge is adjacency for both of its endpoints.
        Deduplicated by id — a self-edge, or an edge whose two endpoints are both
        in the set, matches the seek twice — and ordered by the pair the whole
        index pages by, so the edge list of a neighborhood is in the same order
        every other view of those relations uses.
        """
        wanted = [node_id for node_id in node_ids if isinstance(node_id, str)]
        seen: dict[str, tuple[str, dict[str, Any]]] = {}
        for chunk in _chunks(wanted):
            placeholders = ", ".join("?" * len(chunk))
            rows = self._query(
                "SELECT identity, digest, doc FROM relations "
                f"WHERE from_id IN ({placeholders}) OR to_id IN ({placeholders})",
                [*chunk, *chunk],
            ).fetchall()
            for row in rows:
                seen[row["identity"]] = (row["digest"], self._document(row, "relations"))
        return [record for _, (_, record) in sorted(seen.items(), key=_by_pair)]


# --------------------------------------------------------------------------
# 5. Small helpers
#
# `_source_id`, `_global_id` and `_offset` are `MemoryRepository`'s, which keeps
# them private — a deliberate duplication of three lines rather than a widened
# import surface between two implementations that are meant to be independently
# checkable. `_unit_global_id` is *not* duplicated: nothing here mints a global
# id for a search hit, because `documents.hit` stores the frozen shape whole.
# --------------------------------------------------------------------------


def _source_id(value: Any) -> str:
    try:
        return ids.parse_source_id(value).value
    except ids.IdError as exc:
        raise InvalidId(f"source_id: {exc}") from exc


def _global_id(value: Any, label: str) -> str:
    try:
        return ids.parse_global_id(value).value
    except ids.IdError as exc:
        raise InvalidId(f"{label}: {exc}") from exc


def _offset(query: SearchQuery) -> int:
    start = query.start()
    if start is None:
        return 0
    try:
        offset = int(start.key or "")
    except ValueError as exc:
        raise InvalidQuery("cursor is not a cursor this repository issued") from exc
    if offset < 0:
        raise InvalidQuery("cursor is not a cursor this repository issued")
    return offset


def _encode_offset(query: SearchQuery, offset: int) -> str:
    """The token for the next window of a ranked list."""
    return encode_cursor(query.fingerprint, str(offset))


def _vocabulary_filter(query: NeighborhoodQuery) -> GraphQuery:
    """A neighborhood filters edges by vocabulary only — one matcher, one rule."""
    return GraphQuery(limit=query.limit, relation_vocabulary=query.relation_vocabulary)


def _narrow(*columns: tuple[str, Any]) -> tuple[list[str], list[Any]]:
    """Narrowing clauses for the extracted columns, and their parameters.

    ``(column = ? OR column IS NULL)`` rather than ``column = ?``, and the
    ``OR`` is not slack. The columns are an index over what the stored record
    says, and a clause that dropped every row whose column is ``NULL`` would
    make an unextracted column into a *missing record* — an answer the Python
    predicate could no longer repair. Admitting the nulls keeps the narrowing a
    superset of its filter, which is the only thing ADR 0002 invariant 5 allows
    it to be: the predicate decides, always.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in columns:
        if value is None:
            continue
        clauses.append(f"({column} = ? OR {column} IS NULL)")
        params.append(value)
    return clauses, params


def _where(clauses: Sequence[str]) -> str:
    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def _keyed(model: str) -> Callable[[Mapping[str, Any]], str]:
    """``order_key`` for *model*, read off the record rather than the columns.

    The record is the authority. ``identity`` and ``digest`` are what SQLite
    sorts on and the scanner writes them from these same two functions, so the
    two agree; where they ever did not, the token a page mints would still name
    a position in terms of the record it handed out.
    """
    return lambda record: order_key(record, model)


def _names(records: Sequence[Mapping[str, Any]], model: str, digest: str) -> bool:
    """Whether one of *records* is the row a prefix cursor names."""
    return any(key_digest(order_key(record, model)) == digest for record in records)


def _chunks(values: Sequence[str]) -> Iterator[list[str]]:
    """*values* in ``IN (…)``-sized pieces, deduplicated, in a stable order."""
    unique = sorted({value for value in values})
    for offset in range(0, len(unique), _IN_CHUNK):
        yield unique[offset : offset + _IN_CHUNK]


def _by_pair(item: tuple[str, tuple[str, Mapping[str, Any]]]) -> tuple[str, str]:
    identity_value, (digest, _) = item
    return identity_value, digest
