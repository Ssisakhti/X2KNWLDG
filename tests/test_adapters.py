"""Behaviour tests for the source adapters (T-004).

``tests/test_index_schemas.py`` asks whether the adapter's records satisfy the
v1 model. This module asks the questions the schemas cannot: what the adapter
refuses, what it leaves out, and what it must never supply on the canonical
data's behalf.

It imports no ``jsonschema``, because the adapters are stdlib-only and must keep
working on a bare core install (ADR 0001 invariant 5).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from x2knwldg import ids
from x2knwldg.adapters import (
    ADAPTERS,
    AdapterError,
    YouTubeAdapter,
    adapt_library,
    adapt_project,
    adapt_run,
    get_adapter,
    media_type_for,
    project_relative,
    read_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
SAMPLE_DIR = PROJECT_ROOT / "output" / "pqlWNihgdjI"
LIBRARY_DIR = PROJECT_ROOT / "output" / "library"

requires_library = pytest.mark.skipif(
    not (LIBRARY_DIR / "concepts.json").exists(),
    reason="output/library/ is built by finalize_run and only the real sample has it",
)


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """A writable copy of ``pass-run``, rooted in its own project root.

    Mutating a canonical file is how several of these rules are provoked, and
    the committed fixtures are evidence: they are never edited in place.
    """
    destination = tmp_path / "output" / "pass-run"
    shutil.copytree(FIXTURE_RUNS / "pass-run", destination)
    return destination


def _edit(path: Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# The registry and the contract
# --------------------------------------------------------------------------


def test_youtube_is_registered() -> None:
    assert ADAPTERS["youtube"] is YouTubeAdapter
    assert isinstance(get_adapter("youtube", PROJECT_ROOT), YouTubeAdapter)


def test_unknown_source_type_is_refused_by_name() -> None:
    with pytest.raises(AdapterError) as excinfo:
        get_adapter("tiktok", PROJECT_ROOT)
    assert "tiktok" in str(excinfo.value)
    assert "youtube" in str(excinfo.value), "the refusal should say what is registered"


def test_adapter_ref_names_the_code_that_wrote_the_record(run: Path) -> None:
    """A stale record has to be traceable back to its producer."""
    source = adapt_run(run, run.parents[1]).sources[0]
    assert source["adapter"] == {"name": "youtube", "version": YouTubeAdapter.version}


def test_detect_distinguishes_a_run_from_a_directory(tmp_path: Path, run: Path) -> None:
    adapter = YouTubeAdapter(run.parents[1])
    assert adapter.detect(run)
    assert not adapter.detect(tmp_path)


def test_a_foreign_source_type_is_refused_rather_than_mapped(run: Path) -> None:
    _edit(run / "metadata.json", lambda doc: doc.update(source_type="medium"))
    adapter = YouTubeAdapter(run.parents[1])
    assert not adapter.detect(run)
    with pytest.raises(AdapterError, match="medium"):
        adapter.adapt_run(run)


def test_a_run_without_metadata_is_not_a_run(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="metadata.json"):
        adapt_run(tmp_path, tmp_path)


def test_mapping_is_deterministic(run: Path) -> None:
    """Rebuild-equivalence (T-104) starts here: same input, same records."""
    first = adapt_run(run, run.parents[1]).by_model()
    second = adapt_run(run, run.parents[1]).by_model()
    assert first == second


def test_mapping_does_not_touch_the_run(run: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in sorted(run.rglob("*")) if p.is_file()}
    adapt_run(run, run.parents[1])
    after = {p: p.stat().st_mtime_ns for p in sorted(run.rglob("*")) if p.is_file()}
    assert before == after


# --------------------------------------------------------------------------
# Status is copied, never computed (ADR 0001 invariant 2)
# --------------------------------------------------------------------------


def test_a_missing_validator_file_is_unknown_not_pass(run: Path) -> None:
    (run / "validation.json").unlink()
    status = adapt_run(run, run.parents[1]).sources[0]["status"]
    assert status["validation"] == "UNKNOWN"
    assert status["overall"] == "UNKNOWN"
    assert status["validation_path"] is None
    assert status["coverage"] == "PASS", "the file that is present is still read"


def test_an_unrecognised_status_is_unknown_not_pass(run: Path) -> None:
    _edit(run / "validation.json", lambda doc: doc.update(status="OK"))
    status = adapt_run(run, run.parents[1]).sources[0]["status"]
    assert status["overall"] == "UNKNOWN"


def test_an_unreadable_validator_file_is_unknown(run: Path) -> None:
    (run / "coverage.json").write_text("{not json", encoding="utf-8")
    status = adapt_run(run, run.parents[1]).sources[0]["status"]
    assert status["coverage"] == "UNKNOWN"
    assert status["coverage_path"] is None
    assert status["audit_attempts"] is None


@pytest.mark.parametrize("stated", ["PARTIAL", "FAIL"])
def test_a_bad_status_is_never_coerced_upward(run: Path, stated: str) -> None:
    _edit(run / "validation.json", lambda doc: doc.update(status=stated))
    assert adapt_run(run, run.parents[1]).sources[0]["status"]["overall"] == stated


def test_read_status_has_no_path_to_pass() -> None:
    """The one function every status flows through, checked directly."""
    assert read_status(None) == "UNKNOWN"
    assert read_status({}) == "UNKNOWN"
    assert read_status({"status": "pass"}) == "UNKNOWN", "the vocabulary is exact"
    assert read_status({"status": "FAIL"}) == "FAIL"


def test_counts_are_omitted_rather_than_zeroed_when_unknown(run: Path) -> None:
    """Reporting 0 captions for an unreadable file states something false."""
    (run / "transcript.json").write_text("{not json", encoding="utf-8")
    counts = adapt_run(run, run.parents[1]).sources[0]["counts"]
    assert "captions" not in counts
    assert counts["relationships"] == 1, "the files that are readable are still counted"
    assert counts["knowledge_units"] == 2


# --------------------------------------------------------------------------
# Paths (risk R15)
# --------------------------------------------------------------------------


def test_no_record_carries_an_absolute_path(run: Path) -> None:
    records = adapt_run(run, run.parents[1])
    paths = [
        value
        for record in [*records.sources, *records.artifacts, *records.entities, *records.relations]
        for key, value in record.items()
        if key.endswith(("path", "_dir")) and isinstance(value, str)
    ]
    assert paths
    for path in paths:
        assert not path.startswith("/"), path
        assert ".." not in path.split("/"), path


def test_a_run_outside_the_project_root_is_refused(run: Path, tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="outside the project root"):
        adapt_run(run, tmp_path / "elsewhere")


def test_project_relative_refuses_an_escape(tmp_path: Path) -> None:
    with pytest.raises(AdapterError):
        project_relative(Path("/etc/passwd"), tmp_path)


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------


def test_the_raw_source_extension_is_discovered_not_assumed(run: Path) -> None:
    """pipeline.py:203 names the file after the imported transcript, so the
    extension varies by run and cannot be hard-coded."""
    artifacts = {a["id"]: a for a in adapt_run(run, run.parents[1]).artifacts}
    raw = artifacts["youtube:fixture-pass:raw_source"]
    assert raw["path"].endswith("raw/source.srt")
    assert raw["available"] is True
    assert raw["immutable"] is True, "everything under raw/ is evidence"


def test_an_absent_raw_source_is_omitted_rather_than_guessed(run: Path) -> None:
    for path in (run / "raw").glob("source.*"):
        path.unlink()
    kinds = {a["kind"] for a in adapt_run(run, run.parents[1]).artifacts}
    assert "raw_source" not in kinds


def test_two_raw_sources_are_ambiguous_and_refused(run: Path) -> None:
    (run / "raw" / "source.vtt").write_text("WEBVTT\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="exactly one"):
        adapt_run(run, run.parents[1])


def test_a_missing_canonical_file_is_reported_missing_not_hidden(run: Path) -> None:
    (run / "report.md").unlink()
    report = next(a for a in adapt_run(run, run.parents[1]).artifacts if a["kind"] == "report")
    assert report["available"] is False
    assert report["bytes"] is None
    assert report["path"].endswith("report.md"), "the path is still known"


def test_the_video_has_a_url_and_no_local_file(run: Path) -> None:
    """T-114: the UI must never assume a local media file exists."""
    video = next(a for a in adapt_run(run, run.parents[1]).artifacts if a["kind"] == "video")
    assert video["role"] == "external"
    assert video["path"] is None
    assert video["url"].startswith("https://")


def test_media_type_is_stated_only_when_registered() -> None:
    assert media_type_for(Path("a/transcript.json")) == "application/json"
    assert media_type_for(Path("a/report.md")) == "text/markdown"
    # SubRip has no registered IANA type, so the honest answer is nothing.
    assert media_type_for(Path("a/source.srt")) is None


def test_artifacts_are_not_hashed_unless_asked(run: Path) -> None:
    """Hashing every file of every run is the incremental indexer's cost to
    pay (T-102), not a status lookup's."""
    plain = adapt_run(run, run.parents[1]).artifacts
    assert all(a["sha256"] is None for a in plain)

    hashed = adapt_run(run, run.parents[1], hash_artifacts=True).artifacts
    digests = [a["sha256"] for a in hashed if a["available"] and a["path"]]
    assert digests and all(d is not None and len(d) == 64 for d in digests)


def test_the_vault_export_is_mapped_as_export_not_canonical(run: Path) -> None:
    notes = [a for a in adapt_run(run, run.parents[1]).artifacts if a["kind"] == "vault_note"]
    assert notes
    for note in notes:
        assert note["role"] == "export"
        assert note["immutable"] is False
        assert note["media_type"] == "text/markdown"
    assert len({note["id"] for note in notes}) == len(notes)


# --------------------------------------------------------------------------
# Identifiers (D-011, risk R12)
# --------------------------------------------------------------------------


def test_every_id_round_trips_through_the_id_module(run: Path) -> None:
    records = adapt_run(run, run.parents[1])
    for entity in records.entities:
        global_id = ids.parse_global_id(entity["global_id"])
        assert global_id.value == entity["global_id"]
        if entity["library_id"] is not None:
            assert ids.library_id_from_global_id(global_id) == entity["library_id"]
            assert ids.global_id_from_library_id(entity["library_id"]).value == global_id.value


def test_the_library_id_keeps_its_two_part_form(run: Path) -> None:
    """D-011 is additive. Emitting a three-part id here would break the
    kg_navigator skill, which addresses nodes by the two-part form."""
    units = [e for e in adapt_run(run, run.parents[1]).entities if e["entity_type"] == "knowledge_unit"]
    assert units
    for unit in units:
        assert unit["library_id"].count(":") == 1
        assert unit["global_id"].count(":") == 2


