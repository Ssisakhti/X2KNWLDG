"""The `source_knowledge` apply gate (`T-252`).

`T-251` froze the record and committed a catalogue of dishonest ones; this is
the code that refuses them. So the shape of this file follows that catalogue
rather than the implementation: every fixture filed as ``gate``-refused is fed
to the gate here and must be refused **by name**, because a gate that refuses
the right documents for the wrong reasons is a gate whose error messages send
the next person somewhere else.

Four properties matter more than any individual refusal, and each has a section:

* **No write occurs around the gate.** A refused brief leaves the run exactly as
  it was, byte for byte, ``raw/`` included. A gate that half-writes is not a gate.
* **A status cannot be strengthened.** A brief may be as honest as its run or
  more cautious; never bolder. And the gate does not touch the run's own verdict
  in either direction — an account of a run does not re-grade its subject.
* **Sequencing is enforced, not assumed.** A brief over a run with no extraction,
  or no verdict, or against inputs that have since moved, is refused.
* **The projection is additive.** A run that gains a brief gains one artifact and
  one free-form metadata key; a run without one is byte-identical to before.

Stdlib only, so it runs on a bare core install (ADR 0001 invariant 5).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from x2knwldg import synthesis
from x2knwldg.adapters import adapt_run
from x2knwldg.artifacts import apply_source_knowledge
from x2knwldg.pipeline import PipelineError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "source-map"
VALID = FIXTURE_DIR / "valid"
INVALID = FIXTURE_DIR / "invalid"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(tmp_path: Path, source: Path, name: str = "run") -> Path:
    """A writable copy. The committed fixtures are never edited in place."""
    destination = tmp_path / name
    shutil.copytree(source, destination)
    return destination


def _document(tmp_path: Path, document: dict, name: str = "brief.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _tree(run_dir: Path) -> dict[str, bytes]:
    """Every file in the run, by relative path, as bytes."""
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------
# 1. The happy paths, both media and both honest statuses
# --------------------------------------------------------------------------


def test_a_pass_run_accepts_its_brief(tmp_path: Path) -> None:
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    result = apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")

    assert result["status"] == "PASS"
    assert result["source_id"] == "youtube:fixture-pass"
    assert result["source_knowledge"]["state"] == "available"
    written = _load(run / synthesis.BRIEF_FILENAME)
    assert written == _load(VALID / "youtube-source_knowledge.json")


def test_a_twitter_run_accepts_its_brief(tmp_path: Path) -> None:
    """One gate for both media, and no row in ``MEDIUM_PROFILES``.

    A brief is a thesis, some points, their supporting units and three digests,
    and not one of those differs between a video and a post. The medium-neutral
    claim in `SOURCE_MAP_SPEC.md` §6 is only worth making if it is exercised.
    """
    run = _run(tmp_path, TWITTER_RUNS / "quote")
    result = apply_source_knowledge(run, VALID / "twitter-source_knowledge.json")

    assert result["status"] == "PASS"
    assert result["source_id"].startswith("twitter:")
    assert result["source_knowledge"]["state"] == "available"


def test_a_partial_run_keeps_its_partial_brief(tmp_path: Path) -> None:
    """`PARTIAL` is a real deliverable and is never coerced upward."""
    run = _run(tmp_path, YOUTUBE_RUNS / "partial-run")
    result = apply_source_knowledge(run, VALID / "partial-source_knowledge.json")

    assert result["status"] == "PARTIAL"
    assert _load(run / synthesis.BRIEF_FILENAME)["status"] == "PARTIAL"


def test_a_brief_may_be_more_cautious_than_its_run(tmp_path: Path) -> None:
    """The ordering is one-directional: not stronger, not "equal to"."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    document = _load(VALID / "youtube-source_knowledge.json")
    document["status"] = "PARTIAL"
    apply_source_knowledge(run, _document(tmp_path, document))
    assert _load(run / synthesis.BRIEF_FILENAME)["status"] == "PARTIAL"


