"""Adversarial tests for the source adapters — what they refuse to state.

``tests/test_adapters.py`` maps well-formed runs and asks what the adapter
leaves out. ``tests/test_index_schemas.py`` asks whether the records satisfy the
v1 model. Both only ever see canonical files that are already correct, and that
gap is what this module closes: **every test here feeds the adapter a
deliberately broken canonical file and asserts a refusal.**

The gap was not theoretical. Twelve invalid values — a knowledge kind outside
the vocabulary, a confidence above 1, an unknown provenance class, a label
longer than the model allows, a negative duration — were copied straight through
into records that the project's own frozen schemas reject, and no test noticed,
because no test had ever shown the adapter a bad value.

Two rules are under test throughout:

**An absence is reported as an absence.** A missing file, a missing key, a null:
none of them is an error, and none of them is filled in.

**A value that is present and out of contract is refused.** Not clamped, not
translated to the nearest legal value, and not passed on for someone else's
validator to trip over. A guess is a refusal.

Stdlib only, like the module it tests: the adapters must keep working on a bare
core install (ADR 0001 invariant 5). The frozen schemas are read here as plain
JSON, purely to prove that the bounds mirrored into ``adapters/base.py`` still
say what ``schemas/v1/`` says.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import ids
from x2knwldg.adapters import (
    CANONICAL_RELATION_TYPES,
    KNOWLEDGE_KINDS,
    LIBRARY_SYNTHETIC_RELATION_TYPES,
    PROVENANCE_CLASSES,
    AdapterError,
    adapt_library,
    adapt_project,
    adapt_run,
    base,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
SCHEMAS = PROJECT_ROOT / "schemas" / "v1"

# The fixture unit ids, from tests/fixtures/runs/*/knowledge_units.json.
SOURCE_UNIT = 0
DERIVED_UNIT = 1


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """A writable copy of ``pass-run``, rooted in its own project root."""
    destination = tmp_path / "output" / "pass-run"
    shutil.copytree(FIXTURE_RUNS / "pass-run", destination)
    return destination


def _edit(path: Path, mutate: Callable[[dict], None]) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def _defs() -> dict[str, Any]:
    return _schema("common")["$defs"]


# --------------------------------------------------------------------------
# The schemas stay the authority
# --------------------------------------------------------------------------
#
# base.py mirrors the v1 bounds because the adapters cannot import jsonschema.
# A mirror that is allowed to drift is worse than no mirror: the adapter would
# refuse values the model accepts, or accept values it rejects, and in both
# cases the schema would no longer be the thing being enforced.


def test_the_mirrored_vocabularies_match_the_frozen_schemas() -> None:
    defs = _defs()
    assert KNOWLEDGE_KINDS == set(defs["knowledgeKind"]["enum"])
    assert CANONICAL_RELATION_TYPES == set(defs["canonicalRelationType"]["enum"])
    assert LIBRARY_SYNTHETIC_RELATION_TYPES == set(
        defs["librarySyntheticRelationType"]["enum"]
    )
    assert PROVENANCE_CLASSES == set(defs["provenanceClass"]["enum"])
    assert base.CANONICAL_PROVENANCE_CLASSES < PROVENANCE_CLASSES, (
        "'user' is workspace content and never appears in a canonical file"
    )
    # ``runStatus`` was the one mirrored vocabulary with no drift test, while
    # its four values are the whole of ADR 0001 invariant 2: UNKNOWN is what an
    # absent or unreadable validator file becomes, and it must never be
    # substituted with PASS.
    assert base.RUN_STATUSES | {base.UNKNOWN_STATUS} == set(defs["runStatus"]["enum"])
    assert base.UNKNOWN_STATUS not in base.RUN_STATUSES, (
        "UNKNOWN is the absence of a stated status, not one of them"
    )


@pytest.mark.parametrize(
    "value",
    [
        "output/../../etc/passwd",
        "output\n../../etc/passwd",
        "output/x\n",
        "output/\t../..",
        "/etc/passwd",
        "C:/Windows",
        "..",
        "output/..",
    ],
    ids=[
        "plain-traversal",
        "traversal-after-a-newline",
        "trailing-newline",
        "traversal-after-a-tab",
        "absolute-posix",
        "absolute-windows",
        "bare-dotdot",
        "trailing-dotdot",
    ],
)
def test_the_published_path_pattern_refuses_every_traversal(value: str) -> None:
    """A newline used to defeat the pattern the contract publishes.

    ``.`` matches no newline in either Python ``re`` or ECMA-262 and the
    anchors are not multiline, so ``output/../../etc/passwd`` was rejected
    while ``output\n../../etc/passwd`` was **accepted**. Python's ``$`` also
    matches before a trailing newline, so ``output/x\n`` slipped through there
    and not in a JavaScript consumer — the same hazard ``ISO_TIMESTAMP_PATTERN``
    is anchored with ``\\Z`` for.

    Not exploitable in this repo — ``project_relative`` builds paths
    structurally from ``Path.relative_to`` — but the published contract
    asserted a check it did not perform for any other consumer.
    """
    pattern = _defs()["projectRelativePath"]["pattern"]
    assert re.search(pattern, value) is None, value


@pytest.mark.parametrize(
    "value", ["output/vid1/metadata.json", "output/./x", "a", "ok/ünïcode.json"]
)
def test_the_published_path_pattern_still_accepts_a_real_path(value: str) -> None:
    pattern = _defs()["projectRelativePath"]["pattern"]
    assert re.search(pattern, value) is not None, value


def test_a_corrupt_symlinked_canonical_file_still_leaves_the_run_indexed(
    tmp_path: Path,
) -> None:
    """D-100's wrap, which ``_file_artifact`` got and ``_read`` did not.

    ``self.relative`` resolves symlinks, so a canonical file that is a symlink
    to somewhere outside the project raised ``AdapterError`` out of ``_read``
    and took the **whole run** down — downgrading it from "damaged, and here is
    the file" to "absent". A run whose ``validation.json`` is both symlinked
    outside the root *and* unparseable is damaged in a way the record can
    state, and stating it is what this channel is for.
    """
    project = tmp_path / "project"
    (project / "output").mkdir(parents=True)
    run_dir = project / "output" / "pass-run"
    shutil.copytree(FIXTURE_RUNS / "pass-run", run_dir)

    outside = tmp_path / "outside"
    outside.mkdir()
    broken = outside / "validation.json"
    broken.write_text("{ not json", encoding="utf-8")
    target = run_dir / "validation.json"
    target.unlink()
    target.symlink_to(broken)

    records = adapt_run(run_dir, project)

    source = records.sources[0]
    assert source["id"] == "youtube:fixture-pass", "the run is indexed, not refused"
    damaged = source["adapter_metadata"]["unreadable_files"]
    assert [entry["path"] for entry in damaged] == ["validation.json"]
    reason = damaged[0]["reason"]
    assert "Malformed JSON" in reason, "the damage must still be stated"
    assert "outside the project root" in reason
    # ADR 0003: not the host layout, and not the doubled phrasing either.
    assert str(tmp_path) not in reason
    assert "the project root the project root" not in reason
    # ADR 0001 invariant 2: an unreadable validator file is UNKNOWN, never PASS.
    assert source["status"]["validation"] == "UNKNOWN"
    assert source["status"]["overall"] == "UNKNOWN"


def test_the_producer_refuses_what_the_pattern_refuses(tmp_path: Path) -> None:
    """``project_relative`` may not hand the schemas a value they reject."""
    root = tmp_path / "project"
    (root / "output").mkdir(parents=True)
    named = root / "output" / "we\nird.json"
    named.write_text("{}", encoding="utf-8")

    with pytest.raises(base.AdapterError) as caught:
        base.project_relative(named, root)
    assert "projectRelativePath" in str(caught.value)

    ordinary = root / "output" / "fine.json"
    ordinary.write_text("{}", encoding="utf-8")
    assert base.project_relative(ordinary, root) == "output/fine.json"


def test_every_timestamp_in_the_frozen_documents_carries_the_pattern() -> None:
    """``built_at: "yesterday"`` validated against every check in the tree.

    ``isoTimestamp``'s own ``$comment`` says why: ``format`` is annotation-only
    in 2020-12 unless a validator opts into the format-assertion vocabulary,
    and none of this repo's validators do. ``StatusPayload.index.built_at``
    carried ``format: date-time`` and no pattern, while the identical value on
    ``Source.imported_at`` was correctly rejected.
    """
    api = json.loads(
        (PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json").read_text(encoding="utf-8")
    )
    unchecked: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if node.get("format") == "date-time" and "pattern" not in node:
                unchecked.append(path)
            for key, value in node.items():
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}/{index}")

    for document in (api, _defs(), json.loads((SCHEMAS / "source.schema.json").read_text(encoding="utf-8"))):
        walk(document, "")
    assert unchecked == [], (
        "these fields assert a timestamp shape no validator in this repo checks; "
        f"refer to common.schema.json#/$defs/isoTimestamp instead: {unchecked}"
    )


@pytest.mark.parametrize(
    "stated, parsed",
    [
        # Every Twitter capture: `acquisition.requested_at` is written with a
        # `Z`, and `_metadata` copies it to `metadata.acquired_at`.
        ("2026-09-03T20:36:00Z", "2026-09-03T20:36:00+00:00"),
        ("2026-09-03T20:36:00z", "2026-09-03T20:36:00+00:00"),
        # Fractional seconds of any length are in the pattern; 3.10 parses
        # exactly three or six digits.
        ("2026-09-03T20:36:00.5Z", "2026-09-03T20:36:00.500000+00:00"),
        ("2026-09-03T20:36:00.1234+03:30", "2026-09-03T20:36:00.123400+03:30"),
        # Already in the narrow spelling: rewritten to itself.
        ("2026-09-03T20:36:00.123+00:00", "2026-09-03T20:36:00.123+00:00"),
        ("2026-09-03T20:36:00-05:00", "2026-09-03T20:36:00-05:00"),
    ],
)
def test_a_timestamp_the_floor_interpreter_cannot_parse_is_still_a_timestamp(
    stated: str, parsed: str
) -> None:
    """`requires-python` says 3.10, and 3.10's parser is narrower than RFC 3339.

    `datetime.fromisoformat` accepted a `Z` designator only from 3.11, and
    parses fractional seconds of exactly three or six digits — while
    `common.schema.json#/$defs/isoTimestamp` accepts both spellings and
    `ISO_TIMESTAMP_PATTERN` mirrors it. So projecting an acquired Twitter post
    raised `ValueError: Invalid isoformat string` on the floor interpreter and
    on no other, which is a defect the local suite could not see.

    Asserted on the rewritten string rather than on "it parses here", because
    on 3.11 and later both forms parse and the test would prove nothing.
    """
    assert base._parseable(stated) == parsed
    datetime.fromisoformat(base._parseable(stated))
    # And the copied field is still the model's own text, unchanged: the
    # rewrite is for the parse, never for the record.
    assert base.copied_timestamp(stated, owner="source:x", field="acquired_at") == stated


def test_a_status_timestamp_that_is_not_a_timestamp_is_refused() -> None:
    """The rule asserted over the value, not only over the document.

    ``importorskip``, not a bare import: ``jsonschema`` is the ``dev`` extra
    and the core package installs nothing (ADR 0001 invariant 5), so CI's
    bare-venv job runs this suite with only ``x2knwldg`` and ``pytest``. A
    plain import there is a *failure* where every other schema test in the
    tree skips — which is the whole point of that job, and it caught this on
    the first push.
    """
    jsonschema = pytest.importorskip(
        "jsonschema", reason="jsonschema is the dev extra; the core install has none"
    )
    referencing = pytest.importorskip(
        "referencing", reason="jsonschema's resolver, and likewise optional"
    )
    Draft202012Validator = jsonschema.Draft202012Validator
    Registry, Resource = referencing.Registry, referencing.Resource

    common = json.loads((SCHEMAS / "common.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resource(
        "https://x2knwldg.local/schemas/v1/common.schema.json",
        Resource.from_contents(common),
    )
    validator = Draft202012Validator(
        {"$ref": "https://x2knwldg.local/schemas/v1/common.schema.json#/$defs/isoTimestamp"},
        registry=registry,
    )
    assert list(validator.iter_errors("yesterday"))
    assert list(validator.iter_errors("2026-09-03T00:00:00")), "an offset is required"
    assert not list(validator.iter_errors("2026-09-03T00:00:00+00:00"))


def test_the_mirrored_length_bounds_match_the_frozen_schemas() -> None:
    defs = _defs()
    source = _schema("source")["properties"]
    entity = _schema("entity_ref")["properties"]
    relation = _schema("indexed_relation")["properties"]
    artifact = _schema("artifact")["properties"]
    time_range = _schema("locator")["allOf"][0]["then"]["properties"]

    assert base.ISO_TIMESTAMP_PATTERN == defs["isoTimestamp"]["pattern"].strip("^$")
    assert base.MIN_CONFIDENCE == defs["confidence"]["minimum"]
    assert base.MAX_CONFIDENCE == defs["confidence"]["maximum"]
    assert base.MAX_PATH_LENGTH == defs["projectRelativePath"]["maxLength"]
    assert base.MAX_URL_LENGTH == source["url"]["maxLength"]
    assert base.MAX_TITLE_LENGTH == source["title"]["maxLength"]
    assert base.MAX_AUTHOR_LENGTH == source["author"]["maxLength"]
    assert base.MAX_LANGUAGE_LENGTH == source["language"]["maxLength"]
    assert base.MAX_LABEL_LENGTH == entity["label"]["maxLength"]
    assert base.MAX_EDGE_ID_LENGTH == relation["id"]["maxLength"]
    assert base.MAX_RELATION_LENGTH == relation["relation"]["maxLength"]
    assert base.MAX_MEDIA_TYPE_LENGTH == artifact["media_type"]["maxLength"]
    assert base.MAX_SEGMENT_ID_LENGTH == time_range["segment_id"]["maxLength"]
    assert base.MAX_URL_LENGTH == artifact["url"]["maxLength"]


def test_an_unbounded_field_is_not_given_a_bound_here() -> None:
    """An excerpt and a derivation note are copied verbatim, however long.

    The model states no maximum for either, and inventing one would truncate
    evidence — the one thing a reader of canonical data may never do.
    """
    time_range = _schema("locator")["allOf"][0]["then"]["properties"]
    assert "maxLength" not in time_range["excerpt"]
    assert "maxLength" not in _schema("entity_ref")["properties"]["derivation_note"]


# --------------------------------------------------------------------------
# Every invalid value is refused, not copied
# --------------------------------------------------------------------------
#
# One mutation per case, applied to the pass-run fixture, each naming the rule
# it breaks. Every one of these was copied through into a schema-invalid record
# before the adapter learned to check what it was copying.

LONG = "x" * 5000


def _unit(index: int, **fields: Any) -> Callable[[dict], None]:
    def mutate(document: dict) -> None:
        document["units"][index].update(fields)

    return mutate


def _drop_unit_field(index: int, key: str) -> Callable[[dict], None]:
    def mutate(document: dict) -> None:
        document["units"][index].pop(key)

    return mutate


def _provenance(**fields: Any) -> Callable[[dict], None]:
    def mutate(document: dict) -> None:
        document["units"][SOURCE_UNIT]["source"].update(fields)

    return mutate


def _edge(**fields: Any) -> Callable[[dict], None]:
    def mutate(document: dict) -> None:
        document["relationships"][0].update(fields)

    return mutate


def _drop_edge_field(key: str) -> Callable[[dict], None]:
    def mutate(document: dict) -> None:
        document["relationships"][0].pop(key)

    return mutate


REFUSED: list[tuple[str, str, Callable[[dict], None], str]] = [
    # metadata.json — the Source record
    ("metadata.json", "negative duration", lambda d: d.update(duration_sec=-1), "duration_sec"),
    ("metadata.json", "duration as text", lambda d: d.update(duration_sec="90"), "duration_sec"),
    ("metadata.json", "duration as a flag", lambda d: d.update(duration_sec=True), "duration_sec"),
    ("metadata.json", "title over 1024", lambda d: d.update(title=LONG), "title"),
    ("metadata.json", "channel over 512", lambda d: d.update(channel=LONG), "channel"),
    ("metadata.json", "language over 32", lambda d: d.update(language="e" * 40), "language"),
    ("metadata.json", "title that is a number", lambda d: d.update(title=7), "title"),
    ("metadata.json", "empty url", lambda d: d.update(video_url=""), "video_url"),
    ("metadata.json", "url over 2048", lambda d: d.update(video_url="https://" + LONG), "video_url"),
    ("metadata.json", "unparseable timestamp", lambda d: d.update(imported_at="yesterday"), "imported_at"),
    ("metadata.json", "timestamp that is a number", lambda d: d.update(extracted_at=0), "extracted_at"),
    ("metadata.json", "timestamp with no offset", lambda d: d.update(imported_at="2026-01-01T00:00:00"), "imported_at"),
    ("metadata.json", "a date that does not exist", lambda d: d.update(imported_at="2026-02-30T00:00:00+00:00"), "imported_at"),
    # knowledge_units.json — the EntityRef records
    ("knowledge_units.json", "kind outside the vocabulary", _unit(SOURCE_UNIT, kind="vibe"), "kind"),
    ("knowledge_units.json", "no kind at all", _drop_unit_field(SOURCE_UNIT, "kind"), "kind"),
    ("knowledge_units.json", "confidence above 1", _unit(SOURCE_UNIT, confidence=1.4), "confidence"),
    ("knowledge_units.json", "confidence below 0", _unit(SOURCE_UNIT, confidence=-0.1), "confidence"),
    ("knowledge_units.json", "confidence as text", _unit(SOURCE_UNIT, confidence="high"), "confidence"),
    ("knowledge_units.json", "unknown provenance class", _unit(SOURCE_UNIT, source_class="unknown"), "source_class"),
    ("knowledge_units.json", "user provenance in a canonical file", _unit(SOURCE_UNIT, source_class="user"), "source_class"),
    ("knowledge_units.json", "label over 4096", _unit(SOURCE_UNIT, normalized_statement=LONG), "4096"),
    ("knowledge_units.json", "label that is a number", _unit(SOURCE_UNIT, normalized_statement=3, content=None), "normalized_statement"),
    ("knowledge_units.json", "derived from nothing", _unit(DERIVED_UNIT, derived_from=[]), "empty list"),
    ("knowledge_units.json", "no derived_from at all", _drop_unit_field(DERIVED_UNIT, "derived_from"), "names nothing"),
    ("knowledge_units.json", "derived_from that is not a list", _unit(DERIVED_UNIT, derived_from="KU-000001"), "derived_from"),
    ("knowledge_units.json", "the same provenance twice", _unit(DERIVED_UNIT, derived_from=["KU-000001", "KU-000001"]), "more than once"),
    ("knowledge_units.json", "no derivation note", _drop_unit_field(DERIVED_UNIT, "derivation_note"), "derivation_note"),
    ("knowledge_units.json", "empty derivation note", _unit(DERIVED_UNIT, derivation_note=""), "derivation_note"),
    ("knowledge_units.json", "negative start time", _provenance(start_sec=-1.0), "start_sec"),
    ("knowledge_units.json", "start time as text", _provenance(start_sec="0"), "start_sec"),
    ("knowledge_units.json", "segment id over 128", _provenance(segment_id="s" * 200), "segment_id"),
    ("knowledge_units.json", "empty evidence excerpt", _provenance(evidence_excerpt=""), "evidence_excerpt"),
    ("knowledge_units.json", "units that are not a list", lambda d: d.update(units={"KU-000001": {}}), "units"),
    ("knowledge_units.json", "a unit that is not an object", lambda d: d["units"].append("KU-000003"), "units[2]"),
    # relationships.json — the IndexedRelation records
    ("relationships.json", "relation outside RELATION_TYPES", _edge(relation="sort_of_supports"), "relation"),
    ("relationships.json", "a synthetic relation in the canonical file", _edge(relation="expresses_concept"), "relation"),
    ("relationships.json", "no confidence", _drop_edge_field("confidence"), "confidence"),
    ("relationships.json", "confidence above 1", _edge(confidence=1.4), "confidence"),
    ("relationships.json", "no provenance class", _drop_edge_field("source_class"), "source_class"),
    ("relationships.json", "user provenance on a canonical edge", _edge(source_class="user"), "source_class"),
    # coverage.json — the status block
    ("coverage.json", "audit attempts over the cap", lambda d: d.update(audit_attempts=4), "audit_attempts"),
    ("coverage.json", "audit attempts as text", lambda d: d.update(audit_attempts="two"), "audit_attempts"),
    ("coverage.json", "negative audit attempts", lambda d: d.update(audit_attempts=-1), "audit_attempts"),
]


@pytest.mark.parametrize(
    ("filename", "reason", "mutate", "names"),
    REFUSED,
    ids=[f"{filename.removesuffix('.json')}-{reason}" for filename, reason, _, _ in REFUSED],
)
def test_a_value_the_model_cannot_carry_is_refused(
    run: Path, filename: str, reason: str, mutate: Callable[[dict], None], names: str
) -> None:
    _edit(run / filename, mutate)
    with pytest.raises(AdapterError) as excinfo:
        adapt_run(run, run.parents[1])
    message = str(excinfo.value)
    assert names in message, f"the refusal should name the field: {message}"
    assert filename.removesuffix(".json") in message or "unit" in message or "edge" in message, (
        f"the refusal should name the canonical file to fix: {message}"
    )


def test_the_unmutated_fixture_still_maps(run: Path) -> None:
    """The control. A rule strict enough to refuse everything proves nothing."""
    records = adapt_run(run, run.parents[1])
    assert len(records.sources) == 1
    assert records.artifacts and records.entities and records.relations


@pytest.mark.parametrize("name", ["pass-run", "partial-run", "fail-run"])
def test_every_committed_fixture_still_maps(tmp_path: Path, name: str) -> None:
    """Including the damaged ones: refusing bad *values* must not start
    refusing runs whose *status* is bad. A FAIL run is still indexable."""
    destination = tmp_path / "output" / name
    shutil.copytree(FIXTURE_RUNS / name, destination)
    assert adapt_run(destination, tmp_path).sources


# --------------------------------------------------------------------------
# An absence is still an absence
# --------------------------------------------------------------------------


def test_an_absent_optional_value_is_null_not_a_refusal(run: Path) -> None:
    """Refusing a bad value must not turn into refusing a missing one."""
    def strip(document: dict) -> None:
        for key in ("title", "channel", "language", "duration_sec", "extracted_at"):
            document.pop(key)

    _edit(run / "metadata.json", strip)
    source = adapt_run(run, run.parents[1]).sources[0]
    assert source["title"] is None
    assert source["author"] is None
    assert source["language"] is None
    assert source["duration_sec"] is None
    assert source["extracted_at"] is None


def test_an_absent_confidence_stays_absent(run: Path) -> None:
    _edit(run / "knowledge_units.json", _drop_unit_field(SOURCE_UNIT, "confidence"))
    unit = next(
        e for e in adapt_run(run, run.parents[1]).entities if e["provenance_class"] == "source"
    )
    assert unit["confidence"] is None


def test_an_absent_units_key_is_no_units_rather_than_a_refusal(run: Path) -> None:
    # Both files, because an edge outlives the unit it names only in a damaged
    # run: that case is its own test below, and this one is about the absence.
    _edit(run / "knowledge_units.json", lambda d: d.pop("units"))
    _edit(run / "relationships.json", lambda d: d.update(relationships=[]))
    records = adapt_run(run, run.parents[1])
    assert records.entities == []
    assert records.sources[0]["counts"]["knowledge_units"] == 0


def test_a_never_audited_run_is_carried_through_as_stated(run: Path) -> None:
    """``coverage.py`` writes ``audit_attempts: 0`` for a run that has not been
    audited yet, and WORKFLOW.md calls that the honest state. It is copied, not
    refused and not nulled — nulling would restate 'never audited' as 'no
    coverage file', which is a different claim."""
    _edit(run / "coverage.json", lambda d: d.update(audit_attempts=0, status="PARTIAL"))
    status = adapt_run(run, run.parents[1]).sources[0]["status"]
    assert status["audit_attempts"] == 0
    assert status["coverage"] == "PARTIAL"


