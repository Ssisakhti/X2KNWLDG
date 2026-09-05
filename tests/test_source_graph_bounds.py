"""Every bound the Source Map serves under, and that none of them is silent (`T-254`).

Three bounds meet in these two endpoints, and each exists because an unbounded
array in a response is an unbounded response:

* ``MAX_SOURCE_RELATION_BASIS`` — the grounds one relation carries in one body.
  ``basis_total`` and ``basis_returned`` are **both** required, because a body
  carrying only the second presents a truncation as the whole basis, which is
  risk R27 arriving through the API instead of through the model.
* ``MAX_GRAPH_EDGES`` — the relations one graph body carries, the same cap
  ``GraphPayload.edges`` has and for the same reason (D-175).
* ``limit`` — the relations one neighbourhood body carries across both
  directions.

The corpora here are written by hand rather than gated, and deliberately so: the
apply gate refuses a basis of 400 grounds long before one could reach a
response, so a bound that only ever sees gated documents is a bound nothing has
tested. What is under test is the *reader*, and the reader must be honest about
a file it did not write.

Both repositories answer every case. The oracle reads the canonical file and the
index reads a table a scan wrote, so a bound applied in one and forgotten in the
other is exactly the drift this file exists to catch.

Stdlib only, so this runs on a bare core install.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import source_map_corpus as smc

from x2knwldg import ids
from x2knwldg.constants import MAX_GRAPH_EDGES, MAX_SOURCE_RELATION_BASIS
from x2knwldg.index.schema import has_fts5
from x2knwldg.repository import (
    MAX_LIMIT,
    MemoryRepository,
    SourceGraphQuery,
    SourceNeighborhoodQuery,
)

requires_fts5 = pytest.mark.skipif(
    not has_fts5(sqlite3.connect(":memory:")),
    reason="the migrations declare FTS5 tables, so a build needs an FTS5-enabled SQLite",
)

#: A rationale in Persian, because ``narrativeText`` is what the record declares
#: and a synthetic fixture that wrote English here would be testing the reader
#: against a document the gate would never have accepted.
RATIONALE = "این رابطهٔ آزمایشی فقط برای سنجش کران‌های پاسخ (response bounds) ساخته شده است."


def _relation(
    from_source: str, to_source: str, *, basis: int, salt: str = ""
) -> dict[str, Any]:
    """One stored relation with *basis* grounds.

    The id is built by :func:`x2knwldg.ids.source_relation_id` where it can be —
    over the endpoints, the type and the scope — and salted only where a case
    needs many relations over one pair, which the gate would refuse and a reader
    must still page honestly.
    """
    identifier = ids.source_relation_id(from_source, to_source, "critiques", "partial")
    return {
        "id": f"{identifier}{salt}",
        "from_source_id": from_source,
        "to_source_id": to_source,
        "relation_type": "critiques",
        "scope": "partial",
        "provenance_class": "derived",
        "rationale": RATIONALE,
        "basis": [
            {
                "from_ku_id": f"KU-{index + 1:06d}",
                "to_ku_id": f"KU-{index + 1:06d}",
                "relation_type": "contradicts",
            }
            for index in range(basis)
        ],
        "generated_from": {"from_run_digest": "0" * 64, "to_run_digest": "1" * 64},
    }


def _corpus(root: Path, relations: list[dict[str, Any]]) -> Path:
    """The `T-254` corpus with *relations* written in place of the committed one."""
    project_root = smc.build(root, relations=False).project_root
    synthesis = project_root / "output" / "synthesis"
    synthesis.mkdir(parents=True, exist_ok=True)
    (synthesis / "source_relations.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "candidates": {"considered": len(relations), "omitted": 0, "bound": 25},
                "relations": relations,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_root


def _each(root: Path) -> list[tuple[str, Any]]:
    """``[(label, repository)]``, with the SQLite one built and left open.

    A list rather than a generator, because every test here asks both of them
    the same question and comparing two answers needs both in hand.
    """
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.index.scanner import build_index
    from x2knwldg.index.search import document_indexer, search_retrieval

    build_index(root, index_documents=document_indexer(root))
    return [
        ("oracle", MemoryRepository.from_project(root)),
        ("sqlite", SqliteRepository.open(root, search=search_retrieval)),
    ]


def _closed(pairs: list[tuple[str, Any]]) -> None:
    for _label, repo in pairs:
        close: Callable[[], None] | None = getattr(repo, "close", None)
        if close is not None:
            close()


# --------------------------------------------------------------------------
# 1. The basis bound
# --------------------------------------------------------------------------


@requires_fts5
def test_a_basis_wider_than_the_bound_states_both_counts(tmp_path: Path) -> None:
    """A truncated basis is stated, never implied."""
    over = MAX_SOURCE_RELATION_BASIS + 17
    root = _corpus(
        tmp_path / "wide",
        [_relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=over)],
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            found = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS)
            )
            relation = found.incoming[0]
            assert relation["basis_total"] == over, label
            assert relation["basis_returned"] == MAX_SOURCE_RELATION_BASIS, label
            assert len(relation["basis"]) == MAX_SOURCE_RELATION_BASIS, label
    finally:
        _closed(pairs)


@requires_fts5
def test_a_basis_inside_the_bound_reports_the_two_counts_equal(tmp_path: Path) -> None:
    """The counts are not a truncation marker; they are always both stated."""
    root = _corpus(
        tmp_path / "narrow",
        [_relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=3)],
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            relation = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS)
            ).incoming[0]
            assert relation["basis_total"] == 3, label
            assert relation["basis_returned"] == 3, label
    finally:
        _closed(pairs)


@requires_fts5
def test_the_bounded_basis_keeps_the_order_the_record_states(tmp_path: Path) -> None:
    """Re-ranking a basis would be the reader inventing an order the record lacks."""
    over = MAX_SOURCE_RELATION_BASIS + 5
    root = _corpus(
        tmp_path / "ordered",
        [_relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=over)],
    )
    expected = [f"KU-{index + 1:06d}" for index in range(MAX_SOURCE_RELATION_BASIS)]
    pairs = _each(root)
    try:
        for label, repo in pairs:
            relation = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS)
            ).incoming[0]
            assert [entry["from_ku_id"] for entry in relation["basis"]] == expected, label
    finally:
        _closed(pairs)


# --------------------------------------------------------------------------
# 2. The relation bound on the graph body
# --------------------------------------------------------------------------


@requires_fts5
def test_a_graph_body_carries_at_most_the_edge_bound_and_counts_the_rest(
    tmp_path: Path,
) -> None:
    """``MAX_GRAPH_EDGES`` again, because an edge list is quadratic in its nodes (D-175)."""
    over = MAX_GRAPH_EDGES + 1
    root = _corpus(
        tmp_path / "dense",
        [
            _relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=1, salt=f"-{index:05d}")
            for index in range(over)
        ],
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            page = repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
            payload = page.payload()
            assert len(payload["relations"]) == MAX_GRAPH_EDGES, label
            assert payload["counts"]["relations_returned"] == MAX_GRAPH_EDGES, label
            assert payload["counts"]["relations_omitted"] == over - MAX_GRAPH_EDGES, label
            assert payload["truncated"] is True, label
    finally:
        _closed(pairs)


@requires_fts5
def test_a_page_that_cut_the_nodes_says_so_even_on_its_last_page(
    tmp_path: Path,
) -> None:
    """``truncated`` is about the graph, not about the cursor.

    A last page with no ``next_cursor`` is still a slice of a larger graph, and
    reporting it as whole would let the Map present a cut graph as the library —
    the same rule ``/api/graph`` already carries.
    """
    root = _corpus(tmp_path / "paged", [])
    pairs = _each(root)
    try:
        for label, repo in pairs:
            cursor = None
            pages = []
            for _ in range(50):
                page = repo.source_graph(SourceGraphQuery(limit=1, cursor=cursor))
                pages.append(page)
                cursor = page.next_cursor
                if cursor is None:
                    break
            assert len(pages) == len(smc.SOURCE_IDS), label
            assert pages[-1].next_cursor is None, label
            assert all(page.truncated for page in pages), label
            assert sum(len(page.nodes) for page in pages) == len(smc.SOURCE_IDS), label
    finally:
        _closed(pairs)


# --------------------------------------------------------------------------
# 3. The neighbourhood's own bound
# --------------------------------------------------------------------------


@requires_fts5
def test_limit_bounds_the_two_directions_together_and_says_when_it_did(
    tmp_path: Path,
) -> None:
    """Applied in id order before the split, so a bound cannot erase one direction."""
    root = _corpus(
        tmp_path / "both-ways",
        [
            _relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=1, salt="-a"),
            _relation(smc.YOUTUBE_PASS, smc.TWITTER_QUOTE, basis=1, salt="-b"),
            _relation(smc.YOUTUBE_PARTIAL, smc.YOUTUBE_PASS, basis=1, salt="-c"),
        ],
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            whole = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS, limit=MAX_LIMIT)
            )
            assert len(whole.incoming) + len(whole.outgoing) == 3, label
            assert whole.truncated is False, label

            cut = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS, limit=2)
            )
            assert len(cut.incoming) + len(cut.outgoing) == 2, label
            assert cut.truncated is True, label
            carried = {
                relation["id"] for relation in (*cut.incoming, *cut.outgoing)
            }
            assert carried == set(sorted(
                relation["id"] for relation in (*whole.incoming, *whole.outgoing)
            )[:2]), label
    finally:
        _closed(pairs)


@requires_fts5
def test_a_bounded_neighbourhood_still_has_a_node_for_every_endpoint(
    tmp_path: Path,
) -> None:
    """The bound may drop a relation; it may never leave one dangling."""
    root = _corpus(
        tmp_path / "endpoints",
        [
            _relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=1, salt="-a"),
            _relation(smc.YOUTUBE_PARTIAL, smc.YOUTUBE_PASS, basis=1, salt="-b"),
        ],
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            found = repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=smc.YOUTUBE_PASS, limit=1)
            )
            addressable = {node["source_id"] for node in found.neighbors} | {
                found.source["source_id"]
            }
            for relation in (*found.incoming, *found.outgoing):
                assert {
                    relation["from_source_id"],
                    relation["to_source_id"],
                } <= addressable, label
            assert found.truncated is True, label
    finally:
        _closed(pairs)


# --------------------------------------------------------------------------
# 4. What a damaged synthesis file may not cost
# --------------------------------------------------------------------------


@requires_fts5
def test_an_unreadable_synthesis_file_costs_the_relations_and_not_the_sources(
    tmp_path: Path,
) -> None:
    """A corpus of readable sources must not become unreadable because one derived file did."""
    root = _corpus(tmp_path / "damaged", [])
    (root / "output" / "synthesis" / "source_relations.json").write_text(
        "{ not json", encoding="utf-8"
    )
    pairs = _each(root)
    try:
        for label, repo in pairs:
            page = repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
            assert len(page.nodes) == len(smc.SOURCE_IDS), label
            assert page.relations == [], label
            assert page.payload()["counts"]["relations_omitted"] == 0, label
    finally:
        _closed(pairs)


@requires_fts5
def test_an_id_repeated_in_the_file_is_served_once_by_both_readers(
    tmp_path: Path,
) -> None:
    """The gate refuses a duplicate id; a file that has one anyway was edited past it.

    Serving the record twice would draw one edge twice, and an index whose
    primary key is that id would refuse the whole scan — so the two readers have
    to agree on which of those happens, and neither may be a crash.
    """
    relation = _relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=1)
    root = _corpus(tmp_path / "duplicated", [relation, json.loads(json.dumps(relation))])
    pairs = _each(root)
    try:
        for label, repo in pairs:
            page = repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
            assert [item["id"] for item in page.relations] == [relation["id"]], label
    finally:
        _closed(pairs)


@requires_fts5
def test_no_source_graph_read_touched_a_canonical_file(tmp_path: Path) -> None:
    """The index is a cache; reading it may not move a byte or an mtime under ``output/``."""
    root = _corpus(
        tmp_path / "untouched",
        [_relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=2)],
    )
    files = sorted((root / "output").rglob("*"))
    before = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in files}

    pairs = _each(root)
    try:
        for _label, repo in pairs:
            repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
            for source_id in smc.SOURCE_IDS:
                repo.source_neighborhood(SourceNeighborhoodQuery(source_id=source_id))
    finally:
        _closed(pairs)

    after = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in files}
    assert [str(path) for path in files if before[path] != after[path]] == []


@requires_fts5
def test_the_source_layer_left_the_knowledge_map_where_it_was(tmp_path: Path) -> None:
    """D-249, at the seam: a source node is in no entity list and no entity count.

    ``tests/test_source_map_regression.py`` holds the HTTP end of this. Here it
    is the repository, over a corpus that has briefs and a relation — the state
    in which a source node is most likely to have leaked somewhere.
    """
    root = _corpus(
        tmp_path / "unmoved",
        [_relation(smc.TWITTER_QUOTE, smc.YOUTUBE_PASS, basis=1)],
    )
    plain = tmp_path / "plain"
    shutil.copytree(root, plain)
    shutil.rmtree(plain / "output" / "synthesis")
    for run in (plain / "output").iterdir():
        brief = run / "source_knowledge.json"
        if brief.is_file():
            brief.unlink()

    from x2knwldg.repository import EntityQuery, GraphQuery

    with_source_layer = MemoryRepository.from_project(root)
    entities = with_source_layer.list_entities(EntityQuery(limit=MAX_LIMIT))
    assert entities.items, "the corpus must actually hold knowledge entities"
    assert {entity["entity_type"] for entity in entities.items} <= {
        "knowledge_unit",
        "concept",
    }
    graph = with_source_layer.graph(GraphQuery(limit=MAX_LIMIT))
    assert {node["entity_type"] for node in graph.nodes} <= {"knowledge_unit", "concept"}

    without = MemoryRepository.from_project(plain)
    counted = with_source_layer.status().counts
    bare = without.status().counts
    for family in ("sources", "entities", "relations"):
        assert counted[family] == bare[family], family
    # Artifacts *do* move, and by exactly the three briefs. That is `T-252`'s
    # additive change, not `T-254`'s: a run's brief is a file the run owns, so
    # it is listed among that run's artifacts, and D-257 records the decision to
    # emit it only when the file exists. Asserted rather than excluded, so the
    # difference stays a known quantity.
    assert counted["artifacts"] - bare["artifacts"] == 3
