"""Adversarial tests for ``x2knwldg.validators``.

Every test here started life as a *bypass*: an input that an external audit
drove through the validators and got a ``PASS`` out of, even though the run it
described was unprovable or fabricated. The project's whole claim is auditable
extraction with honest status — "a guess is a refusal" — so a validator that
can be talked into ``PASS`` is worse than no validator at all.

Three bypasses are covered:

* **D-021 degenerate evidence** — ``" "``, a zero-width space, ``"<b>"`` and the
  integer ``0`` each satisfied both ``validate_knowledge_units`` and
  ``validate_provenance``. The excerpt was only ever tested for truthiness, and
  ``validate_provenance`` skipped its substring check entirely when the cleaned
  excerpt was empty, so an excerpt that cleaned away to nothing was reported as
  *proven* provenance.
* **D-022 the source/derived split** — ``SOURCE_KINDS`` and ``DERIVED_KINDS``
  were only ever consulted as a union, so a ``quote`` could declare itself
  ``derived``, owe no evidence block at all, and pass. That is a fabricated
  quotation with a clean bill of health.
* **D-023 the audit-attempt cap** — WORKFLOW.md §4.4 stops coverage repair after
  three total audit attempts. The check was optional: omit ``audit_attempts``
  and the cap did not exist. Mutating the bound from ``> 3`` to ``> 999`` left
  the entire suite green.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from x2knwldg.artifacts import _carry_coverage_scaffold_forward, apply_extraction_bundle
from x2knwldg.constants import COVERAGE_WINDOW_SEC, DERIVED_KINDS, SOURCE_KINDS
from x2knwldg.pipeline import PipelineError
from x2knwldg.validators import (
    MAX_AUDIT_ATTEMPTS,
    MIN_EVIDENCE_EXCERPT_CHARS,
    validate_coverage,
    validate_coverage_links,
    validate_item_coverage,
    validate_item_coverage_links,
    validate_knowledge_units,
    validate_post_provenance,
    validate_provenance,
    validate_relationships,
)

VIDEO_ID = "vid12345678"
SEGMENT_TEXT = "A knowledge unit must carry the evidence it rests on."
TRANSCRIPT_END = 10.0

TRANSCRIPT: dict[str, Any] = {
    "captions": [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": TRANSCRIPT_END, "text": SEGMENT_TEXT}
    ]
}
SEGMENTS: dict[str, Any] = {
    "segments": [
        {
            "segment_id": "seg_000001",
            "start_sec": 0.0,
            "end_sec": TRANSCRIPT_END,
            "text": SEGMENT_TEXT,
        }
    ]
}

# Each of these was accepted as evidence by both validators before the fix.
DEGENERATE_EXCERPTS: list[Any] = [
    " ",  # whitespace only
    "\t\n ",  # other whitespace
    "​",  # zero width space
    "﻿",  # byte order mark
    "​ ‌",  # a mix of invisibles
    "<b>",  # caption markup that clean_text strips to nothing
    0,  # type confusion: str(0) == "0"
    0.0,
    False,
    True,
    [],
    {},
    ["A knowledge unit"],
]


def _source(**overrides: Any) -> dict[str, Any]:
    source = {
        "video_id": VIDEO_ID,
        "segment_id": "seg_000001",
        "start_sec": 0.0,
        "end_sec": 5.0,
        "evidence_excerpt": "carry the evidence it rests on",
    }
    source.update(overrides)
    return source


def _source_unit(**overrides: Any) -> dict[str, Any]:
    unit = {
        "id": "KU-000001",
        "kind": "claim",
        "source_class": "source",
        "content": "A knowledge unit must carry the evidence it rests on.",
        "confidence": 0.9,
        "source": _source(),
    }
    unit.update(overrides)
    return unit


def _derived_unit(**overrides: Any) -> dict[str, Any]:
    unit = {
        "id": "KU-D-0001",
        "kind": "synthesis",
        "source_class": "derived",
        "content": "A synthesis of the above.",
        "confidence": 0.6,
        "derived_from": ["KU-000001"],
        "derivation_note": "Because the source unit says so.",
    }
    unit.update(overrides)
    return unit


def _coverage(**overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": "1.0",
        "video_id": VIDEO_ID,
        "status": "PARTIAL",
        "audit_attempts": 1,
        "windows": [
            {
                "window_id": "CW-0001",
                "start_sec": 0.0,
                "end_sec": TRANSCRIPT_END,
                "status": "covered",
                "knowledge_units": ["KU-000001"],
                "omitted_items": [],
                "unresolved_items": [],
            }
        ],
    }
    document.update(overrides)
    return document


def _codes(result: dict[str, Any]) -> set[str]:
    return {error["code"] for error in result["errors"]}


def _units(*units: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1.0", "video_id": VIDEO_ID, "units": list(units)}


# ---------------------------------------------------------------------------
# 0. The honest run still passes — the fixtures below only differ by the defect
# ---------------------------------------------------------------------------


def test_a_well_formed_run_still_passes_every_validator() -> None:
    document = _units(_source_unit(), _derived_unit())
    assert validate_knowledge_units(document)["status"] == "PASS"
    assert validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)["status"] == "PASS"
    assert validate_coverage(_coverage(), TRANSCRIPT_END)["status"] == "PASS"


# ---------------------------------------------------------------------------
# 1. D-021 — degenerate evidence excerpts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("excerpt", DEGENERATE_EXCERPTS, ids=repr)
def test_degenerate_excerpt_fails_the_unit_validator(excerpt: Any) -> None:
    """No amount of invisible or non-string content is an evidence excerpt."""
    result = validate_knowledge_units(_units(_source_unit(source=_source(evidence_excerpt=excerpt))))
    assert result["status"] == "FAIL", f"{excerpt!r} was accepted as evidence"
    assert _codes(result) & {
        "empty_evidence_excerpt",
        "evidence_excerpt_not_a_string",
        "incomplete_provenance",
    }


@pytest.mark.parametrize("excerpt", DEGENERATE_EXCERPTS, ids=repr)
def test_degenerate_excerpt_fails_the_provenance_validator(excerpt: Any) -> None:
    """The bypass that mattered most: an excerpt that cleans away to nothing
    used to skip the "excerpt appears in the segment" test and be reported as
    proven provenance."""
    document = _units(_source_unit(source=_source(evidence_excerpt=excerpt)))
    result = validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)
    assert result["status"] == "FAIL", f"{excerpt!r} passed the provenance check"
    assert _codes(result) & {
        "empty_evidence_excerpt",
        "evidence_excerpt_not_a_string",
        "missing_evidence_excerpt",
    }


@pytest.mark.parametrize("excerpt", [None, ""], ids=["absent", "empty_string"])
def test_absent_excerpt_fails_both_validators(excerpt: Any) -> None:
    source = _source()
    if excerpt is None:
        source.pop("evidence_excerpt")
    else:
        source["evidence_excerpt"] = excerpt
    document = _units(_source_unit(source=source))
    assert validate_knowledge_units(document)["status"] == "FAIL"
    provenance = validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)
    assert provenance["status"] == "FAIL"
    assert _codes(provenance) & {"missing_evidence_excerpt", "empty_evidence_excerpt"}


@pytest.mark.parametrize(
    "excerpt",
    ["<b>", "<i></i>", "<00:00:01.000>", "<c.colorE5E5E5>", "<span class='x'></span>"],
    ids=repr,
)
def test_markup_only_excerpt_never_passes_provenance(excerpt: str) -> None:
    """Markup is not evidence however ``clean_text`` treats it.

    ``transcripts.clean_text`` decides which tags are caption markup, and that
    rule may change. Either way the excerpt must fail: stripped to nothing it is
    empty evidence, and left standing it is text the segment does not contain.
    """
    result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt=excerpt))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL", f"{excerpt!r} passed as evidence"
    assert _codes(result) & {
        "empty_evidence_excerpt",
        "evidence_excerpt_too_short",
        "evidence_excerpt_not_in_segment",
    }


def test_provenance_rejects_an_excerpt_too_short_to_prove_anything() -> None:
    """A one-character excerpt is a substring of nearly every segment, so the
    containment test would pass without evidencing the unit."""
    tiny = SEGMENT_TEXT[0]
    assert tiny.casefold() in SEGMENT_TEXT.casefold()
    result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt=tiny))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL"
    assert "evidence_excerpt_too_short" in _codes(result)


def test_the_minimum_excerpt_length_is_enforced_at_its_boundary() -> None:
    """Guards the constant itself: shortening it to 0 or 1 must break a test."""
    assert MIN_EVIDENCE_EXCERPT_CHARS == 3
    below, at = "ca", "car"  # both are prefixes of "carry" in the segment
    assert at.casefold() in SEGMENT_TEXT.casefold()
    below_result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt=below))), TRANSCRIPT, SEGMENTS, VIDEO_ID
    )
    at_result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt=at))), TRANSCRIPT, SEGMENTS, VIDEO_ID
    )
    assert below_result["status"] == "FAIL"
    assert at_result["status"] == "PASS"


def test_padding_a_real_excerpt_with_invisibles_still_matches_the_segment() -> None:
    """Hardening must not create a false negative: an excerpt with stray
    whitespace or a stripped tag around real content is still evidence."""
    result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt="  <i>carry the evidence</i>\n"))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "PASS", result["errors"]


def test_an_excerpt_absent_from_the_segment_still_fails() -> None:
    """The original check must survive the hardening."""
    result = validate_provenance(
        _units(_source_unit(source=_source(evidence_excerpt="never said on this recording"))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL"
    assert "evidence_excerpt_not_in_segment" in _codes(result)


# ---------------------------------------------------------------------------
# 2. D-022 — the source/derived kind split
# ---------------------------------------------------------------------------


def test_a_fabricated_quote_cannot_hide_behind_the_derived_class() -> None:
    """The headline bypass: a ``quote`` declared ``derived`` owed no evidence
    block, so a quotation nobody said passed both validators."""
    fabricated = {
        "id": "KU-000002",
        "kind": "quote",
        "source_class": "derived",
        "content": "I never said any of this.",
        "confidence": 1.0,
        "derived_from": ["KU-000001"],
        "derivation_note": "Synthesised.",
    }
    result = validate_knowledge_units(_units(_source_unit(), fabricated))
    assert result["status"] == "FAIL"
    codes = _codes(result)
    assert "kind_source_class_mismatch" in codes
    assert "missing_source" in codes


@pytest.mark.parametrize("kind", sorted(SOURCE_KINDS))
def test_every_source_kind_declared_derived_fails(kind: str) -> None:
    result = validate_knowledge_units(
        _units(_derived_unit(kind=kind, derived_from=["KU-000001"]))
    )
    assert result["status"] == "FAIL", f"{kind} passed while declared derived"
    assert "kind_source_class_mismatch" in _codes(result)


@pytest.mark.parametrize("kind", sorted(DERIVED_KINDS))
def test_every_derived_kind_declared_source_fails(kind: str) -> None:
    result = validate_knowledge_units(_units(_source_unit(kind=kind)))
    assert result["status"] == "FAIL", f"{kind} passed while declared source"
    assert "kind_source_class_mismatch" in _codes(result)


def test_the_two_kind_sets_stay_disjoint() -> None:
    """The split is only enforceable while a kind belongs to exactly one side."""
    assert not SOURCE_KINDS & DERIVED_KINDS


def test_a_source_kind_owes_a_provenance_block_even_when_mislabelled() -> None:
    """The obligation follows the declared kind, not only ``source_class``."""
    result = validate_knowledge_units(
        _units(
            {
                "id": "KU-000003",
                "kind": "statistic",
                "source_class": "derived",
                "content": "42% of everything.",
                "confidence": 0.9,
                "derived_from": ["KU-000001"],
                "derivation_note": "Made up.",
            },
            _source_unit(),
        )
    )
    assert "missing_source" in _codes(result)


def test_a_derived_kind_owes_derived_from_even_when_mislabelled() -> None:
    result = validate_knowledge_units(_units(_source_unit(kind="mental_model")))
    codes = _codes(result)
    assert "missing_derived_from" in codes
    assert "missing_derivation_note" in codes


def test_a_consistent_source_unit_and_derived_unit_pass_together() -> None:
    result = validate_knowledge_units(_units(_source_unit(kind="quote"), _derived_unit()))
    assert result["status"] == "PASS", result["errors"]


# ---------------------------------------------------------------------------
# 3. D-023 — the three-attempt coverage-repair cap
# ---------------------------------------------------------------------------


def test_the_cap_is_the_three_attempts_the_workflow_allows() -> None:
    """WORKFLOW.md §4.4 and CLAUDE.md both say three; nothing else is the cap."""
    assert MAX_AUDIT_ATTEMPTS == 3


def test_coverage_without_an_attempt_count_fails() -> None:
    """Omitting the count used to skip the cap entirely."""
    document = _coverage()
    document.pop("audit_attempts")
    result = validate_coverage(document, TRANSCRIPT_END)
    assert result["status"] == "FAIL"
    assert "missing_audit_attempts" in _codes(result)


def test_a_null_attempt_count_fails() -> None:
    result = validate_coverage(_coverage(audit_attempts=None), TRANSCRIPT_END)
    assert result["status"] == "FAIL"
    assert "missing_audit_attempts" in _codes(result)


@pytest.mark.parametrize("attempts", [MAX_AUDIT_ATTEMPTS + 1, 4, 7, 42, 999, 1000])
def test_exceeding_the_cap_fails(attempts: int) -> None:
    """Kills the mutation the audit found: widening ``> 3`` to ``> 999``."""
    result = validate_coverage(_coverage(audit_attempts=attempts), TRANSCRIPT_END)
    assert result["status"] == "FAIL", f"{attempts} audit attempts were accepted"
    assert "audit_attempts_over_cap" in _codes(result)


@pytest.mark.parametrize("attempts", [1, 2, MAX_AUDIT_ATTEMPTS])
def test_an_attempt_count_within_the_cap_passes(attempts: int) -> None:
    result = validate_coverage(_coverage(audit_attempts=attempts), TRANSCRIPT_END)
    assert result["status"] == "PASS", result["errors"]


@pytest.mark.parametrize(
    "attempts", ["3", "many", 1.5, True, False, [3], {"count": 3}, -1], ids=repr
)
def test_an_attempt_count_of_the_wrong_type_or_sign_fails(attempts: Any) -> None:
    result = validate_coverage(_coverage(audit_attempts=attempts), TRANSCRIPT_END)
    assert result["status"] == "FAIL", f"{attempts!r} was accepted as an attempt count"
    assert "invalid_audit_attempts" in _codes(result)


def test_zero_attempts_is_honest_for_a_pending_document_but_never_a_pass() -> None:
    """A scaffolded run has genuinely audited nothing; it may not claim PASS."""
    pending = validate_coverage(_coverage(audit_attempts=0, status="PARTIAL"), TRANSCRIPT_END)
    assert pending["status"] == "PASS", pending["errors"]
    claimed = validate_coverage(_coverage(audit_attempts=0, status="PASS"), TRANSCRIPT_END)
    assert claimed["status"] == "FAIL"
    assert "unaudited_coverage_pass" in _codes(claimed)


# ---------------------------------------------------------------------------
# 4. D-070 — a source timestamp that is not a number
# ---------------------------------------------------------------------------
#
# ``validate_knowledge_units`` tested the five provenance fields for
# *presence* only — ``source.get(field) in (None, "")`` — so the string
# ``"99999"`` counted as provided. ``validate_provenance`` then guarded both of
# its range checks behind ``isinstance(start, (int, float))`` and **skipped**
# them when the guard failed rather than erroring. A unit citing a moment the
# video does not contain therefore passed both validators, cleared
# ``apply-bundle``, and rendered in ``report.md`` as ``[27:46:39-27:46:39]``
# with a working deep link.
#
# The asymmetry was the tell: the *float* ``99999.0`` failed, the *string*
# ``"99999"`` passed, and ``validate_coverage`` already emitted
# ``invalid_window_timing`` for exactly this shape one function away. The rule
# now lives in ``_is_seconds`` and both validators consult it.

# Each of these was accepted as a source timestamp before the fix.
UNUSABLE_TIMESTAMPS: list[Any] = [
    "99999",  # the audit's case: out of range, and never compared
    "0.0",  # float-shaped, and the shape that later crashes format_timestamp
    "",  # empty string — caught as missing, never as the wrong type
    "twelve",
    True,  # bool is an int in Python, and True is not a time
    False,
    float("nan"),  # every comparison against NaN is False
    float("inf"),
    float("-inf"),
    [0.0],
    {"start": 0.0},
]


@pytest.mark.parametrize("timestamp", UNUSABLE_TIMESTAMPS, ids=repr)
def test_an_unusable_start_time_fails_the_provenance_validator(timestamp: Any) -> None:
    document = _units(_source_unit(source=_source(start_sec=timestamp)))
    result = validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)
    assert result["status"] == "FAIL", f"{timestamp!r} was accepted as a start time"
    assert "invalid_source_timing" in _codes(result)


@pytest.mark.parametrize("timestamp", UNUSABLE_TIMESTAMPS, ids=repr)
def test_an_unusable_end_time_fails_the_provenance_validator(timestamp: Any) -> None:
    document = _units(_source_unit(source=_source(end_sec=timestamp)))
    result = validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)
    assert result["status"] == "FAIL", f"{timestamp!r} was accepted as an end time"
    assert "invalid_source_timing" in _codes(result)


@pytest.mark.parametrize("timestamp", UNUSABLE_TIMESTAMPS, ids=repr)
def test_an_unusable_timestamp_fails_the_unit_validator_too(timestamp: Any) -> None:
    """The unit validator is the one ``import_transcript`` runs on its own.

    ``""`` is reported as ``incomplete_provenance`` rather than as bad timing —
    either code is a refusal, which is all this asserts.
    """
    document = _units(_source_unit(source=_source(start_sec=timestamp)))
    result = validate_knowledge_units(document)
    assert result["status"] == "FAIL", f"{timestamp!r} was accepted as a start time"
    assert _codes(result) & {"invalid_source_timing", "incomplete_provenance"}


def test_the_string_and_the_float_spelling_of_a_bad_time_agree() -> None:
    """The asymmetry that hid the defect: both spellings must now be refused."""
    as_float = validate_provenance(
        _units(_source_unit(source=_source(start_sec=99999.0, end_sec=99999.0))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    as_string = validate_provenance(
        _units(_source_unit(source=_source(start_sec="99999", end_sec="99999"))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert as_float["status"] == as_string["status"] == "FAIL"
    # The float can be compared, so it is refused for being out of range; the
    # string cannot be compared at all, so it is refused for being unusable.
    assert "source_time_outside_transcript" in _codes(as_float)
    assert "invalid_source_timing" in _codes(as_string)


def test_a_time_outside_the_transcript_is_still_named_as_such() -> None:
    """The new guard must not swallow the checks it stopped skipping."""
    result = validate_provenance(
        _units(_source_unit(source=_source(start_sec=0.0, end_sec=TRANSCRIPT_END + 100))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL"
    assert "source_time_outside_transcript" in _codes(result)


@pytest.mark.parametrize("timestamp", [0, 0.0, 5, 5.0, TRANSCRIPT_END], ids=repr)
def test_an_honest_numeric_timestamp_is_still_accepted(timestamp: Any) -> None:
    """``int`` and ``float``, including ``0``, remain usable times."""
    document = _units(_source_unit(source=_source(start_sec=0, end_sec=timestamp)))
    assert validate_knowledge_units(document)["status"] == "PASS"
    assert validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)["status"] == "PASS"


def test_the_timestamp_rule_matches_the_one_the_id_builder_enforces() -> None:
    """One rule, three modules: ``ids`` raises where ``validators`` collects.

    Compared over non-negative values only, because ``ids._require_seconds``
    additionally refuses a negative time while ``_is_seconds`` leaves that to
    the range check that follows it.
    """
    from x2knwldg.ids import IdError, _require_seconds
    from x2knwldg.validators import _is_seconds

    non_negative = [
        value
        for value in [*UNUSABLE_TIMESTAMPS, 0, 0.0, 1, 1.5, 600.0]
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0)
    ]
    for value in non_negative:
        try:
            _require_seconds(value, "start_sec")
        except IdError:
            id_builder_refuses = True
        else:
            id_builder_refuses = False
        assert id_builder_refuses == (not _is_seconds(value)), (
            f"{value!r}: ids refuses={id_builder_refuses}, "
            f"validators accepts={_is_seconds(value)}"
        )


def test_a_string_timestamp_cannot_clear_apply_bundle(tmp_path: Path) -> None:
    """The end of the path the defect opened.

    ``apply_extraction_bundle`` raises when any validator reports an error, so
    proving the validators refuse also proves ``apply-bundle`` refuses — and it
    is ``apply-bundle`` exiting ``0`` that let a fabricated citation reach
    ``report.md``. Built from the committed ``pass-run`` fixture so the *only*
    difference from an honest run is the one timestamp.
    """
    fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
    run_dir = tmp_path / "run"
    shutil.copytree(fixture, run_dir)

    units = json.loads((fixture / "knowledge_units.json").read_text())["units"]
    # D-169: exactly the schema's keys. This bundle used to carry a
    # `schema_version` the schema does not declare, and `additionalProperties:
    # false` was enforced nowhere at runtime, so it was silently accepted.
    bundle = {
        "knowledge_units": units,
        "relationships": json.loads((fixture / "relationships.json").read_text())[
            "relationships"
        ],
        "coverage": json.loads((fixture / "coverage.json").read_text()),
    }

    honest = tmp_path / "honest.json"
    honest.write_text(json.dumps(bundle))
    apply_extraction_bundle(run_dir, honest)  # the fixture is a real PASS run

    # One field, one type. Everything else is byte-identical to the above.
    units[0]["source"]["start_sec"] = str(units[0]["source"]["start_sec"])
    fabricated = tmp_path / "fabricated.json"
    fabricated.write_text(json.dumps(bundle))
    with pytest.raises(PipelineError) as refusal:
        apply_extraction_bundle(run_dir, fabricated)
    assert "invalid_source_timing" in str(refusal.value)


def test_a_unit_wrong_in_two_ways_is_reported_as_wrong_in_two_ways() -> None:
    """The timing refusal must not shadow the excerpt refusal on the same unit."""
    result = validate_provenance(
        _units(_source_unit(source=_source(start_sec="99999", evidence_excerpt="<b>"))),
        TRANSCRIPT,
        SEGMENTS,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL"
    assert {"invalid_source_timing", "empty_evidence_excerpt"} <= _codes(result)


# ---------------------------------------------------------------------------
# 5. D-072 — coverage windows that fail open
# ---------------------------------------------------------------------------
#
# ``isinstance(True, (int, float))`` is ``True`` in Python, so a window bounded
# by booleans validated as the range ``[0, 1]``; a ``NaN`` bound slipped past
# ``end < start`` because every comparison against ``NaN`` is ``False``. And
# three window fields were read as collections — ``len(unresolved_items)``,
# iteration over ``omitted_items``, a truthiness test on ``knowledge_units`` —
# with no type check, so ``unresolved_items: 5`` crashed ``len()`` and
# ``knowledge_units: "u1"`` satisfied ``covered_window_without_accounting``
# because a non-empty string is truthy.


def _window(**overrides: Any) -> dict[str, Any]:
    window = {
        "window_id": "CW-0001",
        "start_sec": 0.0,
        "end_sec": TRANSCRIPT_END,
        "status": "covered",
        "knowledge_units": ["KU-000001"],
        "omitted_items": [],
        "unresolved_items": [],
    }
    window.update(overrides)
    return window


@pytest.mark.parametrize(
    "bound", ["0", True, False, float("nan"), float("inf"), None, [0.0], {}], ids=repr
)
def test_a_window_bound_that_is_not_a_number_fails(bound: Any) -> None:
    result = validate_coverage(_coverage(windows=[_window(start_sec=bound)]), TRANSCRIPT_END)
    assert result["status"] == "FAIL", f"{bound!r} was accepted as a window bound"
    assert "invalid_window_timing" in _codes(result)


def test_a_boolean_window_is_not_the_range_zero_to_one() -> None:
    """The audit's case, verbatim: ``start_sec: False``, ``end_sec: True``."""
    document = {
        "status": "PASS",
        "audit_attempts": 1,
        "windows": [_window(start_sec=False, end_sec=True)],
    }
    result = validate_coverage(document, 1.0)
    assert result["status"] == "FAIL"
    assert "invalid_window_timing" in _codes(result)