def test_an_unusable_unit_id_is_refused(run: Path) -> None:
    """D-018: a canonical id must be usable as one segment of a global id."""
    def break_id(document):
        document["units"][0]["id"] = "../escape"

    _edit(run / "knowledge_units.json", break_id)
    with pytest.raises(AdapterError, match="knowledge unit"):
        adapt_run(run, run.parents[1])


def test_two_records_may_not_claim_one_address(run: Path) -> None:
    """A knowledge unit named after an artifact would collide with it."""
    def rename(document):
        document["units"][0]["id"] = "transcript"

    _edit(run / "knowledge_units.json", rename)
    with pytest.raises(AdapterError, match="global id"):
        adapt_run(run, run.parents[1])


# --------------------------------------------------------------------------
# Locators (invariant 3)
# --------------------------------------------------------------------------


def test_a_locator_addresses_the_segments_artifact(run: Path) -> None:
    """validators.py:166 resolves segment_id against segments.json and requires
    the excerpt to be in that segment's text, so the evidence sits there and
    not in the transcript."""
    unit = next(
        e
        for e in adapt_run(run, run.parents[1]).entities
        if e["provenance_class"] == "source"
    )
    locator = unit["locator"]
    assert locator["type"] == "time_range"
    assert locator["artifact_id"] == "youtube:fixture-pass:segments"
    assert locator["end_sec"] >= locator["start_sec"]
    assert locator["excerpt"]


def test_an_inverted_time_range_is_refused(run: Path) -> None:
    # A plain swap, so the range is inverted and both ends stay inside the
    # bounds a timestamp has: this is invariant 3 under test, not the
    # separate refusal of a negative second (tests/test_adapters_hardening.py).
    def invert(document):
        source = document["units"][0]["source"]
        source["start_sec"], source["end_sec"] = source["end_sec"], source["start_sec"]

    _edit(run / "knowledge_units.json", invert)
    with pytest.raises(AdapterError, match="before it starts"):
        adapt_run(run, run.parents[1])


def test_evidence_attributed_elsewhere_is_left_unaddressed(run: Path) -> None:
    """A unit whose provenance names another video is a canonical error
    (validators.py:163). The run is still indexed and still shown honestly, but
    the locator is not pointed at an artifact that does not hold the evidence."""
    def reattribute(document):
        document["units"][0]["source"]["video_id"] = "some-other-video"

    _edit(run / "knowledge_units.json", reattribute)
    unit = next(
        e
        for e in adapt_run(run, run.parents[1]).entities
        if e["provenance_class"] == "source"
    )
    assert "artifact_id" not in unit["locator"]
    assert unit["locator"]["start_sec"] is not None


