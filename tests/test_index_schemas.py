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
import re
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
    # D-089: this asserted `UNKNOWN`, and the reason it could was a defect —
    # `import_transcript` wrote a `validation.json` with no top-level `status`,
    # so `read_status` had nothing to read and a run the pipeline had just
    # validated described itself as unchecked. It now states the verdict its
    # own sections support: every validator passes over an empty unit set and
    # `coverage.json` says `PARTIAL` about itself, so the run is an honest
    # `PARTIAL`. The guarantee this test exists for is unchanged and is now
    # asserted directly: a scaffolded run is never a `PASS`.
    assert source["status"]["overall"] == "PARTIAL"
    assert source["status"]["overall"] != "PASS", "an unaudited run is not a pass"
    assert source["status"]["coverage"] == "PARTIAL"
    for model, model_records in records.items():
        for record in model_records:
            errors = _check(validators[model], record)
            assert not errors, f"{model} {record.get('id') or record.get('global_id')}: {errors}"


# ---------------------------------------------------------------------------
# The window vocabulary has one home
# ---------------------------------------------------------------------------


def test_the_bundle_window_statuses_are_the_shared_vocabulary() -> None:
    """``pending`` was missing from the schema while the code wrote it.

    ``coverage.create_pending_coverage`` puts ``pending`` in every window of a
    fresh run, and ``constants.COVERAGE_STATUSES`` has always included it — the
    bundle schema was the one place that did not, so it described a document
    the pipeline does not produce. Tying the two together here means the next
    status to be added cannot land in only one of them.
    """
    import json as _json

    from x2knwldg.constants import COVERAGE_STATUSES

    schema = _json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    window = schema["properties"]["coverage"]["properties"]["windows"]["items"]
    assert set(window["properties"]["status"]["enum"]) == COVERAGE_STATUSES


def test_a_fresh_run_writes_windows_the_bundle_schema_accepts() -> None:
    """The check the missing enum value would have failed.

    D-081: this test carried that name while asserting only that the statuses
    written are in ``COVERAGE_STATUSES`` — it never ran ``jsonschema`` against
    the document, so it could not see that the schema bounded
    ``audit_attempts`` at ``minimum: 1`` while ``create_pending_coverage``
    writes ``0`` into every fresh run. Three artifacts blessed ``0`` as the
    honest never-audited state — ``validate_coverage``, WORKFLOW.md §4.4 and
    ``prompts/05`` — and the schema was the outlier. It now validates the real
    document, which is what the name promised.
    """
    from x2knwldg.constants import COVERAGE_STATUSES
    from x2knwldg.coverage import create_pending_coverage

    captions = [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 12.0, "text": "hello"}
    ]
    coverage = create_pending_coverage(captions, "vid1")
    written = {window["status"] for window in coverage["windows"]}
    assert written == {"pending"}
    assert written <= COVERAGE_STATUSES

    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(bundle_schema)
    bundle = {"knowledge_units": [], "relationships": [], "coverage": coverage}
    errors = sorted(
        Draft202012Validator(bundle_schema).iter_errors(bundle), key=lambda e: e.json_path
    )
    assert not errors, [
        f"{error.json_path}: {error.message}" for error in errors
    ]


def test_the_bundle_schema_and_the_validator_accept_the_same_bundles() -> None:
    """The schema blessed bundles ``apply-bundle`` then rejected.

    Three places were looser than ``validators.py``: ``kind`` had no enum,
    ``relation`` had neither an enum nor a ``minLength``, and a
    ``source_class: "source"`` unit was not required to carry a ``source``
    block. A model that validated its output against the *published* schema
    still got ``invalid_kind`` / ``invalid_relation`` / ``missing_source`` —
    the same defect class as D-092 and D-110.
    """
    from x2knwldg.constants import KNOWLEDGE_KINDS, RELATION_TYPES, SOURCE_KINDS

    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    unit = schema["$defs"]["knowledgeUnit"]
    relationship = schema["$defs"]["relationship"]

    assert set(unit["properties"]["kind"]["enum"]) == KNOWLEDGE_KINDS, (
        "`canonical_concept` is library.py's and belongs in no bundle"
    )
    assert set(relationship["properties"]["relation"]["enum"]) == RELATION_TYPES

    # The provenance obligation follows the declared class *or* the kind, which
    # is the rule `validate_knowledge_units` applies.
    guard = unit["allOf"][0]
    branches = guard["if"]["anyOf"]
    assert branches[0]["properties"]["source_class"]["const"] == "source"
    assert set(branches[1]["properties"]["kind"]["enum"]) == SOURCE_KINDS
    assert guard["then"]["required"] == ["source"]