@pytest.mark.parametrize(
    "field", ["knowledge_units", "omitted_items", "unresolved_items"]
)
@pytest.mark.parametrize("value", ["u1", 5, {"id": "u1"}, None], ids=repr)
def test_a_window_collection_that_is_not_an_array_fails(field: str, value: Any) -> None:
    """``unresolved_items: 5`` used to crash ``len()`` from inside the validator."""
    result = validate_coverage(_coverage(windows=[_window(**{field: value})]), TRANSCRIPT_END)
    assert result["status"] == "FAIL", f"{field}={value!r} was accepted"
    assert "window_field_not_array" in _codes(result)


def test_a_string_of_unit_ids_is_not_accounting_for_units() -> None:
    """The truthiness bypass: a `covered` window whose units are the string "u1"."""
    document = {"status": "PASS", "audit_attempts": 1, "windows": [
        _window(start_sec=0.0, end_sec=1.0, knowledge_units="u1")
    ]}
    result = validate_coverage(document, 1.0)
    assert result["status"] == "FAIL"
    assert {"window_field_not_array", "covered_window_without_accounting"} <= _codes(result)


def test_an_honest_window_still_passes() -> None:
    assert validate_coverage(_coverage(windows=[_window()]), TRANSCRIPT_END)["status"] == "PASS"


