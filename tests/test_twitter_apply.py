"""The apply gate for a Twitter run (T-227).

``artifacts.apply_extraction_bundle`` is the gate a model's output goes through
for a YouTube run: a bundle that fails validation is never written, so a run
cannot reach the disk in a state its own validators refuse. This is the same
gate for the other medium, and these tests are about the two halves of that
sentence — what it refuses, and what it *imposes* on what it accepts.

The valid bundles are the committed ones under
``tests/fixtures/twitter-runs/<case>/work/``, so a test here and a fixture there
cannot disagree about what a well-formed bundle looks like: the fixture was
built by applying that exact file.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_twitter_extract import load, stage

from x2knwldg.io import dumps_json
from x2knwldg.twitter import extract
from x2knwldg.validators import bundle_shape_error

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "tests" / "fixtures" / "twitter-runs"


def committed_bundle(case: str) -> dict[str, Any]:
    return json.loads((RUNS / case / "work" / "extraction_bundle.json").read_text("utf-8"))


def initialized(tmp_path: Path, capture_name: str) -> tuple[Path, dict[str, Any]]:
    capture = load(capture_name)
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    return run_dir, capture


def apply(run_dir: Path, bundle: Any) -> dict[str, Any]:
    path = run_dir / "work" / "extraction_bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_json(bundle), encoding="utf-8")
    return extract.apply_extraction_bundle(run_dir, path)


def read(run_dir: Path, name: str) -> dict[str, Any]:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. What it writes
# ---------------------------------------------------------------------------


def test_a_bundle_becomes_the_runs_canonical_files(tmp_path: Path) -> None:
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    result = apply(run_dir, committed_bundle("single-post"))

    assert result["status"] == "PASS", result
    units = read(run_dir, "knowledge_units.json")
    # D-226: the declared source type is what dispatches the provenance rules,
    # and it is declared in the canonical file rather than inferred later.
    assert units["source_type"] == "twitter"
    assert units["video_id"] == "20"
    edge = read(run_dir, "relationships.json")["relationships"][0]
    assert (edge["from"], edge["to"], edge["relation"]) == ("KU-000001", "KU-D-0001", "supports")
    assert read(run_dir, "coverage.json")["status"] == "PASS"
    metadata = read(run_dir, "metadata.json")
    assert metadata["extraction"]["fixture"] is True
    assert metadata["extracted_at"]


def test_the_run_is_validated_as_it_was_written(tmp_path: Path) -> None:
    """The returned report is ``validate_run``'s, over the files just written."""
    run_dir, _ = initialized(tmp_path, "pass-thread-terminal-anchor")
    result = apply(run_dir, committed_bundle("self-thread"))
    assert result == read(run_dir, "validation.json")
    assert [section for section, value in result.items() if value == "FAIL"] == []


def test_a_run_over_a_failing_capture_still_applies_and_still_fails(tmp_path: Path) -> None:
    """The tombstone: a clean extraction over evidence that resolved to nothing.

    The bundle is honest and is accepted — there is nothing wrong with it — and
    the run is ``FAIL`` because the capture under it is. An apply gate that
    refused this would be refusing the correct answer.
    """
    run_dir, _ = initialized(tmp_path, "fail-unavailable-post")
    result = apply(run_dir, committed_bundle("tombstone"))
    assert read(run_dir, "knowledge_units.json")["units"] == []
    assert result["capture"]["status"] == "FAIL"
    assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# 2. The bundle contract, which is not this medium's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda b: {"units": b["knowledge_units"], **{k: v for k, v in b.items() if k != "knowledge_units"}}, "the key is 'knowledge_units'"),
        (lambda b: {k: v for k, v in b.items() if k != "relationships"}, "missing required key(s): relationships"),
        (lambda b: {**b, "windows": []}, "unknown top-level key(s): windows"),
        (lambda b: {**b, "extraction_metadata": "a note about the model"}, "extraction_metadata must be an object"),
        (lambda b: {**b, "coverage": []}, "must contain a coverage object"),
    ],
)
def test_the_bundle_contract_is_the_shared_one(
    tmp_path: Path, mutate: Any, expected: str
) -> None:
    """One implementation, two media (``validators.bundle_shape_error``).

    D-073 and D-169 were both found on the YouTube gate, and both were about a
    bundle key read leniently. A second gate that re-derived these rules would
    be the place the next one hides, so the refusal is asserted here *and*
    checked to be the same function's answer.
    """
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    bundle = mutate(committed_bundle("single-post"))
    with pytest.raises(extract.ExtractionError) as caught:
        apply(run_dir, bundle)
    assert expected in str(caught.value)
    assert str(caught.value) == bundle_shape_error(bundle)


def test_a_bundle_that_is_not_json_is_named_rather_than_raised_through(
    tmp_path: Path,
) -> None:
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    path = run_dir / "work" / "extraction_bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(extract.ExtractionError, match="Extraction bundle:"):
        extract.apply_extraction_bundle(run_dir, path)