def test_a_source_unit_without_provenance_is_refused(run: Path) -> None:
    def strip(document):
        document["units"][0].pop("source")

    _edit(run / "knowledge_units.json", strip)
    with pytest.raises(AdapterError, match="no source block"):
        adapt_run(run, run.parents[1])


# --------------------------------------------------------------------------
# Relations — three vocabularies, kept apart
# --------------------------------------------------------------------------


def test_canonical_and_synthetic_edges_stay_distinguishable(run: Path) -> None:
    relations = adapt_run(run, run.parents[1]).relations
    vocabularies = {r["relation_vocabulary"] for r in relations}
    assert vocabularies == {"canonical", "library_synthetic"}
    for relation in relations:
        if relation["relation_vocabulary"] == "library_synthetic":
            assert relation["relation"] == "derived_from"
            assert relation["provenance_class"] == "derived"
        else:
            assert relation["confidence"] is not None
            assert relation["canonical_path"].endswith("relationships.json")


def test_a_derived_from_edge_carries_no_invented_confidence(run: Path) -> None:
    """The unit's confidence is about the unit. No confidence about the edge
    exists in the canonical data, so the edge does not get one."""
    edge = next(
        r for r in adapt_run(run, run.parents[1]).relations if r["relation"] == "derived_from"
    )
    assert edge["confidence"] is None


def test_edge_ids_are_deterministic_and_address_both_ends_globally(run: Path) -> None:
    for relation in adapt_run(run, run.parents[1]).relations:
        assert relation["id"] == f"{relation['from_id']}|{relation['relation']}|{relation['to_id']}"
        assert ids.is_global_id(relation["from_id"])
        assert ids.is_global_id(relation["to_id"])


# --------------------------------------------------------------------------
# The cross-source library
# --------------------------------------------------------------------------


def test_an_absent_library_is_an_absence_not_an_error(tmp_path: Path) -> None:
    records = adapt_library(tmp_path / "output" / "library", tmp_path)
    assert records.by_model() == {
        "source": [],
        "artifact": [],
        "entity_ref": [],
        "indexed_relation": [],
    }


@requires_library
def test_the_library_emits_no_source_record() -> None:
    """output/library/ is a cross-source index, not an ingested source, and
    inventing a Source for it would give every concept an owner it has not got."""
    assert not adapt_library(LIBRARY_DIR, PROJECT_ROOT).sources


@requires_library
def test_the_library_contributes_only_expresses_concept_edges() -> None:
    """derived_from edges belong to the run that owns them, so taking them from
    the library too would double-count every one of them."""
    relations = adapt_library(LIBRARY_DIR, PROJECT_ROOT).relations
    assert relations
    assert {r["relation"] for r in relations} == {"expresses_concept"}
    for relation in relations:
        assert relation["source_id"] is None, "a concept edge is cross-source"


@requires_library
def test_the_library_never_reads_the_absolute_path_fields() -> None:
    """status.json and videos.json hold absolute host paths (risk R15); the
    library mapping must not need them at all."""
    records = adapt_library(LIBRARY_DIR, PROJECT_ROOT)
    for record in [*records.entities, *records.relations]:
        for key, value in record.items():
            if key.endswith("path") and isinstance(value, str):
                assert not value.startswith("/")


@requires_library
def test_a_concept_is_addressed_in_both_vocabularies() -> None:
    concept = adapt_library(LIBRARY_DIR, PROJECT_ROOT).entities[0]
    assert concept["global_id"] == ids.global_id_from_library_id(concept["library_id"]).value
    assert ids.library_id_from_global_id(concept["global_id"]) == concept["library_id"]


# --------------------------------------------------------------------------
# The whole project
# --------------------------------------------------------------------------


def test_adapt_project_maps_every_run_and_skips_the_library(tmp_path: Path) -> None:
    output = tmp_path / "output"
    for name in ("pass-run", "fail-run"):
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    # A library directory beside them must be read as the library, never as a
    # source that happens to be called 'library'.
    (output / "library").mkdir()
    (output / "library" / "graph.json").write_text('{"nodes": [], "edges": []}', encoding="utf-8")
    (output / "library" / "concepts.json").write_text('{"concepts": []}', encoding="utf-8")

    records = adapt_project(tmp_path)
    assert sorted(source["external_id"] for source in records.sources) == [
        "fixture-fail",
        "fixture-pass",
    ]
    assert {source["status"]["overall"] for source in records.sources} == {"PASS", "FAIL"}
