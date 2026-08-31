"""Contract tests for the identifier helper (T-003, D-011).

Three things are checked:

1. ``ids.py`` and ``schemas/v1/common.schema.json`` agree on every pattern and
   length bound — the drift guard for the mirroring in D-015.
2. The two identifier vocabularies convert to each other without loss, in both
   directions, including for canonical concepts (D-016) — the drift guard for
   risk R12.
3. The three invariants JSON Schema cannot express are enforced in code, and
   contradicting records are rejected.

``library.py`` is exercised against a temporary output root only. No test here
reads or writes the real ``output/`` tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x2knwldg import ids
from x2knwldg.library import rebuild_library
from x2knwldg.validators import validate_knowledge_units

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMON_SCHEMA = PROJECT_ROOT / "schemas" / "v1" / "common.schema.json"
BUNDLE_SCHEMA = PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json"

# A real YouTube id may begin with '-' or '_': the id space is base64url, and
# pipeline.py accepts [0-9A-Za-z_-]{11} at ingestion (D-017).
LEADING_UNDERSCORE_VIDEO_ID = "_wJv0sPBUOI"
LEADING_HYPHEN_VIDEO_ID = "-wJv0sPBUOI"


# --------------------------------------------------------------------------
# 1. The helper and the schema agree
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def common_defs() -> dict[str, dict]:
    return json.loads(COMMON_SCHEMA.read_text(encoding="utf-8"))["$defs"]


def test_source_type_pattern_matches_schema(common_defs: dict[str, dict]) -> None:
    assert common_defs["sourceType"]["pattern"] == f"^{ids.SOURCE_TYPE_PATTERN}$"
    assert common_defs["sourceType"]["maxLength"] == ids.SOURCE_TYPE_MAX_LENGTH


def test_id_part_pattern_matches_schema(common_defs: dict[str, dict]) -> None:
    assert common_defs["idPart"]["pattern"] == f"^{ids.ID_PART_PATTERN}$"
    assert common_defs["idPart"]["maxLength"] == ids.ID_PART_MAX_LENGTH


def test_composed_patterns_match_schema(common_defs: dict[str, dict]) -> None:
    source_type, part = ids.SOURCE_TYPE_PATTERN, ids.ID_PART_PATTERN
    assert common_defs["sourceId"]["pattern"] == f"^{source_type}:{part}$"
    assert common_defs["globalId"]["pattern"] == f"^{source_type}:{part}:{part}$"
    assert common_defs["libraryId"]["pattern"] == f"^{part}:{part}$"
    assert common_defs["sourceId"]["maxLength"] == ids.SOURCE_ID_MAX_LENGTH
    assert common_defs["globalId"]["maxLength"] == ids.GLOBAL_ID_MAX_LENGTH
    assert common_defs["libraryId"]["maxLength"] == ids.LIBRARY_ID_MAX_LENGTH


def test_helper_output_validates_against_the_schema() -> None:
    """The ids the helper builds are ids the v1 schema accepts."""
    jsonschema = pytest.importorskip(
        "jsonschema",
        reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
    )
    schema = json.loads(COMMON_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/globalId", "$defs": schema["$defs"]}
    )
    for video_id in (LEADING_UNDERSCORE_VIDEO_ID, LEADING_HYPHEN_VIDEO_ID, "pqlWNihgdjI"):
        built = ids.make_global_id("youtube", video_id, "KU-000001").value
        assert not list(validator.iter_errors(built)), built
    assert not list(validator.iter_errors(ids.concept_global_id("1f4a9c2b7e01").value))


def test_bundle_schema_agrees_with_the_helper_on_what_an_id_may_be() -> None:
    """A canonical id must be usable as one segment of a global id (D-018)."""
    defs = json.loads(BUNDLE_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    unit = defs["knowledgeUnit"]["properties"]
    relationship = defs["relationship"]["properties"]
    expected = f"^{ids.ID_PART_PATTERN}$"
    assert unit["id"]["pattern"] == expected
    assert unit["id"]["maxLength"] == ids.ID_PART_MAX_LENGTH
    assert unit["derived_from"]["items"]["pattern"] == expected
    assert relationship["from"]["pattern"] == expected
    assert relationship["to"]["pattern"] == expected


@pytest.mark.parametrize("candidate", ["KU-1\n", "youtube\n", "KU-1\r", "KU-1\n\n"])
def test_a_trailing_newline_is_not_a_valid_id_part(candidate: str) -> None:
    """Python's ``$`` matches before a trailing newline; ECMA-262's does not.

    The pattern strings are mirrored verbatim into
    ``schemas/v1/common.schema.json``, where a TypeScript consumer reads them as
    ECMA-262. Anchoring the compiled patterns with ``^...$`` therefore accepted
    ids the declared contract rejects — and ``validators.py`` and
    ``pipeline.resolve_run_dir`` share this gate, so such an id passed canonical
    validation and named a run directory. The drift tests compare pattern
    *strings*, so they cannot see the anchor.
    """
    assert not ids.is_id_part(candidate)


@pytest.mark.parametrize(
    "candidate",
    ["KU-000001", "KU-D-0001", "KU_1", "_leading", "-leading", "a.b", "KU 1", "KU:1", "..", ".hidden"],
)
def test_validators_accept_exactly_the_ids_the_index_can_address(candidate: str) -> None:
    """The contract that closes the crash path: if validation passes, the
    library and the index can build an identifier for the unit (D-018)."""
    unit = {
        "id": candidate,
        "kind": "claim",
        "source_class": "source",
        "content": "x",
        "normalized_statement": "x",
        "confidence": 0.5,
        "source": {
            "video_id": "vid12345678",
            "segment_id": "seg_000001",
            "start_sec": 0,
            "end_sec": 1,
            "evidence_excerpt": "x",
        },
    }
    accepted = validate_knowledge_units([unit])["status"] == "PASS"
    assert accepted == ids.is_id_part(candidate)
    if accepted:
        assert ids.make_library_id("vid12345678", candidate)


# --------------------------------------------------------------------------
# 2. Building and parsing
# --------------------------------------------------------------------------


def test_global_id_is_its_three_parts() -> None:
    global_id = ids.make_global_id("youtube", "pqlWNihgdjI", "KU-000001")
    assert global_id.value == "youtube:pqlWNihgdjI:KU-000001"
    assert str(global_id) == global_id.value
    assert global_id.source_id.value == "youtube:pqlWNihgdjI"


def test_global_id_round_trips() -> None:
    value = "youtube:pqlWNihgdjI:KU-D-0001"
    assert ids.parse_global_id(value).value == value


def test_source_id_round_trips() -> None:
    assert ids.parse_source_id("youtube:pqlWNihgdjI").value == "youtube:pqlWNihgdjI"
    assert ids.make_source_id("youtube", "pqlWNihgdjI").entity("KU-000001").local_id == "KU-000001"


def test_youtube_ids_that_begin_with_underscore_or_hyphen_are_accepted() -> None:
    """pipeline.py ingests these; the index must be able to address them (D-017)."""
    for video_id in (LEADING_UNDERSCORE_VIDEO_ID, LEADING_HYPHEN_VIDEO_ID):
        global_id = ids.make_global_id("youtube", video_id, "KU-000001")
        assert ids.parse_global_id(global_id.value) == global_id


@pytest.mark.parametrize(
    "value",
    [
        "youtube:pqlWNihgdjI",  # two parts where three belong
        "pqlWNihgdjI:KU-000001",  # the library form is not a global id
        "youtube:pqlWNihgdjI:KU:000001",  # a colon inside the local id
        "YouTube:pqlWNihgdjI:KU-000001",  # source type is lowercase snake_case
        "youtube::KU-000001",  # empty external id
        "youtube:pqlWNihgdjI:",  # empty local id
        "youtube:..:KU-000001",  # parent traversal as an id part
        "youtube:.hidden:KU-000001",  # leading dot
        "youtube:pql/WNihgdjI:KU-000001",  # path separator
        "",
    ],
)
def test_malformed_global_id_is_rejected(value: str) -> None:
    assert not ids.is_global_id(value)
    with pytest.raises(ids.IdError):
        ids.parse_global_id(value)


def test_non_string_is_rejected() -> None:
    for value in (None, 12, ["youtube", "x", "y"]):
        assert not ids.is_global_id(value)
        with pytest.raises(ids.IdError):
            ids.parse_global_id(value)  # type: ignore[arg-type]


def test_over_long_part_is_rejected() -> None:
    with pytest.raises(ids.IdError):
        ids.make_global_id("youtube", "a" * (ids.ID_PART_MAX_LENGTH + 1), "KU-000001")


# --------------------------------------------------------------------------
# 3. The two vocabularies convert without drifting (risk R12)
# --------------------------------------------------------------------------


def test_library_id_converts_to_the_global_form() -> None:
    global_id = ids.global_id_from_library_id("pqlWNihgdjI:KU-000001")
    assert global_id.value == "youtube:pqlWNihgdjI:KU-000001"


def test_global_id_converts_back_to_the_library_form() -> None:
    assert ids.library_id_from_global_id("youtube:pqlWNihgdjI:KU-000001") == "pqlWNihgdjI:KU-000001"


@pytest.mark.parametrize(
    "library_id",
    ["pqlWNihgdjI:KU-000001", "pqlWNihgdjI:KU-D-0001", "concept:1f4a9c2b7e01"],
)
def test_conversion_round_trips_in_both_directions(library_id: str) -> None:
    global_id = ids.global_id_from_library_id(library_id)
    assert ids.library_id_from_global_id(global_id) == library_id
    assert global_id.library_id == library_id


def test_canonical_concept_uses_the_reserved_library_namespace() -> None:
    """A concept is cross-source, so it has no owning source (D-016)."""
    global_id = ids.global_id_from_library_id("concept:1f4a9c2b7e01")
    assert global_id.value == "library:concepts:1f4a9c2b7e01"
    assert global_id.is_library_concept
    assert not ids.make_global_id("youtube", "pqlWNihgdjI", "KU-000001").is_library_concept


def test_a_source_type_named_library_is_not_a_concept_unless_the_external_id_matches() -> None:
    assert not ids.make_global_id("library", "somethingelse", "x").is_library_concept


# --------------------------------------------------------------------------
# 4. Invariant 1 — an EntityRef's global_id equals its three parts
# --------------------------------------------------------------------------


VALID_ENTITY = {
    "global_id": "youtube:pqlWNihgdjI:KU-000001",
    "source_type": "youtube",
    "external_id": "pqlWNihgdjI",
    "local_id": "KU-000001",
    "source_id": "youtube:pqlWNihgdjI",
    "library_id": "pqlWNihgdjI:KU-000001",
}

VALID_CONCEPT_ENTITY = {
    "global_id": "library:concepts:1f4a9c2b7e01",
    "source_type": "library",
    "external_id": "concepts",
    "local_id": "1f4a9c2b7e01",
    "source_id": None,
    "library_id": "concept:1f4a9c2b7e01",
}


@pytest.mark.parametrize("record", [VALID_ENTITY, VALID_CONCEPT_ENTITY])
def test_consistent_entity_ref_passes(record: dict) -> None:
    ids.check_entity_ref_ids(record)


@pytest.mark.parametrize(
    ("reason", "override"),
    [
        ("global id contradicts its local part", {"global_id": "youtube:pqlWNihgdjI:KU-999999"}),
        ("global id contradicts its source type", {"global_id": "medium:pqlWNihgdjI:KU-000001"}),
        ("global id is the two-part library form", {"global_id": "pqlWNihgdjI:KU-000001"}),
        ("source id belongs to another source", {"source_id": "youtube:otherVideo"}),
        ("library id contradicts the global id", {"library_id": "pqlWNihgdjI:KU-999999"}),
        ("library id is the three-part form", {"library_id": "youtube:pqlWNihgdjI:KU-000001"}),
    ],
)
def test_contradictory_entity_ref_is_rejected(reason: str, override: dict) -> None:
    with pytest.raises(ids.IdError):
        ids.check_entity_ref_ids({**VALID_ENTITY, **override})


def test_concept_may_not_claim_an_owning_source() -> None:
    with pytest.raises(ids.IdError):
        ids.check_entity_ref_ids({**VALID_CONCEPT_ENTITY, "source_id": "library:concepts"})


def test_absent_optional_fields_are_not_invented() -> None:
    record = {key: VALID_ENTITY[key] for key in ("global_id", "source_type", "external_id", "local_id")}
    ids.check_entity_ref_ids(record)


# --------------------------------------------------------------------------
# 5. Invariant 2 — a Source's id equals its two parts
# --------------------------------------------------------------------------


def test_consistent_source_passes() -> None:
    ids.check_source_ids(
        {"id": "youtube:pqlWNihgdjI", "source_type": "youtube", "external_id": "pqlWNihgdjI"}
    )


@pytest.mark.parametrize(
    "override",
    [
        {"id": "youtube:otherVideo"},
        {"id": "medium:pqlWNihgdjI"},
        {"id": "youtube:pqlWNihgdjI:KU-000001"},
        {"id": "pqlWNihgdjI"},
    ],
)
def test_contradictory_source_is_rejected(override: dict) -> None:
    record = {"id": "youtube:pqlWNihgdjI", "source_type": "youtube", "external_id": "pqlWNihgdjI"}
    with pytest.raises(ids.IdError):
        ids.check_source_ids({**record, **override})


# --------------------------------------------------------------------------
# 6. Invariant 3 — a time_range locator ends no earlier than it starts
# --------------------------------------------------------------------------


def test_forward_time_range_passes() -> None:
    ids.check_locator({"type": "time_range", "start_sec": 12.0, "end_sec": 48.5})


def test_zero_length_time_range_passes() -> None:
    """A caption with identical start and end is real data, not an error."""
    ids.check_locator({"type": "time_range", "start_sec": 12.0, "end_sec": 12.0})


def test_backwards_time_range_is_rejected() -> None:
    with pytest.raises(ids.IdError):
        ids.check_locator({"type": "time_range", "start_sec": 48.5, "end_sec": 12.0})


def test_locator_artifact_id_must_be_a_global_id() -> None:
    with pytest.raises(ids.IdError):
        ids.check_locator(
            {
                "type": "time_range",
                "artifact_id": "pqlWNihgdjI:transcript",
                "start_sec": 1.0,
                "end_sec": 2.0,
            }
        )


def test_non_time_locator_is_not_second_guessed() -> None:
    """Reserved locator types carry no time bound to compare."""
    ids.check_locator({"type": "page", "page": 3})


# --------------------------------------------------------------------------
# 7. library.py emits both forms — the kg_navigator contract is preserved
# --------------------------------------------------------------------------


def _write_run(output_root: Path, video_id: str) -> None:
    run_dir = output_root / video_id
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(
        json.dumps({"video_id": video_id, "title": "T", "channel": "C"}), encoding="utf-8"
    )
    (run_dir / "knowledge_units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "id": "KU-000001",
                        "kind": "concept",
                        "source_class": "source",
                        "content": "A concept stated in the source.",
                        "normalized_statement": "A concept stated in the source.",
                        "confidence": 0.9,
                    },
                    {
                        "id": "KU-D-0001",
                        "kind": "synthesis",
                        "source_class": "derived",
                        "content": "A synthesis.",
                        "derived_from": ["KU-000001"],
                        "derivation_note": "Because.",
                        "confidence": 0.7,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "relationships.json").write_text(
        json.dumps(
            {
                "relationships": [
                    {"from": "KU-000001", "to": "KU-D-0001", "relation": "supports", "confidence": 0.8}
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def library(tmp_path: Path) -> dict:
    _write_run(tmp_path, LEADING_UNDERSCORE_VIDEO_ID)
    rebuild_library(tmp_path)
    return {
        "graph": json.loads((tmp_path / "library" / "graph.json").read_text(encoding="utf-8")),
        "concepts": json.loads((tmp_path / "library" / "concepts.json").read_text(encoding="utf-8")),
    }


def test_node_id_stays_the_two_part_library_form(library: dict) -> None:
    """kg_navigator.md mandates <video-id>:<knowledge-unit-id>. Do not change this."""
    units = [node for node in library["graph"]["nodes"] if node["kind"] != "canonical_concept"]
    assert units
    for node in units:
        assert node["id"] == f"{LEADING_UNDERSCORE_VIDEO_ID}:{node['local_id']}"
        assert ids.parse_library_id(node["id"])


def test_nodes_gain_the_global_form_without_losing_a_field(library: dict) -> None:
    for node in library["graph"]["nodes"]:
        assert ids.is_global_id(node["global_id"])
        assert ids.library_id_from_global_id(node["global_id"]) == node["id"]
        assert node["source_type"] == ids.parse_global_id(node["global_id"]).source_type


def test_concept_nodes_use_the_library_namespace(library: dict) -> None:
    concepts = [node for node in library["graph"]["nodes"] if node["kind"] == "canonical_concept"]
    assert concepts
    for node in concepts:
        assert node["source_type"] == ids.LIBRARY_SOURCE_TYPE
        assert ids.parse_global_id(node["global_id"]).is_library_concept
        assert node["id"].startswith("concept:")
    for concept in library["concepts"]["concepts"]:
        assert ids.library_id_from_global_id(concept["global_id"]) == concept["id"]


def test_library_files_carry_a_portable_path(tmp_path: Path) -> None:
    """An absolute host path is not portable and must not be what the index
    reads (risk R15)."""
    _write_run(tmp_path, LEADING_UNDERSCORE_VIDEO_ID)
    status = rebuild_library(tmp_path)
    videos = json.loads((tmp_path / "library" / "videos.json").read_text(encoding="utf-8"))
    assert status["relative_path"] == "library"
    for video in videos["videos"]:
        assert video["relative_path"] == video["video_id"]
        assert not Path(video["relative_path"]).is_absolute()


def test_edge_endpoints_stay_in_the_library_vocabulary(library: dict) -> None:
    node_ids = {node["id"] for node in library["graph"]["nodes"]}
    assert library["graph"]["edges"]
    for edge in library["graph"]["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids
