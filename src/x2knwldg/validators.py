from __future__ import annotations

import unicodedata
from typing import Any

from .ids import is_id_part
from .constants import (
    COVERAGE_STATUSES,
    DERIVED_KINDS,
    KNOWLEDGE_KINDS,
    # WORKFLOW.md §4.4 and CLAUDE.md: "Run coverage repair no more than three
    # total audit attempts."
    MAX_AUDIT_ATTEMPTS,
    OMISSION_REASONS,
    RELATION_TYPES,
    SOURCE_KINDS,
    # The one timing epsilon. Six independent copies were six chances to disagree.
    TIME_TOLERANCE_SEC,
)
from .transcripts import clean_text

# An excerpt shorter than this cannot be evidence: a one- or two-character
# fragment is a substring of almost every segment, so the "excerpt appears in
# the segment" test would pass without proving anything.
MIN_EVIDENCE_EXCERPT_CHARS = 3

# Categories that carry no visible glyph: control (Cc), format (Cf, which is
# where U+200B-adjacent joiners and U+FEFF live), and every kind of space.
# Counting only visible characters keeps the excerpt rules independent of what
# ``clean_text`` happens to strip today.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})
# U+200B ZERO WIDTH SPACE is category Zs in some Unicode revisions and Cf in
# others; listing it explicitly makes the rule version-independent.
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\u2060\ufeff")


def _visible_length(text: str) -> int:
    """Number of characters in ``text`` that actually render as content."""
    return sum(
        1
        for character in text
        if character not in _ZERO_WIDTH
        and unicodedata.category(character) not in _INVISIBLE_CATEGORIES
    )


def _evidence_excerpt_error(value: Any, minimum: int = 1) -> str | None:
    """Return an error code when ``value`` is not usable evidence, else ``None``.

    Defect D-021: every degenerate excerpt used to satisfy both the unit and the
    provenance validator. ``" "`` and ``"\u200b"`` survived the truthiness test
    in ``validate_knowledge_units``; ``"<b>"`` cleaned away to ``""`` and so
    skipped the substring test in ``validate_provenance``; the integer ``0`` was
    a type confusion that ``str(...)`` laundered into ``"0"``. An excerpt is now
    evidence only if it is a string with real, visible content.
    """
    if value is None:
        return "missing_evidence_excerpt"
    if not isinstance(value, str):
        # bool/int/float/list/dict: never a quotation, and str() would have
        # turned each of them into a plausible-looking excerpt.
        return "evidence_excerpt_not_a_string"
    if _visible_length(value) == 0 or not clean_text(value):
        # Whitespace, zero-width characters, or markup that cleans to nothing.
        return "empty_evidence_excerpt"
    if _visible_length(clean_text(value)) < minimum:
        return "evidence_excerpt_too_short"
    return None


def _result(errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings}


