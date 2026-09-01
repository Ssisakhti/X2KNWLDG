"""The incremental scanner (``T-102``): what it stores, and what it refuses.

Three properties are under test, and every one of them is about honesty rather
than speed:

* **The cheap path skips work, never reporting.** A refresh that re-adapts
  nothing still says how many runs it discovered, how many it carried over, and
  what was wrong with the ones it could not index. A count that omits a run
  without saying so is the defect ``rebuild_library`` was reworked to close
  (D-043), and it is just as available to an incremental indexer.
* **Nothing is committed that cannot be drawn.** A duplicate ``video_id`` across
  two run directories, and a library graph left naming a run that has been
  deleted, are both refused — the first for the whole scan, the second by
  dropping the stale fragment and naming it.
* **The canonical files are never written.** The index is a rebuildable cache
  (ADR 0001 invariant 3), so a build that touched a byte or an mtime under
  ``output/`` would have made the evidence depend on the cache.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pytest

from x2knwldg.adapters import AdapterError, adapt_project
from x2knwldg.index import scanner, schema
from x2knwldg.index.errors import IndexCorrupt
from x2knwldg.library import rebuild_library
from x2knwldg.repository import check_index_integrity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
ALL_FIXTURES = ("pass-run", "partial-run", "fail-run")

#: What the three committed fixtures come to, with ``library/`` rebuilt over
#: them. The seventh entity is the one canonical concept, which belongs to no
#: source (D-016), and three of the nine relations are its ``expresses_concept``
#: edges.
ORACLE = {"sources": 3, "artifacts": 54, "entities": 7, "relations": 9}

#: The same three fixtures with no ``library/`` at all: a project that has never
#: been finalized has no cross-source projection, which is an absence and not an
#: error.
ORACLE_WITHOUT_LIBRARY = {"sources": 3, "artifacts": 54, "entities": 6, "relations": 6}


# --------------------------------------------------------------------------
# Building test projects
# --------------------------------------------------------------------------


def _project(tmp_path: Path, *names: str, library: bool = True) -> Path:
    """A writable project root holding copies of the named fixtures.

    The committed fixtures are evidence and are never edited in place, so every
    test that mutates a canonical file mutates its own copy. Note that a
    fixture's directory name deliberately differs from the ``video_id`` inside
    it — ``pass-run/`` declares ``fixture-pass`` — so nothing here may assume
    the two match.
    """
    output = tmp_path / "output"
    for name in names or ALL_FIXTURES:
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    if library:
        rebuild_library(output)
    return tmp_path


def _edit(path: Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def _rows(root: Path, table: str, columns: str = "*") -> list[sqlite3.Row]:
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        return connection.execute(f"SELECT {columns} FROM {table}").fetchall()
    finally:
        connection.close()


def _stored_records(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Every record the index actually committed, by model.

    Read back out of the ``doc`` column rather than out of the report, because
    the report is a claim about the index and this is the index.
    """
    return {
        model: [json.loads(row["doc"]) for row in _rows(root, table, "doc")]
        for model, table in scanner.MODELS
    }


def _state(root: Path) -> tuple[str, str | None, str | None]:
    rows = _rows(root, "index_state")
    assert len(rows) == 1, "index_state holds exactly one row"
    return rows[0]["state"], rows[0]["built_at"], rows[0]["message"]