def test_an_absent_audit_count_is_null(run: Path) -> None:
    _edit(run / "coverage.json", lambda d: d.pop("audit_attempts"))
    assert adapt_run(run, run.parents[1]).sources[0]["status"]["audit_attempts"] is None


# --------------------------------------------------------------------------
# A derived unit shows its work, and its edge cannot vanish
# --------------------------------------------------------------------------


def test_a_derived_unit_and_its_edges_agree(run: Path) -> None:
    """The unit's ``derived_from`` and the ``derived_from`` edges are read from
    one place, so an edge can no longer go missing while the unit that should
    have produced it is still indexed."""
    records = adapt_run(run, run.parents[1])
    edges: dict[str, set[str]] = {}
    for relation in records.relations:
        if relation["relation"] == "derived_from":
            edges.setdefault(relation["from_id"], set()).add(relation["to_id"])

    derived = [e for e in records.entities if e["provenance_class"] == "derived"]
    assert derived, "the fixture has a derived unit"
    for unit in derived:
        assert set(unit["derived_from"]) == edges[unit["global_id"]]


def test_a_derived_unit_showing_no_work_takes_no_edge_with_it(run: Path) -> None:
    """The old failure mode: an invented empty ``derived_from`` asserted derived
    provenance while naming nothing, and the edge disappeared without a word."""
    _edit(run / "knowledge_units.json", _unit(DERIVED_UNIT, derived_from=[]))
    with pytest.raises(AdapterError, match="empty list"):
        adapt_run(run, run.parents[1])


