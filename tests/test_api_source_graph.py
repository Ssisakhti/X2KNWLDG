"""``GET /api/source-graph`` and its neighbourhood, over both implementations (`T-254`).

The first tests in the project that read a source node, a source brief or a
cross-source relation over HTTP. Every body is validated against the **frozen**
component in ``schemas/api/v1/openapi.json`` — the eight shapes `T-251` froze as
components with no paths (D-254) — because a route test that only checks
``200`` is not a contract test.

Every case runs over ``both_clients``: `T-104` proved the two repositories
answer identically, so a route that behaves differently on one of them has found
a route bug and not an implementation difference. The source layer is the newest
place for the two to drift — the oracle reads the canonical files on demand and
the index reads three tables a scan wrote — so this is where that claim earns
its keep.

The corpus is ``tests/source_map_corpus.py``: four runs across both media, three
briefs, one ``FAIL`` run with none, and the one committed cross-medium relation.
Its documents were generated from the runs' own bytes, so ``available`` really
means available here rather than meaning "a digest nobody checked".
"""

from __future__ import annotations

import json
from pathlib import Path

import api_harness as h
import pytest
import source_map_corpus as smc

from x2knwldg.constants import MAX_SOURCE_RELATION_BASIS

pytestmark = h.requires_fastapi

GRAPH = "/api/source-graph"
NEIGHBORHOOD = "/api/source-graph/neighborhood"


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return smc.build(tmp_path_factory.mktemp("source-map")).project_root


