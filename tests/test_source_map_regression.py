"""Nothing the Knowledge Map serves moved when the source layer arrived (`T-251`).

D-249 is one sentence — *do not change current Knowledge Map payloads* — and it
is the constraint most easily broken by accident here, because the obvious place
to put a source node is the entity list every existing surface already reads.
``IndexRecords.entities`` feeds ``/api/graph``, ``/api/sources/{id}/entities``,
``/api/status`` counts and the SQLite ``entities`` table, and not one of them
filters on ``entity_type``. A source node appended there would have put a
source-scale mark into the Knowledge Map and moved every entity count in the
project, and each of those is a frozen payload.

So the source entities live in a fifth record family that ``by_model`` does not
expose, and the guarantee is structural rather than a filter clause repeated at
four call sites. This file is what holds that structure to its promise, over a
project holding **both** media, through the adapter, the repository seam, the
SQLite index and the HTTP surface — the same four stations `T-228` used, for the
same reason: coexistence is where a change of this kind actually shows.

The HTTP section needs ``fastapi`` and skips without it, exactly as the other
``tests/test_api_*.py`` files do. Everything above it is stdlib only.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from x2knwldg.adapters import adapt_project
from x2knwldg.index.scanner import build_index
from x2knwldg.index.schema import connect, database_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"
OPENAPI_PATH = PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json"

#: The thirteen frozen paths, spelled out. A count alone would pass a rename.
#: Eleven when `T-251` wrote this list; the two the source layer added are here
#: because `T-254` served them, and this file's subject is that **no other path
#: moved** when it did.
FROZEN_PATHS = {
    "/api/status",
    "/api/sources",
    "/api/sources/{source_id}",
    "/api/sources/{source_id}/entities",
    "/api/sources/{source_id}/relations",
    "/api/entities/{entity_id}",
    "/api/artifacts/{artifact_id}",
    "/api/media/{artifact_id}",
    "/api/search",
    "/api/graph",
    "/api/graph/neighborhood/{entity_id}",
    "/api/source-graph",
    "/api/source-graph/neighborhood/{source_id}",
}


@pytest.fixture
def both_media(tmp_path: Path) -> Path:
    """A project root holding one YouTube run and one Twitter run."""
    from x2knwldg.library import rebuild_library

    output = tmp_path / "output"
    output.mkdir(parents=True)
    shutil.copytree(YOUTUBE_RUNS / "pass-run", output / "pass-run")
    shutil.copytree(TWITTER_RUNS / "quote", output / "twitter-quote")
    rebuild_library(output)
    return tmp_path


# --------------------------------------------------------------------------
# 1. The adapter seam
# --------------------------------------------------------------------------


def test_by_model_carries_no_source_entity(both_media: Path) -> None:
    """The load-bearing assertion of this file, in one line.

    ``by_model`` is what ``index.scanner`` writes and what
    ``repository.check_index_integrity`` judges. A source entity reaching it is
    a source entity reaching every existing payload.
    """
    records = adapt_project(both_media)
    types = {entity["entity_type"] for entity in records.by_model()["entity_ref"]}
    assert "source" not in types
    assert records.source_entities, "and they were emitted — this is not vacuous"


def test_the_two_views_differ_by_exactly_the_source_entities(both_media: Path) -> None:
    records = adapt_project(both_media)
    narrow = records.by_model()["entity_ref"]
    wide = records.by_model_with_source_entities()["entity_ref"]
    assert len(wide) - len(narrow) == len(records.source_entities) == 2
    assert wide[: len(narrow)] == narrow, "the existing records keep their order"


def test_by_model_still_names_the_same_four_families(both_media: Path) -> None:
    assert set(adapt_project(both_media).by_model()) == {
        "source",
        "artifact",
        "entity_ref",
        "indexed_relation",
    }


def test_adding_a_source_entity_did_not_renumber_the_youtube_projection() -> None:
    """`T-228`'s own numbers, unmoved.

    ``tests/test_twitter_coexistence.YOUTUBE_ALONE`` records the YouTube
    sample's projection as it was measured before the second medium existed.
    Reading it from there rather than restating it means this test fails if that
    one is ever quietly adjusted to accommodate a change here.
    """
    from test_twitter_coexistence import YOUTUBE_ALONE

    from x2knwldg.adapters import adapt_run

    records = adapt_run(YOUTUBE_RUNS / "pass-run", YOUTUBE_RUNS.parents[1])
    assert {
        "sources": len(records.sources),
        "artifacts": len(records.artifacts),
        "entities": len(records.entities),
        "relations": len(records.relations),
    } == YOUTUBE_ALONE


# --------------------------------------------------------------------------
# 2. The index
# --------------------------------------------------------------------------


def test_the_sqlite_entities_table_holds_no_source_entity(both_media: Path) -> None:
    build_index(both_media)
    with connect(database_path(both_media)) as connection:
        rows = connection.execute("SELECT doc FROM entities").fetchall()
    types = {json.loads(row[0])["entity_type"] for row in rows}
    assert rows, "the index is not empty — this is not vacuous"
    assert "source" not in types


def test_the_index_entity_count_is_the_adapter_entity_count(both_media: Path) -> None:
    """Two independent paths to one number, and the source entities in neither."""
    build_index(both_media)
    with connect(database_path(both_media)) as connection:
        indexed = connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    assert indexed == len(adapt_project(both_media).by_model()["entity_ref"])


# --------------------------------------------------------------------------
# 3. The frozen HTTP surface
# --------------------------------------------------------------------------


def test_the_frozen_paths_are_exactly_the_thirteen() -> None:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert set(document["paths"]) == FROZEN_PATHS


def test_the_packaged_spec_matches_the_authored_one() -> None:
    """The server serves a copy; a stale copy is a contract that forked."""
    packaged = PROJECT_ROOT / "src" / "x2knwldg" / "server" / "openapi.json"
    assert packaged.read_bytes() == OPENAPI_PATH.read_bytes()


def test_v1_is_still_read_only() -> None:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    for path, operations in document["paths"].items():
        assert set(operations) == {"get"}, path


@pytest.mark.parametrize("route", ["/api/graph", "/api/sources", "/api/status"])
def test_no_existing_endpoint_serves_a_source_entity(both_media: Path, route: str) -> None:
    pytest.importorskip("fastapi")
    import api_harness

    for label, client in api_harness.both_clients(both_media):
        body = client.get(route, params={"limit": 500}).json()
        text = json.dumps(body)
        assert '"entity_type": "source"' not in text.replace(" ", ""), f"{label} {route}"
        assert '"entity_type":"source"' not in text, f"{label} {route}"


def test_the_source_entity_is_addressable_only_through_the_source_graph(
    both_media: Path,
) -> None:
    """What `T-254` changed, and the half of it that deliberately did not change.

    ``/api/entities/{id}`` still answers ``404 not_found`` for a source node, and
    that is not an oversight: the entity space that endpoint resolves is the
    Knowledge Map's, a source node is not a member of it (D-251), and answering
    ``200`` there would move a response every existing client already reads.

    The node *is* addressable, through the surface built for it — by its
    two-part source id, which is how the rest of the project addresses a run,
    with the three-part global id echoed back as ``center_id``.
    """
    pytest.importorskip("fastapi")
    import api_harness

    for label, client in api_harness.both_clients(both_media):
        response = client.get("/api/entities/youtube:fixture-pass:source")
        assert response.status_code == 404, label
        assert response.json()["error"]["code"] == "not_found", label

        served = client.get("/api/source-graph/neighborhood/youtube:fixture-pass")
        assert served.status_code == 200, label
        data = served.json()["data"]
        assert data["center_id"] == "youtube:fixture-pass:source", label
        assert data["source"]["entity_type"] == "source", label


def test_the_graph_still_draws_only_knowledge_and_concepts(both_media: Path) -> None:
    pytest.importorskip("fastapi")
    import api_harness

    for label, client in api_harness.both_clients(both_media):
        body = client.get("/api/graph", params={"limit": 500}).json()
        types = {node["entity_type"] for node in body["data"]["nodes"]}
        assert types, label
        assert types <= {"knowledge_unit", "concept"}, f"{label}: {types}"
