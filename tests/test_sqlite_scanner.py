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
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

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


def test_a_convenience_symlink_is_an_alias_and_not_a_second_run(tmp_path: Path) -> None:
    """D-158. ``glob`` follows directory symlinks, so ``output/latest`` was a run.

    Every record it produced was a duplicate of its target's, and
    ``check_index_integrity`` then refused the *whole* index: every count zero,
    every endpoint ``503``, both real runs lost — and the message blamed a
    duplicate ``video_id`` that no directory in the project declares twice.
    """
    root = _project(tmp_path, "pass-run", "partial-run", library=False)
    (root / "output" / "latest").symlink_to(root / "output" / "pass-run")

    report = scanner.build_index(root)

    assert _state(root)[0] == "ready"
    sources = {record["id"] for record in _stored_records(root)["source"]}
    assert sources == {"youtube:fixture-pass", "youtube:fixture-partial"}

    # Named, not silently dropped: the reader is told the link is an alias.
    skipped = {run["relative_path"]: run["reason"] for run in report.payload()["skipped_runs"]}
    assert "output/latest" in skipped
    assert "alias" in skipped["output/latest"]
    assert "output/pass-run" in skipped["output/latest"]


def test_the_oracle_and_the_index_agree_about_an_alias(tmp_path: Path) -> None:
    """``adapt_project`` walked the link too, so both had to learn one rule.

    If only the scanner had, ``strict=True`` — which exists so ``T-104``'s
    equivalence proof holds record for record — would have compared a refusal
    with a clean build.
    """
    root = _project(tmp_path, "pass-run", library=False)
    (root / "output" / "latest").symlink_to(root / "output" / "pass-run")

    records = adapt_project(root)
    assert [record["id"] for record in records.by_model()["source"]] == ["youtube:fixture-pass"]
    scanner.build_index(root, strict=True)
    assert _state(root)[0] == "ready"


def test_the_library_rebuild_sees_the_runs_the_scanner_sees(tmp_path: Path) -> None:
    """D-158: three implementations of one rule, and one had neither guard.

    ``rebuild_library`` globbed with no dot-directory and no ``library/``
    filter, so a staging directory under ``output/`` reached it and nothing
    else. The symptom was every canonical concept and every
    ``expresses_concept`` edge disappearing from a rebuilt library, with
    ``runs_skipped: 0`` reporting nothing wrong.
    """
    root = _project(tmp_path, "pass-run", library=False)
    output = root / "output"
    shutil.copytree(FIXTURE_RUNS / "pass-run", output / ".staging")
    (output / "latest").symlink_to(output / "pass-run")

    status = rebuild_library(output)

    assert status["runs_indexed"] == 1
    assert [run.name for run in scanner.run_dirs(output)] == ["pass-run"]


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


