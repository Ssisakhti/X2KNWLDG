"""Behaviour tests for the indexer ↔ API seam (``T-007``).

``tests/test_api_contract.py`` asks whether the repository's payloads fit the
frozen HTTP contract. This module asks what the schemas cannot: what the seam
**refuses**, what it never invents, and what has to stay true of any second
implementation — because ``T-101``–``T-104`` will write one over SQLite and
``T-105``–``T-108`` must not be able to tell the difference.

Stdlib only. The repository is stdlib-only, so it keeps working on a bare core
install (ADR 0001 invariant 5) and these tests run there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from x2knwldg.adapters import ADAPTERS, IndexRecords, adapt_project
from x2knwldg.repository import (
    DEFAULT_LIMIT,
    INDEX_STATES,
    MAX_CURSOR_LENGTH,
    MAX_LIMIT,
    EntityQuery,
    GraphQuery,
    IndexRepository,
    IndexStatus,
    IndexUnavailable,
    InvalidId,
    InvalidQuery,
    MemoryRepository,
    NeighborhoodQuery,
    Page,
    RelationQuery,
    RepositoryError,
    SearchQuery,
    SourceQuery,
    decode_cursor,
    encode_cursor,
    relation_belongs_to_source,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_OUTPUT_DIR = "tests/fixtures/runs"
FIXTURE_RUNS = PROJECT_ROOT / FIXTURE_OUTPUT_DIR
SAMPLE_DIR = PROJECT_ROOT / "output" / "pqlWNihgdjI"

#: The fixture runs, by the ``external_id`` their metadata declares — which is
#: deliberately not their directory name, so nothing here can quietly assume the
#: two are the same string.
PASS_SOURCE = "youtube:fixture-pass"
PARTIAL_SOURCE = "youtube:fixture-partial"
FAIL_SOURCE = "youtube:fixture-fail"

requires_sample = pytest.mark.skipif(
    not (SAMPLE_DIR / "metadata.json").exists(),
    reason="output/ is gitignored; the real sample is present only on a machine that ingested it",
)


@pytest.fixture(scope="module")
def repo() -> MemoryRepository:
    """The committed fixture runs — a PASS, a PARTIAL and a FAIL (``T-006``)."""
    return MemoryRepository.from_project(PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR)


def _fixture_json(path: Path) -> dict:
    """A committed canonical file, read directly rather than through an adapter."""
    return json.loads(path.read_text(encoding="utf-8"))


def _source_record(source_id: str, *, canonical_dir: str | None) -> dict[str, Any]:
    """A minimal ``Source``, for the cases no committed run can express."""
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


def walk(method: Callable[[Any], Page], query_type, *, limit: int = 2, **filters) -> list[dict]:
    """Every record a paged method yields, walked to the end."""
    collected: list[dict] = []
    cursor: str | None = None
    for _ in range(1000):
        page = method(query_type(limit=limit, cursor=cursor, **filters))
        collected.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return collected
    raise AssertionError("pagination did not terminate")


# --------------------------------------------------------------------------
# 1. The seam covers the frozen surface, and nothing else
# --------------------------------------------------------------------------

#: Every endpoint of ``schemas/api/v1/openapi.json``, and the method that
#: answers it. Written out so that adding an endpoint without deciding how the
#: repository serves it fails here rather than in a route.
ENDPOINT_METHODS = {
    "/api/status": "status",
    "/api/sources": "list_sources",
    "/api/sources/{source_id}": "get_source",
    "/api/sources/{source_id}/entities": "list_entities",
    "/api/sources/{source_id}/relations": "list_relations",
    "/api/entities/{entity_id}": "get_entity",
    "/api/artifacts/{artifact_id}": "get_artifact",
    "/api/media/{artifact_id}": "get_artifact",
    "/api/search": "search",
    "/api/graph": "graph",
    "/api/graph/neighborhood/{entity_id}": "neighborhood",
}


def test_the_reference_implementation_satisfies_the_protocol(repo: MemoryRepository) -> None:
    assert isinstance(repo, IndexRepository)


@pytest.mark.parametrize("endpoint,method", sorted(ENDPOINT_METHODS.items()))
def test_every_frozen_endpoint_has_a_method(endpoint: str, method: str) -> None:
    assert callable(getattr(MemoryRepository, method)), endpoint
    assert hasattr(IndexRepository, method), f"{endpoint} is served by nothing in the protocol"


def test_media_is_served_from_the_artifact_record_not_a_second_method() -> None:
    """``T-108`` owns path safety and range requests; the repository owns the record.

    Two ways to reach a file would be two places for path traversal to be got
    wrong (risk R14).
    """
    assert ENDPOINT_METHODS["/api/media/{artifact_id}"] == "get_artifact"
    assert not hasattr(MemoryRepository, "read_media")


# --------------------------------------------------------------------------
# 2. Status — an empty index and an unbuilt one are different answers (D-030)
# --------------------------------------------------------------------------


def test_status_counts_what_the_canonical_fixture_files_hold(repo: MemoryRepository) -> None:
    """A count is a cache convenience, reproducible from the canonical files.

    Reproducible *from the files* — this used to compute its expectation by
    calling the same ``adapt_project`` the repository was built from, so the two
    sides could only ever agree and the assertion could not fail. The counts
    below are read out of the committed fixture JSON instead.
    """
    counts = repo.status().payload()["counts"]

    runs = sorted(FIXTURE_RUNS.glob("*/metadata.json"))
    units = [
        unit
        for path in runs
        for unit in _fixture_json(path.parent / "knowledge_units.json")["units"]
    ]
    stated = [
        edge
        for path in runs
        for edge in _fixture_json(path.parent / "relationships.json")["relationships"]
    ]
    derived = [unit for unit in units if unit.get("derived_from")]

    assert counts["sources"] == len(runs) == 3
    assert counts["entities"] == len(units) == 6, "one entity per canonical knowledge unit"
    assert counts["relations"] == len(stated) + len(derived) == 6, (
        "every stated relationship, plus the derived_from edge each derived unit "
        "carries (D-025)"
    )
    # An artifact per file the run holds, plus the one external artifact — the
    # video itself, which has a URL and no local path.
    on_disk = sum(1 for path in runs for f in path.parent.rglob("*") if f.is_file())
    assert counts["artifacts"] == on_disk + len(runs) == 54


def test_status_tallies_the_copied_statuses_and_never_invents_one(repo: MemoryRepository) -> None:
    tally = repo.status().payload()["sources_by_status"]
    assert tally == {"FAIL": 1, "PARTIAL": 1, "PASS": 1, "UNKNOWN": 0}
    assert sum(tally.values()) == 3, "every source is counted exactly once"


def test_status_names_the_adapters_that_produced_the_records(repo: MemoryRepository) -> None:
    names = {adapter["name"] for adapter in repo.status().payload()["adapters"]}
    assert names == set(ADAPTERS)


def test_a_repository_with_no_index_still_answers_status() -> None:
    repo = MemoryRepository.unavailable("absent")
    payload = repo.status().payload()
    assert payload["index"]["state"] == "absent"
    assert payload["counts"] == {"sources": 0, "artifacts": 0, "entities": 0, "relations": 0}


@pytest.mark.parametrize("state", ["absent", "building", "error"])
def test_every_question_but_status_is_refused_while_not_ready(state: str) -> None:
    repo = MemoryRepository.unavailable(state)
    calls = [
        lambda: repo.list_sources(SourceQuery()),
        lambda: repo.get_source(PASS_SOURCE),
        lambda: repo.list_entities(EntityQuery()),
        lambda: repo.list_relations(RelationQuery()),
        lambda: repo.get_entity(f"{PASS_SOURCE}:KU-000001"),
        lambda: repo.get_artifact(f"{PASS_SOURCE}:metadata"),
        lambda: repo.search(SearchQuery(q="anything")),
        lambda: repo.graph(GraphQuery()),
        lambda: repo.neighborhood(NeighborhoodQuery(entity_id=f"{PASS_SOURCE}:KU-000001")),
    ]
    for call in calls:
        with pytest.raises(IndexUnavailable) as raised:
            call()
        assert raised.value.state == state
        assert raised.value.http_status == 503
        assert raised.value.code == "index_unavailable"


def test_an_index_state_outside_the_contract_is_refused() -> None:
    with pytest.raises(RepositoryError):
        IndexStatus(state="fine")
    for state in INDEX_STATES:
        assert IndexStatus(state=state).state == state


# --------------------------------------------------------------------------
# 3. The error taxonomy is D-030, executable
# --------------------------------------------------------------------------


def test_the_taxonomy_maps_one_to_one_onto_the_frozen_error_codes() -> None:
    assert (InvalidId.code, InvalidId.http_status) == ("invalid_id", 400)
    assert (InvalidQuery.code, InvalidQuery.http_status) == ("invalid_request", 400)
    assert (IndexUnavailable.code, IndexUnavailable.http_status) == ("index_unavailable", 503)
    assert issubclass(InvalidId, RepositoryError)


@pytest.mark.parametrize("bad", ["../other", "youtube:../other", "notasourceid", "", ":", "a:b:c"])
def test_a_malformed_source_id_is_refused_before_anything_is_read(
    repo: MemoryRepository, bad: str
) -> None:
    """D-020 over the seam: a lookup fails; it never silently reads another run."""
    with pytest.raises(InvalidId):
        repo.get_source(bad)
    with pytest.raises(InvalidId):
        EntityQuery(source_id=bad)
    with pytest.raises(InvalidId):
        RelationQuery(source_id=bad)


@pytest.mark.parametrize("bad", ["../other", "youtube:only-two", "", "youtube:a:.."])
def test_a_malformed_entity_id_is_refused(repo: MemoryRepository, bad: str) -> None:
    with pytest.raises(InvalidId):
        repo.get_entity(bad)
    with pytest.raises(InvalidId):
        repo.get_artifact(bad)
    with pytest.raises(InvalidId):
        NeighborhoodQuery(entity_id=bad)


def test_a_well_formed_id_that_names_nothing_is_absence_not_an_error(
    repo: MemoryRepository,
) -> None:
    """The API renders ``None`` as ``404``; that is not the repository's call."""
    assert repo.get_source("youtube:no-such-run") is None
    assert repo.get_entity("youtube:no-such-run:KU-000001") is None
    assert repo.get_artifact("youtube:no-such-run:metadata") is None
    assert repo.neighborhood(NeighborhoodQuery(entity_id="youtube:no-such:KU-1")) is None
    assert repo.list_entities(EntityQuery(source_id="youtube:no-such-run")).items == []