@pytest.fixture(scope="module")
def bare(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same runs with no ``output/synthesis/`` at all.

    The honest state of every project that has never run source synthesis, and
    the only corpus a "no relation" assertion can be made against.
    """
    return smc.build(
        tmp_path_factory.mktemp("source-map-bare"), relations=False
    ).project_root


# --------------------------------------------------------------------------
# 1. The graph
# --------------------------------------------------------------------------


def test_every_acquired_source_appears_exactly_once(root: Path) -> None:
    """The phase's first acceptance clause, at the HTTP end.

    ``fail-run`` is in here on purpose: a ``FAIL`` run is a source that exists,
    and a Map that omitted it would report a smaller library than the one on
    disk.
    """
    for label, client in h.both_clients(root):
        body = client.get(GRAPH, params={"limit": 500}).json()
        h.assert_contract("SourceGraphResponse", body)
        ids = [node["source_id"] for node in body["data"]["nodes"]]
        assert sorted(ids) == sorted(smc.SOURCE_IDS), label
        assert len(ids) == len(set(ids)), label


def test_every_node_is_a_source_node_and_nothing_else(root: Path) -> None:
    for label, client in h.both_clients(root):
        body = client.get(GRAPH, params={"limit": 500}).json()
        types = {node["entity_type"] for node in body["data"]["nodes"]}
        assert types == {"source"}, f"{label}: {types}"
        assert all(node["kind"] is None for node in body["data"]["nodes"]), label


def test_the_counts_are_three_numbers_rather_than_one(root: Path) -> None:
    """Returned, omitted and total answer three different questions."""
    for label, client in h.both_clients(root):
        body = client.get(GRAPH, params={"limit": 500}).json()
        counts = body["data"]["counts"]
        assert counts["sources_returned"] == len(body["data"]["nodes"]), label
        assert counts["relations_returned"] == len(body["data"]["relations"]), label
        assert counts["relations_omitted"] == 0, label
        assert counts["sources_total"] == len(smc.SOURCE_IDS), label
        assert body["data"]["truncated"] is False, label


def test_a_relation_summary_carries_its_count_and_never_a_score(root: Path) -> None:
    """D-247: a basis count is a count, never a strength, a rank or a confidence."""
    for label, client in h.both_clients(root):
        body = client.get(GRAPH, params={"limit": 500}).json()
        assert len(body["data"]["relations"]) == 1, label
        relation = body["data"]["relations"][0]
        assert relation["id"] == smc.RELATION_ID, label
        assert relation["from_source_id"] == smc.RELATION_FROM, label
        assert relation["to_source_id"] == smc.RELATION_TO, label
        assert relation["provenance_class"] == "derived", label
        assert relation["basis_total"] == 1, label
        text = json.dumps(body)
        for word in ("score", "similarity", "confidence", "strength"):
            assert word not in text, f"{label}: {word}"


def test_the_relation_is_cross_medium(root: Path) -> None:
    """The phase's acceptance clause: an automatic YouTube↔X relationship."""
    for label, client in h.both_clients(root):
        relation = client.get(GRAPH, params={"limit": 500}).json()["data"]["relations"][0]
        media = {
            relation["from_source_id"].split(":", 1)[0],
            relation["to_source_id"].split(":", 1)[0],
        }
        assert media == {"twitter", "youtube"}, f"{label}: {media}"


def test_a_relation_never_names_a_node_the_body_does_not_carry(root: Path) -> None:
    """ADR 0002: an edge to a node the page will not show asserts a node that does not exist."""
    for label, client in h.both_clients(root):
        cursor = None
        while True:
            params = {"limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            body = client.get(GRAPH, params=params).json()
            h.assert_contract("SourceGraphResponse", body)
            drawn = {node["source_id"] for node in body["data"]["nodes"]}
            for relation in body["data"]["relations"]:
                endpoints = {relation["from_source_id"], relation["to_source_id"]}
                assert endpoints & drawn, f"{label}: {relation['id']} touches no drawn node"
            cursor = body["page"]["next_cursor"]
            if cursor is None:
                break


def test_a_full_walk_returns_every_source_once(root: Path) -> None:
    """Paging over nodes is what makes this true; paging over relations would not.

    A source that relates to nothing has no relation to be paged by, and in a
    young corpus that is most of them — three of the four here.
    """
    for label, client in h.both_clients(root):
        seen: list[str] = []
        cursor = None
        for _ in range(50):
            params = {"limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            body = client.get(GRAPH, params=params).json()
            seen.extend(node["source_id"] for node in body["data"]["nodes"])
            cursor = body["page"]["next_cursor"]
            if cursor is None:
                break
        else:  # pragma: no cover - a walk that does not terminate is the failure
            pytest.fail(f"{label}: pagination did not terminate")
        assert sorted(seen) == sorted(smc.SOURCE_IDS), label


def test_a_corpus_with_no_synthesis_reports_no_relation_rather_than_no_answer(
    bare: Path,
) -> None:
    """A no-relation corpus emits none, and says so with counts rather than silence."""
    for label, client in h.both_clients(bare):
        body = client.get(GRAPH, params={"limit": 500}).json()
        h.assert_contract("SourceGraphResponse", body)
        assert body["data"]["relations"] == [], label
        assert body["data"]["counts"]["relations_returned"] == 0, label
        assert body["data"]["counts"]["relations_omitted"] == 0, label
        assert body["data"]["counts"]["sources_total"] == len(smc.SOURCE_IDS), label


# --------------------------------------------------------------------------
# 2. The neighbourhood
# --------------------------------------------------------------------------


def test_a_selected_source_exposes_a_readable_brief(root: Path) -> None:
    """The phase's second acceptance clause: a Persian brief naming its support."""
    for label, client in h.both_clients(root):
        body = client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PASS}").json()
        h.assert_contract("SourceNeighborhoodResponse", body)
        availability = body["data"]["source_knowledge"]
        assert availability["state"] == "available", label
        assert availability["reason"] is None, label
        brief = availability["brief"]
        assert brief["source_id"] == smc.YOUTUBE_PASS, label
        assert brief["thesis"]["based_on"], label
        for point in brief["key_points"]:
            assert point["based_on"], f"{label}: {point['id']} names no support"


def test_the_center_is_echoed_as_the_nodes_global_id(root: Path) -> None:
    """The path takes a source id; ``center_id`` answers with the node's own id."""
    for label, client in h.both_clients(root):
        body = client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PASS}").json()
        assert body["data"]["center_id"] == f"{smc.YOUTUBE_PASS}:source", label
        assert body["data"]["source"]["global_id"] == body["data"]["center_id"], label
        assert body["data"]["source"]["source_id"] == smc.YOUTUBE_PASS, label


def test_direction_is_stated_rather_than_left_to_be_derived(root: Path) -> None:
    """Incoming and outgoing are separate arrays, and each holds the right end."""
    for label, client in h.both_clients(root):
        inbound = client.get(f"{NEIGHBORHOOD}/{smc.RELATION_TO}").json()["data"]
        assert [r["id"] for r in inbound["incoming"]] == [smc.RELATION_ID], label
        assert inbound["outgoing"] == [], label
        assert all(r["to_source_id"] == smc.RELATION_TO for r in inbound["incoming"])

        outbound = client.get(f"{NEIGHBORHOOD}/{smc.RELATION_FROM}").json()["data"]
        assert [r["id"] for r in outbound["outgoing"]] == [smc.RELATION_ID], label
        assert outbound["incoming"] == [], label
        assert all(r["from_source_id"] == smc.RELATION_FROM for r in outbound["outgoing"])


def test_every_returned_relation_has_a_node_for_its_far_endpoint(root: Path) -> None:
    for label, client in h.both_clients(root):
        for source_id in smc.SOURCE_IDS:
            data = client.get(f"{NEIGHBORHOOD}/{source_id}").json()["data"]
            addressable = {node["source_id"] for node in data["neighbors"]} | {
                data["source"]["source_id"]
            }
            for relation in (*data["incoming"], *data["outgoing"]):
                assert {relation["from_source_id"], relation["to_source_id"]} <= (
                    addressable
                ), f"{label}: {source_id} names an endpoint it carries no node for"


def test_the_basis_states_both_counts(root: Path) -> None:
    """``basis_returned`` alone would present a truncation as the whole basis."""
    for label, client in h.both_clients(root):
        relation = client.get(f"{NEIGHBORHOOD}/{smc.RELATION_TO}").json()["data"][
            "incoming"
        ][0]
        assert relation["basis_total"] == len(relation["basis"]), label
        assert relation["basis_returned"] == len(relation["basis"]), label
        assert len(relation["basis"]) <= MAX_SOURCE_RELATION_BASIS, label
        assert relation["rationale"], label


def test_a_run_with_no_brief_says_so_rather_than_returning_an_empty_one(
    root: Path,
) -> None:
    """"This source has no thesis" is a claim about the source, and it would be false."""
    for label, client in h.both_clients(root):
        body = client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_FAIL}").json()
        h.assert_contract("SourceNeighborhoodResponse", body)
        availability = body["data"]["source_knowledge"]
        assert availability["state"] == "unavailable", label
        assert availability["brief"] is None, label
        assert availability["reason"], label


