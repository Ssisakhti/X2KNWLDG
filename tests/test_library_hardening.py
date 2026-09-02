"""Regression tests for the cumulative library, the final artifacts, and the reader.

Three properties are under test here, and all three are about honesty rather
than features:

* **A run is never dropped in silence.** ``rebuild_library`` used to require
  ``relationships.json`` before it would index a run at all, while ``adapt_run``
  indexed the same run without it. ``status.json`` then stated a ``videos``
  count with nothing to say a run had been skipped — and the ``kg_navigator``
  skill instructs agents to *trust* that graph.
* **A damaged run is visible, not fatal.** One unreadable canonical file used to
  abort the rebuild of the whole library with a raw traceback.
* **Nothing is invented.** No confidence nobody measured, no count that is not
  the number of things counted, and no artifact written from a document that has
  not been checked.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import constants
from x2knwldg import io as io_module
from x2knwldg.artifacts import (
    SECTION_ORDER,
    _check_section_order,
    _checked_relationships,
    _checked_units,
    _read,
    apply_extraction_bundle,
    finalize_run,
)
from x2knwldg.io import JsonReadError, read_json, read_json_or_reason, write_json
from x2knwldg.library import rebuild_library
from x2knwldg.pipeline import PipelineError, validate_run

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------
# Building runs
# --------------------------------------------------------------------------


def _unit(unit_id: str, **overrides: Any) -> dict[str, Any]:
    unit = {
        "id": unit_id,
        "kind": "claim",
        "source_class": "source",
        "content": f"Statement {unit_id}.",
        "confidence": 0.8,
    }
    unit.update(overrides)
    return unit


def _write_run(
    output_root: Path,
    video_id: str,
    *,
    units: list[dict[str, Any]] | None = None,
    relationships: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """A run directory holding only what this test needs it to hold.

    ``units``/``relationships`` of ``None`` means *the file is absent*, which is
    the shape a half-finished run actually has on disk.
    """
    run_dir = output_root / video_id
    run_dir.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": "1.0", "video_id": video_id, "title": f"Video {video_id}"}
    document.update(metadata or {})
    write_json(run_dir / "metadata.json", document)
    if units is not None:
        write_json(
            run_dir / "knowledge_units.json",
            {"schema_version": "1.0", "video_id": video_id, "units": units},
        )
    if relationships is not None:
        write_json(
            run_dir / "relationships.json",
            {"schema_version": "1.0", "video_id": video_id, "relationships": relationships},
        )
    return run_dir


def _graph(output_root: Path) -> dict[str, Any]:
    return json.loads((output_root / "library" / "graph.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# A run is never dropped in silence
# --------------------------------------------------------------------------


def test_a_run_without_relationships_is_still_indexed(tmp_path: Path) -> None:
    """``adapt_run`` indexes this run perfectly well; the library used to drop it.

    Two code paths for one fact, and the more tolerant one was the one nobody
    saw: the run vanished from ``graph.json``, from ``videos.json`` and from the
    ``videos`` count, with nothing anywhere to say it had been left out.
    """
    _write_run(tmp_path, "vid00000001", units=[_unit("KU-000001")], relationships=None)

    status = rebuild_library(tmp_path)

    assert status["videos"] == 1
    assert status["runs_indexed"] == 1
    assert [node["local_id"] for node in _graph(tmp_path)["nodes"]] == ["KU-000001"]


def test_a_run_without_knowledge_units_is_still_indexed(tmp_path: Path) -> None:
    """A run imported but not yet extracted is a real state, not a broken one."""
    _write_run(tmp_path, "vid00000001", units=None, relationships=None)

    status = rebuild_library(tmp_path)

    assert status["videos"] == 1
    assert status["knowledge_nodes"] == 0


def test_an_indexed_run_states_which_files_it_was_missing(tmp_path: Path) -> None:
    """Indexing a partial run silently would be the same defect, moved."""
    _write_run(tmp_path, "vid00000001", units=[_unit("KU-000001")], relationships=None)

    status = rebuild_library(tmp_path)

    assert len(status["incomplete_runs"]) == 1
    reported = " ".join(status["incomplete_runs"][0]["problems"])
    assert "relationships.json" in reported
    videos = json.loads((tmp_path / "library" / "videos.json").read_text(encoding="utf-8"))
    assert "relationships.json" in " ".join(videos["videos"][0]["problems"])


def test_status_states_what_it_found_as_well_as_what_it_indexed(tmp_path: Path) -> None:
    """``videos: 1`` beside two run directories is a claim of completeness.

    A count that omits a run without saying so is read by the next agent — and
    by ``kg_navigator`` — as the number of videos in the library.
    """
    _write_run(tmp_path, "vid00000001", units=[_unit("KU-000001")], relationships=[])
    unreadable = tmp_path / "vid00000002"
    unreadable.mkdir()
    (unreadable / "metadata.json").write_text("{not json", encoding="utf-8")

    status = rebuild_library(tmp_path)

    assert status["runs_discovered"] == 2
    assert status["runs_indexed"] == 1
    assert status["runs_skipped"] == 1
    assert status["videos"] == status["runs_indexed"]
    assert status["skipped_runs"][0]["relative_path"] == "vid00000002"
    assert "vid00000002" in status["skipped_runs"][0]["reason"]
    on_disk = json.loads((tmp_path / "library" / "status.json").read_text(encoding="utf-8"))
    assert on_disk == status, "status.json must state everything the caller was told"


def test_a_run_whose_video_id_cannot_be_addressed_is_skipped_by_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "broken"
    run_dir.mkdir()
    write_json(run_dir / "metadata.json", {"video_id": "../escape"})

    status = rebuild_library(tmp_path)

    assert status["runs_indexed"] == 0
    assert status["runs_skipped"] == 1
    assert "video_id" in status["skipped_runs"][0]["reason"]


# --------------------------------------------------------------------------
# A damaged run is visible, not fatal
# --------------------------------------------------------------------------


def test_one_damaged_run_does_not_abort_the_whole_rebuild(tmp_path: Path) -> None:
    """``library.py`` predates ``read_optional_json`` and never adopted it.

    Its sibling adapters read every canonical file tolerantly precisely so that
    "a half-finished or damaged run must still be indexable". One truncated file
    used to take the entire cumulative graph down with it.
    """
    _write_run(tmp_path, "vid00000001", units=[_unit("KU-000001")], relationships=[])
    damaged = _write_run(tmp_path, "vid00000002", units=[_unit("KU-000002")], relationships=[])
    (damaged / "knowledge_units.json").write_text('{"units": [', encoding="utf-8")

    status = rebuild_library(tmp_path)

    assert status["runs_indexed"] == 2, "the healthy run must survive its neighbour"
    assert status["knowledge_nodes"] == 1
    damage = [entry for entry in status["incomplete_runs"] if entry["video_id"] == "vid00000002"]
    assert damage, "the damage must be recorded where a reader will find it"
    assert "knowledge_units.json" in " ".join(damage[0]["problems"])


def test_a_unit_without_an_id_does_not_crash_the_rebuild(tmp_path: Path) -> None:
    """``unit["id"]`` was indexed unguarded in a module that reads unvalidated files."""
    _write_run(
        tmp_path,
        "vid00000001",
        units=[_unit("KU-000001"), {"kind": "claim", "content": "No id."}],
        relationships=[],
    )

    status = rebuild_library(tmp_path)

    assert status["knowledge_nodes"] == 1
    assert "cannot become a library id" in " ".join(status["incomplete_runs"][0]["problems"])


def test_a_relationship_naming_an_unusable_endpoint_is_reported_not_raised(
    tmp_path: Path,
) -> None:
    _write_run(
        tmp_path,
        "vid00000001",
        units=[_unit("KU-000001")],
        relationships=[{"from": "KU-000001", "to": "../escape", "relation": "supports"}],
    )

    status = rebuild_library(tmp_path)

    assert status["runs_indexed"] == 1
    assert "relationships.json" in " ".join(status["incomplete_runs"][0]["problems"])


# --------------------------------------------------------------------------
# Nothing is invented
# --------------------------------------------------------------------------


def test_an_expresses_concept_edge_carries_no_invented_confidence(tmp_path: Path) -> None:
    """D-025 forbids putting a number on a claim nothing made.

    A canonical concept is formed by grouping units on a normalised string key.
    That is a match rule, not a measurement, so there is no confidence in any
    canonical file for the edge to copy — and ``confidence: 1.0`` is the most
    confident value the field has.
    """
    concept = {"kind": "concept", "source_class": "source", "normalized_statement": "Shared idea"}
    _write_run(
        tmp_path,
        "vid00000001",
        units=[_unit("KU-000001", **concept)],
        relationships=[],
    )
    _write_run(
        tmp_path,
        "vid00000002",
        units=[_unit("KU-000002", **concept)],
        relationships=[],
    )

    rebuild_library(tmp_path)

    edges = [e for e in _graph(tmp_path)["edges"] if e["relation"] == "expresses_concept"]
    assert len(edges) == 2
    for edge in edges:
        assert edge["confidence"] is None
        assert edge["source_class"] == "derived"


def test_a_derived_from_edge_copies_the_unit_or_states_nothing(tmp_path: Path) -> None:
    """The unit's own confidence, verbatim — and ``null`` when it states none.

    The default used to be ``0``: a measurement nobody took, and the *least*
    confident value the field has.
    """
    _write_run(
        tmp_path,
        "vid00000001",
        units=[
            _unit("KU-000001"),
            _unit(
                "KU-D-0001",
                kind="synthesis",
                source_class="derived",
                derived_from=["KU-000001"],
                confidence=0.55,
            ),
            {
                "id": "KU-D-0002",
                "kind": "synthesis",
                "source_class": "derived",
                "content": "This unit states no confidence at all.",
                "derived_from": ["KU-000001"],
            },
        ],
        relationships=[],
    )

    rebuild_library(tmp_path)

    edges = {
        edge["from"]: edge["confidence"]
        for edge in _graph(tmp_path)["edges"]
        if edge["relation"] == "derived_from"
    }
    assert edges["vid00000001:KU-D-0001"] == 0.55
    assert edges["vid00000001:KU-D-0002"] is None


def test_knowledge_nodes_counts_the_nodes_it_built(tmp_path: Path) -> None:
    """The count was re-derived from the ``kind`` string after the fact.

    A unit stating ``kind: canonical_concept`` was therefore subtracted from the
    knowledge count and never added to the concept count, so the two numbers a
    human reads as facts did not add up to the graph they describe.
    """
    _write_run(
        tmp_path,
        "vid00000001",
        units=[_unit("KU-000001", kind="canonical_concept")],
        relationships=[],
    )

    status = rebuild_library(tmp_path)

    assert status["knowledge_nodes"] == 1
    assert status["canonical_concepts"] == 0
    assert status["knowledge_nodes"] + status["canonical_concepts"] == len(
        _graph(tmp_path)["nodes"]
    )


# --------------------------------------------------------------------------
# One reader, one error behaviour
# --------------------------------------------------------------------------


def test_the_single_reader_reports_a_missing_file_as_a_pipeline_error(tmp_path: Path) -> None:
    """Three readers for one job meant three failures for one damaged file."""
    with pytest.raises(PipelineError):
        _read(tmp_path / "absent.json")


def test_a_missing_bundle_is_a_pipeline_error_not_a_traceback(tmp_path: Path) -> None:
    with pytest.raises(PipelineError):
        apply_extraction_bundle(tmp_path, tmp_path / "no-such-bundle.json")


def test_the_reader_keeps_refusing_non_finite_numbers(tmp_path: Path) -> None:
    """Preserved from the earlier fix: NaN/Infinity are not portable JSON."""
    path = tmp_path / "nan.json"
    path.write_text('{"confidence": NaN}', encoding="utf-8")
    with pytest.raises(JsonReadError):
        read_json(path)
    assert isinstance(JsonReadError("x"), ValueError)


def test_the_tolerant_reader_returns_the_reason_rather_than_discarding_it(
    tmp_path: Path,
) -> None:
    document, reason = read_json_or_reason(tmp_path / "absent.json")
    assert document is None
    assert "absent.json" in reason
    write_json(tmp_path / "present.json", {"a": 1})
    assert read_json_or_reason(tmp_path / "present.json") == ({"a": 1}, None)


def test_a_failed_write_still_leaves_no_temp_file(tmp_path: Path) -> None:
    """Preserved from the earlier fix, now that write_json is layered."""
    with pytest.raises(ValueError):
        write_json(tmp_path / "out.json", {"value": float("inf")})
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------
# The kind vocabulary has one home
# --------------------------------------------------------------------------


def test_every_kind_has_a_report_section(tmp_path: Path) -> None:
    covered: set[str] = set()
    for _, kinds in SECTION_ORDER:
        covered |= kinds
    assert covered == constants.KNOWLEDGE_KINDS


def test_a_kind_with_no_section_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """"Other Knowledge" is for the unknown, not for the merely unlisted."""
    monkeypatch.setattr(
        constants, "KNOWLEDGE_KINDS", constants.KNOWLEDGE_KINDS | {"newly_added_kind"}
    )
    with pytest.raises(RuntimeError) as caught:
        _check_section_order()
    assert "newly_added_kind" in str(caught.value)


# --------------------------------------------------------------------------
# Nothing is written from a document that has not been checked
# --------------------------------------------------------------------------


@pytest.fixture()
def pass_run(tmp_path: Path) -> Path:
    """A writable copy of the committed ``pass-run`` fixture, already finalized."""
    output_root = tmp_path / "output"
    output_root.mkdir()
    run_dir = output_root / "pass-run"
    shutil.copytree(FIXTURES / "runs" / "pass-run", run_dir)
    finalize_run(run_dir)
    return run_dir


def _snapshot(run_dir: Path) -> dict[str, tuple[int, int]]:
    """Every artifact's size and modification time.

    ``validation.json`` is excluded: ``validate_run`` legitimately refreshes it
    before any refusal, which is the run's own report being kept current.
    """
    return {
        path.relative_to(run_dir).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.name != "validation.json"
    }


def test_finalize_refuses_metadata_it_cannot_print_before_writing_anything(
    pass_run: Path,
) -> None:
    """``metadata['channel']`` was subscripted after ``graph.json`` was replaced.

    ``validate_run`` reads the six canonical documents and says nothing about
    which *fields* ``metadata.json`` carries, so a run missing one validates
    ``PASS`` and then raised a bare ``KeyError`` from the middle of the write
    sequence — leaving a fresh ``graph.json`` beside the previous ``report.md``.
    """
    metadata = json.loads((pass_run / "metadata.json").read_text(encoding="utf-8"))
    del metadata["channel"]
    write_json(pass_run / "metadata.json", metadata)
    assert validate_run(pass_run)["status"] == "PASS", "the run itself is still valid"

    before = _snapshot(pass_run)
    with pytest.raises(PipelineError) as caught:
        finalize_run(pass_run)

    assert "channel" in str(caught.value)
    assert _snapshot(pass_run) == before, "a refused finalize rewrote an artifact"


def test_a_unit_missing_a_field_the_artifacts_index_is_refused() -> None:
    with pytest.raises(PipelineError) as caught:
        _checked_units([{"id": "KU-000001", "content": "x", "source_class": "source"}])
    assert "kind" in str(caught.value)


def test_a_relationship_missing_an_endpoint_is_refused() -> None:
    with pytest.raises(PipelineError) as caught:
        _checked_relationships([{"from": "KU-000001", "relation": "supports"}])
    assert "to" in str(caught.value)


# --------------------------------------------------------------------------
# The canonical files of one extraction land together, or not at all
# --------------------------------------------------------------------------


def _fail_the_nth_replace(monkeypatch: pytest.MonkeyPatch, n: int) -> None:
    """Make the *n*-th atomic file replacement fail, and only that one.

    Every writer in the package finishes with ``os.replace``, so counting them
    is how a mid-sequence failure is simulated without depending on which
    function performed the write.
    """
    calls = {"count": 0}
    real = os.replace

    def replace(source, target, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if calls["count"] == n:
            raise OSError(28, "No space left on device")
        return real(source, target, *args, **kwargs)

    monkeypatch.setattr(io_module.os, "replace", replace)


def test_a_bundle_that_fails_half_way_leaves_the_run_as_it_was(
    pass_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``apply_extraction_bundle`` replaces four files that mean nothing apart.

    Measured on the pre-fix code with the fourth write failing: the new
    ``knowledge_units.json`` was on disk beside the *previous* ``metadata.json``,
    so the run carried one extraction's units under another extraction's
    ``extraction`` provenance block and ``extracted_at`` stamp — and
    ``validate_run``, which runs immediately afterwards and reads all four
    files, reported ``PASS`` on that set, because every individual file is well
    formed. Nothing downstream could have noticed.
    """
    units = json.loads((pass_run / "knowledge_units.json").read_text(encoding="utf-8"))["units"]
    for unit in units:
        unit["confidence"] = 0.5
    bundle = {
        "knowledge_units": units,
        "relationships": json.loads(
            (pass_run / "relationships.json").read_text(encoding="utf-8")
        )["relationships"],
        "coverage": json.loads((pass_run / "coverage.json").read_text(encoding="utf-8")),
        "extraction_metadata": {"model": "a second extraction"},
    }
    bundle_path = pass_run.parent / "bundle.json"
    write_json(bundle_path, bundle)
    canonical = ["knowledge_units.json", "relationships.json", "coverage.json", "metadata.json"]
    before = {name: (pass_run / name).read_bytes() for name in canonical}

    _fail_the_nth_replace(monkeypatch, 4)
    with pytest.raises(OSError):
        apply_extraction_bundle(pass_run, bundle_path)

    after = {name: (pass_run / name).read_bytes() for name in canonical}
    assert after == before, "a half-applied bundle would be validated as though whole"
    assert validate_run(pass_run)["status"] == "PASS"
