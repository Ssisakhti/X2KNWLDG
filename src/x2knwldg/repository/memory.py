"""The reference :class:`~x2knwldg.repository.base.IndexRepository` (``T-007``).

``MemoryRepository`` answers the whole frozen contract from the records
``adapters.adapt_project`` produces, holding them in memory. It exists for three
reasons, and it is honest about not being a production index:

**Track B can start on day one.** ``T-105``–``T-108`` build the routes against
this while ``T-101``–``T-104`` build the SQLite index behind the same interface.
Neither track waits for the other, which is what §8.2 of the project management
document means by "A and B meet only at the repository interface".

**Track A gets an oracle.** ``T-104`` has to prove a rebuilt index equals an
incrementally updated one. Both must also equal *this* — a repository that reads
the canonical files with no cache at all. Where they disagree, the canonical
files are right and the index is stale, which is ADR 0001 invariant 3.

**The contract gets tested against real records.** Every page here is a page of
records the real adapters produced from real runs, so a contract test over this
repository is a test of the same dicts the API will serialise.

What it is not: an index. It re-reads everything on construction, it holds it
all in memory, and it ranks every searchable document in the library on every
search — which is exactly the cost ``T-103``'s FTS5 tables exist to remove. Do
not serve a growing library from it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import ids
from ..adapters import ADAPTERS, IndexRecords, adapt_project
from ..query import SearchDocument, rank_documents, run_documents
from .base import (
    READY,
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
    RelationQuery,
    SearchQuery,
    SourceDetail,
    SourceQuery,
    check_index_integrity,
    encode_cursor,
    graph_nodes,
    keyset_page,
    matches_entity,
    matches_relation,
    matches_source,
    record_copy,
    sort_records,
)

#: Sentinel for "work the source out yourself", so that ``None`` can keep
#: meaning "there is no source for this hit".
_DERIVE = object()

__all__ = ["MemoryRepository"]


class MemoryRepository:
    """Every v1 record for a project, held in memory and answered from there."""

    def __init__(
        self,
        records: IndexRecords,
        *,
        project_root: Path,
        output_dir: str = "output",
        state: str = READY,
        built_at: str | None = None,
        message: str | None = None,
    ) -> None:
        self._project_root = project_root.expanduser().resolve()
        self._output_root = self._project_root / output_dir
        self._state = state
        self._built_at = built_at
        self._message = message

        self._sources = sort_records(records.sources, "source")
        self._artifacts = sort_records(records.artifacts, "artifact")
        self._entities = sort_records(records.entities, "entity_ref")
        self._relations = sort_records(records.relations, "indexed_relation")

        self._source_by_id = {source["id"]: source for source in self._sources}
        self._artifact_by_id = {artifact["id"]: artifact for artifact in self._artifacts}
        self._entity_by_id = {entity["global_id"]: entity for entity in self._entities}

        self._artifacts_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for artifact in self._artifacts:
            self._artifacts_by_source[artifact.get("source_id", "")].append(artifact)

        # An external id maps to a source id only when exactly one source claims
        # it. Two source types could ingest the same external id; guessing which
        # one a search hit came from would mint an address that resolves to the
        # wrong entity, so the honest answer there is None (D-028).
        by_external: dict[str, set[str]] = defaultdict(set)
        for source in self._sources:
            external_id = source.get("external_id")
            if isinstance(external_id, str):
                by_external[external_id].add(source["id"])
        self._source_id_by_external = {
            external_id: next(iter(claims))
            for external_id, claims in by_external.items()
            if len(claims) == 1
        }

        self._adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relation in self._relations:
            for endpoint in (relation.get("from_id"), relation.get("to_id")):
                if isinstance(endpoint, str):
                    self._adjacency[endpoint].append(relation)

        # A set that cannot be paged honestly is refused here rather than
        # quietly mis-served later: a duplicate id deletes a record at a page
        # boundary, and a dangling edge makes the graph and the relations list
        # disagree about one fact.
        check_index_integrity(
            {
                "source": self._sources,
                "artifact": self._artifacts,
                "entity_ref": self._entities,
                "indexed_relation": self._relations,
            }
        )

        # Built on the first search, from the runs this index holds — see
        # :meth:`search`. Not at construction: a repository that never searches
        # should not pay for a corpus, and ``/api/status`` must stay cheap.
        self._corpus: dict[str, list[SearchDocument]] | None = None
        self._unreadable: set[str] = set()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        """The project these records describe.

        Public because ``SqliteRepository.project_root`` is, and the two are
        meant to be interchangeable — ``T-104`` proves they answer the ten
        protocol methods identically, but the equivalence harness compares only
        those, so an attribute one exposes and the other hides slips through it.
        The byte channel is what found the gap: it resolves an artifact's
        project-relative path against this, and worked over SQLite while
        answering ``500`` over the oracle.

        Recorded, never joined onto by this class: no id reaches a path here.
        """
        return self._project_root


    @classmethod
    def from_project(
        cls,
        project_root: Path,
        *,
        output_dir: str = "output",
        hash_artifacts: bool = False,
    ) -> MemoryRepository:
        """Read every run under ``<project_root>/<output_dir>`` and the library.

        ``AdapterError`` propagates: a run that cannot be mapped without
        guessing is not something to paper over with an empty repository. A
        caller that wants to serve anyway can catch it and use
        :meth:`unavailable` so ``/api/status`` reports ``error`` honestly.
        """
        project_root = project_root.expanduser().resolve()
        records = adapt_project(
            project_root, output_dir=output_dir, hash_artifacts=hash_artifacts
        )
        return cls(records, project_root=project_root, output_dir=output_dir)

    @classmethod
    def unavailable(
        cls, state: str, *, project_root: Path | None = None, message: str | None = None
    ) -> MemoryRepository:
        """A repository that can only say why it cannot answer.

        ``/api/status`` still works — that is the whole point of ``absent`` and
        ``building`` being states rather than errors — and every other method
        raises :class:`IndexUnavailable`, which the API renders as ``503``.
        """
        return cls(
            IndexRecords(),
            project_root=project_root or Path("."),
            state=state,
            message=message,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> IndexStatus:
        tally: dict[str, int] = defaultdict(int)
        for source in self._sources:
            status = source.get("status")
            overall = status.get("overall") if isinstance(status, Mapping) else None
            tally[overall if isinstance(overall, str) else "UNKNOWN"] += 1
        return IndexStatus(
            state=self._state,
            built_at=self._built_at,
            message=self._message,
            # There is no persisted index and so no migration to be at. Stating
            # a version here would claim a durable artifact that does not exist.
            index_version=None,
            counts={
                "sources": len(self._sources),
                "artifacts": len(self._artifacts),
                "entities": len(self._entities),
                "relations": len(self._relations),
            },
            sources_by_status=tally,
            adapters=[
                {"name": adapter.source_type, "version": adapter.version}
                for adapter in sorted(ADAPTERS.values(), key=lambda cls: cls.source_type)
            ],
        )

    def _require_ready(self) -> None:
        if self._state != READY:
            raise IndexUnavailable(
                self._message or f"the index is {self._state}, so it cannot answer",
                state=self._state,
            )

    # ------------------------------------------------------------------
    # Sources and artifacts
    # ------------------------------------------------------------------

    def list_sources(self, query: SourceQuery) -> Page:
        self._require_ready()
        matching = [source for source in self._sources if matches_source(source, query)]
        return keyset_page(matching, query, "source")

    def get_source(self, source_id: str) -> SourceDetail | None:
        self._require_ready()
        source = self._source_by_id.get(_source_id(source_id))
        if source is None:
            return None
        return SourceDetail(
            source=record_copy(source),
            artifacts=[
                record_copy(a) for a in self._artifacts_by_source.get(source["id"], ())
            ],
        )

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        self._require_ready()
        artifact = self._artifact_by_id.get(_global_id(artifact_id, "artifact_id"))
        return record_copy(artifact) if artifact is not None else None

    # ------------------------------------------------------------------
    # Entities and relations
    # ------------------------------------------------------------------

    def list_entities(self, query: EntityQuery) -> Page:
        self._require_ready()
        matching = [entity for entity in self._entities if matches_entity(entity, query)]
        return keyset_page(matching, query, "entity_ref")

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        self._require_ready()
        entity = self._entity_by_id.get(_global_id(entity_id, "entity_id"))
        return record_copy(entity) if entity is not None else None

    def list_relations(self, query: RelationQuery) -> Page:
        self._require_ready()
        matching = [rel for rel in self._relations if matches_relation(rel, query)]
        return keyset_page(matching, query, "indexed_relation")

    # ------------------------------------------------------------------
    # Search — D-028's two shapes, plus the two additive fields
    # ------------------------------------------------------------------

    def search(self, query: SearchQuery) -> Page:
        """A page of search hits over the sources **this index holds**.

        Search resolves against the index, not the filesystem. It used to walk
        ``<project_root>/output`` directly, which made it a second, disagreeing
        view of the library: a run that appeared after this repository was built
        was searched and returned hits, and every one of them carried
        ``source_id: null``, because no ``Source`` record existed to resolve it
        against. Renderable, and unnavigable. Now the corpus is built from the
        ``canonical_dir`` each indexed ``Source`` already carries, so a hit
        always names a source ``/api/sources/{id}`` will answer for, and a run
        added after the build simply is not in the index yet — which is what
        every other method here already says about it.

        Resolving through the record rather than the id also retires a
        round-trip the API could not survive. The run directory used to be
        re-derived by name and re-resolved through ``pipeline.resolve_run_dir``,
        so a directory containing a space — an id nothing rejected at ingest —
        came back as ``400 invalid_id`` for an id the API itself had issued, in
        an error body naming the host directory. No id is joined onto a path
        here at all now, and nothing about the host filesystem reaches an error
        body (D-030).

        The cursor is an **offset**, not a key: a relevance rank is not a stable
        order to key off, and there is no total order over hits to page by. It
        is authenticated like every other cursor, so the offset that indexes the
        ranked list is one this repository issued.
        """
        self._require_ready()
        offset = _offset(query)
        corpus = self._documents()

        if query.source_id is not None:
            if query.source_id not in self._source_by_id:
                # A well-formed source id naming no indexed source has nothing
                # to search. An empty page, not an error: absence is a return
                # value, and zero here is a fact rather than an absent count.
                return Page(items=[], limit=query.limit, next_cursor=None, total=0)
            scope = [query.source_id]
        else:
            scope = [source["id"] for source in self._sources]

        documents: list[SearchDocument] = []
        complete = True
        for source_id in scope:
            if source_id in self._unreadable:
                # The source is indexed but its canonical files could not be
                # read. Its hits are not zero; they are unknown, and `total`
                # says so rather than counting them as none.
                complete = False
                continue
            for document in corpus.get(source_id, ()):
                if not query.include_transcript and (
                    document.hit.get("type") == "transcript_caption"
                ):
                    continue
                documents.append(document)

        ranked = rank_documents(documents, query.q)
        window = [record_copy(hit) for hit in ranked[offset : offset + query.limit]]
        exhausted = len(ranked) <= offset + query.limit
        next_cursor = (
            None
            if exhausted or not window
            else encode_cursor(query.fingerprint, str(offset + query.limit))
        )
        return Page(
            items=window,
            limit=query.limit,
            next_cursor=next_cursor,
            total=len(ranked) if complete else None,
        )

    def as_api_hit(
        self, result: Mapping[str, Any], *, source_id: Any = _DERIVE
    ) -> dict[str, Any]:
        """Attach D-028's two additive fields, and no others.

        Every other field passes through from ``query.run_documents`` untouched
        — ``video_id`` stays ``video_id`` (ADR 0001 invariant 6). The source type
        comes from the **indexed source** rather than being assumed to be
        YouTube, and an id that cannot be built honestly is ``None`` rather than
        a plausible string that resolves to nothing.

        *source_id* is passed when the caller already knows which indexed source
        the hit came from, which :meth:`search` always does now. Left out, the
        source is inferred from the hit's ``video_id``, and only when exactly one
        indexed source claims that external id: two source types could ingest
        the same one, and guessing between them would mint an address resolving
        to the wrong entity (D-028).

        A ``transcript_caption`` hit gets **no** ``global_id`` at all: v1 emits
        no caption entities (D-023), so there is no entity to address.
        """
        # Shallow on purpose, unlike every other boundary here: the caller owns
        # the dict this builds, and every hand-out of a stored one is copied.
        hit = dict(result)
        if source_id is _DERIVE:
            video_id = result.get("video_id")
            source_id = (
                self._source_id_by_external.get(video_id)
                if isinstance(video_id, str)
                else None
            )
        hit["source_id"] = source_id
        if result.get("type") == "knowledge_unit":
            hit["global_id"] = _unit_global_id(source_id, result.get("id"))
        return hit

    def _documents(self) -> dict[str, list[SearchDocument]]:
        """The searchable corpus, by source id, built once and kept.

        Building it once is the difference between a page and a walk. Reading
        and rescoring every canonical file per call made paging cost the whole
        library per page — the cost ADR 0002 records as the reason ``T-103``
        exists, paid once per *page* rather than once per query.

        Each run is located by the ``canonical_dir`` its own ``Source`` record
        carries — project-relative and already proven inside the project root by
        ``adapters.project_relative`` (risk R15) — and containment is re-checked
        here, because a resolver that does not re-check is not a boundary
        (ADR 0003 invariant 5). A source whose files cannot be read is recorded
        as unreadable rather than as empty, and no path ever reaches an error.
        """
        if self._corpus is not None:
            return self._corpus
        corpus: dict[str, list[SearchDocument]] = {}
        unreadable: set[str] = set()
        for source in self._sources:
            source_id = source["id"]
            run_dir = self._run_dir(source)
            if run_dir is None:
                unreadable.add(source_id)
                continue
            try:
                documents = run_documents(run_dir)
            except (OSError, ValueError):
                # A canonical file that is present and unparseable is not an
                # empty run. Nothing is invented, and nothing is counted.
                unreadable.add(source_id)
                continue
            corpus[source_id] = [
                SearchDocument(
                    hit=self.as_api_hit(document.hit, source_id=source_id),
                    folded=document.folded,
                    tokens=document.tokens,
                    weight=document.weight,
                )
                for document in documents
            ]
        self._corpus = corpus
        self._unreadable = unreadable
        return corpus

    def _run_dir(self, source: Mapping[str, Any]) -> Path | None:
        """The run directory a ``Source`` record points at, or ``None``.

        The record carries the path; nothing is rebuilt from an id. ``None``
        means the record states no directory, or states one that does not
        resolve inside the project root — in either case the source cannot be
        searched, and saying so is the whole answer.
        """
        canonical_dir = source.get("canonical_dir")
        if not isinstance(canonical_dir, str) or not canonical_dir:
            return None
        run_dir = (self._project_root / canonical_dir).resolve()
        if run_dir != self._project_root and self._project_root not in run_dir.parents:
            return None
        return run_dir

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def graph(self, query: GraphQuery) -> GraphPage:
        """A page of nodes, with the edges that run between nodes of this graph.

        **A graph page is a page of nodes, not of edges.** Paging over edges
        would silently drop an entity that has no relations — a real record, and
        one the Map would then never show. Paging over nodes means every entity
        appears exactly once across a full walk.

        An edge is included when both of its endpoints pass the node filter and
        at least one of them is on this page. Requiring *both* keeps the page
        renderable: an edge to a node the filter excluded would dangle, and a
        Map that draws a dangling edge is asserting a node it will not show.
        An edge whose endpoints straddle two pages appears in both, so a client
        accumulating pages dedupes by ``id``.

        Which nodes a source's graph is drawn over is :func:`graph_nodes`'
        decision, and it is the same membership rule
        ``/api/sources/{id}/relations`` applies. The two views answered it
        differently until now and disagreed about one fact — see that function.

        ``truncated`` is about the *graph*, not about the cursor. A last page
        with no ``next_cursor`` is still a slice of a larger graph, and reporting
        it as whole would let the Map present a cut graph as the library.
        """
        self._require_ready()
        nodes = graph_nodes(self._entities, self._relations, query)
        page = keyset_page(nodes, query, "entity_ref")

        visible = {node["global_id"] for node in nodes}
        on_page = {node["global_id"] for node in page.items}
        edges = [
            record_copy(relation)
            for relation in self._relations
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

    def neighborhood(self, query: NeighborhoodQuery) -> Neighborhood | None:
        """A breadth-first walk from a center, bounded by ``depth`` and ``limit``.

        ``truncated`` reports the **limit** cutting the walk short, not the
        depth: a depth bound is what the client asked for, while a limit bound
        is the server declining to answer it in full.
        """
        self._require_ready()
        center = self._entity_by_id.get(query.entity_id)
        if center is None:
            return None

        collected: dict[str, dict[str, Any]] = {center["global_id"]: record_copy(center)}
        frontier = [center["global_id"]]
        truncated = False
        for _ in range(query.depth):
            neighbours: set[str] = set()
            for node_id in frontier:
                for relation in self._adjacency.get(node_id, ()):
                    if not matches_relation(relation, _vocabulary_filter(query)):
                        continue
                    for endpoint in (relation.get("from_id"), relation.get("to_id")):
                        if isinstance(endpoint, str) and endpoint not in collected:
                            neighbours.add(endpoint)
            frontier = []
            for node_id in sorted(neighbours):
                entity = self._entity_by_id.get(node_id)
                if entity is None:  # pragma: no cover - check_index_integrity refuses these
                    # A dangling endpoint is refused at construction, so this
                    # cannot happen; nothing is invented if it ever does.
                    continue
                if len(collected) >= query.limit:
                    truncated = True
                    break
                collected[node_id] = record_copy(entity)
                frontier.append(node_id)
            if truncated or not frontier:
                break

        edges = [
            record_copy(relation)
            for relation in self._relations
            if matches_relation(relation, _vocabulary_filter(query))
            and relation.get("from_id") in collected
            and relation.get("to_id") in collected
        ]
        return Neighborhood(
            center_id=center["global_id"],
            depth=query.depth,
            nodes=[collected[key] for key in sorted(collected)],
            edges=edges,
            truncated=truncated,
        )


# --------------------------------------------------------------------------
# Small helpers
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


def _unit_global_id(source_id: str | None, local_id: Any) -> str | None:
    if source_id is None:
        return None
    parsed = ids.parse_source_id(source_id)
    try:
        return ids.make_global_id(parsed.source_type, parsed.external_id, local_id).value
    except ids.IdError:
        return None


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


def _vocabulary_filter(query: NeighborhoodQuery) -> GraphQuery:
    """A neighborhood filters edges by vocabulary only — one matcher, one rule."""
    return GraphQuery(limit=query.limit, relation_vocabulary=query.relation_vocabulary)
