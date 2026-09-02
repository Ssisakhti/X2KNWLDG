"""``GET /api/graph`` and ``GET /api/graph/neighborhood/{entity_id}``.

The Map is the one view that can lie by omission: a graph is a claim about what
is connected, and a partial one drawn without saying so is a false claim. So the
questions this file asks are mostly about honesty rather than about shape.

* Does every edge run between nodes that are actually in the response? An edge
  to a node the client will never see is a dangling edge, and a Map that draws
  one asserts a node it will not show.
* Is ``truncated`` the repository's answer, and is it ``true`` whenever ``limit``
  cut the graph short — including on the *last* page of a paged walk, which has
  no ``next_cursor`` and is still a slice?
* Is a malformed id refused as malformed (``400 invalid_id``) rather than
  answered as absent (``404``)? ADR 0003 / D-020: conflating the two hides an
  attack behind an ordinary answer.
* Is ``depth`` outside ``1..3`` refused rather than clamped? The response echoes
  ``depth`` back, so a clamp would tell the client a bound it never set.
* Do the two implementations answer identically? `T-104` proved they do, so a
  divergence here is a bug in the route, not in one of them.

Every assertion about a body goes through :func:`api_harness.assert_contract`,
against the frozen component in ``schemas/api/v1/openapi.json``. A route test
that only checks ``response.status_code == 200`` is not a contract test.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import api_harness
import pytest
from api_harness import (
    assert_contract,
    assert_error,
    both_clients,
    client,
    contract_errors,
    memory_repository,
    project,
    requires_fastapi,
    requires_fts5,
    sqlite_repository,
)

pytestmark = [requires_fastapi, requires_fts5]

GRAPH = "/api/graph"
NEIGHBORHOOD = "/api/graph/neighborhood"

#: A derived unit of the passing run. One hop reaches its own source's entities;
#: two hops reach across the shared concept into the other runs.
CENTER = "youtube:fixture-pass:KU-D-0001"

#: A concept belongs to no source (D-016) and is still a legitimate centre.
CONCEPT_CENTER = "library:concepts:30ba07eea6c0"

#: Well formed by ``common.schema.json#/$defs/globalId``, and named by nothing.
ABSENT_ID = "youtube:fixture-pass:KU-999999"

#: Each is refused by the grammar rather than looked up: two parts, an empty
#: part, a leading digit in the source type, a space.
MALFORMED_IDS = (
    "youtube:fixture-pass",
    "youtube::KU-000001",
    "1youtube:fixture-pass:KU-000001",
    "youtube:fixture pass:KU-000001",
    "not-a-global-id",
)


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project, built once: three runs plus the derived library."""
    return project(tmp_path_factory.mktemp("graph-api"))


# --------------------------------------------------------------------------
# Reading a response without trusting it
# --------------------------------------------------------------------------