def _counting_adapt(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which run directories ``adapt_run`` is actually called for."""
    called: list[str] = []
    original = scanner.adapt_run

    def adapt_run(run_dir: Path, project_root: Path, **kwargs: Any):
        called.append(Path(run_dir).name)
        return original(run_dir, project_root, **kwargs)

    monkeypatch.setattr(scanner, "adapt_run", adapt_run)
    return called


def _fingerprint_of(paths: Iterable[Path]) -> dict[str, tuple[int, str]]:
    """``(mtime_ns, sha256)`` per file — the evidence a scan must not disturb."""
    return {
        str(path): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(paths)
        if path.is_file()
    }


# --------------------------------------------------------------------------
# A full build
# --------------------------------------------------------------------------


def test_a_full_build_populates_all_four_record_families(tmp_path: Path) -> None:
    report = scanner.build_index(_project(tmp_path))

    assert report.counts == ORACLE
    assert dict(report.payload()["counts"]) == ORACLE
    assert (report.runs_discovered, report.runs_indexed, report.runs_reindexed) == (3, 3, 3)
    assert (report.runs_skipped, report.runs_unchanged, report.runs_evicted) == (0, 0, 0)
    assert report.skipped_runs == () and report.incomplete_runs == ()

    stored = _stored_records(tmp_path)
    assert {model: len(records) for model, records in stored.items()} == {
        "source": 3,
        "artifact": 54,
        "entity_ref": 7,
        "indexed_relation": 9,
    }
    # The seventh entity is the cross-source concept, and it has no owner.
    assert sum(1 for entity in stored["entity_ref"] if entity["source_id"] is None) == 1
    assert sum(1 for relation in stored["indexed_relation"] if relation["source_id"] is None) == 3


def test_a_full_build_stores_each_record_verbatim(tmp_path: Path) -> None:
    """``doc`` round-trips; the extracted columns only narrow candidates."""
    root = _project(tmp_path)
    scanner.build_index(root)

    expected = {source["id"]: source for source in adapt_project(root).sources}
    for row in _rows(root, "sources"):
        source = json.loads(row["doc"])
        assert source == expected[row["identity"]], "a stored record is not the adapted one"
        assert row["source_type"] == source["source_type"]
        assert row["status_overall"] == source["status"]["overall"]
    # And the statuses are the ones the validator files state, never recomputed:
    # `fail-run` is the fixture whose files all look finished (ADR 0001 inv. 2).
    assert {row["status_overall"] for row in _rows(root, "sources")} == {
        "PASS",
        "PARTIAL",
        "FAIL",
    }


def test_a_build_reports_the_schema_version_and_a_real_build_time(tmp_path: Path) -> None:
    report = scanner.build_index(_project(tmp_path, "pass-run", library=False))

    assert report.index_version == schema.SCHEMA_VERSION
    assert report.built_at is not None
    assert datetime.fromisoformat(report.built_at).tzinfo is not None, "built_at needs an offset"
    state, built_at, message = _state(tmp_path)
    assert (state, built_at, message) == ("ready", report.built_at, None)


def test_a_project_with_no_library_indexes_the_runs_and_nothing_else(tmp_path: Path) -> None:
    """An unfinalized project has no cross-source projection. That is an absence."""
    report = scanner.build_index(_project(tmp_path, *ALL_FIXTURES, library=False))

    assert report.counts == ORACLE_WITHOUT_LIBRARY
    assert report.skipped_runs == ()
    assert report.library_skipped_reason is None


def test_the_walk_is_the_one_adapt_project_makes_incremental(tmp_path: Path) -> None:
    output = tmp_path / "output"
    for name in ALL_FIXTURES:
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    rebuild_library(output)
    # Neither of these is an ingested run: one is the cross-source projection,
    # the other is hidden.
    shutil.copytree(FIXTURE_RUNS / "pass-run", output / ".hidden-run")

    assert [path.name for path in scanner.run_dirs(output)] == sorted(ALL_FIXTURES)


# --------------------------------------------------------------------------
# Change detection
# --------------------------------------------------------------------------


def test_a_refresh_with_nothing_changed_re_adapts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    scanner.build_index(root)

    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert called == [], "an unchanged run was re-adapted"
    assert (report.runs_discovered, report.runs_unchanged, report.runs_reindexed) == (3, 3, 0)
    assert report.runs_evicted == 0 and report.runs_skipped == 0
    assert report.library_reindexed is False, "the library was re-derived for nothing"
    assert report.counts == ORACLE, "carrying records over changed the index"


def test_touching_one_runs_knowledge_units_reindexes_exactly_that_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    scanner.build_index(root)
    before = _stored_records(root)

    def restate(document: dict) -> None:
        # A re-extraction rewrites the units. Restating one is enough, and it
        # keeps the run internally consistent: dropping a unit would leave
        # `relationships.json` naming it, and `adapt_run` rightly refuses that.
        document["units"][0]["normalized_statement"] = "Restated by a second extraction."

    _edit(root / "output" / "partial-run" / "knowledge_units.json", restate)
    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert called == ["partial-run"], "a re-run rewrote one file and the scan re-read others"
    assert (report.runs_indexed, report.runs_unchanged, report.runs_reindexed) == (3, 2, 1)
    # The library is a projection over every run, so a changed run re-derives it.
    assert report.library_reindexed is True
    after = _stored_records(root)
    assert len(after["entity_ref"]) == len(before["entity_ref"]) and len(after["source"]) == 3
    labels = {entity["label"] for entity in after["entity_ref"]}
    assert "Restated by a second extraction." in labels, "the re-extraction was not stored"
    assert labels - {entity["label"] for entity in before["entity_ref"]}


def test_a_file_whose_mtime_moved_but_whose_bytes_did_not_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mtime is the prefilter; the hash is the answer (canvas §13.1)."""
    root = _project(tmp_path)
    scanner.build_index(root)

    target = root / "output" / "pass-run" / "segments.json"
    stat = target.stat()
    target.touch()
    import os

    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
    assert target.stat().st_mtime_ns != stat.st_mtime_ns

    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert called == [], "a touched file with identical bytes was treated as a re-run"
    assert report.runs_unchanged == 3
    # And the row now carries the new fingerprint, so the *next* scan is cheap
    # again rather than hashing the whole run for ever.
    digests = {row["canonical_dir"]: row["digest"] for row in _rows(root, "runs")}
    scanner.refresh_index(root)
    assert {row["canonical_dir"]: row["digest"] for row in _rows(root, "runs")} == digests


def test_a_new_run_appearing_is_indexed_without_re_adapting_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "pass-run", "partial-run", library=False)
    scanner.build_index(root)

    shutil.copytree(FIXTURE_RUNS / "fail-run", root / "output" / "fail-run")
    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert called == ["fail-run"]
    assert (report.runs_discovered, report.runs_indexed, report.runs_unchanged) == (3, 3, 2)
    assert report.counts == ORACLE_WITHOUT_LIBRARY