def test_a_bundle_the_schema_blesses_is_a_bundle_the_validator_accepts() -> None:
    """Asserted over the documents, not over the two vocabularies.

    Every rejection the validator can produce for these three fields is now a
    rejection the schema produces first.
    """
    from x2knwldg.validators import validate_knowledge_units, validate_relationships

    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    coverage = {"status": "PARTIAL", "audit_attempts": 0, "windows": []}

    def unit(**overrides):
        base = {
            "id": "KU-000001",
            "kind": "claim",
            "source_class": "source",
            "content": "A claim.",
            "confidence": 0.8,
            "source": {
                "video_id": "vid1",
                "segment_id": "seg_0001",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "evidence_excerpt": "A claim.",
            },
        }
        base.update(overrides)
        return base

    def relationship(**overrides):
        base = {
            "from": "KU-000001",
            "relation": "supports",
            "to": "KU-000002",
            "confidence": 0.9,
            "source_class": "source",
        }
        base.update(overrides)
        return base

    # Each of these is what the validator refuses; the schema must refuse it too.
    refused_units = [
        ("invalid_kind", unit(kind="vibes")),
        ("missing_source", {k: v for k, v in unit().items() if k != "source"}),
    ]
    for code, bad in refused_units:
        assert validator.iter_errors(
            {"knowledge_units": [bad], "relationships": [], "coverage": coverage}
        ), f"the schema accepts a unit the validator refuses with {code}"
        codes = {error["code"] for error in validate_knowledge_units([bad])["errors"]}
        assert code in codes, codes

    for code, bad in [
        ("invalid_relation", relationship(relation="")),
        ("invalid_relation", relationship(relation="folklore")),
    ]:
        assert validator.iter_errors(
            {"knowledge_units": [], "relationships": [bad], "coverage": coverage}
        ), f"the schema accepts a relationship the validator refuses with {code}"
        codes = {
            error["code"]
            for error in validate_relationships([bad], {"KU-000001", "KU-000002"})["errors"]
        }
        assert code in codes, codes

    # And the honest documents still validate on both sides.
    good = {
        "knowledge_units": [unit(), unit(id="KU-000002", kind="synthesis",
                                        source_class="derived",
                                        derived_from=["KU-000001"],
                                        derivation_note="because")],
        "relationships": [relationship()],
        "coverage": coverage,
    }
    del good["knowledge_units"][1]["source"]
    assert not list(validator.iter_errors(good)), [
        error.message for error in validator.iter_errors(good)
    ]
    assert validate_knowledge_units(good["knowledge_units"])["status"] == "PASS"
    unit_ids = {item["id"] for item in good["knowledge_units"]}
    assert validate_relationships(good["relationships"], unit_ids)["status"] == "PASS"


def test_the_schemas_audit_attempt_cap_is_the_constant() -> None:
    """D-081: the bound is stated twice, so the two must be asserted equal."""
    from x2knwldg.constants import MAX_AUDIT_ATTEMPTS

    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    attempts = bundle_schema["properties"]["coverage"]["properties"]["audit_attempts"]
    assert attempts["maximum"] == MAX_AUDIT_ATTEMPTS
    # Zero is the honest never-audited state; `validate_coverage` refuses it
    # only alongside a `PASS` claim, and the schema must not refuse it outright.
    assert attempts["minimum"] == 0