def test_applying_twice_replaces_rather_than_accumulates(tmp_path: Path) -> None:
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    document = _load(VALID / "youtube-source_knowledge.json")
    document["key_points"] = document["key_points"][:1]
    apply_source_knowledge(run, _document(tmp_path, document))
    assert len(_load(run / synthesis.BRIEF_FILENAME)["key_points"]) == 1


# --------------------------------------------------------------------------
# 2. The refusals — every gate fixture, refused by name
# --------------------------------------------------------------------------
#
# The catalogue is discovered from the fixture tree rather than listed here, so
# a case added to `tests/fixtures/source-map/invalid/` and filed as `gate` is
# one this file must account for. `_GATE_CASES` maps each brief fixture to the
# run it is a lie *about* and the error code that must name it.

_GATE_CASES = {
    "brief-support-names-an-unknown-unit.json": ("pass-run", "unknown_support"),
    "brief-source-id-is-another-source.json": ("pass-run", "source_id_mismatch"),
    "brief-status-is-stronger-than-the-run.json": ("partial-run", "status_stronger_than_run"),
    "brief-duplicate-point-id.json": ("pass-run", "duplicate_point_id"),
    "brief-digest-is-stale.json": ("pass-run", "stale_input"),
}


def _brief_gate_fixtures() -> list[str]:
    names = []
    for path in sorted(INVALID.glob("brief-*.json")):
        if path.name.endswith(".note.json"):
            continue
        if _load(path.with_name(f"{path.stem}.note.json"))["refused_by"] == "gate":
            names.append(path.name)
    return names


def test_the_catalogue_is_the_one_on_disk() -> None:
    """A hand-kept list beside a generated tree is a list that goes stale."""
    assert sorted(_GATE_CASES) == _brief_gate_fixtures()


@pytest.mark.parametrize("name", sorted(_GATE_CASES))
def test_a_gate_fixture_is_refused_by_the_code_that_names_it(
    tmp_path: Path, name: str
) -> None:
    fixture_run, code = _GATE_CASES[name]
    run = _run(tmp_path, YOUTUBE_RUNS / fixture_run)
    with pytest.raises(PipelineError) as raised:
        apply_source_knowledge(run, INVALID / name)
    assert code in str(raised.value), str(raised.value)


@pytest.mark.parametrize("name", sorted(_GATE_CASES))
def test_a_refused_brief_reaches_no_file(tmp_path: Path, name: str) -> None:
    fixture_run, _ = _GATE_CASES[name]
    run = _run(tmp_path, YOUTUBE_RUNS / fixture_run)
    before = _tree(run)
    with pytest.raises(PipelineError):
        apply_source_knowledge(run, INVALID / name)
    assert _tree(run) == before
    assert not (run / synthesis.BRIEF_FILENAME).exists()


def test_a_refused_brief_does_not_replace_an_accepted_one(tmp_path: Path) -> None:
    """The dangerous case: a run that already has a good brief.

    A gate that wrote and then validated would leave the run holding the refused
    document, and the failure message would be about a file that had already
    won. Checked with a real accepted brief in place rather than only on a bare
    run, because "no write occurs" is easy to satisfy when there is nothing to
    overwrite.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    accepted = (run / synthesis.BRIEF_FILENAME).read_bytes()

    with pytest.raises(PipelineError):
        apply_source_knowledge(run, INVALID / "brief-support-names-an-unknown-unit.json")
    assert (run / synthesis.BRIEF_FILENAME).read_bytes() == accepted


@pytest.mark.parametrize(
    "name",
    [
        "brief-support-is-empty.json",
        "brief-status-is-unknown.json",
        "brief-digests-are-incomplete.json",
        "brief-carries-an-evidence-excerpt.json",
        "brief-has-no-key-points.json",
    ],
)
def test_a_schema_fixture_is_refused_by_the_gate_too(tmp_path: Path, name: str) -> None:
    """The package applies no JSON Schema at runtime, so the gate must.

    ``jsonschema`` is a ``dev`` extra and appears nowhere in the package (ADR
    0001 invariant 5), so a document refused only by ``schemas/synthesis/v1/`` is
    a document refused only in CI. Every shape rule is therefore enforced here
    as well — which is the same argument ``validators.bundle_shape_error``
    carries for the extraction bundle.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    with pytest.raises(PipelineError):
        apply_source_knowledge(run, INVALID / name)