def test_a_deleted_vault_note_is_noticed(tmp_path: Path) -> None:
    """The digest covers the subtree, not the canonical JSONs.

    A vault note is an artifact record. Digesting ``metadata.json`` alone would
    call this run unchanged and leave a record for a file that has gone.
    """
    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root)
    notes = sorted((root / "output" / "pass-run" / "vault").rglob("*.md"))
    assert notes, "the fixture is expected to carry an Obsidian export"

    notes[0].unlink()
    report = scanner.refresh_index(root)

    assert report.runs_reindexed == 1 and report.runs_unchanged == 0
    paths = {artifact["path"] for artifact in _stored_records(root)["artifact"]}
    assert str(notes[0].relative_to(root)) not in paths


# --------------------------------------------------------------------------
# Eviction
# --------------------------------------------------------------------------


def test_deleting_a_run_evicts_its_records_from_every_table(tmp_path: Path) -> None:
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    scanner.build_index(root)
    gone = "youtube:fixture-fail"

    shutil.rmtree(root / "output" / "fail-run")
    report = scanner.refresh_index(root)

    assert (report.runs_discovered, report.runs_indexed, report.runs_evicted) == (2, 2, 1)
    assert report.runs_unchanged == 2, "the surviving runs were re-adapted for nothing"
    stored = _stored_records(root)
    assert [source["id"] for source in stored["source"]] == [
        "youtube:fixture-partial",
        "youtube:fixture-pass",
    ]
    for model in ("artifact", "entity_ref", "indexed_relation"):
        assert not [
            record for record in stored[model] if record.get("source_id") == gone
        ], f"an evicted run left {model} records behind"
    # `output/library` keeps a row of its own so that a `rebuild_library` which
    # changed no run is still noticed; it is not a run and is not discovered as
    # one.
    assert sorted(row["canonical_dir"] for row in _rows(root, "runs")) == [
        "output/library",
        "output/partial-run",
        "output/pass-run",
    ]