@pytest.mark.parametrize("limit", [0, -1, MAX_LIMIT + 1, True, 1.5, "50", None])
def test_a_limit_outside_the_contract_is_refused(limit: Any) -> None:
    with pytest.raises(InvalidQuery):
        SourceQuery(limit=limit)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "GREEN"},
        {"status": "pass"},
        {"source_type": "YouTube"},
        {"source_type": "youtube!"},
    ],
)
def test_an_unknown_source_filter_is_refused(kwargs: dict) -> None:
    with pytest.raises((InvalidQuery, InvalidId)):
        SourceQuery(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provenance_class": "sources"},
        {"kind": "not_a_kind"},
        {"min_confidence": 1.5},
        {"min_confidence": -0.1},
        {"min_confidence": "0.5"},
    ],
)
def test_an_unknown_entity_filter_is_refused(kwargs: dict) -> None:
    with pytest.raises(InvalidQuery):
        EntityQuery(**kwargs)


def test_an_unknown_relation_vocabulary_is_refused() -> None:
    with pytest.raises(InvalidQuery):
        RelationQuery(relation_vocabulary="synthetic")
    with pytest.raises(InvalidQuery):
        GraphQuery(relation_vocabulary="synthetic")


@pytest.mark.parametrize("q", ["", "   ", None, 5])
def test_an_empty_search_is_a_bad_request_not_an_empty_result(q: Any) -> None:
    with pytest.raises(InvalidQuery):
        SearchQuery(q=q)


