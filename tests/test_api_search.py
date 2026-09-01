"""``GET /api/search`` (`T-106`) — the route, against the frozen contract.

Search is the endpoint where the API is least like the rest of itself, so the
tests here are mostly about *not* changing things:

* the two hit shapes are ``query.search_knowledge``'s own, field for field
  (D-028, ADR 0001 invariant 6), so each one is validated against its own
  frozen variant rather than against a shape this test invented;
* the order is ``query.rank_documents``'s (D-046), so a paged walk must
  reproduce an unpaged call exactly — same hits, same order, no duplicate and
  no gap;
* an empty query is a refusal, not an empty page, and a cursor belongs to the
  query that issued it.

Every body is checked with :func:`api_harness.assert_contract`. A test that
only asserted ``200`` would pass against a route that returned the wrong shape,
which is precisely the failure the frozen document exists to catch.

**Both implementations, or it is not tested.** ``T-104`` proved
``MemoryRepository`` and ``SqliteRepository`` answer identically, so anything
that differs between them here is a bug in this route.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import api_harness as h

pytestmark = h.requires_fastapi

#: A query that matches across every fixture run and both hit types.
BROAD = "the"

#: Enough to hold every hit the fixtures produce in one page.
ALL = 100


# --------------------------------------------------------------------------
# A client per implementation
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project of the committed fixtures, copied, shared by every test here."""
    return h.project(tmp_path_factory.mktemp("search-project"))


@pytest.fixture(
    scope="module",
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("sqlite", id="sqlite", marks=h.requires_fts5),
    ],
)
def api(request: pytest.FixtureRequest, root: Path) -> Any:
    """A ``TestClient`` over each implementation in turn."""
    build = h.memory_repository if request.param == "memory" else h.sqlite_repository
    with h.client(build(root)) as test_client:
        _skip_if_thread_bound(test_client, request.param)
        yield test_client


def _skip_if_thread_bound(test_client: Any, label: str) -> None:
    """Skip rather than fail on a defect that is not this route's.

    Starlette runs a sync endpoint in a worker thread, and
    ``index.schema.connect`` opens SQLite with the default
    ``check_same_thread=True`` — so a ``SqliteRepository`` built in the test's
    own thread reports ``state: error`` for every request. That is a seam
    defect affecting all four Track B route modules, reported rather than
    worked around here (`T-106` owns two files, and neither is that one). The
    probe is narrow on purpose: any *other* ``503`` is still a failure.
    """
    response = test_client.get("/api/search", params={"q": BROAD})
    if response.status_code != 503:
        return
    message = response.json()["error"]["message"]
    if "same thread" in message:
        pytest.skip(f"{label}: the repository's SQLite connection is thread-bound — {message}")


def search(test_client: Any, **params: Any) -> Any:
    return test_client.get("/api/search", params=params)


def hits(test_client: Any, **params: Any) -> list[dict[str, Any]]:
    """The ``data`` of a checked ``200``. Every caller validates the envelope."""
    response = search(test_client, **params)
    assert response.status_code == 200, response.text
    body = response.json()
    h.assert_contract("SearchResponse", body)
    return body["data"]


# --------------------------------------------------------------------------
# 1. The shape of an answer
# --------------------------------------------------------------------------


def test_a_page_of_hits_is_a_search_response(api: Any) -> None:
    response = search(api, q=BROAD, limit=5)
    assert response.status_code == 200, response.text
    body = response.json()
    h.assert_contract("SearchResponse", body)
    assert body["data"], "the fixture runs produced no hits to check"
    assert body["page"]["limit"] == 5
    assert set(body["page"]) == {"limit", "next_cursor", "total"}


