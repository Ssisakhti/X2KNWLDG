"""The four ``/api/sources`` endpoints (`T-105`), against the frozen contract.

What these tests are mostly about is the difference between two answers that a
careless route collapses into one:

* **Absent is not malformed.** A well-formed id naming nothing is ``404
  not_found``; an id that is not a source id is ``400 invalid_id`` (D-020, ADR
  0003 decision 4). Collapsing them hides a traversal attempt behind an
  ordinary "no such source", and rewriting the id instead would hand the caller
  a different run than the one asked for.
* **An empty page is not a missing source.** ``list_entities`` answers an
  unknown source with an empty page by design, so ``/api/sources/{id}/entities``
  must check existence itself. A ``200`` with ``data: []`` would assert that the
  source exists and has nothing — a claim about the library that nobody checked.
* **Unbuilt is not empty.** Every endpoint here refuses with ``503
  index_unavailable`` when the index is not ready. Only ``/api/status`` answers.

Paging is asserted end to end rather than by inspecting a token: a walk at
``limit=1`` must reproduce the unpaged call exactly — same records, same order,
no duplicate and no gap. Nothing here persists a cursor across processes;
``encode_cursor`` signs with a per-process key by design.

Every body is validated with :func:`api_harness.assert_contract`. A test that
only checked ``200`` would pass against a route returning the wrong shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import api_harness as h
import pytest

pytestmark = h.requires_fastapi

#: The committed fixtures, in the order ``Source.id`` sorts them. Stated rather
#: than discovered: a paging test that derived its expectation from the same
#: call it is checking would agree with any order the route invented.
SOURCES = ("youtube:fixture-fail", "youtube:fixture-partial", "youtube:fixture-pass")
PASS_SOURCE = "youtube:fixture-pass"

#: Well-formed (`<source_type>:<external_id>`) and naming nothing. This is the
#: `404` case, and it must never be answered the same way as the `400`s below.
UNKNOWN_SOURCE = "youtube:no-such-run"

#: Not source ids at all: one part, three parts, an uppercase adapter
#: namespace, an empty external id, and a traversal-shaped one. Every one is a
#: `400 invalid_id`, and none of them is repaired into something readable.
MALFORMED_IDS = (
    "notasourceid",
    "youtube:fixture-pass:KU-000001",
    "YouTube:fixture-pass",
    "youtube:",
    "youtube:..",
)

#: Enough to hold every record the fixtures produce in one page.
ALL = 100


# --------------------------------------------------------------------------
# A client per implementation
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project of the committed fixtures, copied, shared by every test here."""
    return h.project(tmp_path_factory.mktemp("sources-project"))


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
        yield test_client


# --------------------------------------------------------------------------
# Asking, with the contract checked every time
# --------------------------------------------------------------------------