def test_the_evidence_excerpt_refusal_names_the_field(tmp_path: Path) -> None:
    """The one refusal whose message a reader most needs to understand."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    with pytest.raises(PipelineError) as raised:
        apply_source_knowledge(run, INVALID / "brief-carries-an-evidence-excerpt.json")
    assert "unknown_field" in str(raised.value)
    assert "evidence_excerpt" in str(raised.value)


# --------------------------------------------------------------------------
# 3. Sequencing, staleness and the language policy
# --------------------------------------------------------------------------


def test_a_run_with_no_extraction_has_nothing_to_summarise(tmp_path: Path) -> None:
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    (run / "knowledge_units.json").unlink()
    with pytest.raises(PipelineError, match="apply-bundle"):
        apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")


def test_a_run_with_no_verdict_is_refused(tmp_path: Path) -> None:
    """D-246: generation happens after extraction *and* coverage.

    Refused rather than compared: answering "not stronger than UNKNOWN" would be
    inventing a rank for a run nobody has validated.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    (run / "validation.json").unlink()
    with pytest.raises(PipelineError, match="run_has_no_verdict"):
        apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")


def test_a_brief_generated_against_older_inputs_is_refused(tmp_path: Path) -> None:
    """The staleness rule, exercised on a real change rather than a fake digest."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    document = _load(VALID / "youtube-source_knowledge.json")

    units = _load(run / "knowledge_units.json")
    units["units"][0]["content"] += " (edited after the brief was written)"
    (run / "knowledge_units.json").write_text(
        json.dumps(units, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(PipelineError, match="stale_input"):
        apply_source_knowledge(run, _document(tmp_path, document))


def test_the_gate_does_not_stamp_the_digests_itself(tmp_path: Path) -> None:
    """The failure mode that would quietly delete the staleness check.

    If the gate filled ``generated_from`` in, a brief generated against
    yesterday's units would be filed as describing today's, and the field would
    hide exactly what it exists to expose. So a document that omits the digests
    is refused, not completed.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    document = _load(VALID / "youtube-source_knowledge.json")
    del document["generated_from"]
    with pytest.raises(PipelineError, match="missing_field"):
        apply_source_knowledge(run, _document(tmp_path, document))


def test_an_english_brief_is_refused(tmp_path: Path) -> None:
    """The permanent output-language policy, at the gate.

    A script check and described as one: text with no Perso-Arabic character
    cannot be the Persian the policy requires, which is the whole of what this
    establishes.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    document = _load(VALID / "youtube-source_knowledge.json")
    document["thesis"]["content"] = "This source argues that evidence must travel with claims."
    with pytest.raises(PipelineError, match="narrative_not_in_persian_script"):
        apply_source_knowledge(run, _document(tmp_path, document))


def test_persian_with_an_english_term_in_parentheses_is_accepted(tmp_path: Path) -> None:
    """Because that spelling is what the policy asks for, not a tolerated edge."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    document = _load(VALID / "youtube-source_knowledge.json")
    document["thesis"]["content"] = "هر واحد دانش باید شواهد (evidence) خود را همراه بیاورد."
    apply_source_knowledge(run, _document(tmp_path, document))
    assert (run / synthesis.BRIEF_FILENAME).is_file()