def test_an_over_long_search_query_is_refused() -> None:
    with pytest.raises(InvalidQuery):
        SearchQuery(q="x" * 513)


@pytest.mark.parametrize("depth", [0, 4, True, 1.0])
def test_a_depth_outside_the_contract_is_refused(depth: Any) -> None:
    with pytest.raises(InvalidQuery):
        NeighborhoodQuery(entity_id=f"{PASS_SOURCE}:KU-000001", depth=depth)


def test_the_contract_bounds_are_the_frozen_ones() -> None:
    assert (DEFAULT_LIMIT, MAX_LIMIT, MAX_CURSOR_LENGTH) == (50, 500, 512)


# --------------------------------------------------------------------------
# 4. Cursors — opaque outside, bound to their query
# --------------------------------------------------------------------------


def test_a_full_walk_yields_every_record_exactly_once(repo: MemoryRepository) -> None:
    sources = walk(repo.list_sources, SourceQuery)
    entities = walk(repo.list_entities, EntityQuery)
    relations = walk(repo.list_relations, RelationQuery)
    assert [s["id"] for s in sources] == sorted({s["id"] for s in sources})
    assert [e["global_id"] for e in entities] == sorted({e["global_id"] for e in entities})
    assert [r["id"] for r in relations] == sorted({r["id"] for r in relations})
    assert len(sources) == 3


def test_the_last_page_says_so(repo: MemoryRepository) -> None:
    page = repo.list_sources(SourceQuery(limit=MAX_LIMIT))
    assert page.next_cursor is None
    assert page.total == 3
    assert page.page_info() == {"limit": MAX_LIMIT, "next_cursor": None, "total": 3}


def test_an_empty_collection_pages_to_nothing_without_a_cursor(repo: MemoryRepository) -> None:
    page = repo.list_entities(EntityQuery(source_id="youtube:no-such-run"))
    assert (page.items, page.next_cursor, page.total) == ([], None, 0)


def test_a_cursor_stays_within_the_length_the_contract_allows(repo: MemoryRepository) -> None:
    page = repo.list_entities(EntityQuery(limit=1))
    assert page.next_cursor and len(page.next_cursor) <= MAX_CURSOR_LENGTH


def test_changing_a_filter_invalidates_the_cursor(repo: MemoryRepository) -> None:
    """Re-anchoring would return a page of a collection nobody asked for."""
    page = repo.list_entities(EntityQuery(limit=1, source_id=PASS_SOURCE))
    assert page.next_cursor
    with pytest.raises(InvalidQuery):
        repo.list_entities(
            EntityQuery(limit=1, cursor=page.next_cursor, source_id=FAIL_SOURCE)
        )