def test_a_brief_may_not_claim_more_than_its_run(root: Path) -> None:
    """The ``PARTIAL`` fixture reaches the API as ``PARTIAL``."""
    for label, client in h.both_clients(root):
        brief = client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PARTIAL}").json()["data"][
            "source_knowledge"
        ]["brief"]
        assert brief["status"] == "PARTIAL", label


def test_a_stale_brief_is_carried_with_the_state_saying_so(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """``stale`` is a state rather than an error, and withholding would lose the brief.

    The run is edited *after* the fixture brief was written against it, which is
    exactly how a brief goes stale in life: the knowledge it summarises moved.
    """
    root = smc.build(tmp_path_factory.mktemp("source-map-stale")).project_root
    units = root / "output" / "pass-run" / "knowledge_units.json"
    document = json.loads(units.read_text(encoding="utf-8"))
    document["units"][0]["confidence"] = 0.55
    units.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    for label, client in h.both_clients(root):
        body = client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PASS}").json()
        h.assert_contract("SourceNeighborhoodResponse", body)
        availability = body["data"]["source_knowledge"]
        assert availability["state"] == "stale", label
        assert availability["brief"] is not None, label
        assert "knowledge_units_sha256" in availability["reason"], label


# --------------------------------------------------------------------------
# 3. Refusals
# --------------------------------------------------------------------------


def test_a_malformed_source_id_is_refused_as_malformed(root: Path) -> None:
    """D-020 over HTTP: refused as malformed, never dressed up as absence."""
    for _label, client in h.both_clients(root):
        h.assert_error(client.get(f"{NEIGHBORHOOD}/not-a-source-id"), 400, "invalid_id")


def test_a_well_formed_unknown_source_is_a_not_found(root: Path) -> None:
    for _label, client in h.both_clients(root):
        body = h.assert_error(
            client.get(f"{NEIGHBORHOOD}/{smc.UNKNOWN_SOURCE}"), 404, "not_found"
        )
        assert smc.UNKNOWN_SOURCE not in json.dumps(body), "the refusal echoed the id back"


def test_a_limit_outside_the_contract_is_refused(root: Path) -> None:
    for _label, client in h.both_clients(root):
        h.assert_error(client.get(GRAPH, params={"limit": 501}), 400, "invalid_request")
        h.assert_error(
            client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PASS}", params={"limit": 0}),
            400,
            "invalid_request",
        )


def test_a_cursor_this_server_did_not_issue_is_refused(root: Path) -> None:
    for _label, client in h.both_clients(root):
        h.assert_error(
            client.get(GRAPH, params={"cursor": "bm90LWEtY3Vyc29y"}),
            400,
            "invalid_request",
        )


def test_an_unbuilt_index_says_unbuilt_rather_than_empty(tmp_path: Path) -> None:
    """An empty Source Map and an unbuilt one must never look the same."""
    root = smc.build(tmp_path / "project").project_root
    with h.client(h.sqlite_repository(root, build=False)) as client:
        h.assert_error(client.get(GRAPH), 503, "index_unavailable")
        h.assert_error(
            client.get(f"{NEIGHBORHOOD}/{smc.YOUTUBE_PASS}"), 503, "index_unavailable"
        )


def test_neither_endpoint_writes(root: Path) -> None:
    """v1 is read-only; ``raw/`` is immutable evidence."""
    for _label, client in h.both_clients(root):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(GRAPH).status_code == 405