def test_deleting_a_run_drops_the_stale_library_fragment_by_name(tmp_path: Path) -> None:
    """``library/graph.json`` is rebuilt by the pipeline, not by the scanner.

    So the moment a run directory goes, the library's ``expresses_concept`` edges
    name knowledge units nothing carries. ``adapt_project`` refuses the whole
    project in that state; the index drops the one stale projection instead, and
    says so — every surviving run stays fully indexed.
    """
    root = _project(tmp_path)
    scanner.build_index(root)

    shutil.rmtree(root / "output" / "pass-run")
    report = scanner.refresh_index(root)

    # (a) the surviving runs are still indexed, in full
    assert (report.runs_discovered, report.runs_indexed, report.runs_skipped) == (2, 2, 0)
    assert report.counts["sources"] == 2 and report.counts["artifacts"] > 0

    # (b) the library fragment is reported skipped, naming the dangling endpoint
    reason = report.library_skipped_reason
    assert reason is not None
    assert "youtube:fixture-pass:KU-000001" in reason
    assert "rebuild_library" in reason
    assert report.skipped_runs[-1] == {"relative_path": "output/library", "reason": reason}

    # (c) what was committed can be paged and drawn
    stored = _stored_records(root)
    check_index_integrity(stored)
    assert not [record for record in stored["indexed_relation"] if record["source_id"] is None]
    assert not [record for record in stored["entity_ref"] if record["source_id"] is None]

    # And the same project with its library rebuilt indexes the fragment again.
    rebuild_library(root / "output")
    again = scanner.refresh_index(root)
    assert again.library_skipped_reason is None
    assert again.counts["entities"] == 5 and again.counts["relations"] == 6
    assert again.library_reindexed is True, "a rebuilt library that changed no run was missed"


def test_a_dangling_library_edge_is_never_quietly_filtered_out(tmp_path: Path) -> None:
    """The fragment is dropped whole, so no concept is left expressed by nothing."""
    root = _project(tmp_path)
    scanner.build_index(root)
    shutil.rmtree(root / "output" / "pass-run")
    scanner.refresh_index(root)

    stored = _stored_records(root)
    concepts = [entity for entity in stored["entity_ref"] if entity["kind"] == "canonical_concept"]
    edges = [
        relation
        for relation in stored["indexed_relation"]
        if relation["relation"] == "expresses_concept"
    ]
    assert concepts == [] and edges == [], "a thinner library graph was committed unreported"


# --------------------------------------------------------------------------
# Damage — two tiers, following D-043
# --------------------------------------------------------------------------


def test_a_run_with_a_corrupt_metadata_is_skipped_and_named(tmp_path: Path) -> None:
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    (root / "output" / "fail-run" / "metadata.json").write_text("{not json", encoding="utf-8")

    report = scanner.build_index(root)

    assert (report.runs_discovered, report.runs_indexed, report.runs_skipped) == (3, 2, 1)
    assert [entry["relative_path"] for entry in report.skipped_runs] == ["output/fail-run"]
    assert report.skipped_runs[0]["reason"], "a run was skipped with no reason given"
    # The other runs are unaffected: one broken run costs its own records only.
    assert report.counts["sources"] == 2
    assert {source["external_id"] for source in _stored_records(root)["source"]} == {
        "fixture-pass",
        "fixture-partial",
    }
    # And the skip is remembered, so the next scan re-reports it rather than
    # quietly dropping a run it did not have to look at.
    row = {r["canonical_dir"]: r for r in _rows(root, "runs")}["output/fail-run"]
    assert row["skipped_reason"] and row["source_id"] is None


def test_a_skipped_run_is_still_named_by_a_later_cheap_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    (root / "output" / "fail-run" / "metadata.json").write_text("{not json", encoding="utf-8")
    first = scanner.build_index(root)

    called = _counting_adapt(monkeypatch)
    second = scanner.refresh_index(root)

    assert called == [], "an unchanged run was re-adapted to rediscover a known problem"
    assert second.runs_skipped == 1
    assert second.skipped_runs == first.skipped_runs
    assert second.runs_indexed == 2 and second.runs_unchanged == 2


def test_a_run_that_becomes_unindexable_loses_its_records_and_is_named(tmp_path: Path) -> None:
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    scanner.build_index(root)

    (root / "output" / "pass-run" / "metadata.json").write_text("", encoding="utf-8")
    report = scanner.refresh_index(root)

    assert report.runs_skipped == 1 and report.runs_indexed == 2
    assert [entry["relative_path"] for entry in report.skipped_runs] == ["output/pass-run"]
    surviving = {source["external_id"] for source in _stored_records(root)["source"]}
    assert surviving == {"fixture-partial", "fixture-fail"}