def test_a_run_of_an_unimplemented_medium_is_refused(tmp_path: Path) -> None:
    """No medium profile, no canonical output. Books are not ingested here."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    metadata = _load(run / "metadata.json")
    metadata["source_type"] = "book"
    (run / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="medium profile"):
        apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")


def test_a_missing_document_is_named_rather_than_traced(tmp_path: Path) -> None:
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    with pytest.raises(PipelineError):
        apply_source_knowledge(run, tmp_path / "no-such-brief.json")


# --------------------------------------------------------------------------
# 4. Raw evidence, and the run's own verdict
# --------------------------------------------------------------------------


def test_raw_evidence_is_byte_identical_after_a_successful_apply(tmp_path: Path) -> None:
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    before = {
        path.relative_to(run).as_posix(): path.read_bytes()
        for path in sorted((run / "raw").rglob("*"))
        if path.is_file()
    }
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    after = {
        path.relative_to(run).as_posix(): path.read_bytes()
        for path in sorted((run / "raw").rglob("*"))
        if path.is_file()
    }
    assert after == before and before, "the fixture has raw evidence to protect"


def test_writing_a_brief_changes_exactly_one_file(tmp_path: Path) -> None:
    """No canonical extraction file is rewritten, and no verdict is restamped.

    ``apply-bundle`` stamps ``extracted_at`` into ``metadata.json``; this must
    not, because a brief is not an extraction and moving that timestamp would
    make the run look re-extracted.
    """
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    before = _tree(run)
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    after = _tree(run)
    assert set(after) - set(before) == {synthesis.BRIEF_FILENAME}
    assert {name: value for name, value in after.items() if name in before} == before


def test_the_run_verdict_is_read_rather_than_recomputed(tmp_path: Path) -> None:
    """A `FAIL` run stays `FAIL`, and its brief does not rescue it."""
    run = _run(tmp_path, YOUTUBE_RUNS / "fail-run")
    document = _load(VALID / "youtube-source_knowledge.json")
    document["source_id"] = "youtube:fixture-fail"
    document["status"] = "FAIL"
    document["generated_from"] = synthesis.canonical_input_digests(run)
    units = {unit["id"] for unit in _load(run / "knowledge_units.json")["units"]}
    support = sorted(units)[:1]
    document["thesis"]["based_on"] = support
    for point in document["key_points"]:
        point["based_on"] = support

    result = apply_source_knowledge(run, _document(tmp_path, document))
    assert result["status"] == "FAIL"
    assert _load(run / "validation.json")["status"] == "FAIL"


# --------------------------------------------------------------------------
# 5. The projection
# --------------------------------------------------------------------------


def test_a_run_without_a_brief_projects_exactly_as_before(tmp_path: Path) -> None:
    """D-257: the artifact is omitted, not listed as unavailable forever."""
    run = _run(tmp_path / "project" / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    records = adapt_run(run, tmp_path / "project")
    assert not [a for a in records.artifacts if a["kind"] == "source_knowledge"]
    assert "source_knowledge" not in records.sources[0]["adapter_metadata"]


def test_a_run_with_a_brief_gains_one_artifact(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = _run(project / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    before = adapt_run(run, project)
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    after = adapt_run(run, project)

    assert len(after.artifacts) == len(before.artifacts) + 1
    brief = [a for a in after.artifacts if a["kind"] == "source_knowledge"][0]
    assert brief["role"] == "canonical"
    assert brief["available"] is True
    assert brief["immutable"] is False
    assert brief["path"].endswith("source_knowledge.json")
    # Everything else about the projection is untouched.
    assert after.entities == before.entities
    assert after.relations == before.relations
    assert after.source_entities == before.source_entities


def test_the_index_never_carries_the_brief_text(tmp_path: Path) -> None:
    """``adapter_metadata`` states whether the brief is current, not what it says.

    A whole Persian brief inside a ``Source`` record would put derived narrative
    into a payload that exists to describe a source's files, and would ship it
    verbatim inside ``/api/sources`` bodies.
    """
    project = tmp_path / "project"
    run = _run(project / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    source = adapt_run(run, project).sources[0]
    assert source["adapter_metadata"]["source_knowledge"] == {
        "state": "available",
        "reason": None,
    }
    thesis = _load(VALID / "youtube-source_knowledge.json")["thesis"]["content"]
    assert thesis not in json.dumps(source, ensure_ascii=False)


def test_a_stale_brief_is_projected_as_stale(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = _run(project / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")

    units = _load(run / "knowledge_units.json")
    units["units"][0]["content"] += " (edited)"
    (run / "knowledge_units.json").write_text(
        json.dumps(units, ensure_ascii=False), encoding="utf-8"
    )

    state = adapt_run(run, project).sources[0]["adapter_metadata"]["source_knowledge"]
    assert state["state"] == "stale"
    assert "knowledge_units_sha256" in state["reason"]
    # And the artifact is still listed: the file is there and is readable, which
    # is a different question from whether it is current.
    assert [a for a in adapt_run(run, project).artifacts if a["kind"] == "source_knowledge"]


def test_a_damaged_brief_does_not_take_the_run_down(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = _run(project / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    (run / synthesis.BRIEF_FILENAME).write_text("{ not json", encoding="utf-8")

    records = adapt_run(run, project)
    assert records.sources[0]["adapter_metadata"]["source_knowledge"]["state"] == "unavailable"
    assert records.entities, "the run's knowledge is still projected"


def test_the_brief_state_reason_carries_no_host_path(tmp_path: Path) -> None:
    """It reaches an HTTP response body (D-030, D-051)."""
    project = tmp_path / "project"
    run = _run(project / "output", YOUTUBE_RUNS / "pass-run", "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    (run / synthesis.BRIEF_FILENAME).write_text("{ not json", encoding="utf-8")

    reason = synthesis.brief_state(run)["reason"]
    assert str(tmp_path) not in reason
    assert "/" not in reason.replace("source_knowledge.json", "")


# --------------------------------------------------------------------------
# 6. Through the command, because that is how anyone reaches it
# --------------------------------------------------------------------------
#
# `T-229`'s lesson, one task later: `twitter.extract` was complete and correct
# and unreachable from the CLI, so the journey it implemented could not be
# walked. A gate nothing can invoke is a gate nobody goes through.


def test_the_command_applies_a_brief_and_exits_on_the_run_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    code = main(["apply-source-knowledge", str(run), str(VALID / "youtube-source_knowledge.json")])

    assert code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["source_knowledge"]["state"] == "available"
    assert (run / synthesis.BRIEF_FILENAME).is_file()


def test_the_command_exits_three_over_a_partial_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Writing an account of a run does not re-grade it."""
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "partial-run")
    code = main(["apply-source-knowledge", str(run), str(VALID / "partial-source_knowledge.json")])
    assert code == 3
    assert json.loads(capsys.readouterr().out)["status"] == "PARTIAL"