# ---------------------------------------------------------------------------
# 6. Every rejection code this module can emit
# ---------------------------------------------------------------------------
#
# The audit measured `validators.py` as the least-covered module in the package
# — 81.7%, its uncovered lines almost entirely the rejection branches — and
# found 29 emittable codes that appeared in *no* test. Those branches are the
# ones that exist to stop a bad run claiming `PASS`, so an inverted or
# misspelled predicate in any of them was invisible to 2142 passing tests.
#
# The parametrisation below names a code and the smallest document that must
# produce it. `test_every_emittable_code_is_covered_here` then reads the codes
# out of the module's own source and fails when one of them is not named — so
# a *new* rejection branch cannot be added without a case, which is the part
# that keeps this list from going stale.


def _relationship(**overrides: Any) -> dict[str, Any]:
    edge = {
        "from": "KU-000001",
        "relation": "supports",
        "to": "KU-000002",
        "confidence": 0.9,
        "source_class": "derived",
    }
    edge.update(overrides)
    return edge


def _edges(*edges: Any) -> dict[str, Any]:
    return {"schema_version": "1.0", "video_id": VIDEO_ID, "relationships": list(edges)}


TWO_IDS = {"KU-000001", "KU-000002"}

UNIT_CODES: list[tuple[str, Any]] = [
    ("units_not_array", {"units": "KU-000001"}),
    ("unit_not_object", _units("not a unit")),  # type: ignore[arg-type]
    ("missing_id", _units(_source_unit(id=""))),
    ("duplicate_id", _units(_source_unit(), _source_unit(content="A second unit."))),
    ("invalid_id", _units(_source_unit(id="KU:000001"))),
    ("invalid_kind", _units(_source_unit(kind="anecdote"))),
    ("invalid_source_class", _units(_source_unit(source_class="quoted"))),
    ("kind_source_class_mismatch", _units(_source_unit(kind="synthesis"))),
    ("invalid_confidence", _units(_source_unit(confidence=1.5))),
    ("missing_content", _units(_source_unit(content="   "))),
    ("missing_source", _units(_source_unit(source="seg_000001"))),
    ("incomplete_provenance", _units(_source_unit(source=_source(segment_id=None)))),
    ("invalid_source_timing", _units(_source_unit(source=_source(start_sec="0")))),
    ("empty_evidence_excerpt", _units(_source_unit(source=_source(evidence_excerpt=" ")))),
    (
        "evidence_excerpt_not_a_string",
        _units(_source_unit(source=_source(evidence_excerpt=7))),
    ),
    ("missing_derived_from", _units(_derived_unit(derived_from=[]))),
    ("missing_derivation_note", _units(_derived_unit(derivation_note=""))),
    ("unknown_derived_source", _units(_derived_unit(derived_from=["KU-999999"]))),
]