# --------------------------------------------------------------------------
# An unaddressable vault note is reported, not dropped and not fatal
# --------------------------------------------------------------------------


def _add_note(run: Path, name: str) -> None:
    (run / "vault" / "videos" / name).write_text("# note\n", encoding="utf-8")


def test_an_unaddressable_vault_note_does_not_make_a_project_unindexable(run: Path) -> None:
    """One badly named export file must not take down the whole index. The
    canonical evidence is untouched by what the vault is called."""
    _add_note(run, "my note.md")
    records = adapt_run(run, run.parents[1])
    assert records.sources, "the run is still mapped"
    assert records.entities, "and its knowledge is still there"


def test_an_unaddressable_vault_note_is_reported_rather_than_dropped(run: Path) -> None:
    _add_note(run, "my note.md")
    source = adapt_run(run, run.parents[1]).sources[0]
    reported = source["adapter_metadata"]["unmappable_artifacts"]
    assert [entry["path"] for entry in reported] == ["vault/videos/my note.md"]
    assert "not addressable" in reported[0]["reason"]
    assert not any(
        (a["path"] or "").endswith("my note.md")
        for a in adapt_run(run, run.parents[1]).artifacts
    )


def test_a_run_with_only_addressable_notes_reports_nothing(run: Path) -> None:
    """The report exists to name a real omission, so it is absent when there is
    none: an empty list would look like an unread finding."""
    assert "unmappable_artifacts" not in adapt_run(run, run.parents[1]).sources[0][
        "adapter_metadata"
    ]