def test_the_command_reports_a_refusal_as_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented ``{"status": "ERROR"}`` stderr envelope, not a traceback."""
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    code = main([
        "apply-source-knowledge",
        str(run),
        str(INVALID / "brief-support-names-an-unknown-unit.json"),
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["status"] == "ERROR"
    assert "unknown_support" in captured.err
    assert not (run / synthesis.BRIEF_FILENAME).exists()


def test_the_full_journey_reaches_a_brief_and_finalizes(tmp_path: Path) -> None:
    """apply-bundle → apply-source-knowledge → finalize, in that order.

    The sequence the prompt describes, walked rather than described. Finalize
    comes last and must not care that a brief exists: `report.md`, `graph.json`
    and the vault are the extraction's outputs, and the brief is a separate
    artifact that does not join them until the Source Map surfaces exist.
    """
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    bundle = run / "work" / "extraction_bundle.json"
    assert bundle.is_file(), "the fixture carries the bundle it was built from"

    assert main(["apply-bundle", str(run), str(bundle)]) == 0
    # The brief's digests are computed after apply-bundle, which is the whole
    # reason this is a separate command: apply-bundle rewrites all three inputs.
    document = _load(VALID / "youtube-source_knowledge.json")
    document["generated_from"] = synthesis.canonical_input_digests(run)
    assert main(["apply-source-knowledge", str(run), str(_document(tmp_path, document))]) == 0
    assert main(["finalize", str(run)]) == 0
    assert synthesis.brief_state(run)["state"] == "available"


def test_re_applying_the_same_bundle_leaves_the_brief_current(tmp_path: Path) -> None:
    """Staleness is about content, not about the act of writing (D-256).

    ``apply-bundle`` rewrites all three canonical inputs and stamps a fresh
    ``extracted_at``, so every mtime moves and ``metadata.json`` genuinely
    changes. None of that is a reason for an account of the knowledge to go
    stale, and a digest that folded in mtime — ``index.scanner``'s does — would
    have reported one here. The brief describes the same units it always did.
    """
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    assert main(["apply-bundle", str(run), str(run / "work" / "extraction_bundle.json")]) == 0
    assert synthesis.brief_state(run)["state"] == "available"


def test_re_extracting_a_run_makes_an_existing_brief_stale(tmp_path: Path) -> None:
    """The honest consequence, stated rather than hidden.

    A bundle that actually changes the knowledge invalidates the account written
    about it, and nothing pretends otherwise: the brief stays on disk, keeps its
    own digests, and is reported ``stale`` from that moment. It is not silently
    deleted — the text is still the last thing anyone wrote about this source —
    and it is not silently trusted either.
    """
    from x2knwldg.cli import main

    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")
    assert synthesis.brief_state(run)["state"] == "available"

    bundle = _load(run / "work" / "extraction_bundle.json")
    bundle["knowledge_units"][0]["confidence"] = 0.5
    assert main(["apply-bundle", str(run), str(_document(tmp_path, bundle, "bundle.json"))]) == 0

    state = synthesis.brief_state(run)
    assert state["state"] == "stale"
    assert "knowledge_units_sha256" in state["reason"]
    assert state["brief"] is not None, "the text is kept; only its currency is denied"


def test_a_stale_brief_can_be_replaced_by_a_current_one(tmp_path: Path) -> None:
    """And the way out is the gate, not an edit. Re-run the pass, re-apply."""
    run = _run(tmp_path, YOUTUBE_RUNS / "pass-run")
    apply_source_knowledge(run, VALID / "youtube-source_knowledge.json")

    units = _load(run / "knowledge_units.json")
    units["units"][0]["confidence"] = 0.5
    (run / "knowledge_units.json").write_text(
        json.dumps(units, ensure_ascii=False), encoding="utf-8"
    )
    assert synthesis.brief_state(run)["state"] == "stale"

    refreshed = _load(VALID / "youtube-source_knowledge.json")
    refreshed["generated_from"] = synthesis.canonical_input_digests(run)
    apply_source_knowledge(run, _document(tmp_path, refreshed, "refreshed.json"))
    assert synthesis.brief_state(run)["state"] == "available"


# --------------------------------------------------------------------------
# 7. The counts the documentation quotes are the ones on disk
# --------------------------------------------------------------------------
#
# `T-251` quoted a fixture split of 15/7 against an actual 13/9 and nothing said
# so, which is why that task ended with a guard. The same mistake was available
# here and was made: the §3 row said 25 rejection codes where the validator
# emits 24. So the guard generalises rather than being written once and
# forgotten — same shape, different numbers.

PROJECT_MANAGEMENT = PROJECT_ROOT / "docs" / "PROJECT_MANAGEMENT.md"


def _rejection_codes() -> set[str]:
    """The codes ``validate_source_knowledge`` and its helpers can emit.

    Read out of the module's own source between the brief's key table and the
    next validator, which is the span `T-252` added. Read rather than listed,
    for the reason ``test_every_emittable_code_is_covered_here`` reads rather
    than lists: a branch added later without a case is what the guard is for.
    """
    import re

    import x2knwldg.validators as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    # The brief's span alone. It used to end at `validate_knowledge_units`, and
    # `T-253` inserted the cross-source relation validator in between — so the
    # count silently became "the brief's codes plus the relation's" and this
    # guard reported a number about two contracts. The end marker is now the
    # section header that follows the brief, which moves only if that section
    # does.
    span = source[
        source.index("SOURCE_KNOWLEDGE_KEYS") : source.index("# Cross-source relations")
    ]
    return set(re.findall(r'"code": "([a-z_]+)"', span))


def test_the_rejection_code_count_in_the_docs_is_the_one_in_the_source() -> None:
    codes = _rejection_codes()
    row = PROJECT_MANAGEMENT.read_text(encoding="utf-8")
    assert f"emits **{len(codes)}** distinct rejection codes" in row, (
        f"the validator emits {len(codes)} codes and the §3 row quotes a different number: "
        f"{sorted(codes)}"
    )
