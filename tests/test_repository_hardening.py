"""Regression tests for defects found by audit in the ``T-007`` seam.

Every test here failed against the code as it stood. They are grouped by the
claim each one defends rather than by method, because most of the defects were
one claim being made in two places and only being true in one of them:

* the order ``ORDER_KEYS`` documents was called total and was not, so a tie
  across a page boundary deleted a record while ``total`` kept counting it;
* ``/api/graph?source_id=X`` and ``/api/sources/X/relations`` were two views of
  one fact that disagreed, 101 edges against 118;
* search read the filesystem while every other method read the index, so a run
  added after construction produced hits nothing could navigate to;
* a cut graph reported itself whole on its last page;
* a relation id the schema permits could not be paged at all.

Stdlib only, and no dependency on ``output/`` — a defect that only reproduces on
the machine that ingested a video is a defect CI cannot defend against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from x2knwldg.adapters import IndexRecords
from x2knwldg.query import run_documents
from x2knwldg.repository import (
    MAX_CURSOR_LENGTH,
    MAX_LIMIT,
    EntityQuery,
    GraphQuery,
    InvalidQuery,
    MemoryRepository,
    RelationQuery,
    RepositoryError,
    SearchQuery,
    check_index_integrity,
    decode_cursor,
    encode_cursor,
    keyset_page,
    order_key,
    page_from_window,
    sort_records,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_OUTPUT_DIR = "tests/fixtures/runs"

PASS_SOURCE = "youtube:fixture-pass"
PARTIAL_SOURCE = "youtube:fixture-partial"
FAIL_SOURCE = "youtube:fixture-fail"


# --------------------------------------------------------------------------
# Record builders — inputs to the code under test, never opinions from it
# --------------------------------------------------------------------------


def source_record(source_id: str, *, canonical_dir: str | None) -> dict[str, Any]:
    source_type, external_id = source_id.split(":", 1)
    return {
        "schema_version": "1.0",
        "id": source_id,
        "source_type": source_type,
        "external_id": external_id,
        "canonical_dir": canonical_dir,
        "status": {"overall": "UNKNOWN"},
        "adapter": {"name": source_type, "version": "0"},
    }


def entity_record(global_id: str, **overrides: Any) -> dict[str, Any]:
    source_type, external_id, local_id = global_id.split(":", 2)
    record = {
        "schema_version": "1.0",
        "global_id": global_id,
        "source_type": source_type,
        "external_id": external_id,
        "local_id": local_id,
        "source_id": f"{source_type}:{external_id}",
        "entity_type": "knowledge_unit",
        "provenance_class": "source",
        "kind": "principle",
        "label": local_id,
    }
    record.update(overrides)
    return record


def concept_record(local_id: str) -> dict[str, Any]:
    return entity_record(
        f"library:concepts:{local_id}",
        source_id=None,
        entity_type="concept",
        provenance_class="derived",
        kind="canonical_concept",
        library_id=f"concept:{local_id}",
    )


def relation_record(from_id: str, relation: str, to_id: str, **overrides: Any) -> dict[str, Any]:
    record = {
        "schema_version": "1.0",
        "id": f"{from_id}|{relation}|{to_id}",
        "from_id": from_id,
        "to_id": to_id,
        "relation": relation,
        "relation_vocabulary": "canonical",
        "provenance_class": "source",
        "confidence": 0.9,
        "source_id": ":".join(from_id.split(":")[:2]),
    }
    record.update(overrides)
    return record


def write_run(run_dir: Path, *, video_id: str, text: str = "gravity pulls things down") -> None:
    """A minimal but real canonical run — the files ``run_documents`` reads."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metadata.json").write_text(
        json.dumps({"schema_version": "1.0", "video_id": video_id, "title": f"Run {video_id}"}),
        encoding="utf-8",
    )
    (run_dir / "knowledge_units.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "video_id": video_id,
                "units": [
                    {
                        "id": "KU-000001",
                        "kind": "principle",
                        "source_class": "source",
                        "content": text,
                        "confidence": 0.9,
                        "source": {"start_sec": 1, "end_sec": 2, "evidence_excerpt": text},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def repo() -> MemoryRepository:
    return MemoryRepository.from_project(PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR)


# --------------------------------------------------------------------------
# 1. The order is total, and a duplicate id is detectable (base.order_key)
# --------------------------------------------------------------------------


def test_a_tie_at_a_page_boundary_does_not_delete_a_record() -> None:
    """``ORDER_KEYS`` claimed a total order over a field nothing kept unique.

    Two relations sharing an id sorted equal, so ``key > cursor`` skipped the
    second one: a full walk returned one record while ``total`` reported two —
    a silent deletion, and the worst possible way to be wrong about data.
    """
    twins = [
        relation_record("youtube:a:KU-1", "supports", "youtube:a:KU-2", confidence=0.1),
        relation_record("youtube:a:KU-1", "supports", "youtube:a:KU-2", confidence=0.9),
    ]
    ordered = sort_records(twins, "indexed_relation")
    assert order_key(ordered[0], "indexed_relation") != order_key(
        ordered[1], "indexed_relation"
    ), "records that differ must not share an order key"

    walked: list[dict] = []
    cursor: str | None = None
    for _ in range(10):
        page = keyset_page(ordered, RelationQuery(limit=1, cursor=cursor), "indexed_relation")
        walked.extend(page.items)
        assert page.total == 2
        cursor = page.next_cursor
        if cursor is None:
            break
    assert sorted(item["confidence"] for item in walked) == [0.1, 0.9]


def test_an_index_that_files_one_record_twice_is_refused_not_served() -> None:
    """A true duplicate is one record filed twice; the seam says so out loud."""
    twin = relation_record("youtube:a:KU-1", "supports", "youtube:a:KU-2")
    records = IndexRecords(
        entities=[entity_record("youtube:a:KU-1"), entity_record("youtube:a:KU-2")],
        relations=[dict(twin), dict(twin)],
    )
    with pytest.raises(RepositoryError) as raised:
        MemoryRepository(records, project_root=PROJECT_ROOT)
    assert "claimed twice" in str(raised.value)


def test_an_artifact_and_an_entity_may_not_share_a_global_id() -> None:
    """One namespace per source, so uniqueness is checked across both families."""
    with pytest.raises(RepositoryError):
        check_index_integrity(
            {
                "artifact": [{"id": "youtube:a:metadata"}],
                "entity_ref": [entity_record("youtube:a:metadata")],
            }
        )


def test_an_edge_may_not_name_an_endpoint_no_record_has() -> None:
    """A dangling edge is a graph the Map cannot draw and a list that shows it."""
    with pytest.raises(RepositoryError) as raised:
        MemoryRepository(
            IndexRecords(
                entities=[entity_record("youtube:a:KU-1")],
                relations=[relation_record("youtube:a:KU-1", "supports", "youtube:a:KU-2")],
            ),
            project_root=PROJECT_ROOT,
        )
    assert "which no entity record has" in str(raised.value)


# --------------------------------------------------------------------------
# 2. A relation id the schema permits can be paged (base.encode_cursor)
# --------------------------------------------------------------------------


def _long_ids() -> tuple[str, str]:
    """A global id at the schema's limit: 256-character parts (``idPart``)."""
    part = "x" * 256
    return f"youtube:{part}:{part}", f"youtube:{part}"


def test_a_schema_legal_relation_id_can_be_paged() -> None:
    """``IndexedRelation.id`` is 1300 characters by schema; a cursor is 512.

    Encoding the key verbatim overflowed the contract's cursor and the seam
    raised ``500`` — a record the schema permits, refused by the code that is
    supposed to serve it.
    """
    global_id, source_id = _long_ids()
    relations = [
        relation_record(global_id, "supports", global_id, source_id=source_id),
        relation_record(global_id, "zzz_last", global_id, source_id=source_id),
    ]
    assert len(relations[0]["id"]) > MAX_CURSOR_LENGTH
    repo = MemoryRepository(
        IndexRecords(entities=[entity_record(global_id)], relations=relations),
        project_root=PROJECT_ROOT,
    )

    walked: list[dict] = []
    cursor: str | None = None
    for _ in range(10):
        page = repo.list_relations(RelationQuery(limit=1, cursor=cursor))
        walked.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
        assert len(cursor) <= MAX_CURSOR_LENGTH, "the contract caps a cursor at 512"
    assert [item["relation"] for item in walked] == ["supports", "zzz_last"]


def test_a_cursor_naming_a_vanished_long_key_is_refused_not_guessed() -> None:
    """A short cursor cannot re-find a record that is gone. It says so."""
    global_id, _ = _long_ids()
    key = order_key(relation_record(global_id, "supports", global_id), "indexed_relation")
    token = encode_cursor("f" * 16, key)
    cursor = decode_cursor(token, "f" * 16)
    assert cursor.key is None, "a key this long is carried as a prefix and a digest"
    with pytest.raises(InvalidQuery):
        cursor.tail([{"k": key + "-changed"}], lambda row: row["k"])


# --------------------------------------------------------------------------
# 3. A cursor is authenticated, not merely parsed (base.query_fingerprint)
# --------------------------------------------------------------------------


def _mint(body: dict[str, Any]) -> str:
    """A cursor minted the way anyone could mint one: base64url of JSON.

    This is exactly what the seam used to issue and accept, which is what made a
    cursor forgeable. It is not what it issues now, so this token has to be
    refused — it carries no proof that this process produced it.
    """
    import base64

    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def test_a_cursor_this_process_did_not_sign_is_refused(repo: MemoryRepository) -> None:
    """A cursor used to be an unkeyed hash, so anything could mint one.

    Query-binding was already right — a cursor from another collection is
    refused — but the *position* inside a correctly fingerprinted cursor was
    taken on trust, and the fingerprint is a public digest of public filters.
    """
    fingerprint = EntityQuery(limit=1).fingerprint
    forged = _mint({"f": fingerprint, "k": f"{PASS_SOURCE}:KU-000001"})
    with pytest.raises(InvalidQuery):
        repo.list_entities(EntityQuery(limit=1, cursor=forged))


def test_a_forged_search_offset_is_refused(repo: MemoryRepository) -> None:
    """A search cursor's offset indexes real work, so it is authenticated."""
    query = SearchQuery(q="the", limit=1)
    forged = _mint({"f": query.fingerprint, "k": "5"})
    with pytest.raises(InvalidQuery):
        repo.search(SearchQuery(q="the", limit=1, cursor=forged))


def test_a_cursor_this_process_did_sign_still_works(repo: MemoryRepository) -> None:
    """Authenticating a cursor must not stop it being a cursor."""
    first = repo.list_entities(EntityQuery(limit=1))
    assert first.next_cursor
    second = repo.list_entities(EntityQuery(limit=1, cursor=first.next_cursor))
    assert second.items[0]["global_id"] > first.items[0]["global_id"]
    assert decode_cursor(encode_cursor("a" * 16, "youtube:a:KU-1"), "a" * 16).key == (
        "youtube:a:KU-1"
    )


# --------------------------------------------------------------------------
# 4. The graph and the relations list are two views of one fact
# --------------------------------------------------------------------------


def library_records() -> IndexRecords:
    """Fixture runs plus the cross-source concepts a built library adds."""
    from x2knwldg.adapters import adapt_project

    concepts = [concept_record("aaaa00000001"), concept_record("bbbb00000002")]
    edges = [
        relation_record(
            f"{PASS_SOURCE}:KU-000001",
            "expresses_concept",
            "library:concepts:aaaa00000001",
            relation_vocabulary="library_synthetic",
            provenance_class="derived",
            source_id=None,
        ),
        relation_record(
            f"{PASS_SOURCE}:KU-D-0001",
            "expresses_concept",
            "library:concepts:bbbb00000002",
            relation_vocabulary="library_synthetic",
            provenance_class="derived",
            source_id=None,
        ),
        relation_record(
            f"{PARTIAL_SOURCE}:KU-000001",
            "expresses_concept",
            "library:concepts:aaaa00000001",
            relation_vocabulary="library_synthetic",
            provenance_class="derived",
            source_id=None,
        ),
    ]
    return adapt_project(PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR) + IndexRecords(
        entities=concepts, relations=edges
    )


@pytest.fixture(scope="module")
def library_repo() -> MemoryRepository:
    return MemoryRepository(
        library_records(), project_root=PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR
    )


def _walk_relations(
    repo: MemoryRepository, source_id: str | None, vocabulary: str | None = None
) -> set[str]:
    found: set[str] = set()
    cursor: str | None = None
    for _ in range(1000):
        page = repo.list_relations(
            RelationQuery(
                limit=2, cursor=cursor, source_id=source_id, relation_vocabulary=vocabulary
            )
        )
        found |= {edge["id"] for edge in page.items}
        cursor = page.next_cursor
        if cursor is None:
            return found
    raise AssertionError("pagination did not terminate")


def _walk_graph(
    repo: MemoryRepository, source_id: str | None, vocabulary: str | None = None
) -> tuple[set[str], set[str]]:
    nodes: set[str] = set()
    edges: set[str] = set()
    cursor: str | None = None
    for _ in range(1000):
        page = repo.graph(
            GraphQuery(
                limit=2, cursor=cursor, source_id=source_id, relation_vocabulary=vocabulary
            )
        )
        nodes |= {node["global_id"] for node in page.nodes}
        edges |= {edge["id"] for edge in page.edges}
        cursor = page.next_cursor
        if cursor is None:
            return nodes, edges
    raise AssertionError("pagination did not terminate")


@pytest.mark.parametrize("source_id", [None, PASS_SOURCE, PARTIAL_SOURCE, FAIL_SOURCE])
@pytest.mark.parametrize("vocabulary", [None, "canonical", "library_synthetic"])
def test_the_graph_shows_exactly_the_relations_the_relations_endpoint_lists(
    library_repo: MemoryRepository, source_id: str | None, vocabulary: str | None
) -> None:
    """One fact, one home.

    ``/api/sources/X/relations`` counts an edge as X's when X produced it *or*
    when either endpoint is X's entity (D-034) — which is what keeps the
    ``expresses_concept`` edges, whose ``source_id`` is null (D-025), attached
    to the source that makes them. ``/api/graph?source_id=X`` applied a second
    rule and required both endpoints to be entities *of X*; a concept belongs to
    no source (D-016), so the graph dropped every one of those edges. Over the
    real sample that was 101 edges against 118, with none of the 17
    ``expresses_concept`` edges in the graph at all.
    """
    nodes, edges = _walk_graph(library_repo, source_id, vocabulary)
    assert edges == _walk_relations(library_repo, source_id, vocabulary)
    whole = library_repo.graph(
        GraphQuery(limit=MAX_LIMIT, source_id=source_id, relation_vocabulary=vocabulary)
    )
    for edge in whole.edges:
        assert edge["from_id"] in nodes and edge["to_id"] in nodes, "no edge may dangle"


def test_a_source_graph_reaches_the_concepts_that_source_expresses(
    library_repo: MemoryRepository,
) -> None:
    page = library_repo.graph(GraphQuery(limit=MAX_LIMIT, source_id=PASS_SOURCE))
    expresses = [edge for edge in page.edges if edge["relation"] == "expresses_concept"]
    assert len(expresses) == 2
    concepts = {node["global_id"] for node in page.nodes if node["entity_type"] == "concept"}
    assert concepts == {edge["to_id"] for edge in expresses}


def test_a_node_filter_the_client_asked_for_still_removes_its_edges(
    library_repo: MemoryRepository,
) -> None:
    """Widening membership must not widen a filter the client set itself."""
    page = library_repo.graph(
        GraphQuery(limit=MAX_LIMIT, source_id=PASS_SOURCE, provenance_class="source")
    )
    assert all(node["provenance_class"] == "source" for node in page.nodes)
    visible = {node["global_id"] for node in page.nodes}
    for edge in page.edges:
        assert edge["from_id"] in visible and edge["to_id"] in visible


# --------------------------------------------------------------------------
# 5. A cut graph never says it is whole
# --------------------------------------------------------------------------


def test_the_last_page_of_a_cut_graph_still_says_it_was_cut(
    library_repo: MemoryRepository,
) -> None:
    """``truncated`` tracked the cursor, and the last page has no cursor.

    So a walk ended by presenting its final slice as the whole graph — which for
    a Map is the difference between "here is your library" and "here are the
    last two nodes of it".
    """
    pages = []
    cursor: str | None = None
    for _ in range(1000):
        page = library_repo.graph(GraphQuery(limit=2, cursor=cursor))
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(pages) > 1, "the fixtures must not fit in one page for this to mean anything"
    assert pages[-1].next_cursor is None
    assert all(page.truncated for page in pages), "every page of a paged graph is a slice"

    whole = library_repo.graph(GraphQuery(limit=MAX_LIMIT))
    assert whole.truncated is False, "a graph that fits in one page is not truncated"


# --------------------------------------------------------------------------
# 6. Search resolves against the index, not the filesystem
# --------------------------------------------------------------------------


def _repo_over(tmp_path: Path, *runs: tuple[str, str]) -> MemoryRepository:
    """A repository whose ``Source`` records point at real run directories."""
    sources = []
    for directory, video_id in runs:
        write_run(tmp_path / "output" / directory, video_id=video_id)
        sources.append(
            source_record(f"youtube:{video_id}", canonical_dir=f"output/{directory}")
        )
    return MemoryRepository(IndexRecords(sources=sources), project_root=tmp_path)


def test_a_run_added_after_the_index_was_built_does_not_appear_in_search(
    tmp_path: Path,
) -> None:
    """Case 08: search walked ``output/`` and every other method read the index.

    So a run finalised after construction was searched anyway, and every hit it
    produced carried ``source_id: null`` — renderable, and unnavigable, because
    no ``Source`` record existed to resolve it against.
    """
    repo = _repo_over(tmp_path, ("indexed", "indexed-id"))
    write_run(tmp_path / "output" / "later", video_id="later-id")

    hits = repo.search(SearchQuery(q="gravity", limit=MAX_LIMIT)).items
    assert hits, "the indexed run still answers"
    assert all(hit["source_id"] is not None for hit in hits), (
        "a hit the client cannot navigate to is a hit the seam must not emit"
    )
    assert {hit["video_id"] for hit in hits} == {"indexed-id"}


def test_every_search_hit_names_a_source_the_seam_will_answer_for(
    repo: MemoryRepository,
) -> None:
    for hit in repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items:
        assert repo.get_source(hit["source_id"]) is not None


def test_a_run_directory_the_seam_itself_named_is_still_searchable(tmp_path: Path) -> None:
    """The API refused an id it had issued, and named a host directory doing it.

    ``search`` rebuilt the run directory's *name* and pushed it back through
    ``pipeline.resolve_run_dir``, so a directory containing a space came back as
    ``400 invalid_id`` for the perfectly good source id the client had been
    given — and the error body carried the directory name, which is a fact about
    the host filesystem and none of a client's business (D-030).
    """
    repo = _repo_over(tmp_path, ("a run with spaces", "spaced-id"))
    try:
        page = repo.search(SearchQuery(q="gravity", source_id="youtube:spaced-id"))
    except RepositoryError as exc:  # pragma: no cover - the defect this defends
        message = str(exc)
        assert "a run with spaces" not in message and str(tmp_path) not in message, (
            "an error body disclosed the host filesystem layout"
        )
        pytest.fail(f"the seam refused a source id it issued itself: {message}")
    assert [hit["source_id"] for hit in page.items] == ["youtube:spaced-id"]


def test_a_source_whose_canonical_files_cannot_be_read_reports_an_unknown_total(
    tmp_path: Path,
) -> None:
    """``total: 0`` says "we looked and found none". Null says "we could not look"."""
    run = tmp_path / "output" / "damaged"
    run.mkdir(parents=True)
    (run / "metadata.json").write_text('{"video_id": "damaged-id"}', encoding="utf-8")
    (run / "knowledge_units.json").write_text("{ not json", encoding="utf-8")
    repo = MemoryRepository(
        IndexRecords(sources=[source_record("youtube:damaged-id", canonical_dir="output/damaged")]),
        project_root=tmp_path,
    )
    page = repo.search(SearchQuery(q="gravity"))
    assert page.items == []
    assert page.total is None, "an unreadable run has an unknown hit count, not zero"


def test_a_source_that_states_no_directory_reports_an_unknown_total(tmp_path: Path) -> None:
    """The frozen contract: null is *unknown*, and it never stands in for zero."""
    repo = MemoryRepository(
        IndexRecords(sources=[source_record("youtube:nowhere", canonical_dir=None)]),
        project_root=tmp_path,
    )
    page = repo.search(SearchQuery(q="gravity", source_id="youtube:nowhere"))
    assert page.items == []
    assert page.total is None, "the source is indexed; what it holds is unknown, not none"


def test_a_searched_source_that_matched_nothing_reports_zero(repo: MemoryRepository) -> None:
    """The other half of the distinction: zero is a fact, and it is still stated."""
    assert repo.search(SearchQuery(q="zzqxwphgb")).total == 0


def test_paging_a_search_does_not_re_read_the_library_for_every_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-reading and rescoring per page made a walk cost the library per page.

    Measured over the real sample before the fix: 0.408s to walk 253 hits at
    ``limit=1`` against 0.029s after, and 1.8ms per page against 0.16ms. What
    that comes down to is this assertion — after the corpus exists, paging reads
    no files at all.
    """
    repo = _repo_over(tmp_path, ("one", "one-id"), ("two", "two-id"))

    reads: list[str] = []
    original = Path.read_text

    def counted(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted)

    first = repo.search(SearchQuery(q="gravity", limit=1))
    assert reads, "the first search reads the canonical files it ranks"
    reads.clear()

    cursor = first.next_cursor
    for _ in range(100):
        page = repo.search(SearchQuery(q="gravity", limit=1, cursor=cursor))
        cursor = page.next_cursor
        if cursor is None:
            break
    assert reads == [], "a later page must not re-read a canonical file"


def test_the_seam_and_the_cli_score_with_the_same_rule(tmp_path: Path) -> None:
    """``run_documents`` is one corpus builder, so the two cannot drift apart."""
    write_run(tmp_path / "output" / "one", video_id="one-id")
    documents = run_documents(tmp_path / "output" / "one")
    assert [document.hit["type"] for document in documents] == ["knowledge_unit"]

    repo = _repo_over(tmp_path, ("one", "one-id"))
    hit = repo.search(SearchQuery(q="gravity")).items[0]
    assert {key: hit[key] for key in documents[0].hit} == dict(documents[0].hit)
    assert hit["source_id"] == "youtube:one-id"
    assert hit["global_id"] == "youtube:one-id:KU-000001"


# --------------------------------------------------------------------------
# 7. The paging seam a second implementation can share
# --------------------------------------------------------------------------


def test_a_backend_that_seeks_for_itself_builds_the_identical_page(
    repo: MemoryRepository,
) -> None:
    """``T-104`` compares pages; it must not compare two cursor implementations.

    ``keyset_page`` takes a materialised sequence, which SQLite cannot hand it.
    :func:`page_from_window` is the half that has to be shared — the probe row,
    the cut, and the next cursor — so a ``SELECT … WHERE key > :prefix ORDER BY
    key LIMIT :limit + 1`` produces the same page through the same code.
    """
    ordered = sort_records(
        [
            record
            for record in repo.list_relations(RelationQuery(limit=MAX_LIMIT)).items
        ],
        "indexed_relation",
    )
    assert len(ordered) > 3, "the fixtures must span more than one page here"

    query = RelationQuery(limit=2)
    assert page_from_window(ordered[:3], query, "indexed_relation", total=len(ordered)) == (
        repo.list_relations(query)
    )

    resumed = RelationQuery(limit=2, cursor=repo.list_relations(query).next_cursor)
    position = resumed.start()
    # What a SQL backend does: seek on the indexed id column, take limit + 1.
    seeked = [row for row in ordered if row["id"] >= position.identity_bound]
    exact = position.tail(seeked, lambda row: order_key(row, "indexed_relation"))
    assert page_from_window(
        exact[:3], resumed, "indexed_relation", total=len(ordered)
    ) == repo.list_relations(resumed)