def test_both_hit_types_appear_and_each_fits_its_own_frozen_variant(api: Any) -> None:
    """The discriminated union, exercised on both arms.

    ``SearchResponse`` would validate with only one arm present, so the arms are
    counted here as well as validated: a route that silently dropped every
    caption hit would still produce a conforming body.
    """
    data = hits(api, q=BROAD, limit=ALL)
    by_type = {"knowledge_unit": [], "transcript_caption": []}
    for hit in data:
        by_type.setdefault(hit["type"], []).append(hit)

    assert by_type["knowledge_unit"], "no knowledge-unit hits to validate"
    assert by_type["transcript_caption"], "no transcript-caption hits to validate"
    for hit in by_type["knowledge_unit"]:
        h.assert_contract("SearchHitKnowledgeUnit", hit)
    for hit in by_type["transcript_caption"]:
        h.assert_contract("SearchHitTranscriptCaption", hit)


def test_the_canonical_field_names_survive_the_route(api: Any) -> None:
    """``video_id`` stays ``video_id`` and ``id`` stays the unit id (invariant 6)."""
    units = [hit for hit in hits(api, q=BROAD, limit=ALL) if hit["type"] == "knowledge_unit"]
    assert units
    for hit in units:
        assert "video_id" in hit
        assert "source_id" in hit and "global_id" in hit
        assert "id" in hit and hit["id"].startswith("KU-")


def test_a_caption_hit_carries_no_global_id(api: Any) -> None:
    """v1 emits no caption entities (D-023), so there is no entity to address."""
    captions = [
        hit for hit in hits(api, q=BROAD, limit=ALL) if hit["type"] == "transcript_caption"
    ]
    assert captions
    for hit in captions:
        assert "global_id" not in hit, "a caption hit was given an id for an entity v1 never emits"


def test_no_host_path_reaches_a_success_body(api: Any) -> None:
    """ADR 0003 / D-051 — the error bodies are checked by the harness; this is the 200."""
    blob = json.dumps(search(api, q=BROAD, limit=ALL).json())
    assert str(h.PROJECT_ROOT) not in blob
    assert "/Users/" not in blob and "/home/" not in blob


# --------------------------------------------------------------------------
# 2. The echoed query
# --------------------------------------------------------------------------


def test_the_response_echoes_the_query_as_executed(api: Any) -> None:
    response = search(api, q="evidence", limit=ALL)
    body = response.json()
    h.assert_contract("SearchResponse", body)
    assert body["query"] == "evidence"


def test_the_echo_survives_punctuation_and_case(api: Any) -> None:
    """A client matching responses to requests compares the string it sent."""
    for term in ("Evidence-bearing", "KU-000001", "a b", "100%"):
        body = search(api, q=term, limit=ALL).json()
        h.assert_contract("SearchResponse", body)
        assert body["query"] == term


# --------------------------------------------------------------------------
# 3. The filters
# --------------------------------------------------------------------------


def test_include_transcript_false_drops_captions_and_keeps_units(api: Any) -> None:
    everything = hits(api, q=BROAD, limit=ALL)
    units_only = hits(api, q=BROAD, limit=ALL, include_transcript="false")

    assert {hit["type"] for hit in units_only} == {"knowledge_unit"}
    assert units_only == [hit for hit in everything if hit["type"] == "knowledge_unit"]


def test_include_transcript_defaults_to_true(api: Any) -> None:
    assert hits(api, q=BROAD, limit=ALL) == hits(api, q=BROAD, limit=ALL, include_transcript="true")


def test_source_id_scopes_results_to_that_source(api: Any) -> None:
    everything = hits(api, q=BROAD, limit=ALL)
    sources = sorted({hit["source_id"] for hit in everything})
    assert len(sources) > 1, "the fixture library must hold more than one source to scope by"

    scoped = hits(api, q=BROAD, limit=ALL, source_id=sources[0])
    assert scoped, "scoping to a source that has hits returned none"
    assert {hit["source_id"] for hit in scoped} == {sources[0]}
    assert scoped == [hit for hit in everything if hit["source_id"] == sources[0]]
    assert len(scoped) < len(everything)


