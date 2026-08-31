"""Contract tests for the frozen v1 HTTP API (``T-005``).

``schemas/api/v1/openapi.json`` freezes canvas plan §15. It defines no response
body of its own for anything the index model already describes — it ``$ref``s
``schemas/v1/`` — so the question these tests answer is not "is the document
well-formed" but **"does a real run, put through the real adapters, fit through
these endpoints unchanged?"**

That is why every payload test builds its instance from
``x2knwldg.adapters`` and every search test from ``query.search_knowledge``,
over the committed fixture runs in ``tests/fixtures/runs/`` — which include a
``PARTIAL`` and a ``FAIL`` run — and additionally over the real sample when
``output/`` is on disk. A contract validated only against hand-written examples
would be a contract agreed with nobody.

Nothing here writes to ``output/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
)
from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402
from referencing.jsonschema import DRAFT202012  # noqa: E402

from x2knwldg import ids  # noqa: E402
from x2knwldg.adapters import IndexRecords, adapt_library, adapt_project, adapt_run  # noqa: E402
from x2knwldg.query import search_knowledge  # noqa: E402
from x2knwldg.repository import (  # noqa: E402
    EntityQuery,
    GraphQuery,
    IndexUnavailable,
    InvalidId,
    InvalidQuery,
    MemoryRepository,
    NeighborhoodQuery,
    RelationQuery,
    SearchQuery,
    SourceQuery,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_DIR = PROJECT_ROOT / "schemas" / "v1"
API_DIR = PROJECT_ROOT / "schemas" / "api" / "v1"
OPENAPI_PATH = API_DIR / "openapi.json"
OPENAPI_ID = "https://x2knwldg.local/schemas/api/v1/openapi.json"
SAMPLE_DIR = PROJECT_ROOT / "output" / "pqlWNihgdjI"
LIBRARY_DIR = PROJECT_ROOT / "output" / "library"
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"

SCHEMA_FILES = [
    "common.schema.json",
    "source.schema.json",
    "artifact.schema.json",
    "locator.schema.json",
    "entity_ref.schema.json",
    "indexed_relation.schema.json",
]

#: The frozen surface. Written out so that adding an endpoint is a deliberate
#: act with a test to update, not a side effect of editing the document.
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
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def openapi() -> dict:
    return _load(OPENAPI_PATH)


@pytest.fixture(scope="module")
def registry(openapi: dict) -> Registry:
    resources = [
        (schema["$id"], Resource.from_contents(schema))
        for schema in (_load(V1_DIR / name) for name in SCHEMA_FILES)
    ]
    # The document carries no $id of its own: a root $id is not a legal OpenAPI
    # field, and openapi-spec-validator rejects it. It is registered under an
    # explicit URI instead, which is what its relative $refs resolve against.
    resources.append(
        (OPENAPI_ID, Resource.from_contents(openapi, default_specification=DRAFT202012))
    )
    return Registry().with_resources(resources)


@pytest.fixture(scope="module")
def validate(registry: Registry):
    """Validate an instance against one component of the frozen contract."""

    def _validate(component: str, instance: Any) -> list[str]:
        validator = Draft202012Validator(
            {"$ref": f"{OPENAPI_ID}#/components/schemas/{component}"}, registry=registry
        )
        return [error.message for error in validator.iter_errors(instance)]

    return _validate


# --------------------------------------------------------------------------
# Runs to test against
# --------------------------------------------------------------------------


def _runs() -> list[Path]:
    runs = sorted(path.parent for path in FIXTURE_RUNS.glob("*/metadata.json"))
    assert runs, "the committed run fixtures are missing"
    if (SAMPLE_DIR / "metadata.json").exists():
        runs.append(SAMPLE_DIR)
    return runs


RUNS = _runs()
RUN_IDS = [run.name for run in RUNS]

#: The T-007 seam over the committed fixtures. Section 5 asks whether what it
#: returns fits the endpoints; section 3 uses it for the additive search fields.
FIXTURE_REPO = MemoryRepository.from_project(PROJECT_ROOT, output_dir="tests/fixtures/runs")

#: A canonical concept, and the cross-source edge that reaches it, written out
#: rather than read from ``output/library/`` — which ``finalize_run`` builds and
#: ``.gitignore`` excludes, so a seam test that depended on it never ran in CI.
#: ``adapt_library``'s own output is still validated against the schemas by
#: ``test_cross_source_concepts_fit_the_same_endpoints`` where the sample exists.
LIBRARY_CONCEPT = {
    "schema_version": "1.0",
    "global_id": "library:concepts:aaaa00000001",
    "source_type": "library",
    "external_id": "concepts",
    "local_id": "aaaa00000001",
    "library_id": "concept:aaaa00000001",
    "source_id": None,
    "entity_type": "concept",
    "provenance_class": "derived",
    "kind": "canonical_concept",
    "label": "A concept the fixture runs express",
    "confidence": None,
    "canonical_path": "output/library/concepts.json",
}
LIBRARY_EDGE = {
    "schema_version": "1.0",
    "id": "youtube:fixture-pass:KU-000001|expresses_concept|library:concepts:aaaa00000001",
    "from_id": "youtube:fixture-pass:KU-000001",
    "to_id": "library:concepts:aaaa00000001",
    "relation": "expresses_concept",
    "relation_vocabulary": "library_synthetic",
    "provenance_class": "derived",
    "confidence": 1.0,
    "source_id": None,
    "canonical_path": "output/library/graph.json",
}

#: The same seam with the cross-source library records in scope, on every
#: machine rather than only on one that has ingested a video.
LIBRARY_REPO = MemoryRepository(
    adapt_project(PROJECT_ROOT, output_dir="tests/fixtures/runs")
    + IndexRecords(entities=[dict(LIBRARY_CONCEPT)], relations=[dict(LIBRARY_EDGE)]),
    project_root=PROJECT_ROOT,
    output_dir="tests/fixtures/runs",
)

requires_library = pytest.mark.skipif(
    not (LIBRARY_DIR / "concepts.json").exists(),
    reason="output/library/ is built by finalize_run and only the real sample has it",
)


def _adapt(run_dir: Path) -> dict[str, list[dict]]:
    return adapt_run(run_dir, PROJECT_ROOT).by_model()


def _envelope(**payload: Any) -> dict[str, Any]:
    """The envelope every success response carries."""
    return {"api_version": "v1", "schema_version": "1.0", **payload}


def _page(limit: int = 50, next_cursor: str | None = None) -> dict[str, Any]:
    return {"limit": limit, "next_cursor": next_cursor}


# --------------------------------------------------------------------------
# 1. The document
# --------------------------------------------------------------------------


def test_the_document_declares_openapi_3_1(openapi: dict) -> None:
    assert openapi["openapi"].startswith("3.1")
    assert openapi["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"


def test_the_document_is_valid_openapi() -> None:
    """The structural tests below check what the meta-schema cannot; this checks
    what they do not.

    Without it, a mistake in a corner no hand-written test looks at — ``servers``,
    ``tags``, a response header — stays invisible until an OpenAPI validator or a
    code generator is pointed at the file. That is how the root ``$id`` this
    document used to carry went unnoticed: every structural test passed, and the
    document was still not OpenAPI. Validating with ``base_uri`` also proves the
    ``../../v1/`` references resolve from the filesystem, which is what any real
    generator will do with them.
    """
    validator = pytest.importorskip(
        "openapi_spec_validator",
        reason="openapi-spec-validator is a dev-extra dependency; the core package stays zero-dependency",
    )
    from openapi_spec_validator.readers import read_from_filename

    spec, base_uri = read_from_filename(str(OPENAPI_PATH))
    validator.validate(spec, base_uri=base_uri)


def test_the_document_carries_no_root_id() -> None:
    """A root ``$id`` is not a legal OpenAPI field, and tooling rejects it.

    The registry supplies the base URI instead. Kept as a test because the
    mistake is invisible until an OpenAPI validator or a code generator is
    pointed at the file — which is exactly when it is most expensive.
    """
    assert "$id" not in _load(OPENAPI_PATH)


def test_every_ref_resolves(openapi: dict, registry: Registry) -> None:
    """A dangling $ref would only surface when a real request was served."""
    resolver = registry.resolver(base_uri=OPENAPI_ID)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                resolver.lookup(ref)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(openapi)


def test_the_frozen_surface_is_exactly_what_was_frozen(openapi: dict) -> None:
    assert set(openapi["paths"]) == FROZEN_PATHS


def test_v1_is_read_only(openapi: dict) -> None:
    """No endpoint writes. ``raw/`` is immutable evidence and ``output/`` is canonical."""
    for path, operations in openapi["paths"].items():
        assert set(operations) == {"get"}, f"{path} defines a non-GET method"


def test_board_endpoints_are_not_frozen(openapi: dict) -> None:
    """D-027: boards get a contract when Phase 3 gives them a record schema."""
    assert not [path for path in openapi["paths"] if path.startswith("/api/boards")]


def _operations(openapi: dict) -> Iterator[tuple[str, str, dict]]:
    for path, operations in openapi["paths"].items():
        for method, operation in operations.items():
            yield path, method, operation


def test_operation_ids_are_present_and_unique(openapi: dict) -> None:
    seen = [operation["operationId"] for _, _, operation in _operations(openapi)]
    assert len(seen) == len(set(seen))
    assert len(seen) == len(FROZEN_PATHS)


def _resolve_parameter(parameter: dict, openapi: dict) -> dict:
    ref = parameter.get("$ref")
    if ref is None:
        return parameter
    return openapi["components"]["parameters"][ref.rsplit("/", 1)[1]]


def test_every_path_placeholder_is_a_declared_parameter(openapi: dict) -> None:
    for path, _, operation in _operations(openapi):
        placeholders = {
            part[1:-1] for part in path.split("/") if part.startswith("{") and part.endswith("}")
        }
        declared = {
            _resolve_parameter(parameter, openapi)["name"]
            for parameter in operation.get("parameters", [])
            if _resolve_parameter(parameter, openapi)["in"] == "path"
        }
        assert placeholders == declared, path


def test_every_path_parameter_is_required(openapi: dict) -> None:
    for _, _, operation in _operations(openapi):
        for raw in operation.get("parameters", []):
            parameter = _resolve_parameter(raw, openapi)
            if parameter["in"] == "path":
                assert parameter["required"] is True, parameter["name"]


def test_every_operation_returns_a_body(openapi: dict) -> None:
    for path, _, operation in _operations(openapi):
        success = [code for code in operation["responses"] if code.startswith("2")]
        assert success, path
        for code in success:
            assert operation["responses"][code]["content"], f"{path} {code}"


def test_an_operation_that_takes_an_id_can_answer_not_found(openapi: dict) -> None:
    for path, _, operation in _operations(openapi):
        if "{" not in path:
            continue
        assert "404" in operation["responses"], path


def test_an_operation_that_takes_input_can_refuse_it(openapi: dict) -> None:
    """D-020 over HTTP: a rejected id has to have somewhere to be reported."""
    for path, _, operation in _operations(openapi):
        if not operation.get("parameters"):
            continue
        assert "400" in operation["responses"], path


def test_every_operation_can_report_an_unbuilt_index(openapi: dict) -> None:
    """An empty index and an absent one must never look the same to the UI."""
    for path, _, operation in _operations(openapi):
        assert "503" in operation["responses"], path


def test_every_json_response_is_enveloped(openapi: dict, registry: Registry) -> None:
    """Canvas plan §15: responses must carry a schema version."""
    resolver = registry.resolver(base_uri=OPENAPI_ID)
    for path, _, operation in _operations(openapi):
        for code, response in operation["responses"].items():
            content = response.get("content") or {}
            if "$ref" in response:
                response = resolver.lookup(response["$ref"]).contents
                content = response.get("content") or {}
            schema = (content.get("application/json") or {}).get("schema")
            if schema is None:
                continue
            resolved = resolver.lookup(schema["$ref"]).contents
            assert "api_version" in resolved["required"], f"{path} {code}"
            assert "schema_version" in resolved["required"], f"{path} {code}"


def test_every_declared_component_is_reachable(openapi: dict) -> None:
    """A component nothing references is a shape the contract does not actually fix."""
    text = json.dumps(openapi)
    for name in openapi["components"]["schemas"]:
        if name in {"SearchHit"}:  # referenced through the discriminator mapping too
            continue
        assert f'"#/components/schemas/{name}"' in text, name
    for name in openapi["components"]["parameters"]:
        assert f'"#/components/parameters/{name}"' in text, name
    for name in openapi["components"]["responses"]:
        assert f'"#/components/responses/{name}"' in text, name


# --------------------------------------------------------------------------
# 2. Real adapter records fit through the endpoints unchanged
# --------------------------------------------------------------------------


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_list_sources_carries_real_source_records(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)["source"]
    body = _envelope(data=records, page=_page())
    assert not validate("SourceListResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_get_source_carries_the_run_and_its_artifacts(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)
    body = _envelope(data={"source": records["source"][0], "artifacts": records["artifact"]})
    assert not validate("SourceDetailResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_get_source_lists_every_artifact_the_source_names(run_dir: Path) -> None:
    """The embedded artifacts are the ones ``artifact_ids`` promises, not a subset."""
    records = _adapt(run_dir)
    source = records["source"][0]
    assert set(source["artifact_ids"]) == {artifact["id"] for artifact in records["artifact"]}


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_list_entities_carries_real_entity_records(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)["entity_ref"]
    assert records, f"{run_dir.name} produced no entities"
    body = _envelope(data=records, page=_page())
    assert not validate("EntityListResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_get_entity_carries_one_entity(validate, run_dir: Path) -> None:
    body = _envelope(data=_adapt(run_dir)["entity_ref"][0])
    assert not validate("EntityResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_list_relations_carries_real_relation_records(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)["indexed_relation"]
    body = _envelope(data=records, page=_page())
    assert not validate("RelationListResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_get_artifact_carries_one_artifact(validate, run_dir: Path) -> None:
    for artifact in _adapt(run_dir)["artifact"]:
        assert not validate("ArtifactResponse", _envelope(data=artifact))


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_a_missing_artifact_is_reported_rather_than_masked(validate, run_dir: Path) -> None:
    """Canvas plan §15. The record still validates; ``available`` tells the truth."""
    artifacts = _adapt(run_dir)["artifact"]
    for artifact in artifacts:
        assert isinstance(artifact["available"], bool)
        assert not validate("ArtifactResponse", _envelope(data=artifact))


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_graph_carries_real_nodes_and_edges(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)
    body = _envelope(
        data={
            "nodes": records["entity_ref"],
            "edges": records["indexed_relation"],
            "truncated": False,
        },
        page=_page(),
    )
    assert not validate("GraphResponse", body)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_neighborhood_carries_a_centre_and_its_edges(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)
    centre = records["entity_ref"][0]["global_id"]
    body = _envelope(
        data={
            "center_id": centre,
            "depth": 1,
            "nodes": records["entity_ref"],
            "edges": [
                edge
                for edge in records["indexed_relation"]
                if centre in (edge["from_id"], edge["to_id"])
            ],
            "truncated": False,
        }
    )
    assert not validate("NeighborhoodResponse", body)


@requires_library
def test_cross_source_concepts_fit_the_same_endpoints(validate) -> None:
    """``library:concepts:<hash>`` entities are addressed like any other (D-016)."""
    records = adapt_library(LIBRARY_DIR, PROJECT_ROOT).by_model()
    assert not validate("EntityListResponse", _envelope(data=records["entity_ref"], page=_page()))
    assert not validate(
        "RelationListResponse", _envelope(data=records["indexed_relation"], page=_page())
    )


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_status_reports_copied_statuses_and_nothing_else(validate, run_dir: Path) -> None:
    records = _adapt(run_dir)
    tally = {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "UNKNOWN": 0}
    for source in records["source"]:
        tally[source["status"]["overall"]] += 1
    body = _envelope(
        data={
            "index": {"state": "ready", "built_at": "2026-08-31T00:00:00Z", "index_version": 1},
            "counts": {
                "sources": len(records["source"]),
                "artifacts": len(records["artifact"]),
                "entities": len(records["entity_ref"]),
                "relations": len(records["indexed_relation"]),
            },
            "sources_by_status": tally,
            "adapters": [{"name": "youtube", "version": "1.0"}],
        }
    )
    assert not validate("StatusResponse", body)
    assert sum(tally.values()) == len(records["source"])


def test_the_partial_and_fail_fixtures_reach_the_api_as_themselves(validate) -> None:
    """R11/D-013: a dishonest status must be impossible to produce, not merely rare."""
    for name in ("pass", "partial", "fail"):
        run_dir = FIXTURE_RUNS / f"{name}-run"
        source = _adapt(run_dir)["source"][0]
        assert source["status"]["overall"] == name.upper()
        assert not validate("SourceListResponse", _envelope(data=[source], page=_page()))


# --------------------------------------------------------------------------
# 3. Search — the two shapes query.search_knowledge already returns (D-028)
# --------------------------------------------------------------------------


def _as_api_hit(result: dict[str, Any]) -> dict[str, Any]:
    """The additive fields of D-028, attached by the code that will attach them.

    This used to be a reference implementation living here, which is what risk
    R18 described: the frozen shape was proved *reachable* from real
    ``query.search_knowledge`` output, by a helper no server would ever call.
    ``T-007`` moved it into ``repository/memory.py``, so these tests now check
    the same code path ``T-106`` serves — one implementation, not two.
    """
    return FIXTURE_REPO.as_api_hit(result)


def _search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
    return search_knowledge(FIXTURE_RUNS, query, limit=100, **kwargs)


def test_search_over_the_fixtures_returns_something_to_check() -> None:
    assert _search("the"), "the fixture runs produced no search results to validate against"


def test_real_search_results_fit_the_frozen_hit_shapes(validate) -> None:
    hits = [_as_api_hit(result) for result in _search("the")]
    body = _envelope(query="the", data=hits, page=_page())
    errors = validate("SearchResponse", body)
    assert not errors, errors


def test_both_hit_shapes_are_actually_exercised() -> None:
    kinds = {result["type"] for result in _search("the")}
    assert kinds == {"knowledge_unit", "transcript_caption"}


def test_a_knowledge_unit_hit_keeps_its_canonical_field_names(validate) -> None:
    """ADR 0001 invariant 6: ``video_id`` stays ``video_id``."""
    hits = [_as_api_hit(r) for r in _search("the") if r["type"] == "knowledge_unit"]
    assert hits
    for hit in hits:
        assert "video_id" in hit and "id" in hit
        assert not validate("SearchHitKnowledgeUnit", hit)


def test_a_caption_hit_carries_no_global_id(validate) -> None:
    """D-023: v1 emits no caption entities, so a caption has no entity to address."""
    hits = [_as_api_hit(r) for r in _search("the") if r["type"] == "transcript_caption"]
    assert hits
    for hit in hits:
        assert "global_id" not in hit
        assert not validate("SearchHitTranscriptCaption", hit)
    hits[0]["global_id"] = "youtube:abc:KU-000001"
    assert validate("SearchHitTranscriptCaption", hits[0])


def test_a_source_filtered_search_still_fits(validate) -> None:
    hits = [_as_api_hit(r) for r in _search("the", video_id="pass-run")]
    assert hits
    assert not validate("SearchResponse", _envelope(query="the", data=hits, page=_page()))


def test_disabling_the_transcript_fallback_still_fits(validate) -> None:
    hits = [_as_api_hit(r) for r in _search("the", include_transcript_fallback=False)]
    assert {hit["type"] for hit in hits} == {"knowledge_unit"}
    assert not validate("SearchResponse", _envelope(query="the", data=hits, page=_page()))


# --------------------------------------------------------------------------
# 4. What the contract must refuse
# --------------------------------------------------------------------------


def test_an_unversioned_response_is_rejected(validate) -> None:
    assert validate("StatusResponse", {"data": {}})


def test_a_response_claiming_another_api_version_is_rejected(validate, run_dir=None) -> None:
    body = _envelope(data=_adapt(RUNS[0])["source"], page=_page())
    body["api_version"] = "v2"
    assert validate("SourceListResponse", body)


def test_a_status_outside_the_vocabulary_is_rejected(validate) -> None:
    source = _adapt(FIXTURE_RUNS / "fail-run")["source"][0]
    source["status"]["overall"] = "MOSTLY_PASS"
    assert validate("SourceListResponse", _envelope(data=[source], page=_page()))


def test_an_absolute_host_path_is_rejected(validate) -> None:
    """Risk R15 — an index record must never carry a path off this machine."""
    source = _adapt(RUNS[0])["source"][0]
    source["canonical_dir"] = "/Users/someone/X2KNWLDG/output/pqlWNihgdjI"
    assert validate("SourceListResponse", _envelope(data=[source], page=_page()))


def test_an_unknown_error_code_is_rejected(validate) -> None:
    assert validate(
        "ErrorResponse", _envelope(error={"code": "teapot", "message": "no"})
    )


def test_the_documented_error_codes_are_accepted(validate, openapi: dict) -> None:
    codes = openapi["components"]["schemas"]["ErrorCode"]["enum"]
    assert set(codes) == {
        "invalid_id",
        "invalid_request",
        "not_found",
        "unavailable",
        "index_unavailable",
        "internal",
    }
    for code in codes:
        assert not validate("ErrorResponse", _envelope(error={"code": code, "message": "x"}))


def test_a_page_without_a_cursor_field_is_rejected(validate) -> None:
    body = _envelope(data=[], page={"limit": 50})
    assert validate("SourceListResponse", body)


def test_a_null_next_cursor_is_how_a_collection_ends(validate) -> None:
    assert not validate("SourceListResponse", _envelope(data=[], page=_page()))


def test_a_search_hit_of_an_unknown_type_is_rejected(validate) -> None:
    hit = {"type": "vault_note", "video_id": "x", "title": None, "content": "c"}
    assert validate("SearchResponse", _envelope(query="q", data=[hit], page=_page()))


def test_an_extra_field_on_a_record_is_rejected(validate) -> None:
    """``additionalProperties: false`` is what stops the API growing a shadow shape."""
    source = _adapt(RUNS[0])["source"][0]
    source["summary"] = "a field no canonical file states"
    assert validate("SourceListResponse", _envelope(data=[source], page=_page()))


def test_a_user_relation_may_not_carry_a_confidence(validate) -> None:
    relation = {
        "schema_version": "1.0",
        "id": "user-1",
        "from_id": "youtube:pqlWNihgdjI:KU-000001",
        "to_id": "youtube:pqlWNihgdjI:KU-000002",
        "relation": "reminds me of",
        "relation_vocabulary": "user",
        "provenance_class": "user",
        "confidence": 0.9,
    }
    assert validate("RelationListResponse", _envelope(data=[relation], page=_page()))


# --------------------------------------------------------------------------
# 5. The repository serves these endpoints (T-007)
# --------------------------------------------------------------------------
#
# Sections 2 and 3 ask whether *records* fit the contract. This section asks the
# question that actually decides whether ``T-105``–``T-108`` can be written
# against the seam: does what ``IndexRepository`` returns — payload and page
# alike — validate as the response body of the endpoint it serves, with the
# route adding nothing but the envelope?


def test_the_status_payload_is_served_whole(validate) -> None:
    payload = FIXTURE_REPO.status().payload()
    assert not validate("StatusPayload", payload)
    assert not validate("StatusResponse", _envelope(data=payload))


def test_an_unbuilt_index_still_answers_status(validate) -> None:
    """D-030: ``503`` exists so the UI can tell an empty index from an absent one."""
    payload = MemoryRepository.unavailable("absent").status().payload()
    assert not validate("StatusResponse", _envelope(data=payload))
    assert payload["index"]["state"] == "absent"
    assert payload["counts"]["sources"] == 0


def test_list_sources_is_served_as_a_page(validate) -> None:
    page = FIXTURE_REPO.list_sources(SourceQuery(limit=2))
    assert not validate("PageInfo", page.page_info())
    assert not validate("SourceListResponse", _envelope(data=page.items, page=page.page_info()))
    assert page.next_cursor, "three fixture runs do not fit in a page of two"


def test_get_source_is_served_whole(validate) -> None:
    detail = FIXTURE_REPO.get_source("youtube:fixture-pass")
    assert detail is not None
    assert not validate("SourceDetail", detail.payload())
    assert not validate("SourceDetailResponse", _envelope(data=detail.payload()))


def test_list_entities_and_relations_are_served_as_pages(validate) -> None:
    entities = FIXTURE_REPO.list_entities(EntityQuery(source_id="youtube:fixture-pass"))
    relations = FIXTURE_REPO.list_relations(RelationQuery(source_id="youtube:fixture-pass"))
    assert entities.items and relations.items
    assert not validate(
        "EntityListResponse", _envelope(data=entities.items, page=entities.page_info())
    )
    assert not validate(
        "RelationListResponse", _envelope(data=relations.items, page=relations.page_info())
    )


def test_single_records_are_served_whole(validate) -> None:
    entity = FIXTURE_REPO.list_entities(EntityQuery(limit=1)).items[0]
    assert not validate("EntityResponse", _envelope(data=FIXTURE_REPO.get_entity(entity["global_id"])))
    artifact_id = FIXTURE_REPO.get_source("youtube:fixture-pass").artifacts[0]["id"]
    assert not validate("ArtifactResponse", _envelope(data=FIXTURE_REPO.get_artifact(artifact_id)))


def test_search_is_served_as_a_page(validate) -> None:
    page = FIXTURE_REPO.search(SearchQuery(q="the", limit=5))
    assert page.items
    assert not validate(
        "SearchResponse", _envelope(query="the", data=page.items, page=page.page_info())
    )


def test_graph_and_neighborhood_are_served_whole(validate) -> None:
    graph = FIXTURE_REPO.graph(GraphQuery(limit=2))
    assert not validate("GraphPayload", graph.payload())
    assert not validate("GraphResponse", _envelope(data=graph.payload(), page=graph.page_info()))

    center = graph.nodes[0]["global_id"]
    hood = FIXTURE_REPO.neighborhood(NeighborhoodQuery(entity_id=center, depth=2))
    assert hood is not None
    assert not validate("NeighborhoodPayload", hood.payload())
    assert not validate("NeighborhoodResponse", _envelope(data=hood.payload()))


def test_a_cursor_fits_the_length_the_contract_allows(validate) -> None:
    page = FIXTURE_REPO.list_entities(EntityQuery(limit=1))
    assert not validate("PageInfo", page.page_info())
    assert page.next_cursor and len(page.next_cursor) <= 512


@pytest.mark.parametrize(
    "error,code",
    [
        (InvalidId("bad id"), "invalid_id"),
        (InvalidQuery("bad limit"), "invalid_request"),
        (IndexUnavailable("not built"), "index_unavailable"),
    ],
)
def test_every_repository_refusal_has_a_frozen_error_code(validate, error, code: str) -> None:
    """The taxonomy the repository raises is the taxonomy the contract declares."""
    body = _envelope(error={"code": error.code, "message": str(error)})
    assert error.code == code
    assert not validate("ErrorResponse", body)


def test_the_seam_serves_the_cross_source_concepts_too(validate) -> None:
    page = LIBRARY_REPO.list_entities(EntityQuery(kind="canonical_concept", limit=500))
    assert page.items
    assert not validate("EntityListResponse", _envelope(data=page.items, page=page.page_info()))
    assert all(concept["source_id"] is None for concept in page.items)


def test_the_seam_serves_a_cross_source_edge_from_the_source_that_makes_it(validate) -> None:
    """D-034 over the wire: the edge names no run, and is still the source's."""
    page = LIBRARY_REPO.list_relations(
        RelationQuery(source_id="youtube:fixture-pass", limit=500)
    )
    expresses = [edge for edge in page.items if edge["relation"] == "expresses_concept"]
    assert expresses and all(edge["source_id"] is None for edge in expresses)
    assert not validate(
        "RelationListResponse", _envelope(data=page.items, page=page.page_info())
    )

    graph = LIBRARY_REPO.graph(GraphQuery(source_id="youtube:fixture-pass", limit=500))
    assert not validate("GraphPayload", graph.payload())
    assert {edge["id"] for edge in graph.edges} == {edge["id"] for edge in page.items}, (
        "the graph and the relations list are two views of one fact"
    )