def test_a_run_indexed_with_a_gap_is_reported_incomplete(tmp_path: Path) -> None:
    """Tier two: indexed, and every gap named rather than counted as zero."""
    root = _project(tmp_path, "pass-run", library=False)
    run = root / "output" / "pass-run"
    # One canonical file that is there and cannot be read, and one vault note
    # whose filename cannot spell an id. They are the two keys
    # `adapter_metadata` may carry, and neither is allowed to vanish quietly.
    (run / "coverage.json").write_text("{truncated", encoding="utf-8")
    (run / "vault" / "not an id.md").write_text("# unaddressable\n", encoding="utf-8")

    report = scanner.build_index(root)

    assert report.runs_indexed == 1 and report.runs_skipped == 0
    assert len(report.incomplete_runs) == 1
    entry = report.incomplete_runs[0]
    assert entry["relative_path"] == "output/pass-run"
    assert entry["source_id"] == "youtube:fixture-pass"
    assert any("coverage.json" in problem for problem in entry["problems"])
    assert any("not an id.md" in problem for problem in entry["problems"])
    # An unreadable validator file is UNKNOWN, never PASS (ADR 0001 inv. 2).
    source = _stored_records(root)["source"][0]
    assert source["status"]["coverage"] == "UNKNOWN"
    assert source["status"]["audit_attempts"] is None
    assert report.payload()["incomplete_runs"][0]["problems"] == list(entry["problems"])
    # Remembered, so a cheap refresh re-reports it rather than rediscovering it.
    assert scanner.refresh_index(root).incomplete_runs == report.incomplete_runs


def test_a_damaged_library_is_skipped_rather_than_indexed_as_zero_concepts(
    tmp_path: Path,
) -> None:
    """``adapt_library`` reports damage and absence identically. This does not."""
    root = _project(tmp_path)
    (root / "output" / "library" / "concepts.json").write_text("{truncated", encoding="utf-8")

    report = scanner.build_index(root)

    assert report.runs_indexed == 3, "one damaged library cost a run its records"
    assert report.library_skipped_reason is not None
    assert "concepts.json" in report.library_skipped_reason
    assert report.skipped_runs[-1]["relative_path"] == "output/library"
    assert report.counts == ORACLE_WITHOUT_LIBRARY

    # And the refusal is remembered: a refresh that re-adapts nothing still
    # names it, rather than reporting a project that quietly has no concepts.
    again = scanner.refresh_index(root)
    assert again.runs_unchanged == 3 and again.library_reindexed is False
    assert again.library_skipped_reason == report.library_skipped_reason
    assert again.skipped_runs == report.skipped_runs

    # An *absent* library is a different thing and says nothing at all.
    shutil.rmtree(root / "output" / "library")
    assert scanner.build_index(root).library_skipped_reason is None


def test_a_report_that_disagrees_with_its_own_counts_cannot_be_constructed() -> None:
    with pytest.raises(Exception) as skipped_but_not_counted:
        scanner.ScanReport(runs_discovered=2, runs_indexed=1, runs_skipped=0)
    assert "D-043" in str(skipped_but_not_counted.value)

    with pytest.raises(Exception, match="D-043"):
        scanner.ScanReport(
            runs_discovered=1,
            runs_indexed=0,
            runs_skipped=1,
            skipped_runs=(),
        )


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_two_run_dirs_declaring_one_video_id_are_refused(tmp_path: Path) -> None:
    """Last-write-wins would silently lose one run's whole knowledge."""
    output = tmp_path / "output"
    shutil.copytree(FIXTURE_RUNS / "pass-run", output / "pass-run")
    shutil.copytree(FIXTURE_RUNS / "pass-run", output / "a-second-copy")

    with pytest.raises(IndexCorrupt) as refused:
        scanner.build_index(tmp_path)

    assert "youtube:fixture-pass" in str(refused.value)
    state, built_at, message = _state(tmp_path)
    assert state == "error" and built_at is None
    assert message and "IndexCorrupt" in message
    # Nothing was committed: a refused scan is not a half-written one.
    assert _stored_records(tmp_path) == {
        "source": [],
        "artifact": [],
        "entity_ref": [],
        "indexed_relation": [],
    }