def test_changing_the_page_size_does_not_invalidate_the_cursor(repo: MemoryRepository) -> None:
    """A keyset cursor is a position, not an offset, so the page size is free."""
    first = repo.list_entities(EntityQuery(limit=1))
    assert first.next_cursor
    wider = repo.list_entities(EntityQuery(limit=MAX_LIMIT, cursor=first.next_cursor))
    assert wider.items
    assert wider.items[0]["global_id"] > first.items[-1]["global_id"]


def test_a_cursor_from_another_collection_is_refused(repo: MemoryRepository) -> None:
    sources = repo.list_sources(SourceQuery(limit=1))
    assert sources.next_cursor
    with pytest.raises(InvalidQuery):
        repo.list_entities(EntityQuery(limit=1, cursor=sources.next_cursor))


@pytest.mark.parametrize("token", ["not-base64!!", "", "e30", "eyJmIjogIngifQ", "x" * 600])
def test_a_cursor_this_repository_did_not_issue_is_refused(token: str) -> None:
    with pytest.raises(InvalidQuery):
        decode_cursor(token, "0" * 16)


def test_a_cursor_round_trips_only_under_its_own_fingerprint() -> None:
    token = encode_cursor("abc", "youtube:x:KU-1")
    assert decode_cursor(token, "abc").key == "youtube:x:KU-1"
    with pytest.raises(InvalidQuery):
        decode_cursor(token, "def")


def test_the_cursor_is_opaque_to_its_caller() -> None:
    """The contract calls it opaque; nothing outside the repository may parse it."""
    token = encode_cursor("abc", "youtube:x:KU-1")
    assert "youtube:x:KU-1" not in token


# --------------------------------------------------------------------------
# 5. Filters mean what the contract says they mean
# --------------------------------------------------------------------------


def test_sources_filter_by_the_status_the_validators_stated(repo: MemoryRepository) -> None:
    for status, expected in [("PASS", PASS_SOURCE), ("PARTIAL", PARTIAL_SOURCE), ("FAIL", FAIL_SOURCE)]:
        page = repo.list_sources(SourceQuery(status=status))
        assert [s["id"] for s in page.items] == [expected]
    assert repo.list_sources(SourceQuery(status="UNKNOWN")).items == []


def test_sources_filter_by_source_type(repo: MemoryRepository) -> None:
    assert len(repo.list_sources(SourceQuery(source_type="youtube")).items) == 3
    assert repo.list_sources(SourceQuery(source_type="medium")).items == []


def test_entities_filter_by_provenance_and_kind(repo: MemoryRepository) -> None:
    derived = walk(repo.list_entities, EntityQuery, provenance_class="derived")
    assert derived and all(e["provenance_class"] == "derived" for e in derived)
    for entity in walk(repo.list_entities, EntityQuery, kind="principle"):
        assert entity["kind"] == "principle"


def test_an_entity_with_no_confidence_is_not_confident_enough(repo: MemoryRepository) -> None:
    """A missing confidence is unknown. Passing it would invent a number."""
    everything = walk(repo.list_entities, EntityQuery)
    unscored = [e for e in everything if not isinstance(e.get("confidence"), (int, float))]
    filtered = walk(repo.list_entities, EntityQuery, min_confidence=0.0)
    assert {e["global_id"] for e in filtered} == {
        e["global_id"] for e in everything
    } - {e["global_id"] for e in unscored}


def test_min_confidence_keeps_only_what_clears_the_bar(repo: MemoryRepository) -> None:
    for entity in walk(repo.list_entities, EntityQuery, min_confidence=0.9):
        assert entity["confidence"] >= 0.9


def test_relations_filter_by_vocabulary(repo: MemoryRepository) -> None:
    canonical = walk(repo.list_relations, RelationQuery, relation_vocabulary="canonical")
    assert canonical and all(r["relation_vocabulary"] == "canonical" for r in canonical)
    assert walk(repo.list_relations, RelationQuery, relation_vocabulary="user") == []


def test_a_relation_belongs_to_a_source_by_ownership_or_by_endpoint() -> None:
    """The 17 ``expresses_concept`` edges name no run but are still the source's.

    ``adapt_library`` produces them, so their ``source_id`` is null (D-025). A
    Reader that listed a source's relations without them would hide the source's
    own links to the concepts it expresses.
    """
    owned = {"source_id": "youtube:a", "from_id": "youtube:a:KU-1", "to_id": "youtube:a:KU-2"}
    cross = {"source_id": None, "from_id": "youtube:a:KU-1", "to_id": "library:concepts:h"}
    other = {"source_id": "youtube:b", "from_id": "youtube:b:KU-1", "to_id": "youtube:b:KU-2"}
    assert relation_belongs_to_source(owned, "youtube:a")
    assert relation_belongs_to_source(cross, "youtube:a")
    assert not relation_belongs_to_source(other, "youtube:a")
    # The endpoint rule is the same rule everywhere, so the reserved library
    # namespace matches it too — and that costs nothing, because no Source
    # record exists for the library (D-016), so the route 404s before it lists.
    assert relation_belongs_to_source(cross, "library:concepts")