RELATIONSHIP_CODES: list[tuple[str, Any]] = [
    ("relationships_not_array", {"relationships": "supports"}),
    ("relationship_not_object", _edges("supports")),
    ("unknown_from", _edges(_relationship(**{"from": "KU-999999"}))),
    ("unknown_to", _edges(_relationship(to="KU-999999"))),
    ("invalid_relation", _edges(_relationship(relation="mentions"))),
    ("unintentional_self_loop", _edges(_relationship(to="KU-000001"))),
    ("invalid_confidence", _edges(_relationship(confidence="high"))),
    ("invalid_source_class", _edges(_relationship(source_class="quoted"))),
]

PROVENANCE_CODES: list[tuple[str, Any]] = [
    ("source_video_mismatch", _units(_source_unit(source=_source(video_id="other-video")))),
    ("unknown_source_segment", _units(_source_unit(source=_source(segment_id="seg_999999")))),
    (
        "source_time_outside_transcript",
        _units(_source_unit(source=_source(end_sec=TRANSCRIPT_END + 60))),
    ),
    (
        "evidence_excerpt_not_in_segment",
        _units(_source_unit(source=_source(evidence_excerpt="never said this"))),
    ),
    ("evidence_excerpt_too_short", _units(_source_unit(source=_source(evidence_excerpt="a")))),
    (
        "missing_evidence_excerpt",
        _units(_source_unit(source=_source(evidence_excerpt=None))),
    ),
]

