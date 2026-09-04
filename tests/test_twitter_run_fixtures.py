"""The committed Twitter run fixtures, and what they are worth (T-227).

A fixture is only evidence about the pipeline if it was written *by* the
pipeline. So the load-bearing test here is
:func:`test_re_running_the_builder_is_byte_identical`: every case is rebuilt
into a temporary tree by the real builder and compared byte for byte with what
is committed. If extraction changes shape and these files do not, that test
fails — which is the whole reason a fixture is a run directory and not a
hand-written expectation (``T-006``, D-157).

The rest read the committed files the way a downstream reader will: the runs are
validated where they sit, because ``tests/fixtures/`` is the project root their
captures record evidence against and that resolution is exactly what is being
checked.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from x2knwldg.twitter import extract
from x2knwldg.validators import (
    validate_item_coverage,
    validate_item_coverage_links,
    validate_knowledge_units,
    validate_post_provenance,
    validate_relationships,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "tests" / "fixtures" / "twitter-runs"

#: Loaded by path under a name of its own: ``tests/fixtures/runs`` has a
#: ``build_fixtures`` too, and two modules of that name on one path is a
#: coin toss over which one a test gets.
_spec = importlib.util.spec_from_file_location(
    "twitter_build_fixtures", RUNS / "build_fixtures.py"
)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

CASES = [case for case, _capture, _note in builder.CASES]

#: What each run reports, and it is committed rather than derived so a change in
#: a verdict has to be a deliberate edit to this table.
EXPECTED: dict[str, tuple[str, str]] = {
    "single-post": ("PASS", "PASS"),
    "persian-rtl": ("PASS", "PASS"),
    "persian-rtl-ltr-run": ("PASS", "PASS"),
    "self-thread": ("PASS", "PASS"),
    "partial-thread": ("PARTIAL", "PARTIAL"),
    "edit": ("PASS", "PASS"),
    "tombstone": ("FAIL", "PARTIAL"),
    "quote": ("PASS", "PASS"),
}


def read(case: str, name: str) -> Any:
    return json.loads((RUNS / case / name).read_text(encoding="utf-8"))


def test_every_planned_case_is_present() -> None:
    # By the file that makes a directory a run, so a stray `__pycache__` from
    # importing the builder is not mistaken for a missing case.
    on_disk = sorted(path.parent.name for path in RUNS.glob("*/capture.json"))
    assert on_disk == sorted(CASES)
    assert sorted(EXPECTED) == sorted(CASES)


@pytest.mark.parametrize("case", CASES)
def test_each_run_is_labelled_synthetic(case: str) -> None:
    """No answer, report or UI may present these units as real extraction.

    The capture beside them is real measured bytes; the units are mechanical
    quotations. The marker lives in ``metadata.json`` because the capture
    contract's root is ``additionalProperties: false`` and has nowhere to put
    it (``tests/capture_shapes.py``).
    """
    metadata = read(case, "metadata.json")
    assert metadata["fixture"] is True
    assert "Synthetic test fixture" in metadata["fixture_note"]
    assert metadata["imported_at"] == builder.FIXTURE_TIMESTAMP
    assert metadata["extracted_at"] == builder.FIXTURE_TIMESTAMP
    assert metadata["source_type"] == "twitter"


@pytest.mark.parametrize("case", CASES)
def test_the_committed_verdicts_are_the_ones_the_files_state(case: str) -> None:
    validation, coverage = EXPECTED[case]
    assert read(case, "validation.json")["status"] == validation
    assert read(case, "coverage.json")["status"] == coverage


@pytest.mark.parametrize("case", CASES)
def test_evidence_integrity_holds_where_the_run_sits(case: str) -> None:
    """The digests recompute, and the item set re-derives from the raw bytes.

    Run against the committed location rather than a copy: the paths a capture
    records are resolved against ``run_dir.parent.parent``, and a fixture whose
    evidence is only findable after being moved somewhere else has not proved
    that resolution works.
    """
    run_dir = RUNS / case
    result = extract.evidence_integrity(
        run_dir, read(case, "metadata.json"), read(case, "capture.json")
    )
    assert result["status"] == "PASS", result["errors"]
    assert result["warnings"] == []


@pytest.mark.parametrize("case", CASES)
def test_the_canonical_outputs_validate_as_committed(case: str) -> None:
    """Every validator the run passed through, re-run over the committed bytes.

    ``validate_run`` itself is not called here because it *writes*
    ``validation.json``, and a test that rewrites the fixture it is checking
    proves nothing about what is committed.
    """
    capture = read(case, "capture.json")
    units = read(case, "knowledge_units.json")
    coverage = read(case, "coverage.json")
    unit_ids = {unit["id"] for unit in units["units"]}
    assert validate_knowledge_units(units)["errors"] == []
    assert validate_post_provenance(units, capture)["errors"] == []
    assert validate_relationships(read(case, "relationships.json"), unit_ids)["errors"] == []
    assert validate_item_coverage(coverage, capture)["errors"] == []
    assert validate_item_coverage_links(coverage, units["units"]) == []


@pytest.mark.parametrize("case", CASES)
def test_every_excerpt_is_exactly_its_own_span(case: str) -> None:
    """The rule stated as an equality, over the committed files.

    ``validate_post_provenance`` already enforces it above; this states it
    directly so the fixture's purpose survives a refactor of the validator.
    """
    capture = read(case, "capture.json")
    texts = {
        item["post_id"]: extract.canonical_text(item) for item in capture["items"]
    }
    sources = [
        unit["source"]
        for unit in read(case, "knowledge_units.json")["units"]
        if unit["source_class"] == "source"
    ]
    for source in sources:
        text = texts[source["post_id"]]
        assert text is not None
        assert source["evidence_excerpt"] == text[source["start_char"] : source["end_char"]]


def test_the_persian_runs_keep_the_characters_a_persian_post_is_made_of() -> None:
    """ZWNJ, a NBSP and Persian digits, surviving into the canonical outputs.

    This is the case that breaks first if anything on the excerpt path starts
    cleaning or casefolding: the excerpt would still *look* right and would no
    longer be its span.
    """
    excerpts = "".join(
        unit["source"]["evidence_excerpt"]
        for case in ("persian-rtl", "persian-rtl-ltr-run")
        for unit in read(case, "knowledge_units.json")["units"]
        if unit["source_class"] == "source"
    )
    canonical = "".join(
        item["text"]["canonical"]
        for case in ("persian-rtl", "persian-rtl-ltr-run")
        for item in read(case, "capture.json")["items"]
    )
    assert "‌" in canonical, "the fixture no longer carries a ZWNJ"
    assert " " in canonical, "the fixture no longer carries a NBSP"
    assert "‌" in excerpts
    assert any("۰" <= character <= "۹" for character in canonical)


def test_the_self_thread_is_root_first_and_the_partial_one_is_not() -> None:
    """The two directions of D-217, one fixture each."""
    thread = read("self-thread", "capture.json")
    assert thread["completeness"]["upward"]["status"] == "complete"
    assert "parent_post_id" not in thread["items"][0]
    assert [entry["post_id"] for entry in read("self-thread", "coverage.json")["items"]] == [
        item["post_id"] for item in thread["items"]
    ]

    partial = read("partial-thread", "capture.json")
    assert partial["completeness"]["upward"]["status"] == "incomplete"
    # The first item keeps the parent link that proves it is not a root, which
    # is the only thing standing between this run and a chain presented as
    # though it began at one.
    assert partial["items"][0]["parent_post_id"] == "1795231379619274846"
    assert read("partial-thread", "coverage.json")["excluded_items"][0]["post_id"] == (
        "1795231379619274846"
    )


def test_no_prior_version_id_escapes_the_edit_run() -> None:
    """D-224: a prior version is named on its item and is not an expected item."""
    capture = read("edit", "capture.json")
    priors = capture["items"][0]["edits"]
    assert priors
    written = "".join(
        (RUNS / "edit" / name).read_text(encoding="utf-8")
        for name in ("coverage.json", "metadata.json", "knowledge_units.json", "relationships.json")
    )
    for prior in priors:
        assert prior not in written
    assert read("edit", "metadata.json")["item_count"] == 1


def test_the_quoted_post_stays_a_reference_and_is_not_content() -> None:
    reference = read("quote", "metadata.json")["external_references"][0]
    assert reference["relation"] == "quotes"
    assert reference["fetched"] is False
    quoted = reference["post_id"]
    assert quoted not in {item["post_id"] for item in read("quote", "capture.json")["items"]}
    assert quoted not in {
        entry["post_id"] for entry in read("quote", "coverage.json")["items"]
    }


def test_the_tombstone_run_looks_finished_and_is_still_a_failure() -> None:
    """This directory's counterpart to ``runs/fail-run`` (R11).

    Every canonical file exists and is internally consistent, the audit is
    honest, and the run is ``FAIL`` because the capture under it is. A reader
    that infers status from "the files are there" passes on the other seven and
    lies about this one.
    """
    for name in ("knowledge_units.json", "relationships.json", "coverage.json", "validation.json"):
        assert (RUNS / "tombstone" / name).is_file()
    assert read("tombstone", "knowledge_units.json")["units"] == []
    entry = read("tombstone", "coverage.json")["items"][0]
    assert entry["status"] == "omitted"
    assert [omission["type"] for omission in entry["omitted_items"]] == ["source_unavailable"]
    validation = read("tombstone", "validation.json")
    assert validation["capture"]["errors"][0]["code"] == "capture_not_complete"
    assert validation["status"] == "FAIL"


def test_re_running_the_builder_is_byte_identical(tmp_path: Path, monkeypatch) -> None:
    """The fixtures are what the code writes today, or this test says so.

    Rebuilt into a mirror of this directory rather than over it: the recorded
    evidence paths are relative to the output root's parent, so a mirror named
    the same thing produces the same bytes — and the committed fixtures are
    never touched by a test run.
    """
    mirror = tmp_path / RUNS.name
    mirror.mkdir()
    monkeypatch.setattr(builder, "OUTPUT_ROOT", mirror)
    monkeypatch.setattr(builder, "EVIDENCE_ROOT", tmp_path)

    for case, capture_name, _note in builder.CASES:
        validation, coverage = builder.build(case, capture_name)
        assert (validation, coverage) == EXPECTED[case]

    committed = sorted(
        path.relative_to(RUNS) for case in CASES for path in (RUNS / case).rglob("*") if path.is_file()
    )
    rebuilt = sorted(
        path.relative_to(mirror) for path in mirror.rglob("*") if path.is_file()
    )
    assert committed == rebuilt
    differing = [
        str(relative)
        for relative in committed
        if (RUNS / relative).read_bytes() != (mirror / relative).read_bytes()
    ]
    assert differing == [], (
        "The committed fixtures are not what the builder writes today. Re-run "
        "tests/fixtures/twitter-runs/build_fixtures.py and commit the result."
    )