def test_a_source_only_lists_its_own_entities(repo: MemoryRepository) -> None:
    for entity in walk(repo.list_entities, EntityQuery, source_id=PASS_SOURCE):
        assert entity["source_id"] == PASS_SOURCE


# --------------------------------------------------------------------------
# 6. Lookups
# --------------------------------------------------------------------------


def test_a_source_detail_carries_that_source_s_artifacts(repo: MemoryRepository) -> None:
    detail = repo.get_source(PASS_SOURCE)
    assert detail is not None
    assert detail.source["id"] == PASS_SOURCE
    assert detail.artifacts
    assert all(a["source_id"] == PASS_SOURCE for a in detail.artifacts)
    assert [a["id"] for a in detail.artifacts] == sorted(a["id"] for a in detail.artifacts)
    assert detail.payload().keys() == {"source", "artifacts"}


def test_an_artifact_states_availability_rather_than_hiding_it(repo: MemoryRepository) -> None:
    """Canvas plan §15: a missing file is reported, never masked."""
    detail = repo.get_source(PASS_SOURCE)
    assert detail is not None
    for artifact in detail.artifacts:
        assert isinstance(artifact["available"], bool)
        assert not Path(artifact.get("path") or ".").is_absolute(), "risk R15"


def test_an_entity_comes_back_by_its_global_id(repo: MemoryRepository) -> None:
    entity = walk(repo.list_entities, EntityQuery)[0]
    assert repo.get_entity(entity["global_id"]) == entity


# --------------------------------------------------------------------------
# 7. Search — D-028's shapes, with the additive fields attached here (R18)
# --------------------------------------------------------------------------


def test_search_returns_both_hit_shapes(repo: MemoryRepository) -> None:
    hits = repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items
    assert {hit["type"] for hit in hits} == {"knowledge_unit", "transcript_caption"}


def test_every_hit_carries_the_source_it_came_from(repo: MemoryRepository) -> None:
    for hit in repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items:
        assert hit["source_id"] in {PASS_SOURCE, PARTIAL_SOURCE, FAIL_SOURCE}


def test_a_knowledge_unit_hit_is_addressable_and_a_caption_hit_is_not(
    repo: MemoryRepository,
) -> None:
    """D-023: v1 emits no caption entities, so a caption has no id to hand out."""
    for hit in repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items:
        if hit["type"] == "knowledge_unit":
            assert hit["global_id"] == f"{hit['source_id']}:{hit['id']}"
        else:
            assert "global_id" not in hit


def test_a_hit_keeps_its_canonical_field_names(repo: MemoryRepository) -> None:
    """ADR 0001 invariant 6: ``video_id`` stays ``video_id``, and ``id`` stays canonical."""
    hits = repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items
    units = [hit for hit in hits if hit["type"] == "knowledge_unit"]
    assert units
    for hit in units:
        assert "video_id" in hit
        assert hit["id"].startswith("KU-"), "the canonical unit id, not the global one"


def test_the_source_type_is_read_from_the_index_not_assumed(repo: MemoryRepository) -> None:
    """A hit from a source the index does not hold gets no id at all.

    Hard-coding ``youtube`` would mint an address that resolves to nothing the
    moment a second adapter exists.
    """
    invented = repo.as_api_hit(
        {"type": "knowledge_unit", "video_id": "never-ingested", "id": "KU-000001"}
    )
    assert invented["source_id"] is None
    assert invented["global_id"] is None


def test_a_hit_with_no_video_id_gets_no_invented_one(repo: MemoryRepository) -> None:
    hit = repo.as_api_hit({"type": "knowledge_unit", "video_id": None, "id": "KU-000001"})
    assert hit["source_id"] is None and hit["global_id"] is None


def test_search_can_be_confined_to_one_source(repo: MemoryRepository) -> None:
    hits = repo.search(SearchQuery(q="the", limit=MAX_LIMIT, source_id=PASS_SOURCE)).items
    assert hits
    assert {hit["source_id"] for hit in hits} == {PASS_SOURCE}


def test_search_confined_to_an_unknown_source_is_empty_not_an_error(
    repo: MemoryRepository,
) -> None:
    page = repo.search(SearchQuery(q="the", source_id="youtube:no-such-run"))
    assert (page.items, page.next_cursor, page.total) == ([], None, 0)


def test_disabling_the_transcript_fallback_drops_the_caption_hits(
    repo: MemoryRepository,
) -> None:
    hits = repo.search(
        SearchQuery(q="the", limit=MAX_LIMIT, include_transcript=False)
    ).items
    assert hits and {hit["type"] for hit in hits} == {"knowledge_unit"}


