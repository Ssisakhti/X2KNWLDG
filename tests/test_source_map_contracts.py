"""What `T-251` froze, checked without a JSON Schema validator.

``tests/test_source_map_schemas.py`` holds the records to
``schemas/synthesis/v1/`` and needs ``jsonschema``, a ``dev`` extra. Everything
here needs nothing but the standard library, so the contract's other half runs
on a bare core install too (ADR 0001 invariant 5): the identifiers, the input
digests, the source entity every adapter now emits, the facts the committed
"gate-refused" fixtures actually state, and the frozen API shapes.

The API section was deliberately about *shapes and their absence*. `T-251`
froze ``SourceGraphResponse`` and ``SourceNeighborhoodResponse`` without adding
the two paths that would return them, and this file asserted that the shapes
existed, that they were complete, and that the served surface was still exactly
eleven paths — because a contract frozen ahead of its routes is only honest
while both halves of that sentence are checked.

`T-254` added the routes, which is the event the arrangement was designed to
produce: the assertions about absence *failed*, and each was inverted rather
than deleted, because the claim underneath them — that the served surface
changes only when a task means to change it, and that no declared shape is
unreachable — is the claim worth keeping.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import ids, synthesis
from x2knwldg.adapters import adapt_project, adapt_run
from x2knwldg.constants import (
    MAX_SOURCE_CANDIDATES,
    MAX_SOURCE_RELATION_BASIS,
    SOURCE_RELATION_SCOPES,
    SOURCE_RELATION_TYPES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "source-map"
OPENAPI_PATH = PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json"
TYPES_PATH = PROJECT_ROOT / "schemas" / "api" / "v1" / "types.d.ts"

YOUTUBE_CASES = ["pass-run", "partial-run", "fail-run"]
TWITTER_CASES = [
    "single-post",
    "self-thread",
    "quote",
    "persian-rtl",
    "partial-thread",
    "tombstone",
    "edit",
]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(case: str) -> Path:
    youtube = YOUTUBE_RUNS / case
    return youtube if youtube.is_dir() else TWITTER_RUNS / case


def _adapt(case: str):
    run_dir = _run(case)
    return adapt_run(run_dir, run_dir.parents[1])


# --------------------------------------------------------------------------
# 1. The two identifiers
# --------------------------------------------------------------------------


def test_a_source_entity_id_is_the_reserved_local_id() -> None:
    global_id = ids.source_entity_global_id("youtube:pqlWNihgdjI")
    assert global_id.value == "youtube:pqlWNihgdjI:source"
    assert global_id.local_id == ids.SOURCE_ENTITY_LOCAL_ID


def test_a_source_entity_id_accepts_either_form_of_its_source() -> None:
    """A ``SourceId`` and its string spell the same entity."""
    parsed = ids.make_source_id("twitter", "20")
    assert ids.source_entity_global_id(parsed) == ids.source_entity_global_id("twitter:20")


def test_a_malformed_source_is_refused_rather_than_formatted() -> None:
    for value in ("not-a-source-id", "youtube:", "YouTube:abc", "a:b:c", 7, None):
        with pytest.raises(ids.IdError):
            ids.source_entity_global_id(value)  # type: ignore[arg-type]


def test_a_relation_id_is_deterministic() -> None:
    first = ids.source_relation_id("twitter:20", "youtube:abc", "critiques", "partial")
    again = ids.source_relation_id("twitter:20", "youtube:abc", "critiques", "partial")
    assert first == again
    assert ids.is_source_relation_id(first)


def test_a_relation_id_is_directional() -> None:
    """``critiques`` is not its own inverse, so the endpoints are never sorted."""
    forward = ids.source_relation_id("twitter:20", "youtube:abc", "critiques", "partial")
    backward = ids.source_relation_id("youtube:abc", "twitter:20", "critiques", "partial")
    assert forward != backward


def test_a_relation_id_separates_the_semantics_the_spec_lets_coexist() -> None:
    """Two records between one pair are distinct when type or scope differs."""
    seen = {
        ids.source_relation_id("twitter:20", "youtube:abc", relation, scope)
        for relation in SOURCE_RELATION_TYPES
        for scope in SOURCE_RELATION_SCOPES
    }
    assert len(seen) == len(SOURCE_RELATION_TYPES) * len(SOURCE_RELATION_SCOPES)


def test_a_relation_id_ignores_basis_and_rationale() -> None:
    """Identity by design: more grounds update one record, they do not mint another.

    Stated as a test because it is the decision most likely to be quietly
    reversed later — folding the basis in looks like extra rigour and would
    instead churn ids every time evidence accumulated.
    """
    signature = ("twitter:20", "youtube:abc", "supports", "broad")
    assert ids.source_relation_id(*signature) == ids.source_relation_id(*signature)


def test_a_relation_id_refuses_a_source_related_to_itself() -> None:
    with pytest.raises(ids.IdError, match="two different sources"):
        ids.source_relation_id("youtube:abc", "youtube:abc", "supports", "broad")


def test_a_relation_id_refuses_a_vocabulary_it_does_not_own() -> None:
    """A KU-level type is not a source-level one, however familiar it looks."""
    with pytest.raises(ids.IdError):
        ids.source_relation_id("twitter:20", "youtube:abc", "causes", "broad")
    with pytest.raises(ids.IdError):
        ids.source_relation_id("twitter:20", "youtube:abc", "critiques", "80%")


def test_a_relation_id_cannot_be_forged_across_its_separator() -> None:
    """No part can spell the separator, so no two signatures can collide.

    The endpoints are validated as source ids and the other two against closed
    vocabularies, so a payload-splitting attempt is refused before it is hashed
    rather than producing a second signature's digest.
    """
    with pytest.raises(ids.IdError):
        ids.source_relation_id("twitter:20\x1fyoutube:abc", "youtube:z", "supports", "broad")


def test_a_relation_id_shape_check_is_only_a_shape_check() -> None:
    assert ids.is_source_relation_id("SR-0123456789abcdef")
    assert not ids.is_source_relation_id("SR-0123456789ABCDEF")
    assert not ids.is_source_relation_id("SR-0123")
    assert not ids.is_source_relation_id("SR-")
    assert not ids.is_source_relation_id(None)


# --------------------------------------------------------------------------
# 2. The input digests
# --------------------------------------------------------------------------


def test_the_digest_covers_the_three_canonical_inputs() -> None:
    digests = synthesis.canonical_input_digests(YOUTUBE_RUNS / "pass-run")
    assert set(digests) == {field for field, _ in synthesis.CANONICAL_INPUTS}
    assert all(len(value) == 64 for value in digests.values())


def test_the_digest_is_content_only(tmp_path: Path) -> None:
    """A copied run digests identically; mtime and location are not evidence.

    The distinction from ``index.scanner``'s digest, which folds in mtime as a
    prefilter: that one answers "has anything been touched", and a brief that
    went stale on a file copy would cry wolf until nobody read the warning.
    """
    import shutil

    original = YOUTUBE_RUNS / "pass-run"
    copied = tmp_path / "elsewhere"
    shutil.copytree(original, copied)
    (copied / "report.md").write_text("regenerated, and irrelevant\n", encoding="utf-8")
    assert synthesis.run_digest(copied) == synthesis.run_digest(original)


def test_the_digest_moves_when_the_knowledge_moves(tmp_path: Path) -> None:
    import shutil

    copied = tmp_path / "run"
    shutil.copytree(YOUTUBE_RUNS / "pass-run", copied)
    before = synthesis.run_digest(copied)
    document = _load(copied / "knowledge_units.json")
    document["units"][0]["content"] += " (edited)"
    (copied / "knowledge_units.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    assert synthesis.run_digest(copied) != before


def test_an_unextracted_run_has_a_digest_rather_than_an_error(tmp_path: Path) -> None:
    """Absence is a fact about the run, and a stable one."""
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    assert synthesis.run_digest(empty) == synthesis.run_digest(tmp_path / "also-nothing")
    assert synthesis.file_digest(empty / "knowledge_units.json") == synthesis.ABSENT_DIGEST


def test_a_present_but_unreadable_input_is_not_treated_as_absent(tmp_path: Path) -> None:
    """Damage is not absence: reading it as empty would hide unseen evidence."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "knowledge_units.json").mkdir()  # a directory where a file belongs
    with pytest.raises(OSError):
        synthesis.file_digest(run / "knowledge_units.json")


