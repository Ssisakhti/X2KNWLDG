from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import constants
from .ids import is_id_part
from .io import (
    JsonReadError,
    dumps_json,
    format_timestamp,
    read_json,
    timestamp_url,
    write_group,
)
from .pipeline import PipelineError, VerdictRefusal, validate_run
from .transcripts import transcript_end_sec
from .validators import (
    validate_coverage,
    validate_knowledge_units,
    validate_provenance,
    validate_relationships,
)

#: Report sections, in the order they are printed, and the kinds each collects.
#: The *order* is an editorial decision and lives here; the *vocabulary* does
#: not — it lives in ``constants.KNOWLEDGE_KINDS`` and is checked against this
#: table at import time by :func:`_check_section_order`.
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


def _check_section_order() -> None:
    """Refuse to import if the report sections and the kind vocabulary disagree.

    ``SECTION_ORDER`` used to hand-duplicate every name in
    ``constants.KNOWLEDGE_KINDS``, so adding a kind there put it in "Other
    Knowledge" — a section that exists for the *unknown*, silently reused for
    the merely unlisted. A vocabulary with two homes drifts; this keeps the one
    home and makes the copy answer to it.

    Import time, and loudly, because both sides are constants: there is no input
    that can make this pass or fail, so the first import after the mistake is
    the earliest possible moment to say so.
    """
    covered: set[str] = set()
    for _, kinds in SECTION_ORDER:
        covered |= kinds
    unmapped = sorted(constants.KNOWLEDGE_KINDS - covered)
    unknown = sorted(covered - constants.KNOWLEDGE_KINDS)
    if unmapped or unknown:
        raise RuntimeError(
            "artifacts.SECTION_ORDER and constants.KNOWLEDGE_KINDS disagree. "
            f"Kinds with no report section: {unmapped}. "
            f"Sections naming a kind that is not in the vocabulary: {unknown}. "
            "Add the kind to the section it belongs in (or remove the stale name) "
            "rather than letting report.md file it under 'Other Knowledge'."
        )


_check_section_order()


#: Fields every knowledge unit must carry before any final artifact is written.
#: ``report.md`` and the vault index every one of them directly.
_REQUIRED_UNIT_FIELDS = ("id", "kind", "content", "source_class")

#: Fields of ``metadata.json`` that ``report.md`` and the vault print verbatim.
_REQUIRED_METADATA_FIELDS = ("title", "video_url", "channel", "language", "transcript_hash")


def _read(path: Path) -> Any:
    """One JSON file, or a :class:`PipelineError` naming what is wrong with it.

    The single reader (``io.read_json``) with this module's error behaviour
    wrapped around it. There were three readers for this job and only one of
    them turned a missing file into a ``PipelineError``; a caller of
    ``apply_extraction_bundle`` got a bare ``FileNotFoundError`` traceback for a
    mistyped bundle path.
    """
    try:
        document = read_json(path)
    except JsonReadError as exc:
        raise PipelineError(str(exc)) from exc
    # D-077: `pipeline._read_canonical` enforced this and its twin here did
    # not, so a `metadata.json` holding `[]` reached `metadata["video_id"]` and
    # escaped as `TypeError: list indices must be integers`, and a
    # `knowledge_units.json` holding `[]` reached `.get("units")` as an
    # `AttributeError`. Both read canonical files; one reader, one rule.
    if not isinstance(document, dict):
        raise PipelineError(f"Canonical JSON must be an object: {path}")
    return document