def test_the_id_a_vault_note_would_need_is_the_one_ids_py_rejects(run: Path) -> None:
    """Whatever is skipped is skipped for the reason the report gives."""
    _add_note(run, "my note.md")
    assert not ids.is_id_part("vault.videos.my note")


# --------------------------------------------------------------------------
# Edge ids cannot collide
# --------------------------------------------------------------------------


def test_an_edge_id_cannot_be_spelled_by_another_edge() -> None:
    """The separator is escaped in every part. Nothing splits on it today, which
    is exactly why an unescaped join is a collision waiting for the first
    relation vocabulary that admits the character."""
    # It moved to the base with the relation minting it serves (T-228): the
    # rule is not YouTube's, and a second adapter joining ids its own way is
    # the collision this test is about, one layer up.
    from x2knwldg.adapters.base import edge_id

    collidable = edge_id("youtube:v:a", "supports|youtube:v:b", "youtube:v:c")
    plain = edge_id("youtube:v:a", "supports", "youtube:v:b|youtube:v:c")
    assert collidable != plain


def test_edge_ids_are_unchanged_for_every_id_this_project_produces(run: Path) -> None:
    """Rebuild-equivalence (T-104): escaping must not renumber the world."""
    for relation in adapt_run(run, run.parents[1]).relations:
        assert relation["id"] == "|".join(
            (relation["from_id"], relation["relation"], relation["to_id"])
        )