def test_a_well_formed_source_id_naming_nothing_is_an_empty_page(api: Any) -> None:
    """Absence is a return value, not an error (repository rule 4)."""
    body = search(api, q=BROAD, source_id="youtube:no-such-source").json()
    h.assert_contract("SearchResponse", body)
    assert body["data"] == []
    assert body["page"]["total"] == 0


def test_a_malformed_source_id_is_invalid_id(api: Any) -> None:
    """Malformed is not absent — ``400 invalid_id``, never a quiet empty page (D-020)."""
    h.assert_error(search(api, q=BROAD, source_id="not-a-source-id"), 400, "invalid_id")


# --------------------------------------------------------------------------
# 4. The refusals
# --------------------------------------------------------------------------


def test_a_missing_q_is_a_400_not_a_framework_422(api: Any) -> None:
    """The frozen document lists ``400`` and never ``422`` (`errors.handle_validation_error`)."""
    h.assert_error(search(api), 400, "invalid_request")


def test_an_empty_q_is_a_400_and_not_an_empty_page(api: Any) -> None:
    h.assert_error(search(api, q=""), 400, "invalid_request")


def test_a_whitespace_only_q_is_a_400(api: Any) -> None:
    """A length bound cannot see this one; ``SearchQuery.__post_init__`` can."""
    h.assert_error(search(api, q="   "), 400, "invalid_request")


def test_a_q_of_513_characters_is_refused(api: Any) -> None:
    """512 is inside the contract, 513 is outside it — the bound, not a guess at one."""
    assert search(api, q="a" * 512).status_code == 200
    h.assert_error(search(api, q="a" * 513), 400, "invalid_request")


@pytest.mark.parametrize("limit", [0, 501])
def test_a_limit_outside_the_contract_is_refused(api: Any, limit: int) -> None:
    h.assert_error(search(api, q=BROAD, limit=limit), 400, "invalid_request")


@pytest.mark.parametrize("limit", [1, 500])
def test_the_limit_bounds_themselves_are_accepted(api: Any, limit: int) -> None:
    body = search(api, q=BROAD, limit=limit).json()
    h.assert_contract("SearchResponse", body)
    assert body["page"]["limit"] == limit


def test_a_garbage_cursor_is_invalid_request(api: Any) -> None:
    """Opaque does not mean unchecked: a token this process did not sign is refused."""
    h.assert_error(search(api, q=BROAD, cursor="not-a-cursor"), 400, "invalid_request")


def test_a_cursor_is_bound_to_the_query_that_issued_it(api: Any) -> None:
    """Re-anchoring a cursor onto another question would answer one nobody asked.

    Same process, so the signing key is the same one — this proves the *binding*
    rather than the expiry, and nothing here persists a cursor across processes.
    """
    issued = search(api, q=BROAD, limit=1).json()["page"]["next_cursor"]
    assert issued, "a one-hit page over the fixtures must offer a next cursor"

    h.assert_error(search(api, q="evidence", cursor=issued, limit=1), 400, "invalid_request")
    h.assert_error(
        search(api, q=BROAD, cursor=issued, limit=1, include_transcript="false"),
        400,
        "invalid_request",
    )


def test_a_cursor_survives_a_change_of_limit_alone(api: Any) -> None:
    """A keyset position does not depend on page size (repository rule 3)."""
    issued = search(api, q=BROAD, limit=1).json()["page"]["next_cursor"]
    body = search(api, q=BROAD, limit=5, cursor=issued).json()
    h.assert_contract("SearchResponse", body)
    assert body["data"] == hits(api, q=BROAD, limit=ALL)[1:6]


def test_an_unbuilt_index_is_index_unavailable(tmp_path: Path) -> None:
    """``absent`` is a state, and search cannot answer from it (D-030).

    Distinct from an index that is built and holds nothing: that answers ``200``
    with an empty page. A UI that could not tell them apart would present "never
    indexed" as "nothing found".
    """
    root = h.project(tmp_path)
    with h.client(h.sqlite_repository(root, build=False)) as unbuilt:
        body = h.assert_error(search(unbuilt, q=BROAD), 503, "index_unavailable")
    assert body["error"]["detail"]["state"] == "absent"


