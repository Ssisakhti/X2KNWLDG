"""Contract tests for the Source Map synthesis schemas (``T-251``).

``schemas/synthesis/v1/`` freezes two derived record families: the per-run
readable brief and the cross-source relation. Nothing generates either yet —
that is `T-252` and `T-253` — so what can be tested now is exactly what a
contract is: that the honest record is accepted, that each dishonest one is
refused, and that the vocabularies and patterns mirrored into the schemas still
agree with the code they were copied from.

The last of those is the drift guard. ``constants.py`` and ``ids.py`` are the
authority; the schemas duplicate them so they can stand alone for TypeScript
generation, exactly as ``schemas/v1/common.schema.json`` duplicates the
canonical relation vocabulary. A duplication nobody checks is two facts.

``jsonschema`` is a ``dev`` extra, so this file skips cleanly on a bare core
install (ADR 0001 invariant 5) — except the parts that need no validator, which
are split out into ``tests/test_source_map_contracts.py`` and run everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
)
from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

from x2knwldg import ids, synthesis  # noqa: E402
from x2knwldg.constants import (  # noqa: E402
    MAX_SOURCE_CANDIDATES,
    RELATION_TYPES,
    SOURCE_RELATION_SCOPES,
    SOURCE_RELATION_TYPES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_ROOT / "schemas" / "synthesis" / "v1"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "source-map"

SCHEMA_FILES = [
    "primitives.schema.json",
    "source_knowledge.schema.json",
    "source_relation.schema.json",
    "source_relations.schema.json",
]

#: Which schema each fixture is judged against. A brief is not a container and
#: must not be validated as one: a fixture validated against the wrong schema is
#: refused for the wrong reason, and the suite then reports agreement it never
#: established. The mapping is by filename prefix, and :func:`_schema_for`
#: refuses a name it does not recognise rather than defaulting to one — the
#: first version of this defaulted, and every ``relation-*`` case was silently
#: being validated as a brief.
BRIEF_SCHEMA = "source_knowledge.schema.json"
CONTAINER_SCHEMA = "source_relations.schema.json"

#: Filename prefix → schema. ``valid/`` names are matched by suffix instead.
FIXTURE_SCHEMAS = {
    "brief-": BRIEF_SCHEMA,
    "relation-": CONTAINER_SCHEMA,
    "container-": CONTAINER_SCHEMA,
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict]:
    return {name: _load(SCHEMA_DIR / name) for name in SCHEMA_FILES}


@pytest.fixture(scope="module")
def registry(schemas: dict[str, dict]) -> Registry:
    return Registry().with_resources(
        [(schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()]
    )


@pytest.fixture(scope="module")
def validate(registry: Registry, schemas: dict[str, dict]):
    def _validate(schema_name: str, instance: Any) -> list[str]:
        validator = Draft202012Validator(schemas[schema_name], registry=registry)
        return [error.message for error in validator.iter_errors(instance)]

    return _validate


def _refs(node: object, found: list[str] | None = None) -> list[str]:
    """Every ``$ref`` string under *node*, in document order.

    A plain function rather than a closure defined inside each loop: a closure
    over a loop variable reads whatever that variable holds when it is *called*,
    which is the defect ruff's B023 names and which would have made these checks
    walk the last schema three times.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.append(ref)
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)
    return found


def _schema_for(path: Path) -> str:
    """The schema *path* is judged against, or a refusal naming the gap."""
    if path.name.startswith("source_relations"):
        return CONTAINER_SCHEMA
    if path.name.endswith("source_knowledge.json"):
        return BRIEF_SCHEMA
    for prefix, schema in FIXTURE_SCHEMAS.items():
        if path.name.startswith(prefix):
            return schema
    raise AssertionError(
        f"{path.name} matches no fixture naming rule, so nothing knows which schema "
        "judges it. Name it, or add the rule — never default, because the default "
        "validates it against the wrong contract and calls the result a refusal"
    )


VALID_FIXTURES = sorted((FIXTURE_DIR / "valid").rglob("*.json"))
INVALID_FIXTURES = sorted(
    path for path in (FIXTURE_DIR / "invalid").glob("*.json") if not path.name.endswith(".note.json")
)


# --------------------------------------------------------------------------
# 1. The schemas themselves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_file_is_valid_json_schema(schemas: dict[str, dict], name: str) -> None:
    Draft202012Validator.check_schema(schemas[name])


def test_every_ref_resolves(registry: Registry, schemas: dict[str, dict]) -> None:
    """A dangling ``$ref`` would only surface when a real record was validated."""
    for schema in schemas.values():
        resolver = registry.resolver(base_uri=schema["$id"])
        for ref in _refs(schema):
            resolver.lookup(ref)