# --------------------------------------------------------------------------
# The combined id set across runs
# --------------------------------------------------------------------------


def _project_with(tmp_path: Path, *names: str) -> Path:
    for name in names:
        shutil.copytree(FIXTURE_RUNS / name, tmp_path / "output" / name)
    return tmp_path


def test_two_runs_may_not_declare_the_same_source(tmp_path: Path) -> None:
    """Per-run uniqueness is not project-wide uniqueness. Two directories
    declaring one ``video_id`` collide on every id they produce, and an index
    keyed by id would keep the last and lose the first without a word."""
    project = _project_with(tmp_path, "pass-run", "partial-run")
    _edit(
        project / "output" / "partial-run" / "metadata.json",
        lambda d: d.update(video_id="fixture-pass"),
    )
    with pytest.raises(AdapterError, match="one record, one id"):
        adapt_project(project)


def test_each_run_alone_is_still_valid_when_the_pair_is_not(tmp_path: Path) -> None:
    """The collision is a property of the project, not of either run: this is
    why per-run checking could never have found it."""
    project = _project_with(tmp_path, "pass-run", "partial-run")
    _edit(
        project / "output" / "partial-run" / "metadata.json",
        lambda d: d.update(video_id="fixture-pass"),
    )
    for name in ("pass-run", "partial-run"):
        assert adapt_run(project / "output" / name, project).sources