COVERAGE_CODES: list[tuple[str, Any]] = [
    ("coverage_windows_not_array", {"audit_attempts": 1, "windows": "CW-0001"}),
    ("window_not_object", _coverage(windows=["CW-0001"])),
    ("invalid_window_timing", _coverage(windows=[_window(start_sec=True)])),
    ("window_field_not_array", _coverage(windows=[_window(unresolved_items=1)])),
    ("missing_audit_attempts", {"status": "PARTIAL", "windows": [_window()]}),
    ("invalid_audit_attempts", _coverage(audit_attempts="1")),
    ("audit_attempts_over_cap", _coverage(audit_attempts=MAX_AUDIT_ATTEMPTS + 1)),
    ("unaudited_coverage_pass", _coverage(audit_attempts=0, status="PASS")),
    (
        "coverage_gap_or_overlap",
        _coverage(
            windows=[
                _window(window_id="CW-0001", start_sec=0.0, end_sec=4.0),
                _window(window_id="CW-0002", start_sec=6.0, end_sec=TRANSCRIPT_END),
            ]
        ),
    ),
    ("invalid_window_status", _coverage(windows=[_window(status="done")])),
    ("timeline_not_fully_covered", _coverage(windows=[_window(end_sec=TRANSCRIPT_END - 3)])),
    (
        "invalid_omission_reason",
        _coverage(windows=[_window(omitted_items=[{"type": "boring"}])]),
    ),
    (
        "missing_other_explanation",
        _coverage(windows=[_window(omitted_items=[{"type": "other_explained"}])]),
    ),
    ("false_coverage_pass", _coverage(status="PASS", windows=[_window(status="pending")])),
    (
        "omitted_window_without_accounting",
        _coverage(status="PASS", windows=[_window(status="omitted", omitted_items=[])]),
    ),
    (
        "covered_window_without_accounting",
        _coverage(status="PASS", windows=[_window(knowledge_units=[], omitted_items=[])]),
    ),
    (
        "pass_with_unresolved_items",
        _coverage(
            status="PASS",
            windows=[_window(unresolved_items=[{"type": "unclear", "note": "n"}])],
        ),
    ),
    # D-164: the window geometry, and the summary that used to be write-only.
    ("missing_window_size", _coverage(status="PASS", audit_attempts=1)),
    ("invalid_window_size", _coverage(window_size_sec=0)),
    (
        "window_wider_than_window_size",
        _coverage(
            window_size_sec=4,
            windows=[_window(start_sec=0.0, end_sec=TRANSCRIPT_END)],
        ),
    ),
    ("coverage_summary_not_object", _coverage(summary=[])),
    (
        "coverage_summary_disagrees_with_windows",
        _coverage(
            summary={
                "total_windows": 1,
                "covered_windows": 0,
                "pending_windows": 0,
                "unresolved_important_items": 0,
            }
        ),
    ),
]

#: D-164. The rules that need both documents, so they belong to neither alone:
#: a window's citations, checked against the window's own span.
COVERAGE_LINK_CODES: list[tuple[str, Any, Any]] = [
    (
        "coverage_references_unknown_unit",
        _coverage(windows=[_window(knowledge_units=["KU-999999"])]),
        _units(_source_unit()),
    ),
    (
        "window_knowledge_units_not_array",
        _coverage(windows=[_window(knowledge_units="KU-000001")]),
        _units(_source_unit()),
    ),
    (
        "coverage_pass_omits_source_units",
        _coverage(status="PASS", windows=[_window(knowledge_units=[], omitted_items=[
            {"type": "sponsor", "note": "A sponsor read."}
        ])]),
        _units(_source_unit()),
    ),
    # The bypass the audit demonstrated: every window marked covered, every one
    # naming the same unit from the first ten seconds.
    (
        "coverage_unit_outside_window",
        _coverage(
            window_size_sec=5,
            windows=[
                _window(window_id="CW-0001", start_sec=0.0, end_sec=5.0),
                _window(window_id="CW-0002", start_sec=5.0, end_sec=TRANSCRIPT_END),
            ],
        ),
        _units(_source_unit(source={
            "video_id": VIDEO_ID,
            "segment_id": "seg_000001",
            "start_sec": 0.0,
            "end_sec": 4.0,
            "evidence_excerpt": SEGMENT_TEXT,
        })),
    ),
    (
        "covered_window_without_evidence_in_it",
        _coverage(windows=[_window(knowledge_units=["KU-D-0001"])]),
        _units(_source_unit(), _derived_unit()),
    ),
]