def body_of(test_client: Any, component: str, path: str, **params: Any) -> dict[str, Any]:
    """The validated body of a checked ``200``."""
    response = test_client.get(path, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    h.assert_contract(component, body)
    return body


def ids_of(records: list[dict[str, Any]]) -> list[str]:
    """The order key of each record: ``global_id`` for an entity, ``id`` otherwise."""
    return [record.get("global_id", record.get("id")) for record in records]


def walk(test_client: Any, component: str, path: str, **params: Any) -> list[str]:
    """Follow ``page.next_cursor`` to the end at ``limit=1`` and return every id seen."""
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(ALL):
        page = params if cursor is None else {**params, "cursor": cursor}
        body = body_of(test_client, component, path, limit=1, **page)
        assert len(body["data"]) <= 1
        assert body["page"]["limit"] == 1
        seen.extend(ids_of(body["data"]))
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            return seen
    raise AssertionError(f"{path} never reached the end of the collection")


# --------------------------------------------------------------------------
# 1. GET /api/sources
# --------------------------------------------------------------------------


def test_the_list_carries_every_fixture_run(api: Any) -> None:
    body = body_of(api, "SourceListResponse", "/api/sources")
    assert tuple(ids_of(body["data"])) == SOURCES
    assert body["page"] == {"limit": 50, "next_cursor": None, "total": 3}


def test_the_default_limit_is_the_frozen_one(api: Any) -> None:
    assert body_of(api, "SourceListResponse", "/api/sources")["page"]["limit"] == 50


def test_status_filters_on_the_copied_value(api: Any) -> None:
    """Filtering for `PASS` cannot silently include a `PARTIAL` run."""
    for status, expected in (("PASS", 1), ("PARTIAL", 1), ("FAIL", 1), ("UNKNOWN", 0)):
        body = body_of(api, "SourceListResponse", "/api/sources", status=status)
        assert len(body["data"]) == expected, status
        assert all(record["status"]["overall"] == status for record in body["data"])


def test_source_type_filters_and_an_unused_one_is_an_empty_page(api: Any) -> None:
    assert len(body_of(api, "SourceListResponse", "/api/sources", source_type="youtube")["data"]) == 3
    empty = body_of(api, "SourceListResponse", "/api/sources", source_type="medium")
    assert empty["data"] == []
    assert empty["page"]["next_cursor"] is None


def test_a_status_outside_the_vocabulary_is_refused(api: Any) -> None:
    h.assert_error(api.get("/api/sources", params={"status": "GREAT"}), 400, "invalid_request")


def test_a_malformed_source_type_is_refused(api: Any) -> None:
    h.assert_error(api.get("/api/sources", params={"source_type": "YouTube"}), 400, "invalid_request")


def test_paging_the_list_reproduces_it_exactly(api: Any) -> None:
    unpaged = ids_of(body_of(api, "SourceListResponse", "/api/sources", limit=ALL)["data"])
    paged = walk(api, "SourceListResponse", "/api/sources")
    assert paged == unpaged == list(SOURCES)
    assert len(set(paged)) == len(paged), "a paged walk repeated a record"


def test_a_filtered_walk_pages_the_filter_and_not_the_collection(api: Any) -> None:
    assert walk(api, "SourceListResponse", "/api/sources", status="PASS") == [PASS_SOURCE]


# --------------------------------------------------------------------------
# 2. GET /api/sources/{source_id}
# --------------------------------------------------------------------------


def test_a_source_arrives_with_the_artifacts_it_names(api: Any) -> None:
    body = body_of(api, "SourceDetailResponse", f"/api/sources/{PASS_SOURCE}")
    detail = body["data"]
    assert detail["source"]["id"] == PASS_SOURCE
    assert detail["artifacts"], "the fixture run declares artifacts"
    assert {artifact["id"] for artifact in detail["artifacts"]} == set(
        detail["source"]["artifact_ids"]
    )
    assert all(artifact["source_id"] == PASS_SOURCE for artifact in detail["artifacts"])


def test_every_listed_source_can_be_fetched(api: Any) -> None:
    for source_id in SOURCES:
        body = body_of(api, "SourceDetailResponse", f"/api/sources/{source_id}")
        assert body["data"]["source"]["id"] == source_id


def test_a_well_formed_id_naming_nothing_is_not_found(api: Any) -> None:
    h.assert_error(api.get(f"/api/sources/{UNKNOWN_SOURCE}"), 404, "not_found")


def test_a_malformed_id_is_refused_rather_than_rewritten(api: Any) -> None:
    """400 `invalid_id`, never a 404 and never somebody else's run (ADR 0003)."""
    for source_id in MALFORMED_IDS:
        response = api.get(f"/api/sources/{source_id}")
        h.assert_error(response, 400, "invalid_id")
        assert "data" not in response.json(), source_id


def test_absence_and_malformation_are_different_answers(api: Any) -> None:
    """Stated as one assertion because collapsing them is the failure mode."""
    unknown = api.get(f"/api/sources/{UNKNOWN_SOURCE}")
    malformed = api.get("/api/sources/notasourceid")
    assert (unknown.status_code, malformed.status_code) == (404, 400)
    assert unknown.json()["error"]["code"] != malformed.json()["error"]["code"]


def test_a_detail_body_names_no_host_path(api: Any) -> None:
    """Artifact paths are project-relative; a host path here is a disclosure."""
    blob = json.dumps(body_of(api, "SourceDetailResponse", f"/api/sources/{PASS_SOURCE}"))
    assert str(h.PROJECT_ROOT) not in blob
    assert "/Users/" not in blob and "/home/" not in blob


# --------------------------------------------------------------------------
# 3. GET /api/sources/{source_id}/entities
# --------------------------------------------------------------------------


def test_the_entities_of_a_source_belong_to_it(api: Any) -> None:
    body = body_of(api, "EntityListResponse", f"/api/sources/{PASS_SOURCE}/entities", limit=ALL)
    assert body["data"], "the fixture run declares knowledge units"
    assert all(record["source_id"] == PASS_SOURCE for record in body["data"])
    assert all(record["global_id"].startswith(f"{PASS_SOURCE}:") for record in body["data"])


def test_the_entity_filters_narrow_rather_than_reorder(api: Any) -> None:
    path = f"/api/sources/{PASS_SOURCE}/entities"
    everything = ids_of(body_of(api, "EntityListResponse", path, limit=ALL)["data"])

    for params in (
        {"provenance_class": "source"},
        {"kind": "synthesis"},
        {"min_confidence": 0.8},
    ):
        filtered = ids_of(body_of(api, "EntityListResponse", path, limit=ALL, **params)["data"])
        assert filtered, params
        assert set(filtered) < set(everything), params
        assert filtered == [entity_id for entity_id in everything if entity_id in set(filtered)]


def test_min_confidence_excludes_rather_than_defaults(api: Any) -> None:
    """No canonical file states a confidence for an unconfident entity (D-030 §MinConfidence)."""
    path = f"/api/sources/{PASS_SOURCE}/entities"
    kept = body_of(api, "EntityListResponse", path, limit=ALL, min_confidence=0.8)["data"]
    assert kept
    assert all(record.get("confidence") is not None and record["confidence"] >= 0.8 for record in kept)


def test_a_filter_value_outside_its_vocabulary_is_refused(api: Any) -> None:
    path = f"/api/sources/{PASS_SOURCE}/entities"
    for params in (
        {"provenance_class": "invented"},
        {"kind": "vibes"},
        {"min_confidence": 2},
        {"min_confidence": "high"},
    ):
        h.assert_error(api.get(path, params=params), 400, "invalid_request")


def test_entities_of_an_unknown_source_are_not_found_rather_than_empty(api: Any) -> None:
    """An empty page would assert the source exists and has nothing."""
    response = api.get(f"/api/sources/{UNKNOWN_SOURCE}/entities")
    h.assert_error(response, 404, "not_found")
    assert "data" not in response.json()


def test_entities_of_a_malformed_source_are_refused(api: Any) -> None:
    for source_id in MALFORMED_IDS:
        h.assert_error(api.get(f"/api/sources/{source_id}/entities"), 400, "invalid_id")


def test_paging_the_entities_reproduces_them_exactly(api: Any) -> None:
    path = f"/api/sources/{PASS_SOURCE}/entities"
    unpaged = ids_of(body_of(api, "EntityListResponse", path, limit=ALL)["data"])
    paged = walk(api, "EntityListResponse", path)
    assert paged == unpaged
    assert len(set(paged)) == len(paged), "a paged walk repeated an entity"


# --------------------------------------------------------------------------
# 4. GET /api/sources/{source_id}/relations
# --------------------------------------------------------------------------


def test_the_relations_of_a_source_are_its_own(api: Any) -> None:
    body = body_of(api, "RelationListResponse", f"/api/sources/{PASS_SOURCE}/relations", limit=ALL)
    assert body["data"], "the fixture run declares relations"
    for record in body["data"]:
        endpoints = (record["from_id"], record["to_id"])
        belongs = record.get("source_id") == PASS_SOURCE or any(
            endpoint.startswith(f"{PASS_SOURCE}:") for endpoint in endpoints
        )
        assert belongs, record["id"]


def test_the_vocabulary_filter_partitions_the_relations(api: Any) -> None:
    path = f"/api/sources/{PASS_SOURCE}/relations"
    everything = ids_of(body_of(api, "RelationListResponse", path, limit=ALL)["data"])
    parts: list[str] = []
    for vocabulary in ("canonical", "library_synthetic", "user"):
        records = body_of(
            api, "RelationListResponse", path, limit=ALL, relation_vocabulary=vocabulary
        )["data"]
        assert all(record["relation_vocabulary"] == vocabulary for record in records)
        parts.extend(ids_of(records))
    assert sorted(parts) == sorted(everything), "the three vocabularies must cover the collection"


def test_a_vocabulary_outside_the_three_is_refused(api: Any) -> None:
    h.assert_error(
        api.get(
            f"/api/sources/{PASS_SOURCE}/relations",
            params={"relation_vocabulary": "folklore"},
        ),
        400,
        "invalid_request",
    )


def test_relations_of_an_unknown_source_are_not_found_rather_than_empty(api: Any) -> None:
    response = api.get(f"/api/sources/{UNKNOWN_SOURCE}/relations")
    h.assert_error(response, 404, "not_found")
    assert "data" not in response.json()


def test_relations_of_a_malformed_source_are_refused(api: Any) -> None:
    for source_id in MALFORMED_IDS:
        h.assert_error(api.get(f"/api/sources/{source_id}/relations"), 400, "invalid_id")


def test_paging_the_relations_reproduces_them_exactly(api: Any) -> None:
    path = f"/api/sources/{PASS_SOURCE}/relations"
    unpaged = ids_of(body_of(api, "RelationListResponse", path, limit=ALL)["data"])
    paged = walk(api, "RelationListResponse", path)
    assert paged == unpaged
    assert len(set(paged)) == len(paged), "a paged walk repeated a relation"


# --------------------------------------------------------------------------
# 5. What every paged endpoint here refuses
# --------------------------------------------------------------------------

PAGED_PATHS = (
    "/api/sources",
    f"/api/sources/{PASS_SOURCE}/entities",
    f"/api/sources/{PASS_SOURCE}/relations",
)


@pytest.mark.parametrize("limit", [0, -1, 501, 100000])
def test_a_limit_outside_the_frozen_bounds_is_refused(api: Any, limit: int) -> None:
    for path in PAGED_PATHS:
        h.assert_error(api.get(path, params={"limit": limit}), 400, "invalid_request")


def test_the_bounds_themselves_are_accepted(api: Any) -> None:
    for path in PAGED_PATHS:
        for limit in (1, 500):
            assert api.get(path, params={"limit": limit}).status_code == 200, (path, limit)


def test_a_cursor_the_server_did_not_issue_is_refused(api: Any) -> None:
    for path in PAGED_PATHS:
        h.assert_error(api.get(path, params={"cursor": "not-a-cursor"}), 400, "invalid_request")
        h.assert_error(api.get(path, params={"cursor": "x" * 512}), 400, "invalid_request")


def test_an_over_long_cursor_is_refused_before_it_is_parsed(api: Any) -> None:
    """`maxLength: 512` in the frozen document, enforced as a `400`, not a `422`."""
    h.assert_error(api.get("/api/sources", params={"cursor": "x" * 513}), 400, "invalid_request")


def test_a_cursor_belongs_to_the_query_that_issued_it(api: Any) -> None:
    """Re-anchoring it onto another filter would answer a question nobody asked."""
    cursor = body_of(api, "SourceListResponse", "/api/sources", limit=1)["page"]["next_cursor"]
    assert cursor
    h.assert_error(
        api.get("/api/sources", params={"cursor": cursor, "status": "PASS"}),
        400,
        "invalid_request",
    )


def test_only_the_page_size_may_change_mid_walk(api: Any) -> None:
    """A keyset position does not depend on page size, so a wider second page works."""
    first = body_of(api, "SourceListResponse", "/api/sources", limit=1)
    rest = body_of(
        api, "SourceListResponse", "/api/sources", limit=2, cursor=first["page"]["next_cursor"]
    )
    assert ids_of(first["data"]) + ids_of(rest["data"]) == list(SOURCES)


# --------------------------------------------------------------------------
# 6. An index that cannot answer
# --------------------------------------------------------------------------


UNAVAILABLE_PATHS = (
    "/api/sources",
    f"/api/sources/{PASS_SOURCE}",
    f"/api/sources/{PASS_SOURCE}/entities",
    f"/api/sources/{PASS_SOURCE}/relations",
)


@h.requires_fts5
def test_an_unbuilt_index_refuses_every_endpoint_here(tmp_path: Path) -> None:
    """`absent` is answerable only by `/api/status`; these four say why they cannot."""
    root = h.project(tmp_path, "pass-run")
    with h.client(h.sqlite_repository(root, build=False)) as test_client:
        for path in UNAVAILABLE_PATHS:
            body = h.assert_error(test_client.get(path), 503, "index_unavailable")
            assert body["error"].get("detail", {}).get("state") == "absent", path


def test_the_oracle_refuses_the_same_way() -> None:
    from x2knwldg.repository import MemoryRepository

    with h.client(MemoryRepository.unavailable("absent")) as test_client:
        for path in UNAVAILABLE_PATHS:
            h.assert_error(test_client.get(path), 503, "index_unavailable")


def test_a_refusal_never_stands_in_for_a_page() -> None:
    """503 carries an error body, not an empty `data` a client could render."""
    from x2knwldg.repository import MemoryRepository

    with h.client(MemoryRepository.unavailable("error")) as test_client:
        body = test_client.get("/api/sources").json()
        assert "data" not in body and "page" not in body
