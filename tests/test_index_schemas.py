"""Contract tests for the v1 index/API schemas (T-002) and the adapter (T-004).

These schemas describe the derived index and API layer only. Nothing here reads
or writes a canonical file for anything other than verification, and no test in
this module may modify ``output/``.

Three things are checked:

1. The schema files are themselves valid JSON Schema 2020-12 and cross-resolve.
2. The controlled vocabularies mirrored into the schemas still match
   ``constants.py`` — the drift guard for risk R12.
3. The records the **real** adapter produces are accepted by the model, and a
   catalogue of dishonest records is rejected.

Point 3 used to run against a hand-written shape probe. ``T-004`` replaced it
with ``x2knwldg.adapters``, so the schemas and the code that feeds them are now
tested against each other rather than against a stand-in that could agree with
neither. The adapter's own behaviour — what it refuses, what it leaves out, and
what it must never invent — is tested in ``tests/test_adapters.py``, which needs
no ``jsonschema`` and therefore runs on a bare core install.

Every adapter test runs over the committed fixture runs in
``tests/fixtures/runs/`` — which include a ``PARTIAL`` and a ``FAIL`` run — and
additionally over the real sample when ``output/`` is present. The fixtures are
what keep a fresh clone honest: ``output/`` is gitignored, so without them these
tests would skip and the suite would be green having proved nothing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
)
from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

from x2knwldg.adapters import adapt_library, adapt_run  # noqa: E402
from x2knwldg.constants import (  # noqa: E402
    KNOWLEDGE_KINDS,
    MAX_AUDIT_ATTEMPTS,
    RELATION_TYPES,
)
from x2knwldg.library import rebuild_library  # noqa: E402
from x2knwldg.pipeline import import_transcript  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_ROOT / "schemas" / "v1"
SAMPLE_ID = "pqlWNihgdjI"
SAMPLE_DIR = PROJECT_ROOT / "output" / SAMPLE_ID
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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schemas() -> dict[str, dict]:
    return {name: _load(SCHEMA_DIR / name) for name in SCHEMA_FILES}


def _registry(schemas: dict[str, dict]) -> Registry:
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )


@pytest.fixture(scope="module")
def validators() -> dict[str, Draft202012Validator]:
    schemas = _schemas()
    registry = _registry(schemas)
    return {
        name.removesuffix(".schema.json"): Draft202012Validator(schema, registry=registry)
        for name, schema in schemas.items()
    }


def _check(validator: Draft202012Validator, instance: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


# --------------------------------------------------------------------------
# 1. The schema files themselves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_file_is_valid_json_schema(name: str) -> None:
    schema = _load(SCHEMA_DIR / name)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == f"https://x2knwldg.local/schemas/v1/{name}"


def test_every_ref_resolves(validators: dict[str, Draft202012Validator]) -> None:
    """A dangling $ref would only surface at runtime, on real data."""
    schemas = _schemas()
    registry = _registry(schemas)

    def walk(node: object, resolver) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                resolver.lookup(ref)
            for value in node.values():
                walk(value, resolver)
        elif isinstance(node, list):
            for value in node:
                walk(value, resolver)

    for schema in schemas.values():
        resolver = registry.resolver_with_root(Resource.from_contents(schema))
        walk(schema, resolver)


def test_records_are_versioned() -> None:
    """'Schemas are versioned' is a Phase 0 exit criterion, not a comment."""
    for name in SCHEMA_FILES:
        if name == "common.schema.json":
            continue
        schema = _load(SCHEMA_DIR / name)
        if name == "locator.schema.json":
            continue  # a locator is embedded in a versioned record, never stored alone
        assert "schema_version" in schema["required"], name


# --------------------------------------------------------------------------
# 2. Vocabulary drift guards (R12)
# --------------------------------------------------------------------------


def test_canonical_relation_vocabulary_matches_constants() -> None:
    common = _load(SCHEMA_DIR / "common.schema.json")
    assert set(common["$defs"]["canonicalRelationType"]["enum"]) == RELATION_TYPES


def test_knowledge_kind_vocabulary_matches_constants() -> None:
    common = _load(SCHEMA_DIR / "common.schema.json")
    schema_kinds = set(common["$defs"]["knowledgeKind"]["enum"])
    # canonical_concept is emitted by library.py for concept nodes and is not an
    # extraction kind, so it is the one legitimate addition.
    assert schema_kinds == KNOWLEDGE_KINDS | {"canonical_concept"}


def test_library_synthetic_relations_are_not_canonical() -> None:
    """derived_from and expresses_concept must stay outside RELATION_TYPES."""
    common = _load(SCHEMA_DIR / "common.schema.json")
    synthetic = set(common["$defs"]["librarySyntheticRelationType"]["enum"])
    assert synthetic == {"derived_from", "expresses_concept"}
    assert not synthetic & RELATION_TYPES


# --------------------------------------------------------------------------
# 3. The real adapter produces records the model accepts
# --------------------------------------------------------------------------

requires_sample = pytest.mark.skipif(
    not (SAMPLE_DIR / "metadata.json").exists(),
    reason=f"sample source output/{SAMPLE_ID}/ is not present",
)

requires_library = pytest.mark.skipif(
    not (LIBRARY_DIR / "concepts.json").exists(),
    reason="output/library/ is built by finalize_run and only the real sample has it",
)


def _runs() -> list[Path]:
    """Every run the adapter tests exercise.

    The committed fixtures are always present, so these tests never silently
    reduce to nothing; the real sample joins them when it is on disk.
    """
    runs = sorted(path.parent for path in FIXTURE_RUNS.glob("*/metadata.json"))
    assert runs, "the committed run fixtures are missing"
    if (SAMPLE_DIR / "metadata.json").exists():
        runs.append(SAMPLE_DIR)
    return runs


RUNS = _runs()
RUN_IDS = [run.name for run in RUNS]


def _adapt(run_dir: Path) -> dict[str, list[dict]]:
    """The records the real YouTube adapter produces for one run (T-004)."""
    return adapt_run(run_dir, PROJECT_ROOT).by_model()


@pytest.fixture(scope="module")
def library_records(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    """Canonical-concept records, from a library built out of the fixtures.

    ``output/library/`` is produced by ``finalize_run`` and is gitignored, so
    the two tests below used to skip everywhere except this developer's laptop
    — the suite was green in CI having proved nothing about D-016. The three
    committed runs are copied into a temp root and ``rebuild_library`` is run
    over *them*, which yields a real library (three videos, one canonical
    concept) on any machine. Nothing under ``output/`` is read or written.
    """
    root = tmp_path_factory.mktemp("library-from-fixtures")
    for metadata in sorted(FIXTURE_RUNS.glob("*/metadata.json")):
        shutil.copytree(metadata.parent, root / metadata.parent.name)
    rebuild_library(root)
    return adapt_library(root / "library", root).by_model()


def _adapt_library() -> dict[str, list[dict]]:
    return adapt_library(LIBRARY_DIR, PROJECT_ROOT).by_model()


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
@pytest.mark.parametrize(
    "model", ["source", "artifact", "entity_ref", "indexed_relation"]
)
def test_adapter_records_satisfy_the_model(
    validators: dict[str, Draft202012Validator], model: str, run_dir: Path
) -> None:
    records = _adapt(run_dir)[model]
    assert records, f"the adapter produced no {model} records for {run_dir.name}"
    for record in records:
        errors = _check(validators[model], record)
        assert not errors, f"{model} {record.get('id') or record.get('global_id')}: {errors}"


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_adapter_covers_both_provenance_classes(run_dir: Path) -> None:
    """A mapping that only exercised source units would prove little."""
    entities = _adapt(run_dir)["entity_ref"]
    classes = {entity["provenance_class"] for entity in entities}
    assert {"source", "derived"} <= classes


def _check_library_records(
    validators: dict[str, Draft202012Validator], records: dict[str, list[dict]]
) -> None:
    """Concepts are cross-source, so they come from a library, not a run."""
    assert records["entity_ref"], "no canonical concepts were mapped"
    assert not records["source"], "the library is not an ingested source"
    for model in ("entity_ref", "indexed_relation"):
        for record in records[model]:
            errors = _check(validators[model], record)
            assert not errors, f"{model} {record.get('id') or record.get('global_id')}: {errors}"


def _check_concepts_have_no_owning_source(records: dict[str, list[dict]]) -> None:
    """D-016: a concept lives in the reserved library:concepts namespace and
    has no owning source, which is what check_entity_ref_ids enforces."""
    concepts = [entity for entity in records["entity_ref"] if entity["entity_type"] == "concept"]
    assert concepts
    for concept in concepts:
        assert concept["source_type"] == "library"
        assert concept["external_id"] == "concepts"
        assert concept["source_id"] is None
        assert concept["library_id"].startswith("concept:")


def test_library_adapter_records_satisfy_the_model(
    validators: dict[str, Draft202012Validator], library_records: dict[str, list[dict]]
) -> None:
    _check_library_records(validators, library_records)


def test_canonical_concepts_belong_to_no_single_source(
    library_records: dict[str, list[dict]],
) -> None:
    _check_concepts_have_no_owning_source(library_records)


@requires_library
def test_the_real_library_satisfies_the_model_too(
    validators: dict[str, Draft202012Validator],
) -> None:
    """The fixture-built library is what runs everywhere; the real one joins it
    when it is on disk."""
    records = _adapt_library()
    _check_library_records(validators, records)
    _check_concepts_have_no_owning_source(records)


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_status_is_copied_not_recomputed(run_dir: Path) -> None:
    projected = _adapt(run_dir)["source"][0]["status"]
    assert projected["validation"] == _load(run_dir / "validation.json")["status"]
    assert projected["coverage"] == _load(run_dir / "coverage.json")["status"]


def test_partial_and_fail_runs_are_mapped_as_they_are() -> None:
    """The whole point of the fixtures: a dishonest status must be impossible
    to produce by accident (ADR 0001 invariant 2, risk R11)."""
    overall = {
        name: _adapt(FIXTURE_RUNS / f"{name}-run")["source"][0]["status"]
        for name in ("pass", "partial", "fail")
    }
    assert overall["pass"]["overall"] == "PASS"
    assert overall["partial"]["overall"] == "PARTIAL"
    assert overall["partial"]["coverage"] == "PARTIAL"
    assert overall["fail"]["overall"] == "FAIL"


def test_fixture_runs_are_labelled_as_synthetic() -> None:
    """No fixture may ever be mistaken for evidence about a real video."""
    for run_dir in sorted(FIXTURE_RUNS.glob("*/metadata.json")):
        metadata = _load(run_dir)
        assert metadata["fixture"] is True
        assert "not real evidence" in metadata["fixture_note"]
        assert metadata["video_id"].startswith("fixture-")


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_cross_field_invariants_hold(run_dir: Path) -> None:
    """Two rules JSON Schema cannot express, which the adapter must carry."""
    projected = _adapt(run_dir)
    for entity in projected["entity_ref"]:
        parts = entity["global_id"].split(":", 2)
        assert parts == [entity["source_type"], entity["external_id"], entity["local_id"]]
        locator = entity.get("locator")
        if locator and locator["type"] == "time_range":
            assert locator["end_sec"] >= locator["start_sec"]
    for artifact in projected["artifact"]:
        assert artifact["id"].startswith(f"{artifact['source_id']}:")


@requires_sample
def test_adapter_does_not_touch_canonical_files() -> None:
    """The adapter reads; a regression that made it write would be caught here."""
    before = {
        path: path.stat().st_mtime_ns
        for path in sorted(SAMPLE_DIR.rglob("*"))
        if path.is_file()
    }
    _adapt(SAMPLE_DIR)
    after = {
        path: path.stat().st_mtime_ns
        for path in sorted(SAMPLE_DIR.rglob("*"))
        if path.is_file()
    }
    assert before == after


# --------------------------------------------------------------------------
# 4. Dishonest records are rejected
# --------------------------------------------------------------------------

_VALID_SOURCE = {
    "schema_version": "1.0",
    "id": "youtube:abc123",
    "source_type": "youtube",
    "external_id": "abc123",
    "canonical_dir": "output/abc123",
    "status": {"validation": "PARTIAL", "coverage": "PARTIAL", "overall": "PARTIAL"},
    "adapter": {"name": "youtube", "version": "1.0"},
}

_VALID_UNIT = {
    "schema_version": "1.0",
    "global_id": "youtube:abc123:KU-000001",
    "source_type": "youtube",
    "external_id": "abc123",
    "local_id": "KU-000001",
    "library_id": "abc123:KU-000001",
    "entity_type": "knowledge_unit",
    "provenance_class": "source",
    "kind": "claim",
    "locator": {"type": "time_range", "start_sec": 1.0, "end_sec": 2.0},
}

_VALID_RELATION = {
    "schema_version": "1.0",
    "id": "e1",
    "from_id": "youtube:abc123:KU-000001",
    "to_id": "youtube:abc123:KU-000002",
    "relation": "supports",
    "relation_vocabulary": "canonical",
    "provenance_class": "source",
    "confidence": 0.9,
    "source_id": "youtube:abc123",
}

_VALID_ARTIFACT = {
    "schema_version": "1.0",
    "id": "youtube:abc123:transcript",
    "source_id": "youtube:abc123",
    "kind": "transcript",
    "role": "canonical",
    "path": "output/abc123/transcript.json",
    "immutable": False,
    "available": True,
}


def _without(base: dict, *keys: str) -> dict:
    return {key: value for key, value in base.items() if key not in keys}


REJECTED: list[tuple[str, str, dict]] = [
    # Source — status honesty and path safety
    ("source", "invented status value", {**_VALID_SOURCE, "status": {**_VALID_SOURCE["status"], "validation": "OK"}}),
    ("source", "absolute host path (R15)", {**_VALID_SOURCE, "canonical_dir": "/Users/someone/X2KNWLDG/output/abc123"}),
    ("source", "parent traversal in path", {**_VALID_SOURCE, "canonical_dir": "output/../../etc/passwd"}),
    ("source", "three-part id in a source id field", {**_VALID_SOURCE, "id": "youtube:abc123:KU-000001"}),
    ("source", "audit_attempts above the WORKFLOW.md cap of 3", {**_VALID_SOURCE, "status": {**_VALID_SOURCE["status"], "audit_attempts": 4}}),
    ("source", "a negative number of audit attempts", {**_VALID_SOURCE, "status": {**_VALID_SOURCE["status"], "audit_attempts": -1}}),
    ("source", "a fractional number of audit attempts", {**_VALID_SOURCE, "status": {**_VALID_SOURCE["status"], "audit_attempts": 1.5}}),
    ("source", "unversioned record", _without(_VALID_SOURCE, "schema_version")),
    ("source", "status omitted entirely", _without(_VALID_SOURCE, "status")),
    # isoTimestamp — 'format' is annotation-only in 2020-12 unless a validator
    # opts into the format-assertion vocabulary, and none of this repo's do.
    # Until the pattern was added, every one of these was accepted.
    ("source", "a timestamp that is prose", {**_VALID_SOURCE, "imported_at": "yesterday"}),
    ("source", "a timestamp that is a date", {**_VALID_SOURCE, "imported_at": "2026-01-01"}),
    ("source", "a naive local time with no offset", {**_VALID_SOURCE, "imported_at": "2026-01-01T00:00:00"}),
    ("source", "a timestamp with a bare Z-less offset", {**_VALID_SOURCE, "imported_at": "2026-01-01T00:00:00+0000"}),
    ("source", "an empty timestamp", {**_VALID_SOURCE, "extracted_at": ""}),
    ("source", "a timestamp with trailing prose", {**_VALID_SOURCE, "extracted_at": "2026-01-01T00:00:00Z (roughly)"}),
    ("artifact", "an index time that is prose", {**_VALID_ARTIFACT, "indexed_at": "just now"}),
    ("indexed_relation", "a creation time that is prose", {**_VALID_RELATION, "created_at": "recently"}),
    # EntityRef — provenance integrity
    ("entity_ref", "source-class unit with no locator", _without(_VALID_UNIT, "locator")),
    ("entity_ref", "source-class unit with a null locator", {**_VALID_UNIT, "locator": None}),
    ("entity_ref", "derived unit with no derivation note", {**_without(_VALID_UNIT, "locator"), "provenance_class": "derived", "kind": "synthesis", "derived_from": ["youtube:abc123:KU-000001"]}),
    ("entity_ref", "derived unit derived from nothing", {**_without(_VALID_UNIT, "locator"), "provenance_class": "derived", "kind": "synthesis", "derived_from": [], "derivation_note": "n"}),
    ("entity_ref", "knowledge unit missing the library id form", _without(_VALID_UNIT, "library_id")),
    ("entity_ref", "two-part id where the global id belongs", {**_VALID_UNIT, "global_id": "abc123:KU-000001"}),
    ("entity_ref", "user content claiming a canonical file", {**_without(_VALID_UNIT, "locator", "library_id"), "entity_type": "user_note", "provenance_class": "user", "kind": None, "canonical_path": "output/abc123/knowledge_units.json"}),
    ("entity_ref", "unknown knowledge kind", {**_VALID_UNIT, "kind": "vibe"}),
    ("entity_ref", "confidence above 1", {**_VALID_UNIT, "confidence": 1.5}),
    # Locator — never constructed without canonical data
    ("locator", "time range with no end", {"type": "time_range", "start_sec": 1.0}),
    ("locator", "negative start time", {"type": "time_range", "start_sec": -1.0, "end_sec": 2.0}),
    ("locator", "empty evidence excerpt", {"type": "time_range", "start_sec": 1.0, "end_sec": 2.0, "excerpt": ""}),
    ("locator", "undeclared field", {"type": "time_range", "start_sec": 1.0, "end_sec": 2.0, "page": 3}),
    ("locator", "unknown locator type", {"type": "paragraph", "index": 2}),
    ("locator", "text span with no artifact to address", {"type": "text_span", "start_char": 0, "end_char": 5}),
    # Artifact
    ("artifact", "neither a path nor a url", {**_without(_VALID_ARTIFACT, "path"), "path": None, "url": None}),
    ("artifact", "raw evidence marked mutable", {**_VALID_ARTIFACT, "kind": "raw_transcript", "role": "raw", "path": "output/abc123/raw/transcript.json", "immutable": False}),
    ("artifact", "external artifact with a local path", {**_VALID_ARTIFACT, "kind": "video", "role": "external", "path": "output/abc123/video.mp4", "url": "https://example.invalid/v"}),
    ("artifact", "unknown artifact kind", {**_VALID_ARTIFACT, "kind": "thumbnail"}),
    # IndexedRelation — vocabulary separation
    ("indexed_relation", "canonical vocabulary with a synthetic relation", {**_VALID_RELATION, "relation": "expresses_concept"}),
    ("indexed_relation", "canonical relation outside RELATION_TYPES", {**_VALID_RELATION, "relation": "sort_of_supports"}),
    ("indexed_relation", "canonical edge with no confidence", {**_VALID_RELATION, "confidence": None}),
    ("indexed_relation", "canonical edge marked as user provenance", {**_VALID_RELATION, "provenance_class": "user"}),
    ("indexed_relation", "user relation with an invented confidence", {**_VALID_RELATION, "relation_vocabulary": "user", "relation": "reminds me of", "provenance_class": "user", "confidence": 0.9, "source_id": None}),
    ("indexed_relation", "user relation claiming a canonical file", {**_VALID_RELATION, "relation_vocabulary": "user", "relation": "reminds me of", "provenance_class": "user", "confidence": None, "source_id": None, "canonical_path": "output/abc123/relationships.json"}),
    ("indexed_relation", "synthetic edge claimed as source evidence", {**_VALID_RELATION, "relation_vocabulary": "library_synthetic", "relation": "derived_from", "provenance_class": "source"}),
    ("indexed_relation", "endpoint addressed by a two-part id", {**_VALID_RELATION, "to_id": "abc123:KU-000002"}),
]


@pytest.mark.parametrize(
    ("model", "reason", "instance"),
    REJECTED,
    ids=[f"{model}-{reason}" for model, reason, _ in REJECTED],
)
def test_dishonest_record_is_rejected(
    validators: dict[str, Draft202012Validator], model: str, reason: str, instance: dict
) -> None:
    assert _check(validators[model], instance), f"schema accepted {reason}"


@pytest.mark.parametrize(
    ("model", "instance"),
    [
        ("source", _VALID_SOURCE),
        ("entity_ref", _VALID_UNIT),
        ("indexed_relation", _VALID_RELATION),
        ("artifact", _VALID_ARTIFACT),
        ("locator", {"type": "time_range", "start_sec": 1.0, "end_sec": 2.0}),
    ],
)
def test_baseline_record_is_accepted(
    validators: dict[str, Draft202012Validator], model: str, instance: dict
) -> None:
    """Guards against a schema so strict that the negative cases pass vacuously."""
    assert not _check(validators[model], instance)


# --------------------------------------------------------------------------
# 5. isoTimestamp is asserted, not merely annotated
# --------------------------------------------------------------------------


def test_the_timestamp_format_is_backed_by_a_pattern() -> None:
    """``format`` is an annotation in 2020-12 unless a validator opts into the
    format-assertion vocabulary — none of this repo's do, and a TypeScript or
    Go consumer reading this document asserts even less. A ``pattern`` is
    asserted by every validator there is, so the pattern is the contract and
    ``format`` documents it."""
    common = _load(SCHEMA_DIR / "common.schema.json")
    iso = common["$defs"]["isoTimestamp"]
    assert iso["format"] == "date-time"
    assert "pattern" in iso, "isoTimestamp's format is not asserted by anything"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-08-31T13:06:19.495489+00:00",  # what pipeline.py writes
        "2026-01-01T00:00:00+00:00",  # what the run fixtures carry
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00.5-05:00",
    ],
)
def test_a_real_timestamp_is_still_accepted(
    validators: dict[str, Draft202012Validator], timestamp: str
) -> None:
    """The pattern must not be so tight that it rejects what the pipeline and
    the fixtures actually write."""
    assert not _check(validators["source"], {**_VALID_SOURCE, "imported_at": timestamp})


@pytest.mark.parametrize("run_dir", RUNS, ids=RUN_IDS)
def test_the_timestamps_the_adapter_emits_satisfy_the_pattern(
    validators: dict[str, Draft202012Validator], run_dir: Path
) -> None:
    """The pattern is checked against real adapter output, not only against
    hand-written cases — a rule the schema states and the code cannot meet
    would be a contract nothing keeps."""
    for source in _adapt(run_dir)["source"]:
        assert not _check(validators["source"], source)
        assert any(source.get(field) for field in ("imported_at", "extracted_at")), (
            f"{run_dir.name} carries no timestamp, so this proves nothing"
        )


# --------------------------------------------------------------------------
# 6. A freshly imported run is a valid record, not just a valid file
# --------------------------------------------------------------------------


def test_zero_audit_attempts_is_accepted(
    validators: dict[str, Draft202012Validator],
) -> None:
    """REGRESSION: the floor was 1, so 'never audited' was unrepresentable.

    ``coverage.py`` writes ``audit_attempts: 0`` into every run at import, and
    WORKFLOW.md calls 0 the honest never-audited state — ``validators.py``
    accepts it precisely while the document does not claim ``PASS``. A schema
    that rejected it was calling the pipeline's own honest output invalid.
    """
    record = {**_VALID_SOURCE, "status": {**_VALID_SOURCE["status"], "audit_attempts": 0}}
    assert not _check(validators["source"], record)


def test_the_audit_cap_in_the_schema_is_the_one_in_constants() -> None:
    """Drift guard, the same one MAX_AUDIT_ATTEMPTS earns everywhere else: the
    cap has one home and the schema mirrors it (D-015)."""
    schema = _load(SCHEMA_DIR / "source.schema.json")
    attempts = schema["properties"]["status"]["properties"]["audit_attempts"]
    assert attempts["maximum"] == MAX_AUDIT_ATTEMPTS
    assert attempts["minimum"] == 0


def test_a_scaffolded_run_produces_a_valid_source_record(
    validators: dict[str, Draft202012Validator], tmp_path: Path
) -> None:
    """REGRESSION: nothing validated the record of a run that had only been
    imported, which is why a floor of 1 went unnoticed.

    Every fixture and the real sample carry an extraction, so every Source
    record the suite checked had already been audited. The state the pipeline
    actually leaves behind after ``import_transcript`` — no extraction, no
    validation, ``audit_attempts: 0`` — was never put through the model at all.
    It is now.
    """
    transcript = tmp_path / "transcript.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:30,000\nA caption with a timing.\n\n"
        "2\n00:00:30,000 --> 00:01:00,000\nA second caption.\n",
        encoding="utf-8",
    )
    run_dir = import_transcript(
        transcript,
        tmp_path / "output",
        video_id="scaffolded01",
        title="Scaffolded",
        channel="Fixture",
        language="en",
        source="manual",
    )

    records = adapt_run(run_dir, tmp_path).by_model()
    source = records["source"][0]
    assert source["status"]["audit_attempts"] == 0, "the scaffolded state changed"
    assert source["status"]["overall"] == "UNKNOWN", "an unvalidated run is not PASS"
    for model, model_records in records.items():
        for record in model_records:
            errors = _check(validators[model], record)
            assert not errors, f"{model} {record.get('id') or record.get('global_id')}: {errors}"
