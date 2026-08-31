"""Tests for the generated TypeScript declarations (``T-005``).

Stdlib only, deliberately: ``tools/generate_api_types.py`` has no dependency,
so its guard must run on a bare core install too (ADR 0001 invariant 5).

The load-bearing test is :func:`test_the_committed_declarations_are_current`.
Everything else here is about *how* the generator fails — it must refuse a
construct it does not understand rather than emit ``unknown``, because a
declaration that quietly stops describing the contract still compiles, and the
frontend would go on trusting it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import generate_api_types as gen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TYPES_PATH = PROJECT_ROOT / "schemas" / "api" / "v1" / "types.d.ts"
OPENAPI_PATH = PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json"
COMMON_PATH = PROJECT_ROOT / "schemas" / "v1" / "common.schema.json"


@pytest.fixture(scope="module")
def declarations() -> str:
    return TYPES_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def openapi() -> dict:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def renderer(openapi: dict) -> gen.Renderer:
    common = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    return gen.Renderer(gen.build_name_table(common, openapi))


# --------------------------------------------------------------------------
# The drift guard
# --------------------------------------------------------------------------


def test_the_committed_declarations_are_current(declarations: str) -> None:
    """The contract and the types compiled against it cannot diverge silently."""
    assert declarations == gen.generate(), (
        "schemas/api/v1/types.d.ts is stale. Run: python tools/generate_api_types.py"
    )


def test_check_mode_agrees(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen.main(["--check"]) == 0


def test_the_file_announces_that_it_is_generated(declarations: str) -> None:
    assert "GENERATED FILE — do not edit by hand." in declarations
    assert "python tools/generate_api_types.py" in declarations


# --------------------------------------------------------------------------
# Coverage: nothing in the contract goes undeclared
# --------------------------------------------------------------------------


def test_every_shared_primitive_is_declared(declarations: str) -> None:
    common = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    for key in common["$defs"]:
        assert f"export type {gen._pascal(key)} = " in declarations


def test_every_record_schema_is_declared(declarations: str) -> None:
    for name in gen.RECORD_TYPE_NAMES.values():
        assert f"export type {name} = " in declarations


def test_every_api_component_is_declared(declarations: str, openapi: dict) -> None:
    for name in openapi["components"]["schemas"]:
        assert f"export type {name} = " in declarations


def test_every_operation_appears_in_endpoints(declarations: str, openapi: dict) -> None:
    for operations in openapi["paths"].values():
        for operation in operations.values():
            assert f"  {operation['operationId']}: {{" in declarations


def test_endpoints_carry_the_path_they_belong_to(declarations: str, openapi: dict) -> None:
    for path in openapi["paths"]:
        assert f'path: "{path}";' in declarations


# --------------------------------------------------------------------------
# Shapes that must survive generation
# --------------------------------------------------------------------------


def test_locator_is_a_discriminated_union(declarations: str) -> None:
    """``type`` is the tag, so the Reader can narrow a locator without a cast."""
    locator = json.loads((PROJECT_ROOT / "schemas" / "v1" / "locator.schema.json").read_text("utf-8"))
    branches = [b["then"]["properties"]["type"]["const"] for b in locator["allOf"]]
    for const in branches:
        assert f'export type Locator{gen._pascal(const)} = {{\n  type: "{const}";' in declarations
    union = "export type Locator = " + " | ".join(f"Locator{gen._pascal(c)}" for c in branches) + ";"
    assert union in declarations


def test_a_required_property_is_not_optional(declarations: str) -> None:
    source = declarations.split("export type Source = {", 1)[1].split("\n};", 1)[0]
    assert "\n  id: SourceId;" in source
    assert "\n  canonical_dir: ProjectRelativePath;" in source


def test_an_optional_property_is_marked_optional(declarations: str) -> None:
    source = declarations.split("export type Source = {", 1)[1].split("\n};", 1)[0]
    assert "\n  url?:" in source
    assert "\n  counts?:" in source


def test_a_nullable_field_is_typed_as_nullable(declarations: str) -> None:
    source = declarations.split("export type Source = {", 1)[1].split("\n};", 1)[0]
    assert "url?: string | null;" in source


def test_the_caption_search_hit_has_no_global_id(declarations: str) -> None:
    """D-023: v1 emits no caption entities, so there is no entity to address."""
    hit = declarations.split("export type SearchHitTranscriptCaption = {", 1)[1].split("\n};", 1)[0]
    assert "global_id" not in hit
    assert "source_id" in hit


def test_conditional_constraints_survive_as_documentation(declarations: str) -> None:
    """A rule TypeScript cannot express is written down, not dropped."""
    entity = declarations.split("export type EntityRef = {", 1)[0]
    assert "Runtime invariants, enforced by the adapter" in entity
    assert "A derived-class knowledge unit must show its work." in entity


def test_open_objects_are_the_only_unknowns(declarations: str) -> None:
    """``unknown`` appears only where the schema is deliberately open."""
    offenders = [
        line.strip()
        for line in declarations.splitlines()
        if "unknown" in line
        and "Record<string, unknown>" not in line
        and "[key: string]: unknown;" not in line
        and not line.lstrip().startswith("*")
    ]
    assert offenders == []


# --------------------------------------------------------------------------
# Refusals — the generator will not guess
# --------------------------------------------------------------------------


def test_an_unhandled_keyword_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="not handled"):
        renderer.expression({"type": "string", "contentEncoding": "base64"}, "probe")


def test_an_unresolvable_ref_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="names nothing"):
        renderer.expression({"$ref": "../../v1/board.schema.json"}, "probe")


def test_an_array_without_items_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="no element type"):
        renderer.expression({"type": "array"}, "probe")


def test_an_unknown_type_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="unknown type"):
        renderer.expression({"type": "date"}, "probe")


def test_a_schema_with_nothing_to_render_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="no type"):
        renderer.expression({"description": "a schema that says nothing"}, "probe")


def test_a_bare_allof_is_refused(renderer: gen.Renderer) -> None:
    """Only ``DISCRIMINATED_UNIONS`` may turn an ``allOf`` into a union."""
    with pytest.raises(gen.UnsupportedSchema, match="not a shape"):
        renderer.expression({"allOf": [{"type": "string"}]}, "probe")


def test_an_undocumented_constraint_branch_is_refused() -> None:
    with pytest.raises(gen.UnsupportedSchema, match="silently dropped"):
        gen._constraint_docs({"allOf": [{"if": {}, "then": {}}]}, "probe")


def test_a_name_collision_is_refused() -> None:
    common = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    openapi = {"components": {"schemas": {"SourceType": {"type": "string"}}}}
    with pytest.raises(gen.UnsupportedSchema, match="one schema, one type"):
        gen.build_name_table(common, openapi)


def test_a_parameter_ref_outside_components_is_refused(openapi: dict) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="components/parameters"):
        gen._resolve_parameter({"$ref": "external.json#/limit"}, openapi)


def test_an_operation_without_a_body_is_refused(renderer: gen.Renderer) -> None:
    with pytest.raises(gen.UnsupportedSchema, match="no 2xx response"):
        gen._response({"responses": {"404": {}}}, renderer, "probe")


# --------------------------------------------------------------------------
# Both id vocabularies reach TypeScript (risk R12)
# --------------------------------------------------------------------------


def test_both_identifier_forms_are_declared(declarations: str) -> None:
    assert "export type GlobalId = string;" in declarations
    assert "export type LibraryId = string;" in declarations
    entity = declarations.split("export type EntityRef = {", 1)[1].split("\n};", 1)[0]
    assert "global_id: GlobalId;" in entity
    assert "library_id?: LibraryId | null;" in entity
