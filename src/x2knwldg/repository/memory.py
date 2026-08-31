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
all in memory, and it re-runs the linear scan of ``query.search_knowledge`` for
every search — which is exactly the cost ``T-103``'s FTS5 tables exist to
remove. Do not serve a growing library from it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .. import ids
from ..adapters import ADAPTERS, IndexRecords, adapt_project
from ..pipeline import PipelineError
from ..query import search_knowledge
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
    encode_cursor,
    keyset_page,
    matches_entity,
    matches_relation,
    matches_source,
    record_copy,
    sort_records,
)

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

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_project(
        cls,
        project_root: Path,
        *,
        output_dir: str = "output",
        hash_artifacts: bool = False,
    ) -> "MemoryRepository":
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
    ) -> "MemoryRepository":
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
        """A page of search hits, ranked as ``query.search_knowledge`` ranks them.

        The cursor is an **offset**, not a key: a relevance rank is not a stable
        order to key off, and there is no total order over hits to page by. That
        is a real limitation, stated rather than hidden — a run finalised between
        two pages can shift the ranking under the cursor. Bounded pagination over
        a ranked list is what ``T-103``'s FTS5 replacement inherits, and the
        cursor stays opaque so it can change its encoding then without touching
        the contract.
        """
        self._require_ready()
        offset = _offset(query)
        wanted = offset + query.limit + 1

        output_root, run_id = self._search_root(query.source_id)
        if output_root is None:
            # A well-formed source id naming no indexed source has nothing to
            # search. An empty page, not an error: absence is a return value.
            return Page(items=[], limit=query.limit, next_cursor=None, total=0)

        try:
            results = search_knowledge(
                output_root,
                query.q,
                video_id=run_id,
                limit=wanted,
                include_transcript_fallback=query.include_transcript,
            )
        except PipelineError as exc:  # pragma: no cover - guarded by _search_root
            raise InvalidId(f"source_id: {exc}") from exc

        window = [self.as_api_hit(result) for result in results[offset : offset + query.limit]]
        exhausted = len(results) <= offset + query.limit
        next_cursor = (
            None
            if exhausted or not window
            else encode_cursor(query.fingerprint, str(offset + query.limit))
        )
        # `total` stays None: search_knowledge truncates at `limit` rather than
        # counting matches, and the contract says null means unknown, never zero.
        return Page(items=window, limit=query.limit, next_cursor=next_cursor, total=None)

    def as_api_hit(self, result: Mapping[str, Any]) -> dict[str, Any]:
        """Attach D-028's two additive fields, and no others.

        Every other field passes through from ``query.search_knowledge``
        untouched — ``video_id`` stays ``video_id`` (ADR 0001 invariant 6). The
        source type comes from the **indexed source** rather than being assumed
        to be YouTube, and an id that cannot be built honestly is ``None`` rather
        than a plausible string that resolves to nothing.

        A ``transcript_caption`` hit gets **no** ``global_id`` at all: v1 emits
        no caption entities (D-023), so there is no entity to address.
        """
        # Shallow on purpose, unlike every other boundary here: a search hit is
        # built fresh from disk by search_knowledge on each call, so it aliases
        # nothing the index holds and there is no stored record to protect.
        hit = dict(result)
        video_id = result.get("video_id")
        source_id = (
            self._source_id_by_external.get(video_id) if isinstance(video_id, str) else None
        )
        hit["source_id"] = source_id
        if result.get("type") == "knowledge_unit":
            hit["global_id"] = _unit_global_id(source_id, result.get("id"))
        return hit

    def _search_root(self, source_id: str | None) -> tuple[Path | None, str | None]:
        """Where to search, derived from the record — never from the raw id.

        An externally supplied id is looked **up**, and the directory that comes
        back is the one the ``Source`` record already carries. So a hostile id
        never reaches a path join at all, and a fixture whose directory name
        differs from its ``external_id`` still searches the right run.
        """
        if source_id is None:
            return self._output_root, None
        source = self._source_by_id.get(source_id)
        if source is None:
            return None, None
        canonical_dir = source.get("canonical_dir")
        if not isinstance(canonical_dir, str) or not canonical_dir:
            return None, None
        run_dir = self._project_root / canonical_dir
        return run_dir.parent, run_dir.name

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
        """
        self._require_ready()
        node_filter = query.node_query()
        nodes = [entity for entity in self._entities if matches_entity(entity, node_filter)]
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
            truncated=page.next_cursor is not None,
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
                if entity is None:
                    # An edge may name an endpoint the index holds no entity for.
                    # It is not invented here; it simply does not join the walk.
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
    start = query.start_key()
    if start is None:
        return 0
    try:
        offset = int(start)
    except ValueError as exc:
        raise InvalidQuery("cursor is not a cursor this repository issued") from exc
    if offset < 0:
        raise InvalidQuery("cursor is not a cursor this repository issued")
    return offset


def _vocabulary_filter(query: NeighborhoodQuery) -> GraphQuery:
    """A neighborhood filters edges by vocabulary only — one matcher, one rule."""
    return GraphQuery(limit=query.limit, relation_vocabulary=query.relation_vocabulary)