def test_the_digest_names_its_fields_so_a_later_input_cannot_collide() -> None:
    """The field names are in the hashed text, not only their values.

    Without them, adding a fourth canonical input later would produce a digest
    indistinguishable from one computed over a different three.
    """
    digests = synthesis.canonical_input_digests(YOUTUBE_RUNS / "pass-run")
    assert synthesis.run_digest(YOUTUBE_RUNS / "pass-run") != _naive_digest(digests)


def _naive_digest(digests: dict[str, str]) -> str:
    import hashlib

    return hashlib.sha256("".join(digests.values()).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 3. One source entity per run, both media
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", YOUTUBE_CASES + TWITTER_CASES)
def test_every_run_emits_exactly_one_source_entity(case: str) -> None:
    records = _adapt(case)
    assert len(records.source_entities) == 1


@pytest.mark.parametrize("case", ["fail-run", "partial-run", "tombstone"])
def test_a_run_that_did_not_pass_still_gets_a_source_node(case: str) -> None:
    """A Source Map that omitted a failed run would report a smaller library."""
    assert len(_adapt(case).source_entities) == 1


@pytest.mark.parametrize("case", YOUTUBE_CASES + TWITTER_CASES)
def test_the_source_entity_is_shaped_as_the_contract_states(case: str) -> None:
    run_dir = _run(case)
    entity = _adapt(case).source_entities[0]
    metadata = _load(run_dir / "metadata.json")

    assert entity["entity_type"] == "source"
    assert entity["provenance_class"] == "source"
    assert entity["local_id"] == ids.SOURCE_ENTITY_LOCAL_ID
    assert entity["global_id"] == f"{entity['source_id']}:{ids.SOURCE_ENTITY_LOCAL_ID}"
    assert entity["kind"] is None
    assert entity["canonical_path"].endswith("metadata.json")
    # The label is the original title, verbatim — never a generated summary and
    # never a translation. The output-language policy governs derived narrative;
    # a source title is acquisition metadata and is preserved as it is.
    assert entity["label"] == metadata.get("title")


@pytest.mark.parametrize("case", YOUTUBE_CASES + TWITTER_CASES)
def test_the_source_entity_carries_no_second_copy_of_the_status(case: str) -> None:
    """The ``Source`` record owns the status. Two copies is one that goes stale."""
    entity = _adapt(case).source_entities[0]
    assert "status" not in entity
    assert not any(key.endswith("_status") for key in entity)


@pytest.mark.parametrize("case", YOUTUBE_CASES + TWITTER_CASES)
def test_the_source_entity_id_collides_with_no_artifact(case: str) -> None:
    """``check_records`` claims it in the artifacts' own namespace, so this holds.

    Asserted rather than assumed: ``YouTubeAdapter``'s raw artifact key is
    ``raw_source`` today, and a future adapter spelling one ``source`` would
    otherwise overwrite the source node silently.
    """
    records = _adapt(case)
    artifact_ids = {artifact["id"] for artifact in records.artifacts}
    entity_ids = {entity["global_id"] for entity in records.entities}
    for entity in records.source_entities:
        assert entity["global_id"] not in artifact_ids
        assert entity["global_id"] not in entity_ids


def test_a_project_emits_one_source_entity_per_run(tmp_path: Path) -> None:
    import shutil

    output = tmp_path / "output"
    output.mkdir(parents=True)
    shutil.copytree(YOUTUBE_RUNS / "pass-run", output / "pass-run")
    shutil.copytree(TWITTER_RUNS / "quote", output / "twitter-quote")
    records = adapt_project(tmp_path)
    assert len(records.source_entities) == len(records.sources) == 2
    assert {entity["source_id"] for entity in records.source_entities} == {
        source["id"] for source in records.sources
    }


def test_the_library_projection_emits_no_source_entity(tmp_path: Path) -> None:
    """A canonical concept belongs to no source and is not one."""
    import shutil

    from x2knwldg.adapters import adapt_library
    from x2knwldg.library import rebuild_library

    output = tmp_path / "output"
    output.mkdir(parents=True)
    shutil.copytree(YOUTUBE_RUNS / "pass-run", output / "pass-run")
    rebuild_library(output)
    assert adapt_library(output / "library", tmp_path).source_entities == []


# --------------------------------------------------------------------------
# 4. The committed "gate-refused" fixtures really are dishonest
# --------------------------------------------------------------------------
#
# A fixture filed as gate-refused is, by construction, one the schema accepts.
# That makes it the easiest kind of fixture to get wrong: it can be *valid* in
# every sense and simply not test anything. So the specific fact each one claims
# is asserted here, against the runs it cites, before any gate exists to refuse
# it. T-252 and T-253 are then written against a case that is known to be a lie.


def _brief(name: str) -> dict:
    return _load(FIXTURE_DIR / "invalid" / name)


def _units(run_dir: Path) -> set[str]:
    return {unit["id"] for unit in _load(run_dir / "knowledge_units.json")["units"]}


def test_the_unknown_support_fixture_names_a_unit_the_run_does_not_hold() -> None:
    brief = _brief("brief-support-names-an-unknown-unit.json")
    assert not set(brief["thesis"]["based_on"]) <= _units(YOUTUBE_RUNS / "pass-run")


def test_the_source_mismatch_fixture_cites_another_run_entirely() -> None:
    brief = _brief("brief-source-id-is-another-source.json")
    assert brief["generated_from"] == synthesis.canonical_input_digests(YOUTUBE_RUNS / "pass-run")
    assert not brief["source_id"].startswith("youtube:")


def test_the_overstated_status_fixture_outranks_its_run() -> None:
    brief = _brief("brief-status-is-stronger-than-the-run.json")
    run_status = _load(YOUTUBE_RUNS / "partial-run" / "validation.json")["status"]
    assert brief["status"] == "PASS" and run_status == "PARTIAL"
    assert brief["generated_from"] == synthesis.canonical_input_digests(
        YOUTUBE_RUNS / "partial-run"
    )


def test_the_stale_digest_fixture_does_not_match_the_file_it_names() -> None:
    brief = _brief("brief-digest-is-stale.json")
    actual = synthesis.canonical_input_digests(YOUTUBE_RUNS / "pass-run")
    assert brief["generated_from"]["knowledge_units_sha256"] != actual["knowledge_units_sha256"]
    assert len(brief["generated_from"]["knowledge_units_sha256"]) == 64


def test_the_duplicate_point_fixture_really_repeats_one_id() -> None:
    brief = _brief("brief-duplicate-point-id.json")
    point_ids = [point["id"] for point in brief["key_points"]]
    assert len(point_ids) != len(set(point_ids))


def test_the_misowned_basis_fixture_names_a_unit_of_the_wrong_endpoint() -> None:
    """The named unit is real in the corpus and absent from the endpoint claiming it.

    Both halves are asserted, and the first version of this test asserted
    neither usefully: it checked that ``from_ku_id`` was a unit of *some* run,
    which is true of ``KU-000001`` for every run in the tree — so the fixture it
    vouched for was a perfectly honest document, and `T-253`'s gate accepted it.
    A fixture filed as a lie has to be checked for being one.
    """
    relation = _brief("relation-basis-unit-belongs-to-the-other-endpoint.json")["relations"][0]
    ground = relation["basis"][0]
    claiming_endpoint = _units(YOUTUBE_RUNS / "pass-run")

    assert ground["to_ku_id"] not in claiming_endpoint, "the lie: the endpoint has no such unit"
    assert ground["to_ku_id"] in _units(
        TWITTER_RUNS / "partial-thread"
    ), "and it is a real id elsewhere, so nothing about it looks wrong"
    assert ground["from_ku_id"] in _units(TWITTER_RUNS / "quote"), "the other side is honest"


def test_the_self_relation_fixture_joins_one_source_to_itself() -> None:
    relation = _brief("relation-joins-a-source-to-itself.json")["relations"][0]
    assert relation["from_source_id"] == relation["to_source_id"]
    # And the id it carries could never have been minted for it.
    with pytest.raises(ids.IdError):
        ids.source_relation_id(
            relation["from_source_id"],
            relation["to_source_id"],
            relation["relation_type"],
            relation["scope"],
        )


def test_the_wrong_id_fixture_carries_a_digest_of_something_else() -> None:
    relation = _brief("relation-id-does-not-match-its-parts.json")["relations"][0]
    assert ids.is_source_relation_id(relation["id"])
    assert relation["id"] != ids.source_relation_id(
        relation["from_source_id"],
        relation["to_source_id"],
        relation["relation_type"],
        relation["scope"],
    )


def test_the_duplicate_id_fixture_holds_two_records_under_one_id() -> None:
    relations = _brief("container-duplicates-a-relation-id.json")["relations"]
    assert len({relation["id"] for relation in relations}) < len(relations)
    assert relations[0] != relations[1], "identical records would be caught by uniqueItems"


def test_the_valid_relation_fixture_carries_the_id_its_parts_spell() -> None:
    """The positive case, so the fixture pins the id rule as well as the shape."""
    relation = _load(FIXTURE_DIR / "valid" / "synthesis" / "source_relations.json")["relations"][0]
    assert relation["id"] == ids.source_relation_id(
        relation["from_source_id"],
        relation["to_source_id"],
        relation["relation_type"],
        relation["scope"],
    )


def test_the_valid_fixtures_cite_digests_that_are_current() -> None:
    for name, run_dir in (
        ("youtube-source_knowledge.json", YOUTUBE_RUNS / "pass-run"),
        ("twitter-source_knowledge.json", TWITTER_RUNS / "quote"),
        ("partial-source_knowledge.json", YOUTUBE_RUNS / "partial-run"),
    ):
        brief = _load(FIXTURE_DIR / "valid" / name)
        assert brief["generated_from"] == synthesis.canonical_input_digests(run_dir)


def test_every_valid_support_id_exists_in_the_run_it_cites() -> None:
    for name, run_dir in (
        ("youtube-source_knowledge.json", YOUTUBE_RUNS / "pass-run"),
        ("twitter-source_knowledge.json", TWITTER_RUNS / "quote"),
        ("partial-source_knowledge.json", YOUTUBE_RUNS / "partial-run"),
    ):
        brief = _load(FIXTURE_DIR / "valid" / name)
        units = _units(run_dir)
        supported = [brief["thesis"], *brief["key_points"], *brief["limitations_or_tensions"]]
        for statement in supported:
            assert set(statement["based_on"]) <= units, name
            assert statement["based_on"], name


def test_every_valid_basis_unit_belongs_to_the_endpoint_that_claims_it() -> None:
    owners = {
        "twitter:2094039408081068233": _units(TWITTER_RUNS / "quote"),
        "youtube:fixture-pass": _units(YOUTUBE_RUNS / "pass-run"),
    }
    for name in ("source_relations.json", "source_relations.bounded.json"):
        document = _load(FIXTURE_DIR / "valid" / "synthesis" / name)
        for relation in document["relations"]:
            for ground in relation["basis"]:
                assert ground["from_ku_id"] in owners[relation["from_source_id"]]
                assert ground["to_ku_id"] in owners[relation["to_source_id"]]


# --------------------------------------------------------------------------
# 5. The frozen API shapes — present, complete, and not yet served
# --------------------------------------------------------------------------

SOURCE_GRAPH_COMPONENTS = {
    "SourceKnowledgeAvailability",
    "SourceRelationSummary",
    "SourceRelationDetail",
    "SourceGraphPayload",
    "SourceGraphCounts",
    "SourceGraphResponse",
    "SourceNeighborhoodPayload",
    "SourceNeighborhoodResponse",
}

#: The two operations `T-251` froze the envelopes ahead of, and `T-254` added.
SOURCE_GRAPH_PATHS = {
    "/api/source-graph",
    "/api/source-graph/neighborhood/{source_id}",
}


@pytest.fixture(scope="module")
def openapi() -> dict:
    return _load(OPENAPI_PATH)


def test_the_source_graph_shapes_are_frozen(openapi: dict) -> None:
    assert SOURCE_GRAPH_COMPONENTS <= set(openapi["components"]["schemas"])


def test_the_served_surface_grew_by_exactly_the_two(openapi: dict) -> None:
    """Thirteen paths, all ``GET``. `T-251` added shapes; `T-254` added routes.

    This test read ``len(...) == 11`` and *no* source-graph path while the
    shapes were frozen ahead of the operations. It is inverted rather than
    deleted, because the claim it was making — that the served surface changes
    only when a task means to change it — is the claim worth keeping.
    """
    assert len(openapi["paths"]) == 13
    assert {path for path in openapi["paths"] if "source-graph" in path} == (
        SOURCE_GRAPH_PATHS
    )
    for path, operations in openapi["paths"].items():
        assert set(operations) == {"get"}, path


def test_no_declared_shape_is_unreachable_any_more(openapi: dict) -> None:
    """Every component is reached from an operation, the source-graph ones now too.

    Walked from the operations outward, because a component reached *through*
    another is reached. While the shapes were frozen ahead of their paths this
    asserted that the unreachable set was **exactly** the eight source-graph
    components; `T-254` served them, so the honest assertion is that the set is
    now empty — and it is still exact in both directions, so an existing
    component that stopped being reachable would still show up here.
    """
    schemas = openapi["components"]["schemas"]
    reachable: set[str] = set()
    pending = [
        name
        for name in schemas
        if f'"#/components/schemas/{name}"' in json.dumps(openapi["paths"])
    ]
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        body = json.dumps(schemas[name])
        pending.extend(
            candidate
            for candidate in schemas
            if candidate not in reachable
            and f'"#/components/schemas/{candidate}"' in body
        )
    assert set(schemas) - reachable == set()


def test_nothing_is_referenced_by_nothing_at_all(openapi: dict) -> None:
    """The other side of ``test_every_declared_component_is_reachable``.

    That test exempted two components by name while their operations did not
    exist; this one required the exemption to be exhaustive, so that the day an
    operation referenced ``SourceGraphResponse`` it would **fail** and force the
    exemption out rather than let it outlive its reason. That day was `T-254`,
    and this is what the test became: no component is referenced by nothing.
    """
    document = json.dumps(openapi)
    orphans = {
        name
        for name in openapi["components"]["schemas"]
        if document.count(f'"#/components/schemas/{name}"') == 0
    }
    assert orphans == set()


def test_the_two_operations_return_the_two_envelopes(openapi: dict) -> None:
    """The wiring itself, named rather than inferred from a reachability walk."""
    returned = {
        path: operation["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        for path, operation in openapi["paths"].items()
        if path in SOURCE_GRAPH_PATHS
    }
    assert returned == {
        "/api/source-graph": "#/components/schemas/SourceGraphResponse",
        "/api/source-graph/neighborhood/{source_id}": (
            "#/components/schemas/SourceNeighborhoodResponse"
        ),
    }


def test_the_basis_bound_in_the_contract_is_the_one_in_the_source(openapi: dict) -> None:
    """A number retyped into a document is a number that drifts."""
    detail = openapi["components"]["schemas"]["SourceRelationDetail"]
    assert detail["properties"]["basis"]["maxItems"] == MAX_SOURCE_RELATION_BASIS


def test_a_bounded_basis_must_state_both_counts(openapi: dict) -> None:
    """``basis_returned`` alone would present a truncation as the whole basis."""
    detail = openapi["components"]["schemas"]["SourceRelationDetail"]
    assert {"basis_total", "basis_returned"} <= set(detail["required"])
    summary = openapi["components"]["schemas"]["SourceRelationSummary"]
    assert "basis_total" in summary["required"]
    assert "basis" not in summary["properties"], "a summary carries the count, not the grounds"


def test_the_counts_are_three_separate_numbers(openapi: dict) -> None:
    counts = openapi["components"]["schemas"]["SourceGraphCounts"]
    assert {
        "sources_returned",
        "relations_returned",
        "relations_omitted",
        "sources_total",
    } == set(counts["required"])


def test_an_absent_brief_is_a_state_rather_than_an_empty_one(openapi: dict) -> None:
    availability = openapi["components"]["schemas"]["SourceKnowledgeAvailability"]
    assert set(availability["properties"]["state"]["enum"]) == {
        "available",
        "unavailable",
        "stale",
    }
    assert set(availability["required"]) == {"state", "brief", "reason"}


def test_no_source_relation_shape_publishes_a_confidence(openapi: dict) -> None:
    for name in ("SourceRelationSummary", "SourceRelationDetail"):
        schema = openapi["components"]["schemas"][name]
        assert "confidence" not in schema["properties"], name
        assert schema["additionalProperties"] is False


def test_direction_is_two_fields_rather_than_a_flag(openapi: dict) -> None:
    """The Focus composition places incoming left and outgoing right."""
    payload = openapi["components"]["schemas"]["SourceNeighborhoodPayload"]
    assert {"incoming", "outgoing"} <= set(payload["required"])


def test_the_generated_declarations_carry_the_new_shapes() -> None:
    declarations = TYPES_PATH.read_text(encoding="utf-8")
    for name in SOURCE_GRAPH_COMPONENTS | {"SourceKnowledge", "SourceRelation"}:
        assert f"export type {name} = " in declarations, name


def test_the_declarations_name_the_synthesis_primitives_distinctly() -> None:
    """``SynthesisRunStatus`` is not a renamed ``RunStatus``: it has three members.

    The uniform prefix is what keeps the two contracts' identically-named
    primitives from silently becoming one TypeScript type.
    """
    declarations = TYPES_PATH.read_text(encoding="utf-8")
    assert 'export type SynthesisRunStatus = "PASS" | "PARTIAL" | "FAIL";' in declarations
    assert '"UNKNOWN"' in declarations, "the index model's RunStatus still has it"


def test_the_bounds_are_stated_where_they_are_used() -> None:
    """Both constants are positive and the candidate bound admits the corpus.

    Measured by ``tools/measure_source_bounds.py``: the committed fixtures plus
    any ingested run come to well under ``MAX_SOURCE_CANDIDATES`` counterparts
    per source, so the bound does not bind on this corpus and cannot be
    silently satisfied by an empty one either.
    """
    assert MAX_SOURCE_CANDIDATES > 0
    assert MAX_SOURCE_RELATION_BASIS > 0
    runs = list(YOUTUBE_RUNS.glob("*/metadata.json")) + list(
        TWITTER_RUNS.glob("*/metadata.json")
    )
    assert len(runs) - 1 <= MAX_SOURCE_CANDIDATES


# --------------------------------------------------------------------------
# 6. The counts the documentation quotes are the ones on disk
# --------------------------------------------------------------------------
#
# `PROJECT_MANAGEMENT.md` §3 states how many fixtures there are and how they
# split between "the schema refuses this" and "a later gate must". Those numbers
# were wrong the first time they were written — 15/7 against an actual 13/9 —
# and nothing would have said so, which is the failure mode
# `test_the_map_label_budget_in_the_docs_is_the_one_in_the_source` already
# guards one document over. A fixture added or re-filed now moves a number the
# docs quote, and this fails until the docs are moved with it.

PROJECT_MANAGEMENT = PROJECT_ROOT / "docs" / "PROJECT_MANAGEMENT.md"


def _fixture_split() -> tuple[int, int, int]:
    """``(documents, schema_refused, gate_refused)`` counted from the tree."""
    valid = list((FIXTURE_DIR / "valid").rglob("*.json"))
    invalid = [
        path
        for path in (FIXTURE_DIR / "invalid").glob("*.json")
        if not path.name.endswith(".note.json")
    ]
    refused = [_load(path.with_name(f"{path.stem}.note.json"))["refused_by"] for path in invalid]
    return (
        len(valid) + len(invalid),
        refused.count("schema"),
        refused.count("gate"),
    )


def test_the_fixture_counts_in_the_docs_are_the_ones_on_disk() -> None:
    documents, schema_refused, gate_refused = _fixture_split()
    row = PROJECT_MANAGEMENT.read_text(encoding="utf-8")
    assert f"holds **{documents} documents**" in row
    assert f"**{schema_refused}** refused by the schemas" in row
    assert f"**{gate_refused}** by the `T-252`/`T-253` gates" in row


def test_every_gate_fixture_is_inspected_by_name() -> None:
    """A gate case the schema accepts and no test inspects is a valid document.

    That is the whole hazard of the ``gate`` category: it is filed as dishonest
    precisely because the schema cannot see the lie, so if nothing else looks at
    it either, it is a perfectly valid document sitting in an ``invalid/``
    directory proving nothing. Every one is therefore named in this file, and a
    tenth added without a fact fails here.

    Matched by filename rather than by counting test definitions — the first
    version counted, and counted two assertions about the *valid* fixtures along
    with them.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    unexamined = []
    for path in sorted((FIXTURE_DIR / "invalid").glob("*.json")):
        if path.name.endswith(".note.json"):
            continue
        note = _load(path.with_name(f"{path.stem}.note.json"))
        if note["refused_by"] == "gate" and f'"{path.name}"' not in source:
            unexamined.append(path.name)
    assert unexamined == [], (
        f"these gate fixtures are refused by nothing and inspected by nothing: {unexamined}"
    )