def _fails_to_scan(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    def boom(*args: Any, **kwargs: Any):
        raise RuntimeError(message)

    monkeypatch.setattr(scanner, "_insert_records", boom)


def test_a_failed_scan_records_the_error_and_leaves_the_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-086: the second half of this test's own name was not true.

    ``_apply`` does every write inside one ``with connection:``, so a failure
    rolls all of them back — which this test already asserted. But the scan
    then committed ``state='error'`` anyway, and ``_require_ready`` refuses
    *every* endpoint in that state, so the records being intact bought the
    reader nothing: adding one run that duplicated an existing ``video_id``
    cost them the whole library until the cause was removed. A rolled-back scan
    over a ``ready`` index leaves it ``ready``, as fresh as its ``built_at``
    says, with a message stating that the last scan failed.
    """
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    scanner.build_index(root)
    before = _stored_records(root)
    _built_before = _state(root)[1]

    _fails_to_scan(monkeypatch, "the store fell over")
    _edit(root / "output" / "pass-run" / "knowledge_units.json", lambda d: d["units"].pop())
    with pytest.raises(RuntimeError):
        scanner.refresh_index(root)

    state, built_at, message = _state(root)
    assert _stored_records(root) == before, "a failed scan committed part of itself"
    assert state == "ready", "a rolled-back scan cost the reader a healthy index"
    assert built_at == _built_before, "the index claimed to be fresher than it is"
    assert message and "the store fell over" in message
    assert "last scan failed" in message


def test_a_failed_scan_leaves_the_index_answering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The consequence D-086 had: every endpoint answered 503 for every run."""
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.repository.base import SourceQuery

    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    scanner.build_index(root)
    _fails_to_scan(monkeypatch, "the store fell over")
    _edit(root / "output" / "pass-run" / "knowledge_units.json", lambda d: d["units"].pop())
    with pytest.raises(RuntimeError):
        scanner.refresh_index(root)

    connection = schema.connect(schema.database_path(root), create=False)
    try:
        repository = SqliteRepository(connection)
        status = repository.status().payload()
        assert status["index"]["state"] == "ready"
        # D-086: `index.message` is the only channel that says the last scan
        # did not finish, so a `ready` state without it would be a silent zero.
        assert "the store fell over" in status["index"].get("message", "")
        assert "last scan failed" in status["index"]["message"]
        # And it actually answers, rather than raising IndexUnavailable.
        assert status["counts"]["sources"] == len(ALL_FIXTURES)
        assert [source["id"] for source in repository.list_sources(SourceQuery()).items]
    finally:
        connection.close()


def test_a_scan_that_never_succeeded_still_reports_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-086 only spares an index that *was* ready; there is nothing to spare here."""
    root = _project(tmp_path, *ALL_FIXTURES, library=False)
    _fails_to_scan(monkeypatch, "the store fell over")
    with pytest.raises(RuntimeError):
        scanner.build_index(root)

    state, _built_at, message = _state(root)
    assert state == "error"
    assert message and "the store fell over" in message
    assert "last scan failed" not in message


def test_a_failed_scans_message_carries_no_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-085: the message is served verbatim in a 503 body (D-030, ADR-0003)."""
    root = _project(tmp_path, *ALL_FIXTURES, library=False)

    def boom(*args: Any, **kwargs: Any):
        raise RuntimeError(f"could not read {root / 'output' / 'pass-run' / 'x.json'}")

    monkeypatch.setattr(scanner, "_insert_records", boom)
    with pytest.raises(RuntimeError):
        scanner.build_index(root)

    _state_name, _built_at, message = _state(root)
    assert message is not None
    assert str(root) not in message
    assert str(root.resolve()) not in message
    # The damage is still stated (D-063): only the path is gone.
    assert "could not read" in message


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


# --------------------------------------------------------------------------
# D-078 — a symlinked run directory is skipped and named, not fatal
# --------------------------------------------------------------------------
#
# `project_relative` resolves symlinks, so a run directory that is a symlink to
# somewhere outside the project resolves outside it and the call raises
# `AdapterError`. It was the *first statement* of `_examine` — outside the
# `try:` that implements the D-043 skip-and-name contract — and it appeared a
# second time inside `_apply`'s prior-row lookup. One symlinked directory under
# `output/` therefore took the whole index down even with `strict=False`:
# `state='error'` with the old counts still in the row, and every endpoint
# answering 503 for every run. `run_dirs` globs `*/metadata.json`, and `glob`
# follows directory symlinks, so an ordinary "runs live on an external drive"
# setup reaches it.


def _outside_run(tmp_path: Path, name: str = "outside-run") -> Path:
    """A real run directory that lives outside the project root."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    target = elsewhere / name
    shutil.copytree(FIXTURE_RUNS / "pass-run", target)
    _edit(target / "metadata.json", lambda d: d.update({"video_id": "fixture-outside"}))
    return target


def test_a_symlinked_run_is_skipped_and_named_rather_than_fatal(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    scanner.build_index(root)

    (root / "output" / "linked-run").symlink_to(_outside_run(tmp_path), True)
    report = scanner.refresh_index(root)

    assert report.runs_discovered == 2
    assert report.runs_indexed == 1
    assert report.runs_skipped == 1
    named = {entry["relative_path"] for entry in report.skipped_runs}
    assert named == {"output/linked-run"}
    # The identity ScanReport asserts about itself still holds.
    assert report.runs_discovered == report.runs_indexed + report.runs_skipped


def test_a_symlinked_run_leaves_the_index_readable(tmp_path: Path) -> None:
    """The consequence the defect had: every endpoint answered 503 for every run."""
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    scanner.build_index(root)
    before = _stored_records(root)

    (root / "output" / "linked-run").symlink_to(_outside_run(tmp_path), True)
    scanner.refresh_index(root)

    state, _built_at, _message = _state(root)
    assert state == "ready", "a skipped run must not downgrade the index"
    assert _stored_records(root) == before, "the healthy run's records changed"


def test_the_reason_for_a_symlinked_run_carries_no_host_path(tmp_path: Path) -> None:
    """D-030 and ADR-0003: `skipped_runs[].reason` is served by `/api/status`."""
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    scanner.build_index(root)
    outside = _outside_run(tmp_path)
    (root / "output" / "linked-run").symlink_to(outside, True)

    report = scanner.refresh_index(root)
    reason = next(
        entry["reason"] for entry in report.skipped_runs
        if entry["relative_path"] == "output/linked-run"
    )
    assert "output/linked-run" in reason
    for absolute in (str(outside), str(outside.parent), str(root.resolve())):
        assert absolute not in reason, f"the reason leaks {absolute}"


def test_a_symlinked_run_is_still_named_on_the_next_refresh(tmp_path: Path) -> None:
    """Re-reporting rather than quietly dropping it — the D-043 contract."""
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    (root / "output" / "linked-run").symlink_to(_outside_run(tmp_path), True)

    first = scanner.build_index(root)
    second = scanner.refresh_index(root)
    assert first.runs_skipped == second.runs_skipped == 1
    assert {e["relative_path"] for e in second.skipped_runs} == {"output/linked-run"}


def test_strict_still_refuses_a_symlinked_run(tmp_path: Path) -> None:
    """`strict=True` agrees with `adapt_project`, which raises here too (T-104)."""
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    (root / "output" / "linked-run").symlink_to(_outside_run(tmp_path), True)

    with pytest.raises(AdapterError):
        adapt_project(root)
    with pytest.raises(AdapterError):
        scanner.build_index(root, strict=True)


def test_a_symlinked_library_is_named_rather_than_fatal(tmp_path: Path) -> None:
    """The same class, on the fragment: `library/` has a row of its own."""
    project = tmp_path / "project"
    project.mkdir()
    root = _project(project, "pass-run", library=False)
    elsewhere = tmp_path / "elsewhere-library"
    elsewhere.mkdir()
    (root / "output" / "library").symlink_to(elsewhere, True)

    report = scanner.build_index(root)
    assert report.runs_indexed == 1
    assert report.library_skipped_reason is not None
    assert "output/library" in report.library_skipped_reason
    state, _built_at, _message = _state(root)
    assert state == "ready"


# --------------------------------------------------------------------------
# D-085 — no reason names a host path
# --------------------------------------------------------------------------


def test_an_adapter_refusal_reason_names_no_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_project_relative_reason` was a single `replace(str(run_dir), …)`.

    It redacted only paths *under* the run directory — while
    `project_relative`'s own message also names the absolute project root, and
    a symlink names a path outside the run entirely. Both reach `/api/status`.
    """
    root = _project(tmp_path, "pass-run", "partial-run", library=False)
    outside = tmp_path / "elsewhere" / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("x", encoding="utf-8")

    def refuse(run_dir: Path, project_root: Path):
        raise AdapterError(
            f"{outside.resolve()} lies outside the project root "
            f"{root.resolve()}; and {run_dir.resolve() / 'metadata.json'} is unreadable"
        )

    monkeypatch.setattr(scanner, "adapt_run", refuse)
    report = scanner.refresh_index(root)

    assert report.runs_skipped == 2
    for entry in report.skipped_runs:
        reason = entry["reason"]
        for absolute in (str(root), str(root.resolve()), str(outside), str(outside.parent)):
            assert absolute not in reason, f"the reason leaks {absolute}: {reason}"
        # D-063: the damage is still stated, and the run is still named.
        assert "lies outside the project root" in reason
        assert entry["relative_path"] in reason or "metadata.json" in reason


# --------------------------------------------------------------------------
# D-087 — the library fragment's reason reaches /api/status
# --------------------------------------------------------------------------


def _status_runs(root: Path) -> dict[str, Any]:
    from x2knwldg.index.repository import SqliteRepository

    connection = schema.connect(schema.database_path(root), create=False)
    try:
        return SqliteRepository(connection).status().payload()["runs"]
    finally:
        connection.close()


def test_a_damaged_library_is_named_on_the_status_endpoint(tmp_path: Path) -> None:
    """`_runs_seen` filtered the library row out of `skipped` as well as the counts.

    A broken `library/concepts.json` and a deleted `library/` both read as
    `skipped: []` with the entity and relation counts quietly lower — D-043's
    silent zero, on the one endpoint that exists to be honest.
    """
    root = _project(tmp_path, "pass-run", "partial-run")
    scanner.build_index(root)
    healthy = _status_runs(root)
    assert healthy.get("library_skipped_reason") is None

    (root / "output" / "library" / "concepts.json").write_text("{not json", encoding="utf-8")
    report = scanner.refresh_index(root)
    assert report.library_skipped_reason is not None

    runs = _status_runs(root)
    reason = runs.get("library_skipped_reason")
    assert reason, "a damaged library fragment is reported nowhere"
    assert "concepts.json" in reason
    # Not counted as a run, so the contract's identity still holds.
    assert runs["discovered"] == runs["indexed"] + len(runs["skipped"])
    assert all("library" not in entry["relative_path"] for entry in runs["skipped"])
    for absolute in (str(root), str(root.resolve())):
        assert absolute not in reason


def test_a_damaged_library_is_distinguishable_from_an_absent_one(tmp_path: Path) -> None:
    """The second half of the finding: the two used to read identically."""
    damaged = _project(tmp_path / "damaged", "pass-run")
    (damaged / "output" / "library" / "concepts.json").write_text("{no", encoding="utf-8")
    scanner.build_index(damaged)

    absent = _project(tmp_path / "absent", "pass-run")
    shutil.rmtree(absent / "output" / "library")
    scanner.build_index(absent)

    assert _status_runs(damaged).get("library_skipped_reason")
    # An absent `library/` is the ordinary state of a project that has not run
    # `rebuild-library`; it is not damage and does not claim to be.
    assert _status_runs(absent).get("library_skipped_reason") is None


# --------------------------------------------------------------------------
# D-088 — a whole build discards the search corpus too
# --------------------------------------------------------------------------


def test_a_build_without_the_hook_leaves_no_stale_corpus(tmp_path: Path) -> None:
    """`build_index`'s docstring promises it discards "whatever was stored".

    It discarded every record family *except* the search corpus, which was left
    to `index_documents` — a parameter defaulting to `None`. So
    `build_index(root)`, the default signature, rebuilt the records and left the
    previous pass's documents: measured, an edited unit's new text was
    unfindable while its deleted text was still being returned.
    """
    from x2knwldg.index import search

    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root, index_documents=search.document_indexer(root))
    assert len(_rows(root, "documents")) > 0, "the hook indexed nothing to go stale"

    _edit(
        root / "output" / "pass-run" / "knowledge_units.json",
        lambda d: d["units"][0].update(
            {"content": "zzzunique text", "normalized_statement": "zzzunique text"}
        ),
    )
    scanner.build_index(root)

    assert _rows(root, "documents") == [], "the previous pass's documents survived"
    assert _rows(root, "document_tokens") == []
    # And the FTS5 index agrees with its content table, rather than raising
    # `fts5: missing row N from content table` on the next substring query.
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        found = connection.execute(
            "SELECT count(*) FROM documents_trigrams WHERE folded MATCH ?", ("knowledge",)
        ).fetchone()[0]
        assert found == 0
    finally:
        connection.close()