# --------------------------------------------------------------------------
# 5. Paging
# --------------------------------------------------------------------------


def walk(test_client: Any, **params: Any) -> list[dict[str, Any]]:
    """Follow ``next_cursor`` to exhaustion, validating every page."""
    collected: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(100):
        page_params = dict(params)
        if cursor is not None:
            page_params["cursor"] = cursor
        response = search(test_client, **page_params)
        assert response.status_code == 200, response.text
        body = response.json()
        h.assert_contract("SearchResponse", body)
        assert len(body["data"]) <= body["page"]["limit"]
        collected.extend(body["data"])
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            return collected
    raise AssertionError("the paged walk did not terminate")


def test_a_paged_walk_reproduces_the_unpaged_call_exactly(api: Any) -> None:
    """No duplicate, no gap, and the ranking order unchanged (D-046)."""
    unpaged = hits(api, q=BROAD, limit=ALL)
    assert len(unpaged) > 3, "the fixtures must produce enough hits to page over"
    assert walk(api, q=BROAD, limit=2) == unpaged


def test_a_paged_walk_holds_under_a_filter(api: Any) -> None:
    unpaged = hits(api, q=BROAD, limit=ALL, include_transcript="false")
    assert unpaged
    assert walk(api, q=BROAD, limit=1, include_transcript="false") == unpaged


def test_the_last_page_offers_no_cursor(api: Any) -> None:
    body = search(api, q=BROAD, limit=ALL).json()
    h.assert_contract("SearchResponse", body)
    assert body["page"]["next_cursor"] is None


def test_total_is_reported_as_the_repository_states_it(api: Any) -> None:
    """``null`` means unknown and is never coerced; a number is a count, not a page size."""
    body = search(api, q=BROAD, limit=2).json()
    h.assert_contract("SearchResponse", body)
    total = body["page"]["total"]
    if total is not None:
        assert total == len(hits(api, q=BROAD, limit=ALL))
        assert total > len(body["data"])


# --------------------------------------------------------------------------
# 6. The two implementations answer the same
# --------------------------------------------------------------------------


@h.requires_fts5
@pytest.mark.parametrize(
    "params",
    [
        {"q": BROAD, "limit": ALL},
        {"q": BROAD, "limit": 2},
        {"q": "evidence", "limit": ALL},
        {"q": BROAD, "limit": ALL, "include_transcript": False},
        {"q": BROAD, "limit": ALL, "source_id": "youtube:fixture-pass"},
    ],
)
def test_the_two_implementations_answer_identically(root: Path, params: dict[str, Any]) -> None:
    """`T-104` proved the seam agrees; a divergence here is a route bug.

    The route function is called directly rather than over HTTP, so that the
    comparison is of this module's own output on the two repositories and not of
    two transports. It is also the only way to reach ``SqliteRepository`` while
    its connection is thread-bound — see :func:`_skip_if_thread_bound`.
    """
    from x2knwldg.server.routes.search import search as route

    call = {"q": BROAD, "limit": 50, "cursor": None, "source_id": None, "include_transcript": True}
    call.update(params)

    memory = route(repo=h.memory_repository(root), **call)
    sqlite_repo = h.sqlite_repository(root)
    try:
        sqlite = route(repo=sqlite_repo, **call)
    finally:
        sqlite_repo.close()

    h.assert_contract("SearchResponse", memory)
    h.assert_contract("SearchResponse", sqlite)
    assert memory["data"] == sqlite["data"], "the two implementations returned different hits"
    assert memory["page"] == sqlite["page"], "the two implementations paged differently"
    assert memory["query"] == sqlite["query"] == call["q"]