def test_search_pages_without_repeating_a_hit(repo: MemoryRepository) -> None:
    everything = repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).items
    paged: list[dict] = []
    cursor: str | None = None
    for _ in range(1000):
        page = repo.search(SearchQuery(q="the", limit=2, cursor=cursor))
        paged.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    else:
        raise AssertionError("search pagination did not terminate")
    assert paged == everything


def test_search_counts_what_it_ranked_and_says_unknown_when_it_could_not(
    tmp_path: Path, repo: MemoryRepository
) -> None:
    """Null means unknown; the contract says it never means zero.

    Now that the corpus is the index's own, the count is a real one — and the
    two ways of having no hits stay distinguishable: a source that was searched
    and matched nothing is ``0``, and a source that could not be read at all is
    ``None``.
    """
    page = repo.search(SearchQuery(q="the", limit=MAX_LIMIT))
    assert page.total == len(page.items) > 0

    assert repo.search(SearchQuery(q="zqxjkvwphgb")).total == 0
    assert repo.search(SearchQuery(q="the", source_id="youtube:no-such-run")).total == 0

    unreadable = MemoryRepository(
        IndexRecords(sources=[_source_record("youtube:unreadable", canonical_dir=None)]),
        project_root=tmp_path,
    )
    assert unreadable.search(SearchQuery(q="the")).total is None, (
        "a source whose canonical files could not be read has an unknown hit "
        "count, not a count of zero"
    )


def test_a_search_cursor_is_bound_to_its_query(repo: MemoryRepository) -> None:
    page = repo.search(SearchQuery(q="the", limit=1))
    assert page.next_cursor
    with pytest.raises(InvalidQuery):
        repo.search(SearchQuery(q="knowledge", limit=1, cursor=page.next_cursor))


# --------------------------------------------------------------------------
# 8. Graph — a page of nodes, and no edge to a node it will not show
# --------------------------------------------------------------------------


def test_a_full_graph_walk_loses_no_node_and_no_edge(repo: MemoryRepository) -> None:
    entities = {e["global_id"] for e in walk(repo.list_entities, EntityQuery)}
    relations = {r["id"] for r in walk(repo.list_relations, RelationQuery)}
    nodes: list[str] = []
    edges: set[str] = set()
    cursor: str | None = None
    for _ in range(1000):
        page = repo.graph(GraphQuery(limit=2, cursor=cursor))
        nodes.extend(n["global_id"] for n in page.nodes)
        edges |= {e["id"] for e in page.edges}
        cursor = page.next_cursor
        if cursor is None:
            break
    else:
        raise AssertionError("graph pagination did not terminate")
    assert len(nodes) == len(set(nodes)), "a node must appear on exactly one page"
    assert set(nodes) == entities
    assert edges == relations


def test_a_graph_page_never_draws_an_edge_to_a_node_it_will_not_show(
    repo: MemoryRepository,
) -> None:
    visible = {
        e["global_id"]
        for e in walk(repo.list_entities, EntityQuery, provenance_class="source")
    }
    page = repo.graph(GraphQuery(limit=MAX_LIMIT, provenance_class="source"))
    for edge in page.edges:
        assert edge["from_id"] in visible and edge["to_id"] in visible


def test_a_cut_graph_page_says_it_was_cut(repo: MemoryRepository) -> None:
    cut = repo.graph(GraphQuery(limit=1))
    assert cut.truncated is True and cut.next_cursor is not None
    whole = repo.graph(GraphQuery(limit=MAX_LIMIT))
    assert whole.truncated is False and whole.next_cursor is None
    assert whole.payload().keys() == {"nodes", "edges", "truncated"}


def test_a_graph_page_filters_edges_by_vocabulary(repo: MemoryRepository) -> None:
    page = repo.graph(GraphQuery(limit=MAX_LIMIT, relation_vocabulary="canonical"))
    assert page.edges
    assert all(edge["relation_vocabulary"] == "canonical" for edge in page.edges)


# --------------------------------------------------------------------------
# 9. Neighborhood
# --------------------------------------------------------------------------


def _center(repo: MemoryRepository) -> str:
    relation = walk(repo.list_relations, RelationQuery)[0]
    return relation["from_id"]


def test_a_neighborhood_always_contains_its_center(repo: MemoryRepository) -> None:
    center = _center(repo)
    hood = repo.neighborhood(NeighborhoodQuery(entity_id=center))
    assert hood is not None
    assert hood.center_id == center
    assert center in {node["global_id"] for node in hood.nodes}
    assert hood.payload().keys() == {"center_id", "depth", "nodes", "edges", "truncated"}


def test_a_deeper_walk_never_returns_less(repo: MemoryRepository) -> None:
    center = _center(repo)
    shallow = repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=1, limit=MAX_LIMIT))
    deep = repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=3, limit=MAX_LIMIT))
    assert shallow is not None and deep is not None
    assert {n["global_id"] for n in shallow.nodes} <= {n["global_id"] for n in deep.nodes}