def test_every_reference_names_its_own_document(schemas: dict[str, dict]) -> None:
    """No bare ``#/$defs/...`` anywhere in this directory.

    Not a style rule. ``tools/generate_api_types.py`` resolves a ``$ref`` by the
    string alone, across every schema directory at once, so a reference that is
    only meaningful relative to its own document is a reference that can be
    resolved against the wrong one. Writing the owning filename makes every
    reference name exactly one schema, which is the property the generator's
    duplicate-key guard defends.
    """
    for name, schema in schemas.items():
        bare = [ref for ref in _refs(schema) if ref.startswith("#")]
        assert not bare, f"{name} carries document-relative references: {bare}"


def test_records_are_versioned(schemas: dict[str, dict]) -> None:
    """Every stored record names the model it conforms to, and it is this one."""
    for name in (BRIEF_SCHEMA, CONTAINER_SCHEMA):
        assert "schema_version" in schemas[name]["required"], name
    version = schemas["primitives.schema.json"]["$defs"]["schemaVersion"]["const"]
    assert version == synthesis.SCHEMA_VERSION


def test_no_synthesis_schema_reaches_into_the_index_model(schemas: dict[str, dict]) -> None:
    """The dependency does not run backwards.

    ``schemas/v1/`` is derived *from* what the pipeline writes and says so in
    its own README. A reference from here into there would make that sentence
    false and couple a canonical file to the index layer that reads it.

    Checked over the ``$ref`` values, not over the document text. Prose is
    allowed — and expected — to *name* the index model when explaining why it
    is not referenced; a text search cannot tell the explanation from the
    dependency, and the dependency is the thing that matters.
    """
    for name, schema in schemas.items():
        outside = [ref for ref in _refs(schema) if "v1/" in ref or ".." in ref]
        assert not outside, f"{name} references the index model: {outside}"


# --------------------------------------------------------------------------
# 2. The vocabularies are mirrored, and drift-tested
# --------------------------------------------------------------------------


def test_source_relation_vocabulary_matches_constants(schemas: dict[str, dict]) -> None:
    declared = schemas["primitives.schema.json"]["$defs"]["sourceRelationType"]["enum"]
    assert set(declared) == SOURCE_RELATION_TYPES
    assert len(declared) == len(set(declared)), "the enum repeats a member"


def test_scope_vocabulary_matches_constants(schemas: dict[str, dict]) -> None:
    declared = schemas["primitives.schema.json"]["$defs"]["sourceRelationScope"]["enum"]
    assert set(declared) == SOURCE_RELATION_SCOPES


def test_the_basis_vocabulary_is_the_knowledge_unit_one(schemas: dict[str, dict]) -> None:
    """A basis entry relates two units, so it speaks the KU-level vocabulary."""
    declared = schemas["primitives.schema.json"]["$defs"]["knowledgeRelationType"]["enum"]
    assert set(declared) == RELATION_TYPES


def test_the_two_relation_vocabularies_stay_apart(schemas: dict[str, dict]) -> None:
    """They overlap in wording and are not the same list — that is the risk.

    ``supports`` and ``contradicts`` are in both, meaning a claim about two
    sentences in one and an aggregation over many pairs in the other. If the
    two enums ever became equal, a KU-level edge could be read as a whole-source
    verdict, which is risk R27 written into the data model.
    """
    defs = schemas["primitives.schema.json"]["$defs"]
    source_level = set(defs["sourceRelationType"]["enum"])
    unit_level = set(defs["knowledgeRelationType"]["enum"])
    assert source_level != unit_level
    assert source_level & unit_level == {"supports", "contradicts"}


def test_the_identifier_patterns_mirror_ids(schemas: dict[str, dict]) -> None:
    """The patterns here are copies of ``ids.py``'s, and copies drift."""
    defs = schemas["primitives.schema.json"]["$defs"]
    assert defs["knowledgeUnitId"]["pattern"] == f"^{ids.ID_PART_PATTERN}$"
    assert defs["knowledgeUnitId"]["maxLength"] == ids.ID_PART_MAX_LENGTH
    assert defs["sourceId"]["maxLength"] == ids.SOURCE_ID_MAX_LENGTH
    assert defs["sourceId"]["pattern"] == (
        f"^{ids.SOURCE_TYPE_PATTERN}:{ids.ID_PART_PATTERN}$"
    )
    assert defs["sourceRelationId"]["pattern"] == (
        f"^{ids.SOURCE_RELATION_ID_PREFIX}[0-9a-f]{{{ids.SOURCE_RELATION_DIGEST_LENGTH}}}$"
    )


def test_the_run_status_vocabulary_excludes_unknown(schemas: dict[str, dict]) -> None:
    """A brief cannot summarise a run whose validators never ran."""
    declared = schemas["primitives.schema.json"]["$defs"]["runStatus"]["enum"]
    assert set(declared) == {"PASS", "PARTIAL", "FAIL"}
    assert "UNKNOWN" not in declared


def test_a_relation_cannot_carry_a_confidence(schemas: dict[str, dict]) -> None:
    """Unrepresentable, not merely absent (D-247)."""
    schema = schemas["source_relation.schema.json"]
    assert schema["additionalProperties"] is False
    assert "confidence" not in schema["properties"]


def test_the_canonical_basis_is_not_bounded(schemas: dict[str, dict]) -> None:
    """The file keeps the whole basis; the response is what pages it."""
    basis = schemas["source_relation.schema.json"]["properties"]["basis"]
    assert "maxItems" not in basis
    assert basis["minItems"] == 1


# --------------------------------------------------------------------------
# 3. The committed fixtures
# --------------------------------------------------------------------------


def test_there_are_fixtures_to_test() -> None:
    """A parametrised suite over an empty list is green and proves nothing."""
    assert VALID_FIXTURES, "no valid fixtures; run tests/fixtures/source-map/build_fixtures.py"
    assert INVALID_FIXTURES, "no invalid fixtures"


@pytest.mark.parametrize("path", VALID_FIXTURES, ids=lambda p: p.name)
def test_a_valid_fixture_is_accepted(validate, path: Path) -> None:
    assert not validate(_schema_for(path), _load(path))


@pytest.mark.parametrize("path", INVALID_FIXTURES, ids=lambda p: p.name)
def test_an_invalid_fixture_is_refused_by_whatever_it_claims(validate, path: Path) -> None:
    """Each dishonest document is refused by the thing its note names.

    The note is checked rather than trusted. A case filed under ``schema`` that
    the schema in fact accepts would leave the README claiming a refusal that
    does not happen, and a case filed under ``gate`` that the schema already
    refuses would credit the apply gate with work it does not have to do —
    which matters, because `T-252` and `T-253` are written from this list.
    """
    note = _load(path.with_name(f"{path.stem}.note.json"))
    errors = validate(_schema_for(path), _load(path))
    if note["refused_by"] == "schema":
        assert errors, f"{path.name} is filed as schema-refused and the schema accepts it"
    else:
        assert not errors, (
            f"{path.name} is filed as gate-refused, but the schema already refuses it: "
            f"{errors}. Re-file it as schema-refused rather than leaving the gate "
            "credited with a check it does not perform"
        )


def test_every_invalid_fixture_states_its_lie() -> None:
    for path in INVALID_FIXTURES:
        note = _load(path.with_name(f"{path.stem}.note.json"))
        assert note["fixture"] is True
        assert note["refused_by"] in {"schema", "gate"}
        assert note["lie"].strip()


def test_both_media_are_represented(validate) -> None:
    """A single-medium fixture set would not prove medium neutrality."""
    briefs = [_load(path) for path in VALID_FIXTURES if "source_relations" not in path.name]
    types = {brief["source_id"].split(":", 1)[0] for brief in briefs}
    assert {"youtube", "twitter"} <= types


def test_the_relation_fixture_joins_the_two_media() -> None:
    relation = _load(FIXTURE_DIR / "valid" / "synthesis" / "source_relations.json")["relations"][0]
    endpoints = {
        relation["from_source_id"].split(":", 1)[0],
        relation["to_source_id"].split(":", 1)[0],
    }
    assert endpoints == {"youtube", "twitter"}


def test_a_partial_run_gets_a_partial_brief() -> None:
    brief = _load(FIXTURE_DIR / "valid" / "partial-source_knowledge.json")
    assert brief["status"] == "PARTIAL"


def test_the_bounded_fixture_counts_what_the_bound_omitted() -> None:
    document = _load(FIXTURE_DIR / "valid" / "synthesis" / "source_relations.bounded.json")
    assert document["candidates"]["omitted"] > 0
    assert document["candidates"]["bound"] == MAX_SOURCE_CANDIDATES


def test_the_empty_fixture_is_a_finding_not_a_gap() -> None:
    """No relations, and a candidates block that says a pair was compared."""
    document = _load(FIXTURE_DIR / "valid" / "synthesis" / "source_relations.empty.json")
    assert document["relations"] == []
    assert document["candidates"]["considered"] >= 1