def test_distinct_runs_are_all_kept(tmp_path: Path) -> None:
    project = _project_with(tmp_path, "pass-run", "partial-run", "fail-run")
    records = adapt_project(project)
    assert len(records.sources) == 3
    claimed = [(namespace, value) for namespace, value, _ in records.addressable()]
    assert len(claimed) == len(set(claimed))


def test_a_run_may_not_impersonate_the_library_namespace(tmp_path: Path) -> None:
    """``library:concepts`` is reserved for cross-source entities (D-016), and a
    run that claimed it would collide with the concepts themselves.

    It is refused one step earlier than the collision: no adapter is registered
    for the reserved source type, so nothing can mint an id inside it. This
    records that the namespace is unreachable from a run at all.
    """
    project = _project_with(tmp_path, "pass-run")
    library = project / "output" / "library"
    library.mkdir()
    (library / "concepts.json").write_text(
        json.dumps({"concepts": [{"id": "concept:abc", "canonical_label": "A"}]}),
        encoding="utf-8",
    )
    (library / "graph.json").write_text(
        json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
    )
    _edit(
        project / "output" / "pass-run" / "metadata.json",
        lambda d: d.update(source_type="library", video_id="concepts"),
    )
    with pytest.raises(AdapterError, match="no adapter is registered"):
        adapt_project(project)


# --------------------------------------------------------------------------
# The cross-source library, without the developer's local sample
# --------------------------------------------------------------------------
#
# The library rules were only ever exercised against output/library/, which
# exists on the machine that ingested the real sample and nowhere else — so in
# CI they skipped, and the rules they assert were unproven exactly where proof
# matters. These build a library in the same two-id-form shape library.py emits.

CONCEPT_HASH = "1f4a9c2b7e01"


def _library(tmp_path: Path, **overrides: Any) -> Path:
    library = tmp_path / "output" / "library"
    library.mkdir(parents=True)
    node = {
        "id": "fixture-pass:KU-000001",
        "global_id": "youtube:fixture-pass:KU-000001",
        "label": "A knowledge unit must carry the evidence it rests on.",
        "kind": "principle",
        "source_class": "source",
    }
    concept_node = {
        "id": f"concept:{CONCEPT_HASH}",
        "global_id": f"library:concepts:{CONCEPT_HASH}",
        "label": "evidence",
        "kind": "canonical_concept",
        "source_class": "derived",
    }
    edge = {
        "from": "fixture-pass:KU-000001",
        "to": f"concept:{CONCEPT_HASH}",
        "relation": "expresses_concept",
        "source_class": "derived",
        "confidence": 1.0,
    }
    edge.update(overrides.pop("edge", {}))
    concepts = [{"id": f"concept:{CONCEPT_HASH}", "canonical_label": "evidence"}]
    for key, value in overrides.pop("concept", {}).items():
        concepts[0][key] = value
    (library / "graph.json").write_text(
        json.dumps({"nodes": [node, concept_node], "edges": [edge]}), encoding="utf-8"
    )
    (library / "concepts.json").write_text(
        json.dumps({"concepts": concepts}), encoding="utf-8"
    )
    return library


def test_the_library_emits_no_source_and_only_concept_edges(tmp_path: Path) -> None:
    records = adapt_library(_library(tmp_path), tmp_path)
    assert not records.sources, "the library is not an ingested source"
    assert {r["relation"] for r in records.relations} == {"expresses_concept"}
    assert all(r["source_id"] is None for r in records.relations)


def test_a_concept_is_addressed_in_both_vocabularies(tmp_path: Path) -> None:
    concept = adapt_library(_library(tmp_path), tmp_path).entities[0]
    assert concept["global_id"] == ids.global_id_from_library_id(concept["library_id"]).value
    assert ids.library_id_from_global_id(concept["global_id"]) == concept["library_id"]
    assert concept["source_id"] is None


def test_a_library_edge_claiming_source_evidence_is_refused(tmp_path: Path) -> None:
    """A synthetic edge is recorded synthesis by definition (D-025)."""
    library = _library(tmp_path, edge={"source_class": "source"})
    with pytest.raises(AdapterError, match="source_class"):
        adapt_library(library, tmp_path)


def test_a_library_confidence_outside_the_range_is_refused(tmp_path: Path) -> None:
    library = _library(tmp_path, edge={"confidence": 4})
    with pytest.raises(AdapterError, match="confidence"):
        adapt_library(library, tmp_path)


def test_a_concept_label_the_model_cannot_carry_is_refused(tmp_path: Path) -> None:
    library = _library(tmp_path, concept={"canonical_label": LONG})
    with pytest.raises(AdapterError, match="canonical_label"):
        adapt_library(library, tmp_path)