def test_a_bundle_cannot_be_applied_to_a_run_it_is_not_for(tmp_path: Path) -> None:
    """The run's two documents must agree about which post this run is."""
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    metadata = read(run_dir, "metadata.json")
    metadata["video_id"] = "1795393908886712425"
    (run_dir / "metadata.json").write_text(dumps_json(metadata), encoding="utf-8")
    with pytest.raises(extract.ExtractionError, match="not initialized from this capture"):
        apply(run_dir, committed_bundle("single-post"))


# ---------------------------------------------------------------------------
# 3. What it refuses, and what the run looks like afterwards
# ---------------------------------------------------------------------------


def test_a_bundle_that_fails_validation_is_not_written(tmp_path: Path) -> None:
    """The whole point of a gate: the refused run keeps its scaffold.

    ``initialize_run`` writes the two empty knowledge documents itself now — the
    state ``WORKFLOW.md`` §T1 describes and §T7 grades ``3 PARTIAL`` — so their
    *absence* is no longer what "not written" means here. The stronger claim is
    the one asserted: after a refusal the four canonical files are exactly the
    four the scaffold left, still empty and still unaudited.
    """
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    bundle = committed_bundle("single-post")
    bundle["knowledge_units"][0]["source"]["end_char"] += 3

    with pytest.raises(extract.ExtractionError, match="failed validation"):
        apply(run_dir, bundle)
    assert read(run_dir, "knowledge_units.json")["units"] == []
    assert read(run_dir, "relationships.json")["relationships"] == []
    scaffold = read(run_dir, "coverage.json")
    assert scaffold["audit_attempts"] == 0
    assert scaffold["items"][0]["status"] == "pending"


def test_an_excerpt_that_is_not_its_span_is_refused(tmp_path: Path) -> None:
    """The Persian case, where a normalized excerpt would differ and nowhere else."""
    run_dir, _ = initialized(tmp_path, "pass-single-post-fa")
    bundle = committed_bundle("persian-rtl")
    unit = bundle["knowledge_units"][0]
    unit["source"]["evidence_excerpt"] = unit["source"]["evidence_excerpt"].replace(
        "‌", " "
    )
    with pytest.raises(extract.ExtractionError, match="evidence_excerpt_is_not_its_span"):
        apply(run_dir, bundle)


def test_a_unit_cited_under_another_post_is_refused(tmp_path: Path) -> None:
    """The cross-document rule an apply gate exists to catch."""
    run_dir, _ = initialized(tmp_path, "pass-thread-terminal-anchor")
    bundle = committed_bundle("self-thread")
    first, second = bundle["coverage"]["items"][0], bundle["coverage"]["items"][1]
    first["knowledge_units"], second["knowledge_units"] = (
        second["knowledge_units"],
        first["knowledge_units"],
    )
    with pytest.raises(extract.ExtractionError, match="unit_cited_under_another_post"):
        apply(run_dir, bundle)


def test_a_claim_on_an_unavailable_post_is_refused(tmp_path: Path) -> None:
    run_dir, capture = initialized(tmp_path, "fail-unavailable-post")
    bundle = committed_bundle("tombstone")
    bundle["knowledge_units"] = [
        {
            "id": "KU-000001",
            "kind": "quote",
            "source_class": "source",
            "content": "Something this post is imagined to have said.",
            "confidence": 0.9,
            "source": {
                "post_id": capture["items"][0]["post_id"],
                "start_char": 0,
                "end_char": 10,
                "evidence_excerpt": "invented!!",
            },
        }
    ]
    with pytest.raises(extract.ExtractionError, match="claim_cites_unavailable_post"):
        apply(run_dir, bundle)


# ---------------------------------------------------------------------------
# 4. What it imposes — the three states the prompt promises are not the model's
# ---------------------------------------------------------------------------


def test_the_capture_facts_are_imposed_not_accepted(tmp_path: Path) -> None:
    """``basis``, ``source_id`` and ``excluded_items`` are read off the capture.

    A document that renamed its own ``basis`` would be read by the time-window
    validator and report every post missing; one that shortened
    ``excluded_items`` would quietly promote a third-party parent into something
    nobody has to account for.
    """
    run_dir, _ = initialized(tmp_path, "partial-thread-dangling-chain")
    bundle = committed_bundle("partial-thread")
    bundle["coverage"]["basis"] = "windows"
    bundle["coverage"]["source_id"] = "999999999999999999"
    bundle["coverage"]["excluded_items"] = []
    apply(run_dir, bundle)

    coverage = read(run_dir, "coverage.json")
    assert coverage["basis"] == "items"
    assert coverage["source_id"] == "1795393908886712425"
    assert [entry["post_id"] for entry in coverage["excluded_items"]] == [
        "1795231379619274846"
    ]
    assert coverage["summary"]["excluded_items"] == 1


def test_the_summary_is_recomputed_rather_than_believed(tmp_path: Path) -> None:
    run_dir, _ = initialized(tmp_path, "pass-thread-terminal-anchor")
    bundle = committed_bundle("self-thread")
    bundle["coverage"]["summary"] = {
        "total_items": 1,
        "covered_items": 1,
        "pending_items": 0,
        "unresolved_important_items": 0,
        "excluded_items": 0,
    }
    apply(run_dir, bundle)
    assert read(run_dir, "coverage.json")["summary"]["total_items"] == 10