WARNING_CODES: list[tuple[str, Any]] = [
    ("unstructured_statistic", _units(_source_unit(kind="statistic"))),
    (
        "claim_evidence_status_missing",
        _units(_source_unit(kind="claim", importance="high")),
    ),
    (
        "possible_duplicate_unit",
        _units(_source_unit(), _source_unit(id="KU-000002")),
    ),
]


@pytest.mark.parametrize("code,document", UNIT_CODES, ids=[code for code, _ in UNIT_CODES])
def test_the_unit_validator_emits(code: str, document: Any) -> None:
    result = validate_knowledge_units(document)
    assert result["status"] == "FAIL", f"{code}: the document was accepted"
    assert code in _codes(result), f"{code} not in {sorted(_codes(result))}"


@pytest.mark.parametrize(
    "code,document", RELATIONSHIP_CODES, ids=[code for code, _ in RELATIONSHIP_CODES]
)
def test_the_relationship_validator_emits(code: str, document: Any) -> None:
    result = validate_relationships(document, TWO_IDS)
    assert result["status"] == "FAIL", f"{code}: the document was accepted"
    assert code in _codes(result), f"{code} not in {sorted(_codes(result))}"


@pytest.mark.parametrize(
    "code,document", PROVENANCE_CODES, ids=[code for code, _ in PROVENANCE_CODES]
)
def test_the_provenance_validator_emits(code: str, document: Any) -> None:
    result = validate_provenance(document, TRANSCRIPT, SEGMENTS, VIDEO_ID)
    assert result["status"] == "FAIL", f"{code}: the document was accepted"
    assert code in _codes(result), f"{code} not in {sorted(_codes(result))}"


@pytest.mark.parametrize(
    "code,document", COVERAGE_CODES, ids=[code for code, _ in COVERAGE_CODES]
)
def test_the_coverage_validator_emits(code: str, document: Any) -> None:
    result = validate_coverage(document, TRANSCRIPT_END)
    assert result["status"] == "FAIL", f"{code}: the document was accepted"
    assert code in _codes(result), f"{code} not in {sorted(_codes(result))}"


@pytest.mark.parametrize("code,document", WARNING_CODES, ids=[code for code, _ in WARNING_CODES])
def test_the_unit_validator_warns(code: str, document: Any) -> None:
    """A warning is not a refusal: the status stays ``PASS`` and the note is made."""
    result = validate_knowledge_units(document)
    assert result["status"] == "PASS", result["errors"]
    assert code in {warning["code"] for warning in result["warnings"]}


@pytest.mark.parametrize(
    "code,coverage,units",
    COVERAGE_LINK_CODES,
    ids=[code for code, _, _ in COVERAGE_LINK_CODES],
)
def test_the_coverage_link_check_emits(code: str, coverage: Any, units: Any) -> None:
    errors = validate_coverage_links(coverage, units["units"])
    assert code in {error["code"] for error in errors}, sorted(
        {error["code"] for error in errors}
    )


def test_one_window_over_the_whole_timeline_cannot_claim_pass() -> None:
    """The first bypass the audit demonstrated, on a 30-minute run.

    Collapse six 300-second windows into a single ``[0, 1800]`` window citing
    one unit at 0-10s, and the coverage audit reported ``PASS`` over 29
    unaudited minutes. Nothing read ``window_size_sec``, so a window's span was
    whatever the document said it was.
    """
    collapsed = _coverage(
        status="PASS",
        audit_attempts=1,
        window_size_sec=300,
        windows=[_window(window_id="CW-0001", start_sec=0.0, end_sec=1800.0)],
    )
    result = validate_coverage(collapsed, 1800.0)
    assert result["status"] == "FAIL"
    assert "window_wider_than_window_size" in _codes(result)


def test_a_bundle_cannot_name_the_bound_it_is_measured_against(tmp_path: Path) -> None:
    """The third bypass: not a wider window, a wider *ruler*.

    `validate_coverage` measures every window against the ``window_size_sec``
    the audited document itself carries, and `_carry_coverage_scaffold_forward`
    restored the scaffold's value only when the bundle omitted it. So the
    window `test_one_window_over_the_whole_timeline_cannot_claim_pass` proves
    is refused came back by *stating* its own bound — identical geometry, one
    extra field, `FAIL` becomes `PASS`. That test cannot see this one, because
    it pins ``window_size_sec=300`` in its own fixture, which is the input the
    bypass changes.

    Both halves are asserted here: that the two documents differ only in the
    field, and that the carry-forward is what closes it.
    """
    honest = _coverage(
        status="PASS",
        audit_attempts=1,
        window_size_sec=300,
        windows=[_window(window_id="CW-0001", start_sec=0.0, end_sec=1795.0)],
    )
    assert validate_coverage(honest, 1795.0)["status"] == "FAIL"

    claimed = _coverage(
        status="PASS",
        audit_attempts=1,
        window_size_sec=1795.0,
        windows=[_window(window_id="CW-0001", start_sec=0.0, end_sec=1795.0)],
    )
    assert validate_coverage(claimed, 1795.0)["status"] == "PASS", (
        "the validator measures the document against itself; the guard is upstream"
    )

    # Upstream is the carry-forward, and it has to overwrite rather than fill in.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "coverage.json").write_text(
        json.dumps(
            _coverage(
                status="pending",
                audit_attempts=0,
                window_size_sec=300,
                windows=[_window(window_id="CW-0001", status="pending")],
            )
        ),
        encoding="utf-8",
    )
    _carry_coverage_scaffold_forward(run_dir, claimed)
    assert claimed["window_size_sec"] == 300, "the scaffold's bound is the run's bound"
    assert "window_wider_than_window_size" in _codes(validate_coverage(claimed, 1795.0))