def test_the_library_never_reads_the_absolute_path_fields(tmp_path: Path) -> None:
    """status.json and videos.json hold absolute host paths (risk R15), and the
    mapping must not need them: neither file exists here."""
    records = adapt_library(_library(tmp_path), tmp_path)
    assert records.entities and records.relations
    for record in [*records.entities, *records.relations]:
        for key, value in record.items():
            if key.endswith("path") and isinstance(value, str):
                assert not value.startswith("/")


# --------------------------------------------------------------------------
# The set is refused where it is built, not where it is served
# --------------------------------------------------------------------------
#
# ``repository.check_index_integrity`` refuses a duplicate id and a dangling
# edge when a repository is constructed. That is the right failure at the wrong
# end of the seam: the records are produced here. These assert that
# ``check_records`` refuses exactly what the far side refuses — the two must
# never disagree, because a rule with two spellings is a rule with two answers.


def _entity(local_id: str = "KU-000001", **fields: Any) -> dict[str, Any]:
    entity = {
        "schema_version": "1.0",
        "global_id": f"youtube:v:{local_id}",
        "source_type": "youtube",
        "external_id": "v",
        "local_id": local_id,
        "library_id": f"v:{local_id}",
        "source_id": "youtube:v",
        "entity_type": "knowledge_unit",
        "provenance_class": "derived",
        "kind": "synthesis",
        "label": local_id,
        "confidence": None,
        "derived_from": ["youtube:v:KU-000002"],
        "derivation_note": "n",
        "canonical_path": "output/v/knowledge_units.json",
    }
    entity.update(fields)
    return entity


def _relation(from_id: str, to_id: str, **fields: Any) -> dict[str, Any]:
    relation = {
        "schema_version": "1.0",
        "id": f"{from_id}|supports|{to_id}",
        "from_id": from_id,
        "to_id": to_id,
        "relation": "supports",
        "relation_vocabulary": "canonical",
        "provenance_class": "derived",
        "confidence": 0.5,
        "source_id": "youtube:v",
        "canonical_path": "output/v/relationships.json",
    }
    relation.update(fields)
    return relation


def test_two_relations_may_not_claim_one_edge_id() -> None:
    """A duplicate id makes the repository's page order non-total, and a tie
    across a page boundary drops a record while ``total`` keeps counting it."""
    records = base.IndexRecords(
        entities=[_entity("KU-000001"), _entity("KU-000002")],
        relations=[
            _relation("youtube:v:KU-000001", "youtube:v:KU-000002"),
            _relation("youtube:v:KU-000001", "youtube:v:KU-000002"),
        ],
    )
    with pytest.raises(AdapterError, match="one record, one id"):
        base.check_records(records)


def test_an_edge_may_not_name_an_endpoint_no_entity_has() -> None:
    """A dangling edge is excluded from the graph and listed by the relations
    endpoint, so the two views disagree about one fact."""
    records = base.IndexRecords(
        entities=[_entity("KU-000001")],
        relations=[_relation("youtube:v:KU-000001", "youtube:v:KU-000009")],
    )
    with pytest.raises(AdapterError, match="which no entity record has"):
        base.check_records(records)


def test_an_edge_may_not_be_anchored_to_an_artifact() -> None:
    """An artifact shares the global-id namespace with an entity but is not one:
    the repository resolves an endpoint against entity records alone."""
    records = base.IndexRecords(
        artifacts=[
            {
                "schema_version": "1.0",
                "id": "youtube:v:transcript",
                "source_id": "youtube:v",
                "kind": "transcript",
                "role": "canonical",
                "media_type": "application/json",
                "path": "output/v/transcript.json",
                "url": None,
                "bytes": None,
                "sha256": None,
                "immutable": False,
                "available": True,
            }
        ],
        entities=[_entity("KU-000001")],
        relations=[_relation("youtube:v:KU-000001", "youtube:v:transcript")],
    )
    with pytest.raises(AdapterError, match="which no entity record has"):
        base.check_records(records)


def test_the_adapter_and_the_repository_refuse_the_same_sets() -> None:
    """The one test that fails if the two spellings of the rule drift apart."""
    repository = pytest.importorskip("x2knwldg.repository.base")
    good = base.IndexRecords(
        entities=[_entity("KU-000001"), _entity("KU-000002")],
        relations=[_relation("youtube:v:KU-000001", "youtube:v:KU-000002")],
    )
    duplicate = base.IndexRecords(
        entities=[_entity("KU-000001"), _entity("KU-000001")], relations=[]
    )
    dangling = base.IndexRecords(
        entities=[_entity("KU-000001")],
        relations=[_relation("youtube:v:KU-000001", "youtube:v:KU-000009")],
    )

    repository.check_index_integrity(good.by_model())
    assert base.check_records(good) is good

    for records in (duplicate, dangling):
        with pytest.raises(repository.RepositoryError):
            repository.check_index_integrity(records.by_model())
        with pytest.raises(AdapterError):
            base.check_records(records)


def test_a_library_fragment_is_not_judged_on_endpoints_it_cannot_have(
    tmp_path: Path,
) -> None:
    """``expresses_concept`` runs from a unit the run owns to a concept the
    library owns (D-025), so the library's own set can never contain both ends.
    Uniqueness still applies to it; membership is judged over the union."""
    records = adapt_library(_library(tmp_path), tmp_path)
    assert records.relations
    with pytest.raises(AdapterError, match="which no entity record has"):
        base.check_records(records)


def test_the_union_of_runs_and_library_is_judged_on_endpoints(tmp_path: Path) -> None:
    """And the union is where the library's edges do find their far ends."""
    project = _project_with(tmp_path, "pass-run")
    _library(project)
    records = adapt_project(project)
    entities = {entity["global_id"] for entity in records.entities}
    assert {r["relation"] for r in records.relations} >= {"expresses_concept"}
    for relation in records.relations:
        assert relation["from_id"] in entities and relation["to_id"] in entities