def test_an_audit_may_not_drop_the_unavailable_omission(tmp_path: Path) -> None:
    """D-225's reason, kept rather than trusted.

    ``source_unavailable`` is minted by the pipeline because the post was never
    observed. An audit that deletes it leaves an item marked ``omitted`` with
    nothing accounting for the omission.
    """
    run_dir, _ = initialized(tmp_path, "fail-unavailable-post")
    bundle = committed_bundle("tombstone")
    bundle["coverage"]["items"][0]["omitted_items"] = []
    apply(run_dir, bundle)

    entry = read(run_dir, "coverage.json")["items"][0]
    assert [omission["type"] for omission in entry["omitted_items"]] == ["source_unavailable"]


def truncated_bundle(capture: dict[str, Any], coverage: dict[str, Any], status: str) -> dict:
    """A hand-built audit for the one capture whose text is known to be short.

    ``partial-tier0-truncated-text`` is not one of the eight fixture cases, so
    there is no committed bundle for it — and it is the only committed capture
    carrying ``known_truncated``, which is the state this section is about.
    """
    text = extract.canonical_text(capture["items"][0]) or ""
    end = len(text.split("\n", 1)[0].rstrip())
    entry = copy.deepcopy(coverage["items"][0])
    entry["status"] = "covered"
    entry["knowledge_units"] = ["KU-000001"]
    entry["unresolved_items"] = []
    return {
        "knowledge_units": [
            {
                "id": "KU-000001",
                "kind": "quote",
                "source_class": "source",
                "content": text[:end],
                "confidence": 0.9,
                "source": {
                    "post_id": capture["items"][0]["post_id"],
                    "start_char": 0,
                    "end_char": end,
                    "evidence_excerpt": text[:end],
                },
            }
        ],
        "relationships": [],
        "coverage": {"status": status, "audit_attempts": 1, "items": [entry]},
    }


def test_an_audit_may_not_delete_the_truncation_gap(tmp_path: Path) -> None:
    """The item-based analogue of D-164's ``window_size_sec``.

    Tier 0 returned 9% of this post and said nothing about it (D-207). The gap
    is a fact about what was observed, so deleting it is not an audit result —
    and re-imposing it is what keeps a truncated run off ``PASS``.
    """
    run_dir, capture = initialized(tmp_path, "partial-tier0-truncated-text")
    coverage = read(run_dir, "coverage.json")
    apply(run_dir, truncated_bundle(capture, coverage, "PARTIAL"))

    entry = read(run_dir, "coverage.json")["items"][0]
    assert [item["type"] for item in entry["unresolved_items"]] == ["capture_text_truncated"]
    assert read(run_dir, "coverage.json")["summary"]["unresolved_important_items"] == 1


def test_a_pass_claimed_over_a_deleted_truncation_gap_is_refused(tmp_path: Path) -> None:
    run_dir, capture = initialized(tmp_path, "partial-tier0-truncated-text")
    coverage = read(run_dir, "coverage.json")
    with pytest.raises(extract.ExtractionError, match="pass_with_unresolved_items"):
        apply(run_dir, truncated_bundle(capture, coverage, "PASS"))


def test_an_audit_resolves_the_scaffolds_own_not_yet_audited_note(tmp_path: Path) -> None:
    """The one minted item an audit *is* entitled to clear, and does."""
    run_dir, _ = initialized(tmp_path, "pass-single-post-en")
    scaffold = read(run_dir, "coverage.json")
    assert [item["type"] for item in scaffold["items"][0]["unresolved_items"]] == [
        "coverage_not_audited"
    ]
    apply(run_dir, committed_bundle("single-post"))
    assert read(run_dir, "coverage.json")["items"][0]["unresolved_items"] == []


def test_a_minted_state_survives_an_entry_that_omits_the_field_entirely(
    tmp_path: Path,
) -> None:
    """Dropping the key is not a quieter way of dropping the omission.

    An audit that writes no ``omitted_items`` at all has said nothing about the
    omission, and what the pipeline minted still holds. An audit that writes a
    *malformed* one is a different case and is refused rather than repaired.
    """
    run_dir, _ = initialized(tmp_path, "fail-unavailable-post")
    bundle = committed_bundle("tombstone")
    del bundle["coverage"]["items"][0]["omitted_items"]
    apply(run_dir, bundle)
    entry = read(run_dir, "coverage.json")["items"][0]
    assert [omission["type"] for omission in entry["omitted_items"]] == ["source_unavailable"]

    run_dir, _ = initialized(tmp_path / "second", "fail-unavailable-post")
    bundle = committed_bundle("tombstone")
    bundle["coverage"]["items"][0]["omitted_items"] = "source_unavailable"
    with pytest.raises(extract.ExtractionError, match="coverage_item_field_not_array"):
        apply(run_dir, bundle)