def test_a_neighborhood_cut_by_the_limit_says_so(repo: MemoryRepository) -> None:
    center = _center(repo)
    hood = repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=3, limit=1))
    assert hood is not None
    assert hood.nodes and hood.truncated is True


def test_a_neighborhood_bounded_by_depth_alone_is_not_called_truncated(
    repo: MemoryRepository,
) -> None:
    """Depth is what the client asked for; the limit is the server declining."""
    center = _center(repo)
    hood = repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=1, limit=MAX_LIMIT))
    assert hood is not None and hood.truncated is False


def test_a_neighborhood_edge_joins_two_nodes_it_returned(repo: MemoryRepository) -> None:
    hood = repo.neighborhood(NeighborhoodQuery(entity_id=_center(repo), depth=3, limit=MAX_LIMIT))
    assert hood is not None
    returned = {node["global_id"] for node in hood.nodes}
    for edge in hood.edges:
        assert edge["from_id"] in returned and edge["to_id"] in returned


# --------------------------------------------------------------------------
# 10. A repository is a reader
# --------------------------------------------------------------------------


def test_answering_every_question_does_not_touch_the_runs() -> None:
    before = {p: p.stat().st_mtime_ns for p in sorted(FIXTURE_RUNS.rglob("*")) if p.is_file()}
    repo = MemoryRepository.from_project(PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR)
    repo.status()
    walk(repo.list_sources, SourceQuery)
    walk(repo.list_entities, EntityQuery)
    walk(repo.list_relations, RelationQuery)
    repo.search(SearchQuery(q="the", limit=MAX_LIMIT))
    repo.graph(GraphQuery(limit=MAX_LIMIT))
    repo.neighborhood(NeighborhoodQuery(entity_id=_center(repo), depth=3, limit=MAX_LIMIT))
    after = {p: p.stat().st_mtime_ns for p in sorted(FIXTURE_RUNS.rglob("*")) if p.is_file()}
    assert before == after


def test_a_returned_record_cannot_be_edited_back_into_the_repository(
    repo: MemoryRepository,
) -> None:
    """The API serialises what it is handed; it must not be able to poison the index."""
    first = repo.get_source(PASS_SOURCE)
    assert first is not None
    first.source["title"] = "tampered"
    first.artifacts.clear()
    again = repo.get_source(PASS_SOURCE)
    assert again is not None and again.source["title"] != "tampered"
    assert again.artifacts

    page = repo.list_entities(EntityQuery(limit=1))
    page.items[0]["confidence"] = 1.0
    assert repo.list_entities(EntityQuery(limit=1)).items[0]["confidence"] != 1.0

    # Nested values too, which is the case this test used to miss: dict(record)
    # is shallow, so status, artifact_ids, locator and derived_from stayed live
    # references into the index. Mutating only top-level scalars, as the
    # assertions above do, cannot detect that. Coercing a stored FAIL upward
    # through a returned record is precisely what ADR 0001 invariant 2 forbids.
    failing = repo.get_source(FAIL_SOURCE)
    assert failing is not None
    failing.source["status"]["overall"] = "PASS"
    failing.source["artifact_ids"].clear()

    reread = repo.get_source(FAIL_SOURCE)
    assert reread is not None
    assert reread.source["status"]["overall"] == "FAIL", "a returned record coerced a stored status"
    assert reread.source["artifact_ids"], "a returned record emptied a stored list"
    assert repo.status().payload()["sources_by_status"]["FAIL"] == 1

    located = next(
        (item for item in repo.list_entities(EntityQuery(limit=MAX_LIMIT)).items
         if isinstance(item.get("locator"), dict)),
        None,
    )
    if located is not None:
        target = located["global_id"]
        located["locator"]["start_sec"] = 999_999
        again = repo.get_entity(target)
        assert again is not None and again["locator"].get("start_sec") != 999_999