def test_a_run_whose_units_are_damaged_but_whose_edges_are_not_is_refused(
    run: Path,
) -> None:
    """The edges outlive the units they name, and every one of them is then an
    edge to nothing. Refused here, by name — the repository would otherwise
    refuse the *whole index* at construction, naming only the symptom."""
    (run / "knowledge_units.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AdapterError, match="which no entity record has"):
        adapt_run(run, run.parents[1])


# --------------------------------------------------------------------------
# One reader, and the reason it gives is not thrown away
# --------------------------------------------------------------------------


def test_the_reader_refuses_a_constant_no_other_parser_can_read(run: Path) -> None:
    """``json`` accepts ``NaN`` and ``Infinity``; nothing else does, and a
    canonical file carrying one cannot be read back by the TypeScript client
    the API generates types for. ``io``'s reader refuses them, and the adapter
    now reads through it rather than through a fifth bare ``json.loads``."""
    (run / "coverage.json").write_text('{"status": "PASS", "x": NaN}', encoding="utf-8")
    status = adapt_run(run, run.parents[1]).sources[0]["status"]
    assert status["coverage"] == "UNKNOWN", "an unreadable file is never read as PASS"


def test_a_damaged_canonical_file_is_named_rather_than_merely_missed(run: Path) -> None:
    """The counts were already omitted rather than zeroed — but 'this count is
    absent' does not say the file is broken, and only one of the two is
    actionable. The reason ``io`` returns is reported, not discarded."""
    (run / "transcript.json").write_text("{not json", encoding="utf-8")
    source = adapt_run(run, run.parents[1]).sources[0]
    reported = source["adapter_metadata"]["unreadable_files"]
    assert [entry["path"] for entry in reported] == ["output/pass-run/transcript.json"]
    assert "Malformed JSON" in reported[0]["reason"]
    assert "captions" not in source["counts"], "and the count is still omitted"


def test_an_absent_file_is_not_reported_as_damage(run: Path) -> None:
    """A run that has not been finalized is missing files by definition. Listing
    every one of them as damage would bury the one file that is actually
    broken."""
    (run / "coverage.json").unlink()
    (run / "validation.json").unlink()
    source = adapt_run(run, run.parents[1]).sources[0]
    assert "unreadable_files" not in source["adapter_metadata"]
    assert source["status"]["coverage"] == "UNKNOWN"


def test_the_tolerant_reader_separates_absence_from_damage(tmp_path: Path) -> None:
    """The distinction at the level of the function itself."""
    absent = tmp_path / "gone.json"
    assert base.read_optional_json_or_reason(absent) == (None, None)

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    document, reason = base.read_optional_json_or_reason(broken)
    assert document is None
    assert reason and str(broken) in reason

    a_directory = tmp_path / "dir.json"
    a_directory.mkdir()
    assert base.read_optional_json_or_reason(a_directory)[1], "a directory is damage"

    good = tmp_path / "good.json"
    good.write_text('{"a": 1}', encoding="utf-8")
    assert base.read_optional_json_or_reason(good) == ({"a": 1}, None)


def test_the_package_has_one_tolerant_json_reader() -> None:
    """``read_optional_json`` is a name for ``io.read_json_or_reason``, not a
    second implementation of it: five readers of one format is five answers to
    'what is a damaged file'."""
    source = (
        PROJECT_ROOT / "src" / "x2knwldg" / "adapters" / "base.py"
    ).read_text(encoding="utf-8")
    assert "json.loads(" not in source
    assert "read_json_or_reason" in source


# ---------------------------------------------------------------------------
# D-100 — a symlinked artifact is named, not fatal to its run
# ---------------------------------------------------------------------------
#
# `Adapter.relative` resolves symlinks, so a canonical file that *is* a symlink
# to somewhere outside the project resolved outside it and raised — taking the
# whole run down over one file. Since D-078 that is a skipped-and-named run
# rather than a dead index, which is better and still wrong:
# `adapter_metadata.unmappable_artifacts` is the channel that already exists
# for a thing the index model cannot address (D-045).


@pytest.mark.parametrize(
    "where",
    ["report.md", "raw/source.srt", "vault/knowledge_units/source/KU-LINK.md"],
)
def test_a_symlinked_artifact_does_not_take_its_run_down(tmp_path: Path, where: str) -> None:
    import shutil

    from x2knwldg.adapters import adapt_run

    root = tmp_path / "project"
    run_dir = root / "output" / "pass-run"
    shutil.copytree(FIXTURE_RUNS / "pass-run", run_dir)
    outside = tmp_path / "elsewhere" / "notes.md"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("# outside the project\n", encoding="utf-8")
    target = run_dir / where
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(outside)

    records = adapt_run(run_dir, root)
    source = records.by_model()["source"][0]
    unmappable = source.get("adapter_metadata", {}).get("unmappable_artifacts", [])
    assert unmappable, f"the symlinked {where} was neither indexed nor named"
    assert any(where.rsplit("/", 1)[-1] in entry["path"] for entry in unmappable), unmappable
    # D-085: the reason reaches `/api/status`, so no host path may survive.
    blob = json.dumps(unmappable)
    for absolute in (str(outside), str(outside.parent), str(root.resolve())):
        assert absolute not in blob, f"the reason leaks {absolute}"


def test_a_symlinked_file_is_not_in_the_runs_digest(tmp_path: Path) -> None:
    """`path.is_file()` follows symlinks, so the *target* went into the digest
    and `io.sha256_file` read it in full on every scan — for a file the run does
    not own, whose changes moved the digest and whose repointing did not."""
    import shutil

    from x2knwldg.index import scanner

    root = tmp_path / "project"
    run_dir = root / "output" / "pass-run"
    shutil.copytree(FIXTURE_RUNS / "pass-run", run_dir)
    outside = tmp_path / "elsewhere" / "big.bin"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"x" * 1024)
    (run_dir / "linked.bin").symlink_to(outside)

    walked = scanner._run_files(run_dir)
    assert all(not path.is_symlink() for path in walked)
    assert not any(path.name == "linked.bin" for path in walked)