def _checked_video_id(metadata: dict[str, Any]) -> str:
    """The run's own ``video_id``, refused unless it is one safe path segment.

    ``_obsidian_files`` builds two filenames out of this value, so an id that is
    not a single path segment escapes ``output/<video-id>/`` entirely — and a
    run's ``metadata.json`` is an ordinary canonical file, not immutable
    evidence, so its contents are not automatically trustworthy.

    ``is_id_part`` is the gate ``resolve_run_dir`` already applies to an id
    arriving from outside the process (D-020), and it *rejects* rather than
    rewrites: a finalize that quietly wrote somewhere else would be worse than
    one that stopped. Note the asymmetry this closes — ``_slug`` below has always
    guarded the unit ids used as filenames; the run's own id was the one that
    reached a path unchecked.
    """
    video_id = metadata.get("video_id")
    if not isinstance(video_id, str) or not is_id_part(video_id):
        raise PipelineError(
            f"metadata.json declares an unusable video_id: {video_id!r}. "
            "It must be a single path segment matching the v1 idPart pattern."
        )
    return video_id


def _checked_units(units: Any) -> list[dict[str, Any]]:
    """Every unit, refused unless it carries the fields the artifacts index.

    ``report.md``, ``graph.json`` and the vault each subscript ``unit['kind']``,
    ``unit['id']``, ``unit['content']`` and ``unit['source_class']`` directly, so
    a unit missing one of them used to raise a bare ``KeyError`` — and it raised
    it *after* ``graph.json`` had already been replaced, leaving the run's
    outputs disagreeing with each other. Checking the whole set before the first
    write turns a mid-write crash into a refusal that names the unit.
    """
    if not isinstance(units, list):
        raise PipelineError("knowledge_units.json must state a list of units")
    problems: list[str] = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            problems.append(f"unit at position {index} is not a JSON object")
            continue
        missing = [
            field
            for field in _REQUIRED_UNIT_FIELDS
            if not isinstance(unit.get(field), str) or not unit[field]
        ]
        if missing:
            problems.append(f"unit {unit.get('id', f'at position {index}')!r} lacks {missing}")
    if problems:
        raise PipelineError(
            "Refusing to write final artifacts from unusable knowledge units: "
            + "; ".join(problems)
        )
    return units


def _checked_relationships(relationships: Any) -> list[dict[str, Any]]:
    """Every relationship, refused unless both endpoints and the relation exist."""
    if not isinstance(relationships, list):
        raise PipelineError("relationships.json must state a list of relationships")
    problems: list[str] = []
    for index, edge in enumerate(relationships):
        if not isinstance(edge, dict):
            problems.append(f"relationship at position {index} is not a JSON object")
            continue
        missing = [
            field
            for field in ("from", "to", "relation")
            if not isinstance(edge.get(field), str) or not edge[field]
        ]
        if missing:
            problems.append(f"relationship at position {index} lacks {missing}")
    if problems:
        raise PipelineError(
            "Refusing to write final artifacts from unusable relationships: "
            + "; ".join(problems)
        )
    return relationships


def _checked_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """``metadata.json``, refused unless it carries the fields the report prints."""
    missing = [field for field in _REQUIRED_METADATA_FIELDS if not isinstance(metadata.get(field), str)]
    if missing:
        raise PipelineError(
            f"metadata.json lacks the fields the final report states: {missing}"
        )
    return metadata


def _slug(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\t\n\r]", "_", value).strip().rstrip(".")
    return value or "untitled"


