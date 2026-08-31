from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any

from .io import format_timestamp, timestamp_url, write_json
from .pipeline import PipelineError, validate_run
from .validators import (
    validate_coverage,
    validate_knowledge_units,
    validate_provenance,
    validate_relationships,
)


SECTION_ORDER = [
    ("Core Thesis", {"claim", "principle"}),
    ("Evidence", {"evidence"}),
    ("Concepts & Definitions", {"concept", "definition"}),
    ("Frameworks & Mental Models", {"framework", "mental_model", "diagnostic_model"}),
    ("Processes / How-To", {"process", "instruction"}),
    ("Examples & Case Studies", {"example", "case_study", "analogy"}),
    ("Facts & Statistics", {"fact", "statistic"}),
    ("Recommendations", {"recommendation", "actionable_experiment"}),
    ("Caveats & Limitations", {"caveat", "limitation", "assumption", "counterargument"}),
    ("Open Questions", {"question", "open_problem", "hypothesis"}),
    ("Derived Synthesis", {"relationship", "implication", "generalized_rule", "synthesis"}),
    ("References & Quotes", {"reference", "quote"}),
]


def _read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _slug(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\t\n\r]", "_", value).strip().rstrip(".")
    return value or "untitled"


def apply_extraction_bundle(run_dir: Path, bundle_path: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    bundle = _read(bundle_path.expanduser().resolve())
    if not isinstance(bundle, dict):
        raise PipelineError("Extraction bundle must be a JSON object")
    metadata = _read(run_dir / "metadata.json")
    units_document = {
        "schema_version": "1.0",
        "video_id": metadata["video_id"],
        "units": bundle.get("knowledge_units", bundle.get("units", [])),
    }
    relationships_document = {
        "schema_version": "1.0",
        "video_id": units_document["video_id"],
        "relationships": bundle.get("relationships", []),
    }
    coverage_document = bundle.get("coverage")
    if not isinstance(coverage_document, dict):
        raise PipelineError("Extraction bundle must contain a coverage object")
    coverage_document.setdefault("schema_version", "1.0")
    coverage_document.setdefault("video_id", units_document["video_id"])

    unit_validation = validate_knowledge_units(units_document)
    unit_ids = {
        unit.get("id")
        for unit in units_document["units"]
        if isinstance(unit, dict) and unit.get("id")
    }
    relationship_validation = validate_relationships(relationships_document, unit_ids)
    transcript = _read(run_dir / "transcript.json")
    segments = _read(run_dir / "segments.json")
    provenance_validation = validate_provenance(
        units_document, transcript, segments, metadata["video_id"]
    )
    transcript_end = max(
        (caption.get("end_sec", 0) for caption in transcript.get("captions", [])), default=0
    )
    coverage_validation = validate_coverage(coverage_document, transcript_end)
    errors = {
        "knowledge_units": unit_validation["errors"],
        "provenance": provenance_validation["errors"],
        "relationships": relationship_validation["errors"],
        "coverage": coverage_validation["errors"],
    }
    if any(errors.values()):
        raise PipelineError(f"Extraction bundle failed validation: {json.dumps(errors, ensure_ascii=False)}")

    referenced = {
        unit_id
        for window in coverage_document.get("windows", [])
        for unit_id in window.get("knowledge_units", [])
    }
    unknown = sorted(referenced - unit_ids)
    if unknown:
        raise PipelineError(f"Coverage references unknown knowledge units: {unknown}")
    source_ids = {
        unit["id"]
        for unit in units_document["units"]
        if isinstance(unit, dict) and unit.get("source_class") == "source"
    }
    missing_from_coverage = sorted(source_ids - referenced)
    if coverage_document.get("status") == "PASS" and missing_from_coverage:
        raise PipelineError(
            f"Coverage PASS does not account for source units: {missing_from_coverage}"
        )

    write_json(run_dir / "knowledge_units.json", units_document)
    write_json(run_dir / "relationships.json", relationships_document)
    write_json(run_dir / "coverage.json", coverage_document)
    extraction_metadata = bundle.get("extraction_metadata")
    if isinstance(extraction_metadata, dict):
        metadata["extraction"] = extraction_metadata
    metadata["extracted_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run_dir / "metadata.json", metadata)
    return validate_run(run_dir)


def _unit_markdown(unit: dict[str, Any], video_id: str) -> list[str]:
    lines = [f"### {unit['id']} — {unit['kind']}", "", f"**Statement:** {unit['content']}"]
    if unit.get("normalized_statement"):
        lines.append(f"**Normalized:** {unit['normalized_statement']}")
    if unit.get("source_class") == "source":
        source = unit.get("source", {})
        start = source.get("start_sec", 0)
        end = source.get("end_sec", start)
        lines.append(
            f"**Source:** [{format_timestamp(start)}–{format_timestamp(end)}]"
            f"({timestamp_url(video_id, start)})"
        )
        if source.get("evidence_excerpt"):
            lines.append(f"**Evidence excerpt:** “{source['evidence_excerpt']}”")
    else:
        derived = ", ".join(unit.get("derived_from", []))
        lines.append(f"**Derived from:** {derived}")
        lines.append(f"**Derivation:** {unit.get('derivation_note', '')}")
    lines.extend([f"**Confidence:** {unit.get('confidence')}", ""])
    return lines


def _coverage_markdown(coverage: dict[str, Any]) -> str:
    lines = ["# Coverage Audit", "", f"**Coverage: {coverage.get('status', 'UNKNOWN')}**", ""]
    for window in coverage.get("windows", []):
        lines.extend(
            [
                f"## {window.get('window_id')}",
                "",
                f"- Span: {format_timestamp(window.get('start_sec', 0))}–{format_timestamp(window.get('end_sec', 0))}",
                f"- Status: `{window.get('status')}`",
                f"- Knowledge units: {', '.join(window.get('knowledge_units', [])) or 'none'}",
            ]
        )
        for omission in window.get("omitted_items", []):
            lines.append(f"- Omitted `{omission.get('type')}`: {omission.get('note', '')}")
        for unresolved in window.get("unresolved_items", []):
            lines.append(f"- Unresolved `{unresolved.get('type')}`: {unresolved.get('note', '')}")
        lines.append("")
    return "\n".join(lines)


def _export_obsidian(
    run_dir: Path,
    metadata: dict[str, Any],
    units: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> list[str]:
    vault = run_dir / "vault"
    video_path = vault / "videos" / f"{metadata['video_id']}.md"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    unit_links = [f"- [[{unit['id']}]] — {unit['content']}" for unit in units]
    video_path.write_text(
        "\n".join(
            [
                "---",
                "type: video",
                f"video_id: {metadata['video_id']}",
                f"source_url: \"{metadata['video_url']}\"",
                "---",
                "",
                f"# {metadata['title']}",
                "",
                *unit_links,
                "",
            ]
        ),
        encoding="utf-8",
    )
    created = [str(video_path)]
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in relationships:
        outgoing[edge["from"]].append(edge)
    for unit in units:
        category = "derived" if unit.get("source_class") == "derived" else "source"
        unit_path = vault / "knowledge_units" / category / f"{_slug(unit['id'])}.md"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "---",
            "type: knowledge_unit",
            f"kind: {unit['kind']}",
            f"source_class: {unit['source_class']}",
            f"video_id: {metadata['video_id']}",
            "---",
            "",
            f"# {unit['id']}",
            "",
            unit["content"],
            "",
            f"Source video: [[{metadata['video_id']}]]",
            "",
        ]
        if unit.get("derived_from"):
            lines.extend(["## Derived from", "", *[f"- [[{item}]]" for item in unit["derived_from"]], ""])
        if outgoing.get(unit["id"]):
            lines.extend(["## Relationships", ""])
            for edge in outgoing[unit["id"]]:
                lines.append(f"- {edge['relation']}: [[{edge['to']}]]")
            lines.append("")
        unit_path.write_text("\n".join(lines), encoding="utf-8")
        created.append(str(unit_path))
    coverage_path = vault / "reports" / f"{metadata['video_id']}-coverage.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(_coverage_markdown(coverage), encoding="utf-8")
    created.append(str(coverage_path))
    return created


def finalize_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    validation = validate_run(run_dir)
    metadata = _read(run_dir / "metadata.json")
    units = _read(run_dir / "knowledge_units.json").get("units", [])
    relationships = _read(run_dir / "relationships.json").get("relationships", [])
    coverage = _read(run_dir / "coverage.json")
    video_id = metadata["video_id"]

    nodes = [
        {
            "id": unit["id"],
            "label": unit.get("normalized_statement") or unit["content"],
            "kind": unit["kind"],
            "source_class": unit["source_class"],
        }
        for unit in units
    ]
    write_json(run_dir / "graph.json", {"nodes": nodes, "edges": relationships})

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        grouped[unit["kind"]].append(unit)
    lines = [
        f"# {metadata['title']}",
        "",
        "## Metadata",
        "",
        f"- Source: {metadata['video_url']}",
        f"- Channel: {metadata['channel']}",
        f"- Language: `{metadata['language']}`",
        f"- Transcript hash: `{metadata['transcript_hash']}`",
        "",
    ]
    included: set[str] = set()
    for title, kinds in SECTION_ORDER:
        section_units = [unit for kind in kinds for unit in grouped.get(kind, [])]
        if not section_units:
            continue
        lines.extend([f"## {title}", ""])
        for unit in section_units:
            included.add(unit["id"])
            lines.extend(_unit_markdown(unit, video_id))
    remaining = [unit for unit in units if unit["id"] not in included]
    if remaining:
        lines.extend(["## Other Knowledge", ""])
        for unit in remaining:
            lines.extend(_unit_markdown(unit, video_id))
    lines.extend(
        [
            "## Relationships",
            "",
            *[
                f"- [[{edge['from']}]] —`{edge['relation']}`→ [[{edge['to']}]] "
                f"(confidence {edge['confidence']})"
                for edge in relationships
            ],
            "",
            "## Coverage Audit",
            "",
            f"**Coverage: {coverage.get('status', 'UNKNOWN')}**",
            "",
            f"See `coverage.json` and `vault/reports/{video_id}-coverage.md` for the window-by-window audit.",
            "",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    obsidian_files = _export_obsidian(run_dir, metadata, units, relationships, coverage)
    from .library import rebuild_library

    library = rebuild_library(run_dir.parent)
    return {
        "status": validation["status"],
        "coverage": coverage.get("status"),
        "knowledge_units": len(units),
        "relationships": len(relationships),
        "obsidian_files": len(obsidian_files),
        "report": str(run_dir / "report.md"),
        "graph": str(run_dir / "graph.json"),
        "library": library,
    }