def validate_knowledge_units(document: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    units = document.get("units") if isinstance(document, dict) else document
    if not isinstance(units, list):
        return _result([{"code": "units_not_array"}], warnings)
    ids: set[str] = set()
    normalized_seen: dict[str, str] = {}
    for index, unit in enumerate(units):
        location = unit.get("id", index) if isinstance(unit, dict) else index
        if not isinstance(unit, dict):
            errors.append({"code": "unit_not_object", "unit": location})
            continue
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id:
            errors.append({"code": "missing_id", "unit": location})
        elif unit_id in ids:
            errors.append({"code": "duplicate_id", "unit": unit_id})
        else:
            # An id that cannot become a global id (D-011) would leave the unit
            # unaddressable by the index and the API, so it is rejected here
            # rather than crashing rebuild_library later (D-018).
            if not is_id_part(unit_id):
                errors.append({"code": "invalid_id", "unit": unit_id})
            ids.add(unit_id)
        kind = unit.get("kind")
        if kind not in KNOWLEDGE_KINDS:
            errors.append({"code": "invalid_kind", "unit": location, "value": kind})
        source_class = unit.get("source_class")
        if source_class not in {"source", "derived"}:
            errors.append({"code": "invalid_source_class", "unit": location})
        # Defect D-022: only the union of SOURCE_KINDS and DERIVED_KINDS was
        # ever checked, so a `quote` could declare itself derived and skip the
        # evidence block entirely — a fabricated quotation passed both
        # validators. The two sets are disjoint, so the declared kind fixes the
        # provenance shape the unit owes, and disagreement is itself a failure.
        expected_class = (
            "source" if kind in SOURCE_KINDS else "derived" if kind in DERIVED_KINDS else None
        )
        if expected_class is not None and source_class in {"source", "derived"}:
            if source_class != expected_class:
                errors.append(
                    {
                        "code": "kind_source_class_mismatch",
                        "unit": location,
                        "kind": kind,
                        "source_class": source_class,
                        "expected_source_class": expected_class,
                    }
                )
        # The obligation follows the kind as well as the declaration, so a unit
        # cannot shed either duty by mislabelling itself.
        requires_provenance = source_class == "source" or kind in SOURCE_KINDS
        requires_derivation = source_class == "derived" or kind in DERIVED_KINDS
        confidence = unit.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append({"code": "invalid_confidence", "unit": location})
        if not str(unit.get("content") or "").strip():
            errors.append({"code": "missing_content", "unit": location})
        if requires_provenance:
            source = unit.get("source")
            required = {"video_id", "segment_id", "start_sec", "end_sec", "evidence_excerpt"}
            if not isinstance(source, dict):
                errors.append({"code": "missing_source", "unit": location})
            else:
                missing = sorted(field for field in required if source.get(field) in (None, ""))
                if missing:
                    errors.append({"code": "incomplete_provenance", "unit": location, "fields": missing})
                excerpt_error = _evidence_excerpt_error(source.get("evidence_excerpt"))
                if excerpt_error is not None and "evidence_excerpt" not in missing:
                    errors.append(
                        {
                            "code": excerpt_error,
                            "unit": location,
                            "type": type(source.get("evidence_excerpt")).__name__,
                        }
                    )
        if requires_derivation:
            if not isinstance(unit.get("derived_from"), list) or not unit.get("derived_from"):
                errors.append({"code": "missing_derived_from", "unit": location})
            if not str(unit.get("derivation_note") or "").strip():
                errors.append({"code": "missing_derivation_note", "unit": location})
        if unit.get("kind") == "statistic":
            missing_numeric = [
                field for field in ("value", "unit", "context") if unit.get(field) in (None, "")
            ]
            if missing_numeric:
                warnings.append(
                    {"code": "unstructured_statistic", "unit": location, "fields": missing_numeric}
                )
        if unit.get("importance") == "high" and unit.get("kind") == "claim":
            if not unit.get("supported_by") and not unit.get("evidence_status"):
                warnings.append({"code": "claim_evidence_status_missing", "unit": location})
        normalized = clean_text(
            str(unit.get("normalized_statement") or unit.get("content") or "")
        ).casefold()
        if normalized:
            if normalized in normalized_seen:
                warnings.append(
                    {
                        "code": "possible_duplicate_unit",
                        "unit": location,
                        "matches": normalized_seen[normalized],
                    }
                )
            elif isinstance(unit_id, str):
                normalized_seen[normalized] = unit_id

    for unit in units:
        if not isinstance(unit, dict) or unit.get("source_class") != "derived":
            continue
        for source_id in unit.get("derived_from", []):
            if source_id not in ids:
                errors.append(
                    {"code": "unknown_derived_source", "unit": unit.get("id"), "source_id": source_id}
                )
    return _result(errors, warnings)


def validate_relationships(document: Any, unit_ids: set[str]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    relationships = document.get("relationships") if isinstance(document, dict) else document
    if not isinstance(relationships, list):
        return _result([{"code": "relationships_not_array"}], warnings)
    for index, edge in enumerate(relationships):
        if not isinstance(edge, dict):
            errors.append({"code": "relationship_not_object", "relationship": index})
            continue
        source = edge.get("from")
        target = edge.get("to")
        relation = edge.get("relation")
        if source not in unit_ids:
            errors.append({"code": "unknown_from", "relationship": index, "value": source})
        if target not in unit_ids:
            errors.append({"code": "unknown_to", "relationship": index, "value": target})
        if relation not in RELATION_TYPES:
            errors.append({"code": "invalid_relation", "relationship": index, "value": relation})
        if source == target and not edge.get("intentional_self_loop"):
            errors.append({"code": "unintentional_self_loop", "relationship": index})
        confidence = edge.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append({"code": "invalid_confidence", "relationship": index})
        if edge.get("source_class") not in {"source", "derived"}:
            errors.append({"code": "invalid_source_class", "relationship": index})
    return _result(errors, warnings)


def validate_provenance(
    knowledge_document: Any,
    transcript_document: Any,
    segments_document: Any,
    video_id: str,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    units = knowledge_document.get("units", []) if isinstance(knowledge_document, dict) else []
    segments = {
        segment.get("segment_id"): segment
        for segment in segments_document.get("segments", [])
        if isinstance(segment, dict) and segment.get("segment_id")
    }
    transcript_end = max(
        (
            caption.get("end_sec", 0)
            for caption in transcript_document.get("captions", [])
            if isinstance(caption, dict)
        ),
        default=0,
    )
    for unit in units:
        if not isinstance(unit, dict) or unit.get("source_class") != "source":
            continue
        unit_id = unit.get("id")
        source = unit.get("source")
        if not isinstance(source, dict):
            continue
        if source.get("video_id") != video_id:
            errors.append({"code": "source_video_mismatch", "unit": unit_id})
        segment_id = source.get("segment_id")
        segment = segments.get(segment_id)
        if segment is None:
            errors.append({"code": "unknown_source_segment", "unit": unit_id, "value": segment_id})
            continue
        start = source.get("start_sec")
        end = source.get("end_sec")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            if start < 0 or end < start or end > transcript_end + TIME_TOLERANCE_SEC:
                errors.append({"code": "source_time_outside_transcript", "unit": unit_id})
            if start < segment.get("start_sec", 0) - TIME_TOLERANCE_SEC or end > segment.get("end_sec", 0) + TIME_TOLERANCE_SEC:
                errors.append({"code": "source_time_outside_segment", "unit": unit_id})
        raw_excerpt = source.get("evidence_excerpt")
        excerpt_error = _evidence_excerpt_error(raw_excerpt, MIN_EVIDENCE_EXCERPT_CHARS)
        if excerpt_error is not None:
            # An excerpt that cleans away to nothing must fail here rather than
            # skip the substring test and be reported as proven provenance.
            errors.append(
                {
                    "code": excerpt_error,
                    "unit": unit_id,
                    "type": type(raw_excerpt).__name__,
                }
            )
            continue
        excerpt = clean_text(raw_excerpt).casefold()
        segment_text = clean_text(str(segment.get("text") or "")).casefold()
        if excerpt not in segment_text:
            errors.append({"code": "evidence_excerpt_not_in_segment", "unit": unit_id})
    return _result(errors, warnings)


def validate_coverage(document: Any, transcript_end_sec: float) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(document, dict) or not isinstance(document.get("windows"), list):
        return _result([{"code": "coverage_windows_not_array"}], warnings)
    windows = document["windows"]
    # The three-attempt repair cap used to be optional and self-reported,
    # so omitting the count skipped it altogether. The count is now required;
    # a coverage document that will not say how many audits it took cannot be
    # validated against the cap, and an unverifiable claim is a failure.
    audit_attempts = document.get("audit_attempts")
    if "audit_attempts" not in document or audit_attempts is None:
        errors.append({"code": "missing_audit_attempts", "max": MAX_AUDIT_ATTEMPTS})
    elif isinstance(audit_attempts, bool) or not isinstance(audit_attempts, int):
        errors.append({"code": "invalid_audit_attempts", "value": audit_attempts})
    elif audit_attempts < 0:
        errors.append({"code": "invalid_audit_attempts", "value": audit_attempts})
    elif audit_attempts > MAX_AUDIT_ATTEMPTS:
        errors.append(
            {
                "code": "audit_attempts_over_cap",
                "value": audit_attempts,
                "max": MAX_AUDIT_ATTEMPTS,
            }
        )
    elif audit_attempts == 0 and document.get("status") == "PASS":
        # Zero attempts is the honest state of a freshly scaffolded, never
        # audited coverage document — but it can never be a PASS.
        errors.append({"code": "unaudited_coverage_pass", "value": audit_attempts})
    cursor = 0.0
    unresolved = 0
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            errors.append({"code": "window_not_object", "window": index})
            continue
        start = window.get("start_sec")
        end = window.get("end_sec")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append({"code": "invalid_window_timing", "window": index})
            continue
        if abs(start - cursor) > TIME_TOLERANCE_SEC:
            errors.append({"code": "coverage_gap_or_overlap", "window": index, "expected": cursor, "actual": start})
        if end < start:
            errors.append({"code": "invalid_window_timing", "window": index})
        cursor = end
        if window.get("status") not in COVERAGE_STATUSES:
            errors.append({"code": "invalid_window_status", "window": index})
        unresolved += len(window.get("unresolved_items") or [])
        for omission in window.get("omitted_items") or []:
            reason = omission.get("type") if isinstance(omission, dict) else None
            if reason not in OMISSION_REASONS:
                errors.append({"code": "invalid_omission_reason", "window": index, "value": reason})
            if reason == "other_explained" and not str(omission.get("note") or "").strip():
                errors.append({"code": "missing_other_explanation", "window": index})
    if abs(cursor - transcript_end_sec) > TIME_TOLERANCE_SEC:
        errors.append({"code": "timeline_not_fully_covered", "expected": transcript_end_sec, "actual": cursor})
    if document.get("status") == "PASS":
        for index, window in enumerate(windows):
            if not isinstance(window, dict):
                continue
            status = window.get("status")
            if status not in {"covered", "omitted"}:
                errors.append({"code": "false_coverage_pass", "window": index})
            if status == "omitted" and not window.get("omitted_items"):
                errors.append({"code": "omitted_window_without_accounting", "window": index})
            if status == "covered" and not (
                window.get("knowledge_units") or window.get("omitted_items")
            ):
                errors.append({"code": "covered_window_without_accounting", "window": index})
        if unresolved:
            errors.append({"code": "pass_with_unresolved_items", "count": unresolved})
    return _result(errors, warnings)
