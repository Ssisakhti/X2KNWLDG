from __future__ import annotations

from typing import Any

from .ids import is_id_part
from .constants import (
    COVERAGE_STATUSES,
    KNOWLEDGE_KINDS,
    OMISSION_REASONS,
    RELATION_TYPES,
)
from .transcripts import clean_text


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
        if unit.get("kind") not in KNOWLEDGE_KINDS:
            errors.append({"code": "invalid_kind", "unit": location, "value": unit.get("kind")})
        source_class = unit.get("source_class")
        if source_class not in {"source", "derived"}:
            errors.append({"code": "invalid_source_class", "unit": location})
        confidence = unit.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append({"code": "invalid_confidence", "unit": location})
        if not str(unit.get("content") or "").strip():
            errors.append({"code": "missing_content", "unit": location})
        if source_class == "source":
            source = unit.get("source")
            required = {"video_id", "segment_id", "start_sec", "end_sec", "evidence_excerpt"}
            if not isinstance(source, dict):
                errors.append({"code": "missing_source", "unit": location})
            else:
                missing = sorted(field for field in required if source.get(field) in (None, ""))
                if missing:
                    errors.append({"code": "incomplete_provenance", "unit": location, "fields": missing})
        if source_class == "derived":
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
            if start < 0 or end < start or end > transcript_end + 0.01:
                errors.append({"code": "source_time_outside_transcript", "unit": unit_id})
            if start < segment.get("start_sec", 0) - 0.01 or end > segment.get("end_sec", 0) + 0.01:
                errors.append({"code": "source_time_outside_segment", "unit": unit_id})
        excerpt = clean_text(str(source.get("evidence_excerpt") or "")).casefold()
        segment_text = clean_text(str(segment.get("text") or "")).casefold()
        if excerpt and excerpt not in segment_text:
            errors.append({"code": "evidence_excerpt_not_in_segment", "unit": unit_id})
    return _result(errors, warnings)


def validate_coverage(document: Any, transcript_end_sec: float) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(document, dict) or not isinstance(document.get("windows"), list):
        return _result([{"code": "coverage_windows_not_array"}], warnings)
    windows = document["windows"]
    audit_attempts = document.get("audit_attempts")
    if audit_attempts is not None and (
        not isinstance(audit_attempts, int) or audit_attempts < 1 or audit_attempts > 3
    ):
        errors.append({"code": "invalid_audit_attempts", "value": audit_attempts})
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
        if abs(start - cursor) > 0.01:
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
    if abs(cursor - transcript_end_sec) > 0.01:
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