def apply_extraction_bundle(run_dir: Path, bundle_path: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    bundle = _read(bundle_path.expanduser().resolve())
    if not isinstance(bundle, dict):
        raise PipelineError("Extraction bundle must be a JSON object")
    metadata = _read(run_dir / "metadata.json")
    # D-073: this used to read `bundle.get("knowledge_units",
    # bundle.get("units", []))`. The bundle schema requires `knowledge_units`
    # and sets `additionalProperties: false`, so it rejects `units` outright —
    # while prompts 01, 02 and 04 all told the agent to return `{"units": ...}`
    # and this line silently accepted both spellings. Nothing broke, and so the
    # divergence between the prompts and the schema went unnoticed. Refusing
    # here names the right key instead of guessing which one was meant.
    if "knowledge_units" not in bundle and "units" in bundle:
        raise PipelineError(
            "Extraction bundle uses 'units'; the key is 'knowledge_units' "
            "(schemas/extraction_bundle.schema.json). The canonical "
            "knowledge_units.json file uses 'units' — the bundle does not."
        )
    # D-077: `metadata["video_id"]` raised a bare `KeyError` for a
    # metadata.json that had lost the key. `finalize_run` already read it
    # through `_checked_video_id`; apply-bundle did not.
    video_id = _checked_video_id(metadata)
    units_document = {
        "schema_version": "1.0",
        "video_id": video_id,
        "units": bundle.get("knowledge_units", []),
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
        unit["id"]
        for unit in units_document["units"]
        # D-114: `str` rather than "anything truthy" — a non-string id is
        # already a failing run (`missing_id`), so this narrows without
        # changing a verdict.
        if isinstance(unit, dict) and isinstance(unit.get("id"), str) and unit["id"]
    }
    relationship_validation = validate_relationships(relationships_document, unit_ids)
    transcript = _read(run_dir / "transcript.json")
    segments = _read(run_dir / "segments.json")
    provenance_validation = validate_provenance(
        units_document, transcript, segments, video_id
    )
    transcript_end = transcript_end_sec(transcript.get("captions"))
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

    extraction_metadata = bundle.get("extraction_metadata")
    if isinstance(extraction_metadata, dict):
        metadata["extraction"] = extraction_metadata
    metadata["extracted_at"] = datetime.now(timezone.utc).isoformat()
    # One step, not four. These four files describe the same extraction, and
    # ``validate_run`` immediately below reads all four: a half-applied bundle
    # would be validated as though it were a whole one.
    write_group(
        [
            (run_dir / "knowledge_units.json", dumps_json(units_document)),
            (run_dir / "relationships.json", dumps_json(relationships_document)),
            (run_dir / "coverage.json", dumps_json(coverage_document)),
            (run_dir / "metadata.json", dumps_json(metadata)),
        ]
    )
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


def _obsidian_files(
    run_dir: Path,
    metadata: dict[str, Any],
    units: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    coverage: dict[str, Any],
    video_id: str,
) -> list[tuple[Path, str]]:
    """Build the vault as ``(path, text)`` pairs. It writes nothing.

    *video_id* has already passed :func:`_checked_video_id`. It arrives as a
    parameter rather than being re-read from *metadata* so that the unchecked
    value cannot reach a path from inside this function.

    Building every file before any of them is written is what lets
    :func:`finalize_run` fail without having half-replaced a vault.
    """
    vault = run_dir / "vault"
    video_path = vault / "videos" / f"{video_id}.md"
    unit_links = [f"- [[{unit['id']}]] — {unit['content']}" for unit in units]
    files: list[tuple[Path, str]] = [
        (
            video_path,
            "\n".join(
                [
                    "---",
                    "type: video",
                    f"video_id: {video_id}",
                    f"source_url: \"{metadata['video_url']}\"",
                    "---",
                    "",
                    f"# {metadata['title']}",
                    "",
                    *unit_links,
                    "",
                ]
            ),
        )
    ]
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in relationships:
        outgoing[edge["from"]].append(edge)
    for unit in units:
        category = "derived" if unit.get("source_class") == "derived" else "source"
        unit_path = vault / "knowledge_units" / category / f"{_slug(unit['id'])}.md"
        lines = [
            "---",
            "type: knowledge_unit",
            f"kind: {unit['kind']}",
            f"source_class: {unit['source_class']}",
            f"video_id: {video_id}",
            "---",
            "",
            f"# {unit['id']}",
            "",
            unit["content"],
            "",
            f"Source video: [[{video_id}]]",
            "",
        ]
        if unit.get("derived_from"):
            lines.extend(["## Derived from", "", *[f"- [[{item}]]" for item in unit["derived_from"]], ""])
        if outgoing.get(unit["id"]):
            lines.extend(["## Relationships", ""])
            for edge in outgoing[unit["id"]]:
                lines.append(f"- {edge['relation']}: [[{edge['to']}]]")
            lines.append("")
        files.append((unit_path, "\n".join(lines)))
    files.append((vault / "reports" / f"{video_id}-coverage.md", _coverage_markdown(coverage)))
    return files


def finalize_run(run_dir: Path) -> dict[str, Any]:
    """Write the final artifacts for a run that has earned them.

    Two refusals come before the first write, because everything after it is
    hard to take back: ``graph.json`` and ``report.md`` are overwritten in place,
    and ``rebuild_library`` merges this run into the cumulative cross-video graph
    that other tools are told to trust.

    **A ``FAIL`` run is refused.** ``WORKFLOW.md`` section 5 applies the bundle
    through the validator *before* final artifacts are generated, and
    ``CLAUDE.md`` forbids claiming completion without a passing validation. This
    function used to compute the verdict and then write regardless, so a run
    whose units cited evidence absent from the transcript produced a full vault,
    a report that mentioned no failure, and a poisoned library.

    ``PARTIAL`` still finalizes: an honestly incomplete run is a real
    deliverable (``WORKFLOW.md`` section 4.5 says to use ``PARTIAL``, never
    ``PASS``), and its status travels in the returned dict and in
    ``validation.json``.
    """
    run_dir = run_dir.expanduser().resolve()
    validation = validate_run(run_dir)
    metadata = _read(run_dir / "metadata.json")
    video_id = _checked_video_id(metadata)
    if validation["status"] == "FAIL":
        failed = ", ".join(
            name
            for name, section in validation.items()
            if isinstance(section, dict) and section.get("status") not in {None, "PASS"}
        )
        # D-082: a verdict, not a breakage. `VerdictRefusal` carries the status
        # so the CLI exits `4` through `VERDICT_EXIT_CODES` rather than `1`.
        raise VerdictRefusal(
            validation["status"],
            "Refusing to finalize a run that fails validation "
            f"({failed or 'see validation.json'}). Repair the run and re-apply "
            f"the bundle; the full report is in {run_dir / 'validation.json'}.",
        )
    # Everything the artifacts need, checked before anything is written. A unit
    # missing ``kind`` used to raise a bare ``KeyError`` from the middle of the
    # write sequence, with ``graph.json`` already replaced.
    _checked_metadata(metadata)
    units = _checked_units(_read(run_dir / "knowledge_units.json").get("units", []))
    relationships = _checked_relationships(
        _read(run_dir / "relationships.json").get("relationships", [])
    )
    coverage = _read(run_dir / "coverage.json")

    nodes = [
        {
            "id": unit["id"],
            "label": unit.get("normalized_statement") or unit["content"],
            "kind": unit["kind"],
            "source_class": unit["source_class"],
        }
        for unit in units
    ]
    graph_text = dumps_json({"nodes": nodes, "edges": relationships})

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
                f"(confidence {edge.get('confidence')})"
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
    obsidian_files = _obsidian_files(
        run_dir, metadata, units, relationships, coverage, video_id
    )
    # Every artifact is built before any of it is written, and the whole set
    # lands together or not at all. A run whose ``graph.json`` came from this
    # finalize while its ``report.md`` came from the last one is a run that
    # describes itself two ways, and nothing downstream would notice.
    write_group(
        [
            (run_dir / "graph.json", graph_text),
            (run_dir / "report.md", "\n".join(lines)),
            *obsidian_files,
        ],
        # D-090: the three subtrees `_obsidian_files` generates into, so a unit
        # retracted between two finalizes stops having a note. Named
        # individually rather than as `vault/` so a file a reader put somewhere
        # else under the vault is not something this function deletes.
        prune=[
            run_dir / "vault" / "videos",
            run_dir / "vault" / "knowledge_units",
            run_dir / "vault" / "reports",
        ],
    )
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
