from __future__ import annotations

import unicodedata
from typing import Any, TypeGuard

from .constants import (
    COVERAGE_STATUSES,
    COVERAGE_WINDOW_SEC,
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
from .ids import is_id_part
from .io import is_finite_seconds
from .transcripts import clean_text, transcript_end_sec

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


def _is_seconds(value: Any) -> TypeGuard[float]:
    """Whether ``value`` is a timestamp this validator can actually check.

    Defect D-070: ``validate_provenance`` guarded both of its range checks
    behind ``isinstance(start, (int, float))`` and *skipped* them when the guard
    failed, so a source block timed ``"99999"`` — a string, which the presence
    test in ``validate_knowledge_units`` counts as provided — came back as
    proven provenance. The validator failed open on precisely the shapes it
    exists to reject.

    ``bool`` is excluded because ``True`` is an ``int`` in Python and is not a
    time. Non-finite floats are excluded because every comparison against
    ``NaN`` is ``False``, so a ``NaN`` bound slips past an ``end < start`` test
    and lands in ``report.md`` as a moment the video does not contain. Mirrors
    ``ids._require_seconds`` and ``segmenter._require_seconds``, which raise
    where this one collects an error code.
    """
    return is_finite_seconds(value)


def _seconds_or(value: Any, fallback: float) -> float:
    """*value* as a number of seconds, or *fallback* when it is not one."""
    return float(value) if is_finite_seconds(value) else fallback


def _as_list(value: Any) -> list[Any]:
    """The list a coverage window field holds, or ``[]`` when it holds anything else.

    Defect D-072: three window fields are read as collections —
    ``len(unresolved_items)``, iteration over ``omitted_items``, and a
    truthiness test on ``knowledge_units``. None checked its type, so
    ``unresolved_items: 5`` crashed ``len()``, a string ``omitted_items`` was
    iterated one character at a time into meaningless
    ``invalid_omission_reason`` errors, and ``knowledge_units: "u1"`` satisfied
    the ``covered_window_without_accounting`` guard because a non-empty string
    is truthy — a window accounting for no units at all reported ``PASS``.

    Paired with the ``window_field_not_array`` error: that names the wrong type
    once, and reading the field as empty here lets the remaining checks run on
    the rest of the document instead of crashing or inventing errors.
    """
    return value if isinstance(value, list) else []


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
                # D-070: the presence test above counts the string "99999" as
                # provided, and a bound that is not a number cannot be checked
                # against anything. Reported here as well as in
                # ``validate_provenance`` because this is the validator
                # ``import_transcript`` runs on its own.
                unusable_timing = sorted(
                    field
                    for field in ("start_sec", "end_sec")
                    if field not in missing and not _is_seconds(source.get(field))
                )
                if unusable_timing:
                    errors.append(
                        {
                            "code": "invalid_source_timing",
                            "unit": location,
                            "fields": unusable_timing,
                            "types": {
                                field: type(source.get(field)).__name__
                                for field in unusable_timing
                            },
                        }
                    )
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
    # D-077: one implementation of "where does the transcript end", shared with
    # `pipeline.validate_run`, `artifacts.apply_extraction_bundle` and
    # `transcript_integrity`. It used to exist four times at three guard levels.
    transcript_end = transcript_end_sec(
        transcript_document.get("captions") if isinstance(transcript_document, dict) else None
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
        if not _is_seconds(start) or not _is_seconds(end):
            # D-070: the two range checks below were guarded by
            # `isinstance(start, (int, float))` and *nothing else*, so a
            # non-number skipped both and the unit came back reported as
            # proven. The guard was never the bug; the missing error was. A
            # citation whose time cannot be compared to the transcript is
            # unverifiable, and an unverifiable citation is a failure.
            errors.append(
                {
                    "code": "invalid_source_timing",
                    "unit": unit_id,
                    "start_sec_type": type(start).__name__,
                    "end_sec_type": type(end).__name__,
                }
            )
        else:
            # Reached only with two comparable bounds. Falling through to the
            # excerpt check rather than `continue`-ing keeps a unit that is
            # wrong in two ways reported as wrong in two ways.
            if start < 0 or end < start or end > transcript_end + TIME_TOLERANCE_SEC:
                errors.append({"code": "source_time_outside_transcript", "unit": unit_id})
            # D-114: through `_seconds_or`, because a segment bound is read from
            # the same untrusted document as everything else here — a string
            # bound used to raise `TypeError` from inside the comparison, which
            # is the D-077 family of defect one level down.
            segment_start = _seconds_or(segment.get("start_sec"), 0.0)
            segment_end = _seconds_or(segment.get("end_sec"), 0.0)
            if start < segment_start - TIME_TOLERANCE_SEC or end > segment_end + TIME_TOLERANCE_SEC:
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
        # `_evidence_excerpt_error` returns non-`None` for anything that is not
        # a string, so the fallback is unreachable — written out rather than
        # asserted so the narrowing is visible to a reader and to the checker.
        excerpt = clean_text(raw_excerpt if isinstance(raw_excerpt, str) else "").casefold()
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
    # D-164: `window_size_sec` is what `constants.py` calls part of the file
    # format, and nothing in the package read it. Without it a window's span is
    # whatever the document says it is, so six 300-second windows could be
    # collapsed into one `[0, 1800]` window citing a single unit at 0-10s and
    # the audit still reported `PASS` over 29 unaudited minutes.
    window_size = document.get("window_size_sec")
    if window_size is not None and (not _is_seconds(window_size) or window_size <= 0):
        errors.append({"code": "invalid_window_size", "value": window_size})
        window_size = None
    elif window_size is None and document.get("status") == "PASS":
        # Absent, and the document claims PASS: the geometry cannot be checked,
        # and an unverifiable claim is a failure. Absent on a PARTIAL document
        # is the honest state of a run still being worked on.
        errors.append({"code": "missing_window_size", "expected": COVERAGE_WINDOW_SEC})

    cursor = 0.0
    unresolved = 0
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            errors.append({"code": "window_not_object", "window": index})
            continue
        # D-072: checked before anything reads these as collections, so a
        # wrong type is named once rather than crashing `len()` or being
        # iterated character by character. Absence stays the business of the
        # accounting checks below, which already treat an empty window as
        # unaccounted for.
        malformed = sorted(
            field
            for field in ("knowledge_units", "omitted_items", "unresolved_items")
            if field in window and not isinstance(window[field], list)
        )
        if malformed:
            errors.append(
                {
                    "code": "window_field_not_array",
                    "window": index,
                    "fields": malformed,
                    "types": {field: type(window[field]).__name__ for field in malformed},
                }
            )
        start = window.get("start_sec")
        end = window.get("end_sec")
        if not _is_seconds(start) or not _is_seconds(end):
            # D-070/D-072: `isinstance(True, (int, float))` is True in Python,
            # so a window bounded by booleans validated as the range [0, 1],
            # and a NaN bound slipped past `end < start` because every
            # comparison against NaN is False. `ids._require_seconds` and
            # `segmenter._require_seconds` already excluded both; this
            # validator was the one that did not.
            errors.append(
                {
                    "code": "invalid_window_timing",
                    "window": index,
                    "start_sec_type": type(start).__name__,
                    "end_sec_type": type(end).__name__,
                }
            )
            continue
        if abs(start - cursor) > TIME_TOLERANCE_SEC:
            errors.append({"code": "coverage_gap_or_overlap", "window": index, "expected": cursor, "actual": start})
        if end < start:
            errors.append({"code": "invalid_window_timing", "window": index})
        elif _is_seconds(window_size) and end - start > window_size + TIME_TOLERANCE_SEC:
            # A one-sided bound, deliberately. `create_pending_coverage` mints
            # windows of exactly `window_size_sec` (the last owns whatever
            # remains), and an audit is free to *subdivide* one — auditing at a
            # finer granularity than the scaffold is honest work, and the
            # committed `partial-run` fixture does exactly that. What no audit
            # may do is **coarsen**: a window wider than `window_size_sec`
            # covers more of the timeline per citation than the format allows,
            # which is how six 300-second windows became one `[0, 1800]` window
            # citing a single unit at 0-10s and still reported `PASS`.
            errors.append(
                {
                    "code": "window_wider_than_window_size",
                    "window": index,
                    "window_id": window.get("window_id"),
                    "max": window_size,
                    "actual": round(end - start, 3),
                }
            )
        cursor = end
        if window.get("status") not in COVERAGE_STATUSES:
            errors.append({"code": "invalid_window_status", "window": index})
        unresolved += len(_as_list(window.get("unresolved_items")))
        for omission in _as_list(window.get("omitted_items")):
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
            if status == "omitted" and not _as_list(window.get("omitted_items")):
                errors.append({"code": "omitted_window_without_accounting", "window": index})
            if status == "covered" and not (
                _as_list(window.get("knowledge_units")) or _as_list(window.get("omitted_items"))
            ):
                errors.append({"code": "covered_window_without_accounting", "window": index})
        if unresolved:
            errors.append({"code": "pass_with_unresolved_items", "count": unresolved})
    errors.extend(_coverage_summary_errors(document, windows, unresolved))
    return _result(errors, warnings)


def _coverage_summary_errors(
    document: Any, windows: list[Any], unresolved: int
) -> list[dict[str, Any]]:
    """The ``summary`` block, recomputed and compared (D-164).

    It was written by ``create_pending_coverage`` and read by nothing — not by
    a validator, not by ``_coverage_markdown``, which iterates the windows
    directly. So ``summary.covered_windows`` could say ``0`` while every window
    said ``covered``, and the two halves of one document could disagree with
    nothing to say so. Every field is derived from the windows, so the honest
    check is to derive them again.
    """
    summary = document.get("summary")
    if summary is None:
        return []
    if not isinstance(summary, dict):
        return [{"code": "coverage_summary_not_object", "type": type(summary).__name__}]
    statuses = [
        window.get("status") if isinstance(window, dict) else None for window in windows
    ]
    expected = {
        "total_windows": len(windows),
        "covered_windows": sum(1 for status in statuses if status == "covered"),
        "pending_windows": sum(1 for status in statuses if status == "pending"),
        "unresolved_important_items": unresolved,
    }
    return [
        {
            "code": "coverage_summary_disagrees_with_windows",
            "field": field,
            "stated": summary[field],
            "actual": value,
        }
        for field, value in expected.items()
        if field in summary and summary[field] != value
    ]


def validate_coverage_links(coverage: Any, units: Any) -> list[dict[str, Any]]:
    """``coverage.json`` cross-checked against ``knowledge_units.json``.

    :func:`validate_coverage` reads one document, so it can confirm that a
    window *names* units without knowing whether any of them exist — or, before
    D-164, whether any of them has anything to do with the stretch of time the
    window covers. Nothing tied a window's citations to its own span, so
    ``PASS`` was structurally unverifiable: keep all six 300-second windows,
    mark every one ``covered``, name the same unit from 0-10s in each, and the
    audit passed with 29 of 30 minutes unaudited by construction.

    Three rules, and the third is the new one:

    * A named unit must exist.
    * A ``PASS`` must account for every ``source`` unit.
    * A named ``source`` unit's evidence must **overlap the window that names
      it**, and a ``covered`` window must have at least one such unit — or an
      accounted omission, which is the other honest way for a window to be
      covered without a citation. ``derived`` units carry no timing and can
      never anchor a window; they may still be named beside one that does.

    One implementation, called by ``pipeline.validate_run`` and by
    ``artifacts.apply_extraction_bundle``, which each carried a partial copy.
    """
    errors: list[dict[str, Any]] = []
    if not isinstance(coverage, dict) or not isinstance(coverage.get("windows"), list):
        # `validate_coverage` already reports the shape failure.
        return errors
    unit_list = [unit for unit in _as_list(units) if isinstance(unit, dict)]
    by_id = {
        unit["id"]: unit for unit in unit_list if isinstance(unit.get("id"), str) and unit["id"]
    }

    referenced: set[str] = set()
    for index, window in enumerate(coverage["windows"]):
        if not isinstance(window, dict):
            continue
        named = window.get("knowledge_units") or []
        if not isinstance(named, list):
            errors.append({"code": "window_knowledge_units_not_array", "window": index})
            continue
        raw_start = window.get("start_sec")
        raw_end = window.get("end_sec")
        # `validate_coverage` reports an unusable bound; here it only means the
        # window cannot be compared with anything, so the timing rules below are
        # skipped rather than restated as a second failure.
        span: tuple[float, float] | None = (
            (raw_start, raw_end)
            if _is_seconds(raw_start) and _is_seconds(raw_end) and raw_end >= raw_start
            else None
        )
        anchored = False
        for unit_id in named:
            if isinstance(unit_id, str):
                referenced.add(unit_id)
            unit = by_id.get(unit_id) if isinstance(unit_id, str) else None
            if unit is None:
                errors.append(
                    {
                        "code": "coverage_references_unknown_unit",
                        "window": index,
                        "window_id": window.get("window_id"),
                        "value": unit_id,
                    }
                )
                continue
            if unit.get("source_class") != "source" or span is None:
                continue
            start, end = span
            source = unit.get("source")
            unit_start = source.get("start_sec") if isinstance(source, dict) else None
            unit_end = source.get("end_sec") if isinstance(source, dict) else None
            if not _is_seconds(unit_start) or not _is_seconds(unit_end):
                # `validate_provenance` reports the unusable timing itself; it
                # simply cannot anchor a window.
                continue
            if unit_end > start - TIME_TOLERANCE_SEC and unit_start < end + TIME_TOLERANCE_SEC:
                anchored = True
            else:
                errors.append(
                    {
                        "code": "coverage_unit_outside_window",
                        "window": index,
                        "window_id": window.get("window_id"),
                        "unit": unit_id,
                        "window_span": list(span),
                        "unit_span": [unit_start, unit_end],
                    }
                )
        if (
            window.get("status") == "covered"
            and not anchored
            and not _as_list(window.get("omitted_items"))
        ):
            errors.append(
                {
                    "code": "covered_window_without_evidence_in_it",
                    "window": index,
                    "window_id": window.get("window_id"),
                }
            )

    if coverage.get("status") == "PASS":
        unaccounted = sorted(
            unit["id"]
            for unit in unit_list
            if unit.get("source_class") == "source"
            and isinstance(unit.get("id"), str)
            and unit["id"] not in referenced
        )
        if unaccounted:
            errors.append({"code": "coverage_pass_omits_source_units", "units": unaccounted})
    return errors