def test_a_build_with_the_hook_still_ends_up_populated(tmp_path: Path) -> None:
    """Clearing happens before the hook, so a hooked build is unaffected."""
    from x2knwldg.index import search

    root = _project(tmp_path, "pass-run", "partial-run", library=False)
    scanner.build_index(root, index_documents=search.document_indexer(root))
    first = len(_rows(root, "documents"))
    assert first > 0
    scanner.build_index(root, index_documents=search.document_indexer(root))
    assert len(_rows(root, "documents")) == first, "a rebuild duplicated or lost documents"


# --------------------------------------------------------------------------
# The version the stored rows were written at
#
# "Unchanged" was a function of a run's *files* alone, and a migration does not
# touch a file under `output/`. So a schema bump created its tables empty and
# every later refresh reported a healthy, fully indexed library over them.
# --------------------------------------------------------------------------


def _downgrade_to_schema_1(root: Path) -> None:
    """Rewrite a built index into the shape schema 1 left on disk.

    Not a mock: the migration-2 tables are dropped, ``index_state`` is rebuilt
    at its migration-1 declaration — three columns, no record of what wrote the
    rows — and the ledger is rolled back to ``1``. The four record families,
    the ``runs`` rows and their digests are left exactly as the build committed
    them, which is what a real project upgrading across the migration has.
    """
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        state, built_at, message = _state(root)
        for table in ("source_entities", "source_briefs", "source_relations"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("DROP TABLE index_state")
        connection.execute(
            "CREATE TABLE index_state (id INTEGER PRIMARY KEY CHECK (id = 1), "
            "state TEXT NOT NULL, built_at TEXT, message TEXT)"
        )
        connection.execute(
            "INSERT INTO index_state (id, state, built_at, message) VALUES (1, ?, ?, ?)",
            (state, built_at, message),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version > 1")
        connection.commit()
    finally:
        connection.close()
    assert _rows(root, "schema_migrations", "version")[-1]["version"] == 1


def test_a_migration_forces_a_whole_build_rather_than_leaving_its_tables_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema bump is a change to the index even when no file moved.

    The measured defect: with a populated schema-1 index, ``schema.migrate``
    created ``source_entities``, ``source_briefs`` and ``source_relations``
    empty; every run then hashed identical, so the refresh reported
    ``discovered=3 indexed=3 unchanged=3 skipped=0`` and ``state: ready,
    message: None`` while the whole source layer held nothing. A healthy report
    over an empty layer is the silent zero D-043 forbids, and the only escape
    was to delete the cache directory.
    """
    root = _project(tmp_path)
    scanner.build_index(root)
    populated = len(_rows(root, "source_entities"))
    assert populated == 3 and len(_rows(root, "source_briefs")) == 3, (
        "the premise: a whole build fills the source layer"
    )

    _downgrade_to_schema_1(root)
    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert report.runs_unchanged == 0, "a migrated index carried its rows forward"
    assert sorted(called) == sorted(ALL_FIXTURES), "not every run was re-adapted"
    assert len(_rows(root, "source_entities")) == populated
    assert len(_rows(root, "source_briefs")) == 3
    # And the reason is *said*, not merely acted on: a refresh that quietly
    # re-adapts every run is indistinguishable from one that is simply slow.
    assert report.full_rebuild_reason is not None
    assert "schema version" in report.full_rebuild_reason
    assert report.payload()["full_rebuild_reason"] == report.full_rebuild_reason


def test_a_migrated_index_serves_the_source_layer_it_just_gained(tmp_path: Path) -> None:
    """The symptom, at the seam that showed it: 0 nodes and a `None` neighborhood."""
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.repository import SourceGraphQuery, SourceNeighborhoodQuery

    root = _project(tmp_path)
    scanner.build_index(root)
    _downgrade_to_schema_1(root)
    scanner.refresh_index(root)

    repository = SqliteRepository.open(root)
    try:
        page = repository.source_graph(SourceGraphQuery(limit=50))
        assert len(page.nodes) == 3, "the source graph answered from an empty layer"
        hood = repository.source_neighborhood(
            SourceNeighborhoodQuery(source_id="youtube:fixture-pass", limit=50)
        )
        assert hood is not None, "a source the index holds had no neighborhood"
    finally:
        repository.close()


def test_a_bumped_adapter_version_re_adapts_rather_than_carrying_records_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unchanged run keeps the records of the pass that adapted it.

    ``/api/status.adapters`` reads ``version`` live off the class, so without
    this the endpoint announced a version no stored record had been written at
    — a version nothing compares is not a version.
    """
    root = _project(tmp_path)
    scanner.build_index(root)

    monkeypatch.setattr(scanner, "RECORD_SCHEMA_VERSION", "2.0")
    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert sorted(called) == sorted(ALL_FIXTURES)
    assert report.runs_unchanged == 0
    assert report.full_rebuild_reason is not None
    assert "adapter versions" in report.full_rebuild_reason


def test_an_unchanged_refresh_leaves_the_versions_it_can_be_trusted_by(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two cheap refreshes in a row stay cheap.

    ``INSERT OR REPLACE`` writes a whole row, so a ``_write_state`` call that
    omitted the version columns would blank them — and a blanked record reads
    as "migrated up from an older build", costing every subsequent refresh a
    full rebuild that nothing asked for.
    """
    root = _project(tmp_path)
    scanner.build_index(root)
    assert scanner.refresh_index(root).runs_unchanged == 3

    called = _counting_adapt(monkeypatch)
    second = scanner.refresh_index(root)
    assert called == [] and second.runs_unchanged == 3
    assert second.full_rebuild_reason is None
    row = _rows(root, "index_state")[0]
    assert row["schema_version"] == schema.SCHEMA_VERSION
    assert row["adapter_versions"] == scanner.adapter_versions()


def test_a_failed_scan_does_not_cost_the_next_one_a_full_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rolled-back scan leaves the previous pass's rows *and* its versions.

    D-086 keeps the index ``ready`` through a failed scan because the records
    are exactly what they were. The record of what wrote them has to survive the
    same way, or the failure would be paid for twice.
    """
    root = _project(tmp_path)
    scanner.build_index(root)

    def boom(*args: Any, **kwargs: Any) -> None:
        # Not `_insert_records`: an unchanged refresh inserts nothing, and the
        # failure has to land inside `_apply`'s one transaction to be rolled
        # back. `_write_source_relations` runs on every pass by construction.
        raise RuntimeError("boom")

    monkeypatch.setattr(scanner, "_write_source_relations", boom)
    with pytest.raises(RuntimeError):
        scanner.refresh_index(root)
    monkeypatch.undo()

    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)
    assert called == [], "a failed scan cost the next one every run"
    assert report.runs_unchanged == 3 and report.full_rebuild_reason is None


# --------------------------------------------------------------------------
# The prefilter's agreement is not evidence
# --------------------------------------------------------------------------


def test_a_rewrite_at_the_same_size_with_a_restored_mtime_is_not_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rsync -t``, ``cp -p`` and ``touch -r`` all produce exactly this.

    The measured defect: ``_digest_of_files`` returned the *stored* content hash
    whenever ``(path, mtime_ns, size)`` matched, so the strong half was never
    computed. A run whose ``knowledge_units.json`` was rewritten with different
    bytes at the same size and its mtime restored came back ``1 unchanged of
    1`` — while ``search.document_indexer``, which re-reads the canonical files
    on every pass, indexed the *new* text. One build, two answers: search
    returned the new statement and the stored record still held the old one.
    """
    import os

    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root)

    target = root / "output" / "pass-run" / "knowledge_units.json"
    before = target.stat()
    document = json.loads(target.read_text(encoding="utf-8"))
    original = document["units"][0]["normalized_statement"]
    # Same length, different bytes: `size` cannot notice, and the mtime is put
    # back exactly where it was.
    replacement = "Z" * len(original)
    assert replacement != original
    target.write_text(
        target.read_text(encoding="utf-8").replace(original, replacement), encoding="utf-8"
    )
    assert target.stat().st_size == before.st_size, "the rewrite must not change the size"
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert target.stat().st_mtime_ns == before.st_mtime_ns

    called = _counting_adapt(monkeypatch)
    report = scanner.refresh_index(root)

    assert called == ["pass-run"], "the rewritten run was carried over unread"
    assert (report.runs_unchanged, report.runs_reindexed) == (0, 1)
    labels = {entity["label"] for entity in _stored_records(root)["entity_ref"]}
    assert replacement in labels, "the stored record still holds the superseded text"


def test_the_record_half_and_the_search_half_cannot_disagree_inside_one_build(
    tmp_path: Path,
) -> None:
    """The asymmetry that made the defect visible, pinned.

    ``search.document_indexer`` re-reads every run's canonical files on every
    pass, so a stale record half meant ``/api/search`` returning text that
    ``/api/entities/{id}`` did not have. Whatever the corpus can find, the
    records must hold.
    """
    import os

    from x2knwldg.index import search

    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root, index_documents=search.document_indexer(root))

    target = root / "output" / "pass-run" / "knowledge_units.json"
    before = target.stat()
    document = json.loads(target.read_text(encoding="utf-8"))
    original = document["units"][0]["normalized_statement"]
    replacement = "Q" * len(original)
    target.write_text(
        target.read_text(encoding="utf-8").replace(original, replacement), encoding="utf-8"
    )
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

    scanner.refresh_index(root, index_documents=search.document_indexer(root))

    folded = [row["folded"] for row in _rows(root, "documents", "folded")]
    findable = any(replacement.casefold() in text for text in folded)
    stored = {entity["label"] for entity in _stored_records(root)["entity_ref"]}
    assert findable, "the premise: the corpus is rebuilt from the files every pass"
    assert replacement in stored, (
        "search returns text the stored records do not have — one build, two answers"
    )


def test_a_touched_media_file_still_costs_nothing(tmp_path: Path) -> None:
    """The prefilter is kept where it is the right question.

    A run's non-JSON files reach a record as a name, an existence and a size —
    never as bytes — so hashing them on every scan would buy nothing and cost
    the whole subtree. Touching one must still be free.
    """
    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root)

    notes = sorted((root / "output" / "pass-run").rglob("*.md"))
    assert notes, "the fixture is expected to carry a non-JSON file"
    hashed: list[Path] = []
    original = scanner.sha256_file

    def counting(path: Path) -> str:
        hashed.append(Path(path))
        return original(path)

    import x2knwldg.index.scanner as module

    saved = module.sha256_file
    module.sha256_file = counting  # type: ignore[assignment]
    try:
        report = scanner.refresh_index(root)
    finally:
        module.sha256_file = saved  # type: ignore[assignment]

    assert report.runs_unchanged == 1
    assert all(path.suffix == ".json" for path in hashed), (
        f"the cheap half read bytes it does not need: "
        f"{sorted({path.suffix for path in hashed})}"
    )


# --------------------------------------------------------------------------
# Every writer reports a collision as damage, not as a driver error
# --------------------------------------------------------------------------


def test_a_source_relation_collision_is_named_rather_than_leaked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_write_source_relations`` issued a bare ``execute`` and this escaped raw.

    ``_insert_records`` deliberately turns a primary-key collision into an
    ``IndexCorrupt`` a reader can act on; the two ``T-254`` writers did not, so
    the same condition arrived in ``index.message`` as ``IntegrityError: UNIQUE
    constraint failed: source_relations.identity`` — a sentence about SQLite,
    offered to someone holding a canonical file.
    """
    root = _project(tmp_path, "pass-run", library=False)

    relation = {
        "schema_version": "1.0",
        "id": "SR-collision",
        "from_source_id": "youtube:fixture-pass",
        "to_source_id": "youtube:fixture-partial",
    }
    monkeypatch.setattr(
        "x2knwldg.artifacts.source_relations_document",
        lambda output_root: [dict(relation), dict(relation)],
    )
    with pytest.raises(IndexCorrupt) as refused:
        scanner.build_index(root)
    assert "source_relation" in str(refused.value)
    assert "SR-collision" in str(refused.value)
    assert "one id" in str(refused.value)


def test_a_brief_collision_is_named_rather_than_leaked(tmp_path: Path) -> None:
    """The other bare ``execute``. ``source_briefs`` is keyed by ``source_id``."""
    root = _project(tmp_path, "pass-run", library=False)
    scanner.build_index(root)

    run = scanner._Run(
        "output/pass-run",
        scanner._REINDEXED,
        scanner._Digest("a", "b"),
        source_id="youtube:fixture-pass",
        brief={"state": "unavailable", "reason": "no source_knowledge.json", "brief": None},
    )
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        with pytest.raises(IndexCorrupt) as refused:
            scanner._write_brief(connection, run)
    finally:
        connection.close()
    assert "source_brief" in str(refused.value)
    assert "youtube:fixture-pass" in str(refused.value)


# --------------------------------------------------------------------------
# `x2knwldg index` — the scanner's only name outside `ui`
#
# `refresh_index` was reachable from step 4 of `cli._run_ui` and nowhere else,
# so the only documented escape from an index that had gone wrong was knowing
# that `.x2knwldg/` is a cache and deleting it.
# --------------------------------------------------------------------------


def test_the_index_command_builds_an_index_and_reports_what_it_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg import cli

    root = _project(tmp_path)
    assert not schema.database_path(root).exists(), "the premise: nothing is built yet"

    assert cli.main(["index", "--root", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["counts"] == ORACLE
    assert (payload["runs_discovered"], payload["runs_skipped"]) == (3, 0)
    # Named, never merely counted — the D-043 rule the whole module turns on.
    assert payload["skipped_runs"] == [] and payload["incomplete_runs"] == []
    assert payload["rebuilt"] is False
    assert payload["index_version"] == schema.SCHEMA_VERSION


def test_the_index_command_is_incremental_and_rebuild_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg import cli

    root = _project(tmp_path)
    assert cli.main(["index", "--root", str(root)]) == 0
    capsys.readouterr()

    called = _counting_adapt(monkeypatch)
    assert cli.main(["index", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["runs_unchanged"] == 3
    assert called == [], "the default pass re-adapted an unchanged run"

    assert cli.main(["index", "--root", str(root), "--rebuild"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert sorted(called) == sorted(ALL_FIXTURES), "--rebuild carried rows over"
    assert (payload["runs_unchanged"], payload["rebuilt"]) == (0, True)


def test_the_index_command_wires_the_search_corpus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The pairing `ui` had to remember, made one call site.

    Without ``index_documents`` the scan produces a complete, correct index of
    every record family and ``/api/search`` answers ``0`` for every query,
    because the corpus it searches was never written — and nothing else looks
    wrong.
    """
    from x2knwldg import cli

    root = _project(tmp_path)
    assert cli.main(["index", "--root", str(root)]) == 0
    capsys.readouterr()
    assert len(_rows(root, "documents")) > 0, "the index was built with no searchable text"


def test_the_index_command_reports_a_refusal_rather_than_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scan the store refuses exits ``1`` through the documented envelope."""
    from x2knwldg import cli

    root = _project(tmp_path, "pass-run", library=False)
    shutil.copytree(FIXTURE_RUNS / "pass-run", root / "output" / "second-copy")

    assert cli.main(["index", "--root", str(root)]) == cli.EXIT_ERROR
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["status"] == "ERROR"
    assert "youtube:fixture-pass" in envelope["message"]
    assert captured.out == "", "a refusal printed a report as well"


def test_a_missing_project_root_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg import cli

    assert cli.main(["index", "--root", str(tmp_path / "nowhere")]) == cli.EXIT_ERROR
    assert json.loads(capsys.readouterr().err)["status"] == "ERROR"


def test_the_ui_and_the_index_command_run_the_same_scan() -> None:
    """One helper, so the two cannot drift about what a scan is.

    ``_run_ui``'s step 4 and this command wire ``index_documents`` identically
    because they wire it in one place; two hand-written call sites are two
    places it can be left out.
    """
    import inspect

    from x2knwldg import cli

    for function in (cli._run_ui, cli._run_index):
        source = inspect.getsource(function)
        assert "_scan_index(" in source, function.__name__
        assert "refresh_index(" not in source, (
            f"{function.__name__} calls the scanner directly rather than through "
            "the one helper that pairs it with the search corpus"
        )