def graph_body(test_client: Any, **params: Any) -> dict[str, Any]:
    """A ``200`` from ``/api/graph``, validated against ``GraphResponse``."""
    response = test_client.get(GRAPH, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert_contract("GraphResponse", body)
    return body


def neighborhood_body(test_client: Any, entity_id: str, **params: Any) -> dict[str, Any]:
    """A ``200`` from the neighborhood route, validated against its component."""
    response = test_client.get(f"{NEIGHBORHOOD}/{entity_id}", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert_contract("NeighborhoodResponse", body)
    return body


def node_ids(payload: dict[str, Any]) -> list[str]:
    return [node["global_id"] for node in payload["nodes"]]


def assert_edges_stay_inside(payload: dict[str, Any], where: str) -> None:
    """Every edge runs between two nodes this payload actually returned.

    This is the invariant the Map depends on and the one a route is most likely
    to break by "helpfully" adding edges the repository left out. It holds
    outright for a neighborhood and for a graph that fits in one page; the paged
    case is weaker on purpose and has its own assertion below.
    """
    present = set(node_ids(payload))
    for edge in payload["edges"]:
        assert edge["from_id"] in present, f"{where}: edge {edge['id']} leaves the returned nodes"
        assert edge["to_id"] in present, f"{where}: edge {edge['id']} leaves the returned nodes"


def assert_edges_touch_the_page(payload: dict[str, Any], whole: set[str], where: str) -> None:
    """What a *page* of a graph guarantees, which is less — and deliberately so.

    ``graph()`` includes an edge when **both** endpoints pass the node filter
    and **at least one** is on this page (``repository/README.md``). So an edge
    may name a node that is on another page — an edge straddling a page boundary
    appears in both — but never one the filter excluded, which is what would
    make it dangle against a node the client will never receive. A client
    accumulating pages dedupes by ``id`` and ends up with every endpoint.
    """
    on_page = set(node_ids(payload))
    for edge in payload["edges"]:
        endpoints = {edge["from_id"], edge["to_id"]}
        assert endpoints & on_page, f"{where}: edge {edge['id']} touches no node on this page"
        assert endpoints <= whole, (
            f"{where}: edge {edge['id']} names a node the filter excluded from the graph"
        )


def assert_no_host_path(body: Any) -> None:
    """No response names the filesystem it was served from (ADR 0003, D-051)."""
    blob = json.dumps(body)
    assert str(api_harness.PROJECT_ROOT) not in blob
    assert "/Users/" not in blob and "/home/" not in blob


def clients(root: Path) -> Iterator[tuple[str, Any]]:
    """Each implementation's client in turn, labelled.

    Every route assertion in this file runs against both. `T-104` proved the two
    answer identically, so a divergence found here is a bug in the route.
    """
    return both_clients(root)


# --------------------------------------------------------------------------
# The shapes the contract froze
# --------------------------------------------------------------------------


def test_a_graph_page_validates_against_the_frozen_component(root: Path) -> None:
    for label, test_client in clients(root):
        body = graph_body(test_client, limit=500)
        data = body["data"]
        assert data["nodes"], f"{label}: the fixture library has nodes"
        assert data["edges"], f"{label}: the fixture library has edges"
        assert body["page"]["limit"] == 500, label
        assert_no_host_path(body)


def test_a_neighborhood_validates_against_the_frozen_component(root: Path) -> None:
    for label, test_client in clients(root):
        body = neighborhood_body(test_client, CENTER, depth=2)
        data = body["data"]
        assert data["center_id"] == CENTER, label
        assert data["depth"] == 2, label
        assert CENTER in node_ids(data), f"{label}: the centre is part of its own neighborhood"
        assert_no_host_path(body)


def test_a_concept_is_a_legitimate_node_and_a_legitimate_centre(root: Path) -> None:
    """D-016: a concept belongs to no source, and must still be reachable."""
    for label, test_client in clients(root):
        nodes = graph_body(test_client, limit=500)["data"]["nodes"]
        concepts = [node for node in nodes if node.get("source_id") is None]
        assert concepts, f"{label}: the library derives at least one source-less concept"

        data = neighborhood_body(test_client, CONCEPT_CENTER)["data"]
        assert data["center_id"] == CONCEPT_CENTER, label
        assert len(data["nodes"]) > 1, f"{label}: the concept is connected to something"


def test_the_neighborhood_response_carries_no_page_member(root: Path) -> None:
    """The asymmetry is the contract's, and ``additionalProperties: false`` enforces it."""
    for label, test_client in clients(root):
        body = neighborhood_body(test_client, CENTER)
        assert "page" not in body, f"{label}: a neighborhood is not paged"
        with_page = dict(body, page={"limit": 50, "next_cursor": None, "total": None})
        assert contract_errors("NeighborhoodResponse", with_page), (
            f"{label}: NeighborhoodResponse must reject a page member outright"
        )


# --------------------------------------------------------------------------
# Edges never leave the nodes
# --------------------------------------------------------------------------


def test_graph_edges_never_name_a_node_that_was_not_returned(root: Path) -> None:
    """A graph that fits in one page carries no edge that leaves it."""
    for label, test_client in clients(root):
        payload = graph_body(test_client, limit=500)["data"]
        assert payload["truncated"] is False, f"{label}: this must be the whole graph"
        assert_edges_stay_inside(payload, f"{label} whole graph")

        for filters in (
            {"source_id": "youtube:fixture-pass"},
            {"provenance_class": "source"},
            {"relation_vocabulary": "library_synthetic"},
        ):
            filtered = graph_body(test_client, limit=500, **filters)["data"]
            assert_edges_stay_inside(filtered, f"{label} whole graph {filters}")


def test_a_page_of_the_graph_carries_no_edge_the_filter_excluded(root: Path) -> None:
    """The paged guarantee, stated as it actually is.

    An edge may reach a node on another page — that node is a real record the
    walk will deliver — but never one the filter removed from the graph.
    """
    for label, test_client in clients(root):
        whole = set(node_ids(graph_body(test_client, limit=500)["data"]))
        for limit in (1, 2, 3):
            payload = graph_body(test_client, limit=limit)["data"]
            assert len(payload["nodes"]) <= limit, label
            assert_edges_touch_the_page(payload, whole, f"{label} graph limit={limit}")


def test_neighborhood_edges_never_name_a_node_that_was_not_returned(root: Path) -> None:
    for label, test_client in clients(root):
        for depth in (1, 2, 3):
            for limit in (2, 500):
                payload = neighborhood_body(test_client, CENTER, depth=depth, limit=limit)["data"]
                assert_edges_stay_inside(payload, f"{label} depth={depth} limit={limit}")


# --------------------------------------------------------------------------
# `truncated` is stated, never implied
# --------------------------------------------------------------------------


def test_graph_states_truncation_when_limit_cuts_it_short(root: Path) -> None:
    for label, test_client in clients(root):
        whole = graph_body(test_client, limit=500)["data"]
        assert whole["truncated"] is False, f"{label}: the whole graph fits in 500"

        cut = graph_body(test_client, limit=2)["data"]
        assert len(whole["nodes"]) > 2, f"{label}: the fixture must be bigger than the cut"
        assert cut["truncated"] is True, f"{label}: a cut graph says so"


def test_the_last_page_of_a_walk_is_still_a_slice(root: Path) -> None:
    """``truncated`` is about the graph, not about the cursor.

    A last page has no ``next_cursor`` and is not the whole graph; reporting it
    as whole would let the Map present the tail of the library as the library.
    """
    for label, test_client in clients(root):
        cursor: str | None = None
        pages = 0
        while True:
            params: dict[str, Any] = {"limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            body = graph_body(test_client, **params)
            pages += 1
            assert body["data"]["truncated"] is True, f"{label}: page {pages} is a slice"
            cursor = body["page"]["next_cursor"]
            if cursor is None:
                break
            assert pages < 20, f"{label}: paging did not terminate"
        assert pages > 1, f"{label}: the fixture pages at limit=2"


def test_a_neighborhood_states_truncation_from_the_limit_not_the_depth(root: Path) -> None:
    for label, test_client in clients(root):
        whole = neighborhood_body(test_client, CENTER, depth=3, limit=500)["data"]
        assert whole["truncated"] is False, f"{label}: nothing was cut"
        assert len(whole["nodes"]) > 2, f"{label}: depth 3 reaches more than a pair"

        cut = neighborhood_body(test_client, CENTER, depth=3, limit=2)["data"]
        assert cut["truncated"] is True, f"{label}: the limit cut the walk short"
        assert len(cut["nodes"]) <= 2, label

        bounded = neighborhood_body(test_client, CENTER, depth=1, limit=500)["data"]
        assert bounded["truncated"] is False, (
            f"{label}: a depth bound is what the client asked for, not a truncation"
        )


# --------------------------------------------------------------------------
# Filters narrow, and a value outside the vocabulary is refused
# --------------------------------------------------------------------------


def test_source_id_narrows_the_graph(root: Path) -> None:
    for label, test_client in clients(root):
        whole = graph_body(test_client, limit=500)["data"]
        one = graph_body(test_client, limit=500, source_id="youtube:fixture-pass")["data"]
        assert one["nodes"], label
        assert len(one["nodes"]) < len(whole["nodes"]), f"{label}: the filter narrowed nothing"
        assert set(node_ids(one)) <= set(node_ids(whole)), label
        assert_edges_stay_inside(one, f"{label} source_id")


def test_provenance_class_narrows_the_graph(root: Path) -> None:
    for label, test_client in clients(root):
        whole = graph_body(test_client, limit=500)["data"]
        for provenance in ("source", "derived"):
            payload = graph_body(test_client, limit=500, provenance_class=provenance)["data"]
            assert payload["nodes"], f"{label}: the fixture has {provenance} nodes"
            assert len(payload["nodes"]) < len(whole["nodes"]), f"{label}: {provenance}"
            assert all(node["provenance_class"] == provenance for node in payload["nodes"]), label
            assert_edges_stay_inside(payload, f"{label} provenance={provenance}")


def test_relation_vocabulary_narrows_the_edges(root: Path) -> None:
    for label, test_client in clients(root):
        whole = graph_body(test_client, limit=500)["data"]
        for vocabulary in ("canonical", "library_synthetic"):
            payload = graph_body(test_client, limit=500, relation_vocabulary=vocabulary)["data"]
            assert payload["edges"], f"{label}: the fixture has {vocabulary} edges"
            assert len(payload["edges"]) < len(whole["edges"]), f"{label}: {vocabulary}"
            assert all(
                edge["relation_vocabulary"] == vocabulary for edge in payload["edges"]
            ), label
            assert_edges_stay_inside(payload, f"{label} vocabulary={vocabulary}")


def test_relation_vocabulary_narrows_a_neighborhood(root: Path) -> None:
    for label, test_client in clients(root):
        whole = neighborhood_body(test_client, CENTER, depth=3, limit=500)["data"]
        payload = neighborhood_body(
            test_client, CENTER, depth=3, limit=500, relation_vocabulary="canonical"
        )["data"]
        assert all(
            edge["relation_vocabulary"] == "canonical" for edge in payload["edges"]
        ), label
        assert len(payload["edges"]) < len(whole["edges"]), f"{label}: the filter narrowed nothing"
        assert set(node_ids(payload)) <= set(node_ids(whole)), label
        assert_edges_stay_inside(payload, f"{label} neighborhood vocabulary")


def test_a_filter_value_outside_the_vocabulary_is_refused(root: Path) -> None:
    """A value the contract's enum does not list is a bad request, not an empty page."""
    for _label, test_client in clients(root):
        assert_error(
            test_client.get(GRAPH, params={"provenance_class": "everything"}), 400, "invalid_request"
        )
        assert_error(
            test_client.get(GRAPH, params={"relation_vocabulary": "spooky"}), 400, "invalid_request"
        )
        assert_error(
            test_client.get(f"{NEIGHBORHOOD}/{CENTER}", params={"relation_vocabulary": "spooky"}),
            400,
            "invalid_request",
        )
        # A malformed *id* is a different refusal from a bad enum (D-030).
        assert_error(
            test_client.get(GRAPH, params={"source_id": "not a source id"}), 400, "invalid_id"
        )


# --------------------------------------------------------------------------
# `depth` is refused, never clamped
# --------------------------------------------------------------------------


@pytest.mark.parametrize("depth", [0, 4, -1, 99])
def test_a_depth_outside_the_contract_is_a_bad_request(root: Path, depth: int) -> None:
    with client(memory_repository(root)) as test_client:
        assert_error(
            test_client.get(f"{NEIGHBORHOOD}/{CENTER}", params={"depth": depth}),
            400,
            "invalid_request",
        )


def test_a_deeper_walk_never_reaches_fewer_nodes(root: Path) -> None:
    for label, test_client in clients(root):
        reached = [
            set(node_ids(neighborhood_body(test_client, CENTER, depth=depth, limit=500)["data"]))
            for depth in (1, 2, 3)
        ]
        assert reached[0] <= reached[1] <= reached[2], f"{label}: a deeper walk lost a node"
        assert len(reached[1]) > len(reached[0]), (
            f"{label}: depth 2 must cross the shared concept into the other runs"
        )


# --------------------------------------------------------------------------
# A malformed id and an unknown one are different answers (ADR 0003 / D-020)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("entity_id", MALFORMED_IDS)
def test_a_malformed_entity_id_is_rejected_as_malformed(root: Path, entity_id: str) -> None:
    with client(memory_repository(root)) as test_client:
        body = assert_error(test_client.get(f"{NEIGHBORHOOD}/{entity_id}"), 400, "invalid_id")
        # The repository's own message quotes the id it refused; what matters is
        # that nothing was rewritten into a lookup. The id names no run
        # directory, and the walk never started.
        assert body["error"]["code"] == "invalid_id"


def test_a_well_formed_unknown_entity_id_is_not_found(root: Path) -> None:
    for label, test_client in clients(root):
        body = assert_error(test_client.get(f"{NEIGHBORHOOD}/{ABSENT_ID}"), 404, "not_found")
        assert ABSENT_ID not in json.dumps(body), f"{label}: the 404 echoes the input back"


def test_a_cursor_this_process_did_not_issue_is_refused(root: Path) -> None:
    with client(memory_repository(root)) as test_client:
        assert_error(
            test_client.get(GRAPH, params={"cursor": "bm90LWEtY3Vyc29y.forged"}),
            400,
            "invalid_request",
        )


# --------------------------------------------------------------------------
# Paging: no duplicates, no gaps
# --------------------------------------------------------------------------


def test_paging_the_graph_yields_every_node_exactly_once(root: Path) -> None:
    for label, test_client in clients(root):
        whole = graph_body(test_client, limit=500)["data"]
        expected = node_ids(whole)

        seen: list[str] = []
        edges: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        for _ in range(20):
            params: dict[str, Any] = {"limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            body = graph_body(test_client, **params)
            payload = body["data"]
            assert_edges_touch_the_page(payload, set(expected), f"{label} paged")
            seen.extend(node_ids(payload))
            for edge in payload["edges"]:
                edges[edge["id"]] = edge
            cursor = body["page"]["next_cursor"]
            if cursor is None:
                break
        else:  # pragma: no cover - a runaway walk is a failure, not a long test
            pytest.fail(f"{label}: paging did not terminate")

        assert len(seen) == len(set(seen)), f"{label}: a node appeared on two pages"
        assert set(seen) == set(expected), f"{label}: the walk lost or invented a node"
        assert sorted(edges) == sorted(edge["id"] for edge in whole["edges"]), (
            f"{label}: accumulating pages must recover every edge"
        )
        # No gap: once the walk is complete, every edge it handed out runs
        # between two nodes it also handed out.
        assert_edges_stay_inside(
            {"nodes": whole["nodes"], "edges": list(edges.values())}, f"{label} accumulated"
        )


def test_a_cursor_is_bound_to_the_query_that_issued_it(root: Path) -> None:
    """Changing a filter mid-walk is refused rather than re-anchored."""
    with client(memory_repository(root)) as test_client:
        first = graph_body(test_client, limit=2)
        cursor = first["page"]["next_cursor"]
        assert cursor is not None
        assert_error(
            test_client.get(GRAPH, params={"limit": 2, "cursor": cursor, "provenance_class": "source"}),
            400,
            "invalid_request",
        )


# --------------------------------------------------------------------------
# The index may be unable to answer at all
# --------------------------------------------------------------------------


def test_an_unbuilt_index_refuses_both_endpoints(tmp_path: Path) -> None:
    unbuilt = project(tmp_path / "unbuilt")
    with client(sqlite_repository(unbuilt, build=False)) as test_client:
        body = assert_error(test_client.get(GRAPH), 503, "index_unavailable")
        assert body["error"].get("detail", {}).get("state") == "absent", (
            "an absent index is not an empty one"
        )
        assert_error(
            test_client.get(f"{NEIGHBORHOOD}/{CENTER}"), 503, "index_unavailable"
        )


# --------------------------------------------------------------------------
# The two implementations answer the same question the same way
# --------------------------------------------------------------------------


def _questions() -> dict[str, Any]:
    """The queries the two endpoints build, as the route would build them."""
    from x2knwldg.repository import GraphQuery, NeighborhoodQuery

    return {
        "graph": GraphQuery(limit=500),
        "graph_page": GraphQuery(limit=3),
        "graph_by_source": GraphQuery(limit=500, source_id="youtube:fixture-pass"),
        "graph_derived": GraphQuery(limit=500, provenance_class="derived"),
        "graph_canonical": GraphQuery(limit=500, relation_vocabulary="canonical"),
        "neighborhood": NeighborhoodQuery(entity_id=CENTER, depth=2, limit=500),
        "concept": NeighborhoodQuery(entity_id=CONCEPT_CENTER, depth=1, limit=500),
        "neighborhood_cut": NeighborhoodQuery(entity_id=CENTER, depth=3, limit=2),
    }


#: The same requests, asked of both clients: ``(name, path, params)``.
REQUESTS = (
    ("graph", GRAPH, {"limit": 500}),
    ("graph_page", GRAPH, {"limit": 3}),
    ("graph_by_source", GRAPH, {"limit": 500, "source_id": "youtube:fixture-pass"}),
    ("graph_derived", GRAPH, {"limit": 500, "provenance_class": "derived"}),
    ("graph_canonical", GRAPH, {"limit": 500, "relation_vocabulary": "canonical"}),
    ("neighborhood", f"{NEIGHBORHOOD}/{CENTER}", {"depth": 2, "limit": 500}),
    ("concept", f"{NEIGHBORHOOD}/{CONCEPT_CENTER}", {"depth": 1, "limit": 500}),
    ("neighborhood_cut", f"{NEIGHBORHOOD}/{CENTER}", {"depth": 3, "limit": 2}),
)


def test_both_implementations_return_the_same_nodes_and_edges(root: Path) -> None:
    """`T-104` proved the seam has one answer; a divergence here is a route bug."""
    answers: dict[str, dict[str, Any]] = {}
    for label, test_client in clients(root):
        collected: dict[str, Any] = {}
        for name, path, params in REQUESTS:
            response = test_client.get(path, params=params)
            assert response.status_code == 200, f"{label} {name}: {response.text}"
            collected[name] = response.json()
        answers[label] = collected

    assert sorted(answers) == ["memory", "sqlite"]
    memory, sqlite = answers["memory"], answers["sqlite"]
    for name, _, _ in REQUESTS:
        left, right = memory[name]["data"], sqlite[name]["data"]
        assert node_ids(left) == node_ids(right), f"{name}: the nodes diverged"
        assert [edge["id"] for edge in left["edges"]] == [
            edge["id"] for edge in right["edges"]
        ], f"{name}: the edges diverged"
        assert left["truncated"] == right["truncated"], f"{name}: truncated diverged"
        assert left == right, f"{name}: the payloads diverged beyond nodes and edges"
        assert memory[name].get("page") == sqlite[name].get("page"), f"{name}: page diverged"


def test_the_route_renders_the_repository_payload_verbatim(root: Path) -> None:
    """The route reshapes nothing, so what the seam agrees on is what is served.

    ``truncated`` in particular is passed through, never recomputed: the body's
    value is the repository's object, not a comparison the route made.
    """
    oracle = memory_repository(root)
    with client(memory_repository(root)) as test_client:
        graph = oracle.graph(_questions()["graph_page"])
        body = graph_body(test_client, limit=3)
        assert body["data"] == graph.payload()
        assert body["page"] == graph.page_info()

        walk = oracle.neighborhood(_questions()["neighborhood"])
        assert walk is not None
        assert neighborhood_body(test_client, CENTER, depth=2, limit=500)["data"] == walk.payload()