def test_an_empty_project_is_an_empty_index_not_a_broken_one(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    repo = MemoryRepository.from_project(tmp_path)
    assert repo.status().payload()["counts"]["sources"] == 0
    assert repo.list_sources(SourceQuery()).items == []
    assert repo.status().state == "ready", "an empty index is ready; it is not absent"


def test_records_can_be_supplied_without_a_project_at_all() -> None:
    """``T-101`` will construct one from SQLite rows, not from a directory."""
    repo = MemoryRepository(IndexRecords(), project_root=Path("."))
    assert repo.status().payload()["counts"]["entities"] == 0


# --------------------------------------------------------------------------
# 11. The cross-source library, over records every machine has
# --------------------------------------------------------------------------
#
# ``output/library/`` is written by ``finalize_run`` and gitignored, so these
# used to be ``@requires_sample`` and asserted counts read off one developer's
# ingested video — 17 concepts, 118 relations. They never ran in CI, which is
# exactly where a regression in cross-source behaviour would land. The concept
# records below are written out here instead: the repository is the code under
# test, and hand-written records are an input to it, not a second opinion from
# it.


def _concept(local_id: str, label: str) -> dict[str, Any]:
    """A canonical concept, shaped as ``adapt_library`` shapes one (D-016)."""
    return {
        "schema_version": "1.0",
        "global_id": f"library:concepts:{local_id}",
        "source_type": "library",
        "external_id": "concepts",
        "local_id": local_id,
        "library_id": f"concept:{local_id}",
        "source_id": None,
        "entity_type": "concept",
        "provenance_class": "derived",
        "kind": "canonical_concept",
        "label": label,
        "confidence": None,
        "canonical_path": "output/library/concepts.json",
    }


def _expresses(unit_global_id: str, concept_local_id: str) -> dict[str, Any]:
    """An ``expresses_concept`` edge: cross-source, so it names no run (D-025)."""
    concept = f"library:concepts:{concept_local_id}"
    return {
        "schema_version": "1.0",
        "id": f"{unit_global_id}|expresses_concept|{concept}",
        "from_id": unit_global_id,
        "to_id": concept,
        "relation": "expresses_concept",
        "relation_vocabulary": "library_synthetic",
        "provenance_class": "derived",
        "confidence": 1.0,
        "source_id": None,
        "canonical_path": "output/library/graph.json",
    }


#: One concept per fixture run, each expressed by that run's source-class unit,
#: plus one concept two runs share — which is the case a single-source sample
#: cannot exercise at all.
LIBRARY_CONCEPTS = [
    _concept("aaaa00000001", "A concept the pass run expresses"),
    _concept("bbbb00000002", "A concept the partial run expresses"),
    _concept("cccc00000003", "A concept two runs share"),
]
LIBRARY_EDGES = [
    _expresses(f"{PASS_SOURCE}:KU-000001", "aaaa00000001"),
    _expresses(f"{PARTIAL_SOURCE}:KU-000001", "bbbb00000002"),
    _expresses(f"{PASS_SOURCE}:KU-D-0001", "cccc00000003"),
    _expresses(f"{FAIL_SOURCE}:KU-D-0001", "cccc00000003"),
]


@pytest.fixture(scope="module")
def library_repo() -> MemoryRepository:
    """The fixture runs plus the cross-source concepts a built library adds."""
    records = adapt_project(PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR) + IndexRecords(
        entities=list(LIBRARY_CONCEPTS), relations=list(LIBRARY_EDGES)
    )
    return MemoryRepository(
        records, project_root=PROJECT_ROOT, output_dir=FIXTURE_OUTPUT_DIR
    )


def test_every_record_walks_through_the_seam_intact(library_repo: MemoryRepository) -> None:
    counts = library_repo.status().payload()["counts"]
    assert counts["entities"] == 6 + len(LIBRARY_CONCEPTS)
    assert counts["relations"] == 6 + len(LIBRARY_EDGES)
    assert len(walk(library_repo.list_entities, EntityQuery, limit=3)) == counts["entities"]
    assert len(walk(library_repo.list_relations, RelationQuery, limit=3)) == counts["relations"]


def test_a_concept_belongs_to_no_source_but_is_still_reachable(
    library_repo: MemoryRepository,
) -> None:
    """D-016: a cross-source concept has no owning source, and needs none."""
    concepts = walk(library_repo.list_entities, EntityQuery, kind="canonical_concept")
    assert len(concepts) == len(LIBRARY_CONCEPTS)
    assert all(concept["source_id"] is None for concept in concepts)
    assert library_repo.get_entity(concepts[0]["global_id"]) == concepts[0]
    owned = {
        e["global_id"]
        for e in walk(library_repo.list_entities, EntityQuery, source_id=PASS_SOURCE)
    }
    assert owned, "the fixture source owns entities of its own"
    assert owned.isdisjoint({c["global_id"] for c in concepts})


def test_the_cross_source_edges_stay_visible_from_the_source_that_makes_them(
    library_repo: MemoryRepository,
) -> None:
    relations = walk(library_repo.list_relations, RelationQuery, source_id=PASS_SOURCE)
    expresses = [r for r in relations if r["relation"] == "expresses_concept"]
    assert len(expresses) == 2
    assert all(r["source_id"] is None for r in expresses), "they name no run, and still belong"


@requires_sample
def test_the_real_sample_walks_through_the_seam_intact() -> None:
    """The same invariants over a real ingested run, where one is on disk.

    No counts read off one machine's library: what has to hold is that a full
    walk loses nothing and that the seam's own tally agrees with it.
    """
    repo = MemoryRepository.from_project(PROJECT_ROOT)
    counts = repo.status().payload()["counts"]
    assert counts["sources"] >= 1
    assert len(walk(repo.list_entities, EntityQuery, limit=25)) == counts["entities"]
    assert len(walk(repo.list_relations, RelationQuery, limit=25)) == counts["relations"]
