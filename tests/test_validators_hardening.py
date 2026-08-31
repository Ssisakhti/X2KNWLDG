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

from typing import Any

import pytest

from x2knwldg.constants import DERIVED_KINDS, SOURCE_KINDS
from x2knwldg.validators import (
    MAX_AUDIT_ATTEMPTS,
    MIN_EVIDENCE_EXCERPT_CHARS,
    validate_coverage,
    validate_knowledge_units,
    validate_provenance,
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