def test_strict_mode_refuses_the_whole_project_exactly_as_adapt_project_does(
    tmp_path: Path,
) -> None:
    """The mode ``T-104``'s equivalence proof needs.

    Skip-and-name is right for a reader (D-043), but it makes the index a named
    superset of what the ``MemoryRepository`` oracle can produce on a damaged
    project. ``strict=True`` reproduces the oracle's refusal instead.
    """
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    (root / "output" / "fail-run" / "metadata.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(AdapterError):
        adapt_project(root)
    with pytest.raises(AdapterError):
        scanner.build_index(root, strict=True)
    assert _state(root)[0] == "error"

    # The default indexes what it can and names what it cannot.
    assert scanner.build_index(root).runs_indexed == 2


# --------------------------------------------------------------------------
# The build lifecycle
# --------------------------------------------------------------------------


def test_an_interrupted_build_reopens_as_building_and_never_as_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash must not leave a half-full index claiming to be complete."""
    root = _project(tmp_path, *ALL_FIXTURES, library=False)

    def crash(*args: Any, **kwargs: Any):
        raise KeyboardInterrupt("Ctrl-C half way through a build")

    monkeypatch.setattr(scanner, "_apply", crash)
    with pytest.raises(KeyboardInterrupt):
        scanner.build_index(root)

    state, built_at, _message = _state(root)
    assert state == "building" and built_at is None
    assert _stored_records(root)["source"] == []

    # And a refresh over that state is a full build, not an incremental one
    # against rows whose provenance the state already doubts.
    monkeypatch.undo()
    report = scanner.refresh_index(root)
    assert (report.runs_unchanged, report.runs_reindexed) == (0, 3)
    assert _state(root)[0] == "ready"


def test_a_failed_scan_records_the_error_and_leaves_the_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    scanner.build_index(root)
    before = _stored_records(root)

    def boom(*args: Any, **kwargs: Any):
        raise RuntimeError("the store fell over")

    monkeypatch.setattr(scanner, "_insert_records", boom)
    _edit(root / "output" / "pass-run" / "knowledge_units.json", lambda d: d["units"].pop())
    with pytest.raises(RuntimeError):
        scanner.refresh_index(root)

    state, _built_at, message = _state(root)
    assert state == "error" and message and "the store fell over" in message
    assert _stored_records(root) == before, "a failed scan committed part of itself"


def test_the_documents_tables_are_left_to_the_search_module(tmp_path: Path) -> None:
    """``T-102`` fills no FTS table; the hook is where ``T-103`` wires in."""
    root = _project(tmp_path)
    handed: list[Any] = []

    report = scanner.build_index(
        root, index_documents=lambda connection, records: handed.append(records)
    )

    assert _rows(root, "documents") == []
    assert len(handed) == 1
    combined = handed[0]
    assert len(combined.sources) == report.counts["sources"]
    assert len(combined.entities) == report.counts["entities"]
    # A build with no hook is still a build; search is simply unpopulated.
    assert scanner.build_index(root).counts == ORACLE


def test_a_second_build_is_a_rebuild_and_not_a_duplication(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = scanner.build_index(root)
    second = scanner.build_index(root)

    assert second.counts == first.counts == ORACLE
    assert (second.runs_reindexed, second.runs_unchanged) == (3, 0)
    assert len(_rows(root, "runs")) == 4  # three runs and the library fragment


def test_the_index_lives_where_the_schema_says_and_deleting_it_loses_nothing(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    first = scanner.build_index(root)
    database = schema.database_path(root)
    assert database.exists() and database.parent.name == schema.DATABASE_DIRNAME

    shutil.rmtree(database.parent)
    again = scanner.build_index(root)
    assert again.counts == first.counts
    assert _stored_records(root).keys() == {"source", "artifact", "entity_ref", "indexed_relation"}


# --------------------------------------------------------------------------
# The canonical files are never written
# --------------------------------------------------------------------------


def test_building_the_index_does_not_touch_the_runs(tmp_path: Path) -> None:
    root = _project(tmp_path)
    watched = list((root / "output").rglob("*"))
    before = _fingerprint_of(watched)
    assert before, "the project under test is expected to hold files"

    scanner.build_index(root)
    scanner.refresh_index(root)
    (root / "output" / "pass-run" / "vault" / "extra.md").write_text("x", encoding="utf-8")
    scanner.refresh_index(root)

    after = _fingerprint_of(watched)
    assert after == before, "a scan wrote a canonical file, or moved its mtime"


def test_scanning_never_writes_the_committed_fixtures(tmp_path: Path) -> None:
    """The same guarantee, over the evidence in the repository itself."""
    before = _fingerprint_of(FIXTURE_RUNS.rglob("*"))
    root = _project(tmp_path)
    scanner.build_index(root)
    scanner.refresh_index(root)
    assert _fingerprint_of(FIXTURE_RUNS.rglob("*")) == before


# --------------------------------------------------------------------------
# What is ignored, and what only looks ignorable
# --------------------------------------------------------------------------


def test_a_ds_store_is_ignored_and_a_dotted_vault_note_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignoring dotfiles wholesale would let a real artifact go unindexed.

    ``.DS_Store`` churns on every Finder visit and no adapter reads it. A note
    named ``.notes.md`` is picked up by ``_vault_artifacts``' ``*.md`` walk and
    becomes an artifact record, so the digest has to see it.
    """
    root = _project(tmp_path, "pass-run", library=False)
    first = scanner.build_index(root)

    (root / "output" / "pass-run" / ".DS_Store").write_bytes(b"\x00finder")
    called = _counting_adapt(monkeypatch)
    assert scanner.refresh_index(root).runs_unchanged == 1
    assert called == [], "a Finder file forced a re-index"

    (root / "output" / "pass-run" / "vault" / ".notes.md").write_text("# note", encoding="utf-8")
    second = scanner.refresh_index(root)
    assert called == ["pass-run"], "a new vault note went unnoticed"
    assert second.counts["artifacts"] == first.counts["artifacts"] + 1
    assert "output/pass-run/vault/.notes.md" in {
        artifact["path"] for artifact in _stored_records(root)["artifact"]
    }


def test_a_file_that_cannot_be_hashed_is_named_and_costs_no_other_run(tmp_path: Path) -> None:
    """``io.sha256_file`` lets ``OSError`` escape, so every call is wrapped."""
    root = _project(tmp_path, "pass-run", "fail-run", library=False)
    unreadable = root / "output" / "pass-run" / "segments.json"
    unreadable.chmod(0o000)
    if unreadable.stat().st_size and _readable(unreadable):
        pytest.skip("this user can read a mode-000 file, so the failure cannot be provoked")

    try:
        report = scanner.build_index(root)
    finally:
        unreadable.chmod(0o644)

    assert report.runs_indexed == 2, "one unhashable file cost a run its records"
    problems = [
        problem
        for entry in report.incomplete_runs
        if entry["relative_path"] == "output/pass-run"
        for problem in entry["problems"]
    ]
    assert any("segments.json" in problem for problem in problems)
    assert report.counts["sources"] == 2


def _readable(path: Path) -> bool:
    try:
        path.read_bytes()
    except OSError:
        return False
    return True


def test_a_still_broken_run_being_re_edited_does_not_cost_the_library(tmp_path: Path) -> None:
    """A run with no stored ``source_id`` has nothing to evict.

    ``source_id`` is ``NULL`` on the row of a run that could not be indexed, and
    ``NULL`` is also how the library fragment is addressed — its concepts belong
    to no source (D-016). So evicting "whatever that row points at" would delete
    the library instead, and a scan that re-derived nothing would never put it
    back: the concepts would vanish with no report at all.
    """
    output = tmp_path / "output"
    for name in ("pass-run", "partial-run"):
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    broken = output / "partial-run" / "metadata.json"
    broken.write_text("{not json", encoding="utf-8")
    rebuild_library(output)
    first = scanner.build_index(tmp_path)
    assert first.runs_skipped == 1 and first.library_skipped_reason is None
    concepts = [
        entity
        for entity in _stored_records(tmp_path)["entity_ref"]
        if entity["source_id"] is None
    ]
    assert concepts, "the fixture project is expected to carry a canonical concept"

    # Still broken, and broken differently: the digest moves, the run stays
    # skipped, and no run's records change.
    broken.write_text("{still not json", encoding="utf-8")
    second = scanner.refresh_index(tmp_path)

    assert second.runs_skipped == 1 and second.runs_indexed == 1
    assert second.library_skipped_reason is None
    assert [
        entity for entity in _stored_records(tmp_path)["entity_ref"] if entity["source_id"] is None
    ] == concepts, "the library fragment was evicted by a run that never had records"
    assert second.counts == first.counts