#: The prompts in ``prompts/`` that do not feed the extraction bundle. Each
#: returns a document with its own contract and its own gate: `T-252`'s brief
#: and `T-253`'s cross-source relations.
SOURCE_KNOWLEDGE_PROMPT = "06_source_knowledge.md"
SOURCE_RELATIONS_PROMPT = "07_source_relations.md"
SYNTHESIS_PROMPTS = (SOURCE_KNOWLEDGE_PROMPT, SOURCE_RELATIONS_PROMPT)


def test_the_source_knowledge_prompt_matches_its_own_schema() -> None:
    """D-073's rule, applied to the contract `T-252`'s prompt actually has.

    The sixth prompt returns a ``source_knowledge`` document, so the question is
    the same one and the schema is a different one: does the JSON it tells the
    agent to return use keys that contract accepts, and does it name every key
    that contract requires? A prompt that omitted a required key would send the
    agent to a gate its own output cannot pass.
    """
    schema = json.loads(
        (
            PROJECT_ROOT
            / "schemas"
            / "synthesis"
            / "v1"
            / "source_knowledge.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False, (
        "this test only means something while the schema forbids other keys"
    )
    text = (PROJECT_ROOT / "prompts" / SOURCE_KNOWLEDGE_PROMPT).read_text(encoding="utf-8")

    marker = text.index("Return JSON only:")
    block = text[marker:].split("```json", 1)[1].split("```", 1)[0]
    document = json.loads(block)

    assert set(document) - set(schema["properties"]) == set(), sorted(document)
    missing = [key for key in schema["required"] if key not in document]
    assert not missing, f"the prompt's example omits required key(s): {missing}"


def test_the_source_relations_prompt_matches_its_own_schema() -> None:
    """The same question as the brief's, against the container's contract."""
    schema = json.loads(
        (
            PROJECT_ROOT / "schemas" / "synthesis" / "v1" / "source_relations.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    text = (PROJECT_ROOT / "prompts" / SOURCE_RELATIONS_PROMPT).read_text(encoding="utf-8")

    marker = text.index("Return JSON only:")
    block = text[marker:].split("```json", 1)[1].split("```", 1)[0]
    document = json.loads(block)

    assert set(document) - set(schema["properties"]) == set(), sorted(document)
    missing = [key for key in schema["required"] if key not in document]
    assert not missing, f"the prompt's example omits required key(s): {missing}"


def test_the_source_relations_prompt_states_what_a_candidate_is_not() -> None:
    """The rule the whole pass turns on, and the one most easily lost.

    Similarity, chronology and shared concepts put a pair in front of the model;
    none of them is evidence of support, critique, response or influence (D-247).
    A prompt that omitted this would be asking for exactly the overclaim risk
    R27 names, and the gate cannot catch it — "these two sources overlap" is a
    perfectly well-formed `overlaps_with` with a real basis.
    """
    text = (PROJECT_ROOT / "prompts" / SOURCE_RELATIONS_PROMPT).read_text(encoding="utf-8")
    assert "A candidate is not a relationship" in text
    assert "Chronology is not influence" in text
    assert "Similarity is not agreement" in text
    assert "no relation" in text.lower()
    assert "confidence" in text


def test_the_source_knowledge_prompt_refuses_to_carry_evidence() -> None:
    """The one field whose presence would turn derived narrative into a quotation.

    ``additionalProperties: false`` already makes it unrepresentable, and a
    committed fixture pins the refusal. This checks the prompt *says so*, because
    the model reading it is the one deciding whether to copy an excerpt across,
    and a rule enforced only after the fact is a rule the model never saw.
    """
    text = (PROJECT_ROOT / "prompts" / SOURCE_KNOWLEDGE_PROMPT).read_text(encoding="utf-8")
    assert "evidence_excerpt" in text
    assert "Persian" in text
    assert "never be stronger" in text or "may never be stronger" in text


def test_every_prompt_returns_a_key_the_bundle_schema_accepts() -> None:
    """D-073: the prompts and the schema named different keys, and code hid it.

    Prompts 01, 02 and 04 all said ``Return JSON only: {"units": [...]}`` while
    the bundle schema requires ``knowledge_units`` and sets
    ``additionalProperties: false`` — so the schema rejected the literal output
    of the prompts WORKFLOW.md §5 sends the agent to. Nothing broke only
    because ``artifacts.apply_extraction_bundle`` silently accepted both
    spellings, which is exactly why it went unnoticed.
    """
    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    accepted = set(bundle_schema["properties"])
    assert bundle_schema["additionalProperties"] is False, (
        "this test only means something while the schema forbids other keys"
    )

    # The **bundle** passes, and only those. `T-252` and `T-253` added prompts
    # whose output is not a bundle key at all — a `source_knowledge` document and
    # a `source_relations` container, both of which the bundle schema rejects and
    # is supposed to, because each goes through a different gate against a
    # different contract. Checking them here would report the schemas disagreeing
    # when in fact they describe different things; each has a test below that
    # holds it to the schema it actually has.
    prompts = [
        path
        for path in sorted((PROJECT_ROOT / "prompts").glob("*.md"))
        if path.name not in SYNTHESIS_PROMPTS
    ]
    assert len(prompts) == 5, [path.name for path in prompts]

    declared: dict[str, set[str]] = {}
    for path in prompts:
        text = path.read_text(encoding="utf-8")
        keys: set[str] = set()
        # The contract is stated two ways — inline as `{ "key": [...] }` and as
        # a fenced JSON block — so read the first object key after each marker
        # rather than matching one layout.
        for marker in re.finditer(r"Return JSON only:", text):
            found = re.search(r'\{\s*"([a-z_]+)"', text[marker.end() : marker.end() + 300])
            if found is not None:
                keys.add(found.group(1))
        if keys:
            declared[path.name] = keys

    # `prompts/05` states its output in prose — "return a complete coverage
    # object" — rather than with a JSON contract, so it has no key to compare.
    assert sorted(declared) == [
        "01_segment_extraction.md",
        "02_normalize_deduplicate.md",
        "03_relationships.md",
        "04_derived_synthesis.md",
    ], sorted(declared)

    wrong = {
        name: sorted(keys - accepted) for name, keys in declared.items() if keys - accepted
    }
    assert not wrong, (
        "these prompts tell the agent to return a top-level key the bundle "
        f"schema rejects: {wrong} (accepted: {sorted(accepted)})"
    )
    # And the mapping is complete in the other direction: the passes between
    # them must name the two array keys the bundle is assembled from, or
    # WORKFLOW.md §5 sends the agent to a schema nothing produces.
    named = set().union(*declared.values())
    assert {"knowledge_units", "relationships"} <= named, sorted(named)


def test_the_omission_item_schema_states_the_keys_validators_read() -> None:
    """D-092: the schema typed an omission as a bare object with no properties.

    ``validate_coverage`` reads ``omission["type"]`` and ``omission["note"]``,
    and those key names appeared only in ``validators.py`` and an archival spec
    the workflow never links — so a model emitting ``{"reason": "sponsor"}``
    passed the schema and was then rejected by ``apply-bundle`` as
    ``invalid_omission_reason`` naming ``null``.
    """
    from x2knwldg.constants import OMISSION_REASONS

    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    window = bundle_schema["properties"]["coverage"]["properties"]["windows"]["items"]
    omission = window["properties"]["omitted_items"]["items"]
    assert omission["required"] == ["type"]
    assert set(omission["properties"]["type"]["enum"]) == set(OMISSION_REASONS)
    # `other_explained` is the one label `validate_coverage` also requires a
    # note for, and the schema now says so rather than leaving it to be found.
    assert omission["then"]["required"] == ["type", "note"]


def test_the_omission_schema_agrees_with_the_validator_case_by_case() -> None:
    """Both gates, over the same entries. Neither may accept what the other refuses."""
    from x2knwldg.validators import validate_coverage

    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(bundle_schema)

    def coverage(omitted: list[dict[str, object]]) -> dict[str, object]:
        return {
            "status": "PARTIAL",
            "audit_attempts": 1,
            "windows": [
                {
                    "window_id": "CW-0001",
                    "start_sec": 0.0,
                    "end_sec": 10.0,
                    "status": "covered",
                    "knowledge_units": ["KU-000001"],
                    "omitted_items": omitted,
                    "unresolved_items": [],
                }
            ],
        }

    cases: list[tuple[list[dict[str, object]], bool]] = [
        ([], True),
        ([{"type": "sponsor"}], True),
        ([{"type": "sponsor", "note": "a sponsor read"}], True),
        ([{"type": "other_explained", "note": "why"}], True),
        # The audit's case: the schema used to accept this and apply-bundle did not.
        ([{"reason": "sponsor"}], False),
        ([{"type": "boring"}], False),
        ([{"type": "other_explained"}], False),
        ([{"type": "other_explained", "note": "   "}], False),
    ]
    for omitted, expected in cases:
        document = coverage(omitted)
        schema_ok = validator.is_valid({
            "knowledge_units": [],
            "relationships": [],
            "coverage": document,
        })
        validator_ok = validate_coverage(document, 10.0)["status"] == "PASS"
        assert schema_ok == validator_ok == expected, (
            omitted,
            {"schema": schema_ok, "validators": validator_ok, "expected": expected},
        )


def test_a_committed_fixture_carries_a_non_empty_omitted_items() -> None:
    """D-092: all three carried `omitted_items: []`, so CI never reached this path.

    Only the gitignored real sample had entries, which is exactly how the key
    mismatch above stayed invisible.
    """
    from x2knwldg.constants import OMISSION_REASONS

    entries = [
        omission
        for path in sorted((PROJECT_ROOT / "tests" / "fixtures" / "runs").glob("*/coverage.json"))
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]
        for omission in window.get("omitted_items") or []
    ]
    assert entries, "no committed fixture exercises omitted_items"
    assert {entry["type"] for entry in entries} <= set(OMISSION_REASONS)
    assert any(entry["type"] == "other_explained" and entry.get("note") for entry in entries), (
        "no fixture exercises the one label that also requires a note"
    )


def test_every_prompt_that_emits_units_names_the_fields_the_schema_requires() -> None:
    """D-110: `prompts/04` stated three obligations and omitted four.

    It named `source_class`, `derived_from` and `derivation_note` — the three a
    derived unit owes beyond an ordinary one — and left out `id`, `kind`,
    `content` and `confidence`, which the bundle schema *requires* of every
    unit. Prompt 01 spells out a full template; prompt 04 did not, so a model
    reading only pass 4 emitted units `apply-bundle` rejects.
    """
    bundle_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(encoding="utf-8")
    )
    required = set(bundle_schema["$defs"]["knowledgeUnit"]["required"])
    assert required, "the schema requires nothing of a unit; this test asserts nothing"

    emitting = ("01_segment_extraction.md", "04_derived_synthesis.md")
    for name in emitting:
        text = (PROJECT_ROOT / "prompts" / name).read_text(encoding="utf-8")
        missing = sorted(field for field in required if f'"{field}"' not in text)
        assert not missing, (
            f"{name} tells the agent to return units without naming "
            f"{missing}, which the bundle schema requires"
        )


def test_the_derived_prompt_does_not_ask_for_a_source_block() -> None:
    """A derived unit cites units, not the transcript.

    `validate_knowledge_units` refuses a derived unit that carries a source
    kind (`kind_source_class_mismatch`), and a `source` block on a synthesis is
    how it comes to look like a quotation.
    """
    text = (PROJECT_ROOT / "prompts" / "04_derived_synthesis.md").read_text(encoding="utf-8")
    assert "evidence_excerpt" not in text
    assert "no** `source` block" in text or "no `source` block" in text