def test_a_bundle_applied_without_a_scaffold_still_cannot_name_its_own_bound(
    tmp_path: Path,
) -> None:
    """The same rule where there is no scaffold left to carry forward.

    A run whose ``coverage.json`` was removed or damaged has no stored bound,
    and the bundle must not get to supply one: the widest window the format
    allows is what `create_pending_coverage` would have minted.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for stated in (1795.0, "wide", True, None):
        coverage: dict[str, Any] = {"windows": []}
        if stated is not None:
            coverage["window_size_sec"] = stated
        _carry_coverage_scaffold_forward(run_dir, coverage)
        assert coverage["window_size_sec"] == COVERAGE_WINDOW_SEC, stated

    narrower: dict[str, Any] = {"window_size_sec": 120, "windows": []}
    _carry_coverage_scaffold_forward(run_dir, narrower)
    assert narrower["window_size_sec"] == 120, "subdividing is honest work"


def test_every_window_naming_the_same_first_unit_cannot_claim_pass() -> None:
    """The second bypass: six honest windows, one unit, cited six times.

    The geometry is correct here — every window is exactly ``window_size_sec``
    and they tile the timeline — so only the link between a window and the
    evidence *inside it* can catch this one.
    """
    windows = [
        _window(
            window_id=f"CW-{index + 1:04d}",
            start_sec=float(index * 300),
            end_sec=float((index + 1) * 300),
            knowledge_units=["KU-000001"],
        )
        for index in range(6)
    ]
    coverage = _coverage(
        status="PASS", audit_attempts=1, window_size_sec=300, windows=windows
    )
    assert validate_coverage(coverage, 1800.0)["status"] == "PASS", (
        "the document is internally consistent; only the units expose it"
    )

    units = _units(
        _source_unit(
            source={
                "video_id": VIDEO_ID,
                "segment_id": "seg_000001",
                "start_sec": 0.0,
                "end_sec": 10.0,
                "evidence_excerpt": SEGMENT_TEXT,
            }
        )
    )
    errors = validate_coverage_links(coverage, units["units"])
    outside = [error for error in errors if error["code"] == "coverage_unit_outside_window"]
    assert [error["window_id"] for error in outside] == [
        "CW-0002",
        "CW-0003",
        "CW-0004",
        "CW-0005",
        "CW-0006",
    ], "the first window is the only one that unit is evidence for"


# ---------------------------------------------------------------------------
# T-227 — the Twitter medium: a post id and a codepoint span, and item coverage
#
# Same doctrine as everything above: each fixture differs from an honest one by
# exactly one defect, so a passing case proves the branch and nothing else.
# ---------------------------------------------------------------------------

POST_ID = "1795393908886712425"
OTHER_POST_ID = "1795265406191735191"
POST_TEXT = "Convolutional networks were introduced in 1989."


def _post_source(**overrides: Any) -> dict[str, Any]:
    # No run id: a post claim carries none, and the cross-run guard is the
    # `post_id` having to be an item of this run's capture.
    source = {
        "post_id": POST_ID,
        "start_char": 0,
        "end_char": 22,
        "evidence_excerpt": POST_TEXT[0:22],
    }
    source.update(overrides)
    return source


def _post_unit(**overrides: Any) -> dict[str, Any]:
    unit = {
        "id": "KU-000001",
        "kind": "claim",
        "source_class": "source",
        "content": "ConvNets were introduced in 1989.",
        "confidence": 0.9,
        "source": _post_source(),
    }
    unit.update(overrides)
    return unit


def _post_units(*units: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": "1.0",
        "video_id": POST_ID,
        "source_type": "twitter",
        "units": list(units),
    }
    document.update(overrides)
    return document


def _item(post_id: str = POST_ID, *, available: bool = True, text: Any = POST_TEXT) -> dict[str, Any]:
    item: dict[str, Any] = {
        "post_id": post_id,
        "availability": {"state": "available" if available else "unavailable"},
    }
    if available and text is not None:
        item["text"] = {"canonical": text, "form": "authored"}
    return item


def _capture(**overrides: Any) -> dict[str, Any]:
    capture = {
        "schema_version": "1.0",
        "items": [_item()],
        "anchor": {"post_id": POST_ID, "role": "single_post", "terminal_claim": "none"},
        "order": {"basis": "single_item"},
        "coverage": {
            "status": "PASS",
            "expected_item_count": 1,
            "included_post_ids": [POST_ID],
            "omitted_items": [],
        },
    }
    capture.update(overrides)
    return capture


def _coverage_item(**overrides: Any) -> dict[str, Any]:
    entry = {
        "item_id": "CI-0001",
        "post_id": POST_ID,
        "status": "covered",
        "knowledge_units": ["KU-000001"],
        "omitted_items": [],
        "unresolved_items": [],
    }
    entry.update(overrides)
    return entry


def _item_coverage(**overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": "1.0",
        "source_type": "twitter",
        "source_id": POST_ID,
        "basis": "items",
        "status": "PARTIAL",
        "audit_attempts": 1,
        "items": [_coverage_item()],
        "excluded_items": [],
    }
    document.update(overrides)
    return document


def test_an_honest_twitter_run_passes_every_validator() -> None:
    document = _post_units(_post_unit())
    assert validate_knowledge_units(document)["status"] == "PASS"
    assert validate_post_provenance(document, _capture())["status"] == "PASS"
    assert validate_item_coverage(_item_coverage(), _capture())["status"] == "PASS"
    assert validate_item_coverage_links(_item_coverage(), document["units"]) == []


def test_a_twitter_unit_is_not_asked_for_seconds_it_cannot_have() -> None:
    """The dispatch, stated as the defect it prevents (D-226).

    Before the medium was declared, `required` was the YouTube set
    unconditionally, so every post claim came back missing `video_id`,
    `segment_id`, `start_sec` and `end_sec` — four errors for a unit that is
    correct — and `invalid_source_timing` on top, because a bound that is absent
    is not a number.
    """
    result = validate_knowledge_units(_post_units(_post_unit()))
    assert result["status"] == "PASS", result["errors"]
    # And the same unit filed as a YouTube run is refused, so the dispatch is
    # not merely widening what everyone accepts.
    as_youtube = _post_units(_post_unit())
    del as_youtube["source_type"]
    codes = {error["code"] for error in validate_knowledge_units(as_youtube)["errors"]}
    assert "incomplete_provenance" in codes


POST_UNIT_CODES: list[tuple[str, Any]] = [
    ("unknown_source_type", _post_units(_post_unit(), source_type="mastodon")),
    (
        "invalid_source_span",
        _post_units(_post_unit(source=_post_source(start_char=True))),
    ),
]


POST_PROVENANCE_CODES: list[tuple[str, Any, Any]] = [
    (
        "unknown_source_post",
        _post_units(_post_unit(source=_post_source(post_id="999999999999999999"))),
        _capture(),
    ),
    (
        "claim_cites_unavailable_post",
        _post_units(_post_unit()),
        _capture(items=[_item(available=False)]),
    ),
    (
        "source_post_without_text",
        _post_units(_post_unit()),
        _capture(items=[_item(text=None)]),
    ),
    (
        "invalid_source_span",
        _post_units(_post_unit(source=_post_source(end_char="22"))),
        _capture(),
    ),
    (
        "source_span_outside_post",
        _post_units(_post_unit(source=_post_source(end_char=len(POST_TEXT) + 10))),
        _capture(),
    ),
    (
        # The span points at one phrase and the excerpt quotes another. Both
        # are "in the post", which is why the YouTube substring rule would
        # have accepted this one.
        "evidence_excerpt_is_not_its_span",
        _post_units(_post_unit(source=_post_source(evidence_excerpt=POST_TEXT[28:38]))),
        _capture(),
    ),
]


@pytest.mark.parametrize("code,document,capture", POST_PROVENANCE_CODES, ids=[c for c, _, _ in POST_PROVENANCE_CODES])
def test_post_provenance_defects_are_named(code: str, document: Any, capture: Any) -> None:
    result = validate_post_provenance(document, capture)
    assert result["status"] == "FAIL"
    assert code in {error["code"] for error in result["errors"]}


ITEM_COVERAGE_CODES: list[tuple[str, Any, Any]] = [
    ("coverage_items_not_array", {"audit_attempts": 1, "items": "CI-0001"}, _capture()),
    ("coverage_basis_not_items", _item_coverage(basis="windows"), _capture()),
    ("coverage_item_not_object", _item_coverage(items=["CI-0001"]), _capture()),
    (
        "coverage_item_field_not_array",
        _item_coverage(items=[_coverage_item(unresolved_items=1)]),
        _capture(),
    ),
    (
        "coverage_item_without_post_id",
        _item_coverage(items=[_coverage_item(post_id="")]),
        _capture(),
    ),
    (
        "duplicate_coverage_item",
        _item_coverage(items=[_coverage_item(), _coverage_item(item_id="CI-0002")]),
        _capture(),
    ),
    (
        "coverage_item_not_in_capture",
        _item_coverage(items=[_coverage_item(post_id="999999999999999999")]),
        _capture(),
    ),
    (
        "invalid_coverage_item_status",
        _item_coverage(items=[_coverage_item(status="audited")]),
        _capture(),
    ),
    (
        # The acceptance clause: an included post with no entry at all.
        "included_post_without_coverage",
        _item_coverage(items=[]),
        _capture(),
    ),
    (
        "unavailable_post_not_omitted",
        _item_coverage(items=[_coverage_item(status="covered")]),
        _capture(items=[_item(available=False)]),
    ),
    (
        "unavailable_post_with_units",
        _item_coverage(items=[_coverage_item(status="omitted", omitted_items=[{"type": "source_unavailable"}])]),
        _capture(items=[_item(available=False)]),
    ),
    (
        "omitted_item_without_accounting",
        _item_coverage(status="PASS", items=[_coverage_item(status="omitted", knowledge_units=[])]),
        _capture(),
    ),
    (
        "covered_item_without_accounting",
        _item_coverage(status="PASS", items=[_coverage_item(knowledge_units=[])]),
        _capture(),
    ),
    (
        # A run cannot be more complete than the evidence under it.
        "coverage_pass_over_incomplete_capture",
        _item_coverage(status="PASS"),
        _capture(
            coverage={
                "status": "PARTIAL",
                "expected_item_count": 2,
                "included_post_ids": [POST_ID],
                "omitted_items": [{"post_id": OTHER_POST_ID, "reason": "by another author"}],
            }
        ),
    ),
    (
        "coverage_summary_disagrees_with_items",
        _item_coverage(summary={"total_items": 7}),
        _capture(),
    ),
]


@pytest.mark.parametrize("code,document,capture", ITEM_COVERAGE_CODES, ids=[c for c, _, _ in ITEM_COVERAGE_CODES])
def test_item_coverage_defects_are_named(code: str, document: Any, capture: Any) -> None:
    result = validate_item_coverage(document, capture)
    assert result["status"] == "FAIL"
    assert code in {error["code"] for error in result["errors"]}


ITEM_COVERAGE_LINK_CODES: list[tuple[str, Any, Any]] = [
    (
        "coverage_item_knowledge_units_not_array",
        _item_coverage(items=[_coverage_item(knowledge_units="KU-000001")]),
        _post_units(_post_unit()),
    ),
    (
        "coverage_names_unknown_unit",
        _item_coverage(items=[_coverage_item(knowledge_units=["KU-999999"])]),
        _post_units(_post_unit()),
    ),
    (
        # A claim about another post, cited under this one: the entry looks
        # covered and has no evidence of its own.
        "unit_cited_under_another_post",
        _item_coverage(items=[_coverage_item()]),
        _post_units(_post_unit(source=_post_source(post_id=OTHER_POST_ID))),
    ),
    (
        "covered_item_without_own_evidence",
        _item_coverage(items=[_coverage_item(knowledge_units=[])]),
        _post_units(_post_unit()),
    ),
    (
        "pass_with_uncited_units",
        _item_coverage(status="PASS", items=[_coverage_item(knowledge_units=[], omitted_items=[{"type": "off_topic"}])]),
        _post_units(_post_unit()),
    ),
]


@pytest.mark.parametrize("code,coverage,knowledge", ITEM_COVERAGE_LINK_CODES, ids=[c for c, _, _ in ITEM_COVERAGE_LINK_CODES])
def test_item_coverage_link_defects_are_named(code: str, coverage: Any, knowledge: Any) -> None:
    errors = validate_item_coverage_links(coverage, knowledge["units"])
    assert code in {error["code"] for error in errors}


@pytest.mark.parametrize("code,document", POST_UNIT_CODES, ids=[c for c, _ in POST_UNIT_CODES])
def test_post_unit_defects_are_named(code: str, document: Any) -> None:
    result = validate_knowledge_units(document)
    assert code in {error["code"] for error in result["errors"]}


def test_every_emittable_code_is_covered_here() -> None:
    """The guard that keeps the lists above from going stale.

    Reads the codes out of the module's own source, so a rejection branch added
    later without a case fails this test rather than joining the 29 the audit
    found sitting untested.
    """
    import re
    from pathlib import Path

    import x2knwldg.validators as module

    emittable = set(
        re.findall(r'"code":\s*"([a-z_]+)"', Path(module.__file__).read_text(encoding="utf-8"))
    )
    # The two codes chosen by `_evidence_excerpt_error` and returned through a
    # variable rather than written at the append site.
    emittable |= {
        "missing_evidence_excerpt",
        "evidence_excerpt_not_a_string",
        "empty_evidence_excerpt",
        "evidence_excerpt_too_short",
    }
    covered = {
        code
        for code, _ in (
            *UNIT_CODES,
            *RELATIONSHIP_CODES,
            *PROVENANCE_CODES,
            *COVERAGE_CODES,
            *WARNING_CODES,
        )
    }
    covered |= {code for code, _, _ in COVERAGE_LINK_CODES}
    # T-227's medium-dispatched validators, cased in the same file for the same
    # reason: one place that proves every code's branch still fires.
    covered |= {code for code, _ in POST_UNIT_CODES}
    covered |= {code for code, _, _ in POST_PROVENANCE_CODES}
    covered |= {code for code, _, _ in ITEM_COVERAGE_CODES}
    covered |= {code for code, _, _ in ITEM_COVERAGE_LINK_CODES}
    # Named elsewhere in this file, by the tests that introduced them.
    covered |= {"source_time_outside_segment", "invalid_source_timing"}
    missing = sorted(emittable - covered)
    assert not missing, (
        "these rejection codes have no case in this file, so nothing proves the "
        f"branch that emits them still fires: {missing}"
    )


def test_a_source_time_outside_its_own_segment_is_named() -> None:
    """Inside the transcript, outside the segment the unit cites."""
    segments = {
        "segments": [
            {"segment_id": "seg_000001", "start_sec": 0.0, "end_sec": 4.0, "text": SEGMENT_TEXT},
            {"segment_id": "seg_000002", "start_sec": 4.0, "end_sec": TRANSCRIPT_END, "text": "x"},
        ]
    }
    result = validate_provenance(
        _units(_source_unit(source=_source(start_sec=0.0, end_sec=8.0))),
        TRANSCRIPT,
        segments,
        VIDEO_ID,
    )
    assert result["status"] == "FAIL"
    assert "source_time_outside_segment" in _codes(result)
