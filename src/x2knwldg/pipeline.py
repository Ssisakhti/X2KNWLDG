from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .coverage import create_pending_coverage
from .ids import is_id_part
from .io import format_timestamp, sha256_file, timestamp_url, write_json
from .segmenter import create_segments
from .transcripts import parse_transcript_file, transcript_integrity
from .validators import (
    validate_coverage,
    validate_knowledge_units,
    validate_provenance,
    validate_relationships,
)


class PipelineError(RuntimeError):
    pass


def extract_video_id(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if re.fullmatch(r"[0-9A-Za-z_-]{11}", candidate) else None
    if parsed.hostname and "youtube.com" in parsed.hostname:
        candidate = parse_qs(parsed.query).get("v", [None])[0]
        if candidate and re.fullmatch(r"[0-9A-Za-z_-]{11}", candidate):
            return candidate
        path_match = re.search(r"/(?:shorts|embed)/([0-9A-Za-z_-]{11})", parsed.path)
        return path_match.group(1) if path_match else None
    return value if re.fullmatch(r"[0-9A-Za-z_-]{6,64}", value) else None


def resolve_run_dir(output_root: Path, video_id: str) -> Path:
    """Resolve ``output_root/<video_id>`` for reading, rejecting any escape.

    ``_safe_identifier`` *rewrites* a bad id, which is right when creating a run
    and wrong when looking one up: ``../other`` must fail, not silently become
    ``_other``. Every id that arrives from outside the process — an MCP tool
    argument, and later an HTTP path parameter (``T-108``) — goes through here
    (risk R14).
    """
    if not is_id_part(video_id):
        raise PipelineError(f"Invalid video ID: {video_id!r}")
    root = output_root.expanduser().resolve()
    run_dir = (root / video_id).resolve()
    if root not in run_dir.parents:
        raise PipelineError(f"Video ID resolves outside the output root: {video_id!r}")
    return run_dir


def project_root(explicit: Path | None = None) -> Path:
    """Resolve the project root: an explicit path, else ``X2KNWLDG_PROJECT_ROOT``,
    else the working directory.

    One implementation, because the MCP server and the ``ui`` command must agree
    on what 'the project' is. Two rules for the same lookup is what D-020 is
    about: :func:`resolve_run_dir` exists because ``_safe_identifier`` was the
    second rule for resolving a run. Callers get an absolute path; whether the
    root actually holds a project is the caller's question, not this function's.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return Path(os.environ.get("X2KNWLDG_PROJECT_ROOT", Path.cwd())).expanduser().resolve()


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_-]+", "_", value).strip("_")
    if not normalized:
        raise PipelineError("A valid video ID is required")
    return normalized[:80]


def _metadata(
    video_id: str,
    video_url: str | None,
    title: str | None,
    channel: str | None,
    language: str,
    transcript_source: str,
    transcript_hash: str,
    integrity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "pipeline_version": __version__,
        "video_id": video_id,
        "video_url": video_url or f"https://www.youtube.com/watch?v={video_id}",
        "title": title or "Unknown title",
        "channel": channel or "Unknown channel",
        "language": language,
        "transcript_source": transcript_source,
        "transcript_hash": transcript_hash,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": integrity["stats"]["duration_sec"],
    }


def _transcript_markdown(captions: list[dict[str, Any]], video_id: str) -> str:
    lines = ["# Timestamped transcript", ""]
    for caption in captions:
        start = format_timestamp(caption["start_sec"])
        end = format_timestamp(caption["end_sec"])
        link = timestamp_url(video_id, caption["start_sec"])
        speaker = f" **{caption['speaker']}:**" if caption.get("speaker") else ""
        lines.append(f"[{start}–{end}]({link}){speaker} {caption['text']}")
        lines.append("")
    return "\n".join(lines)


def _initial_report(metadata: dict[str, Any], integrity: dict[str, Any], segment_count: int) -> str:
    return f"""# {metadata['title']}

## Metadata

- Video ID: `{metadata['video_id']}`
- Source: {metadata['video_url']}
- Language: `{metadata['language']}`
- Transcript source: `{metadata['transcript_source']}`
- Duration: {format_timestamp(metadata['duration_sec'])}

## Transcript integrity

- Status: **{integrity['status']}**
- Captions: {integrity['stats']['caption_count']}
- Segments prepared: {segment_count}
- Warnings: {len(integrity['warnings'])}

## Knowledge extraction

Pending. Source knowledge, derived knowledge, relationships, and coverage must be produced from the canonical transcript before this report can be marked complete.

## Coverage audit

**PARTIAL** — audit windows exist, but extraction and semantic coverage review have not run yet.
"""


def import_transcript(
    transcript_path: Path,
    output_root: Path,
    *,
    video_id: str,
    video_url: str | None = None,
    title: str | None = None,
    channel: str | None = None,
    language: str = "unknown",
    source: str | None = None,
    target_segment_sec: float = 240,
    overlap_sec: float = 15,
) -> Path:
    transcript_path = transcript_path.expanduser().resolve()
    if not transcript_path.is_file():
        raise PipelineError(f"Transcript file not found: {transcript_path}")
    video_id = _safe_identifier(video_id)
    run_dir = output_root.expanduser().resolve() / video_id
    if (run_dir / "transcript.json").exists():
        raise PipelineError(
            f"Output already exists for {video_id}; move/version it before reprocessing: {run_dir}"
        )

    captions = parse_transcript_file(transcript_path, language=language, source=source)
    integrity = transcript_integrity(captions)
    if integrity["status"] != "PASS":
        raise PipelineError(f"Transcript integrity failed: {json.dumps(integrity['errors'])}")
    segments = create_segments(
        captions, target_sec=target_segment_sec, overlap_sec=overlap_sec
    )
    transcript_hash = sha256_file(transcript_path)
    transcript_source = source or captions[0]["source"]
    metadata = _metadata(
        video_id,
        video_url,
        title,
        channel,
        language,
        transcript_source,
        transcript_hash,
        integrity,
    )
    transcript_document = {
        "schema_version": "1.0",
        "video_id": video_id,
        "language": language,
        "transcript_source": transcript_source,
        "transcript_hash": transcript_hash,
        "captions": captions,
    }
    segment_document = {
        "schema_version": "1.0",
        "video_id": video_id,
        "strategy": {
            "type": "time_aware_with_boundary_preference",
            "target_sec": target_segment_sec,
            "overlap_sec": overlap_sec,
        },
        "segments": segments,
    }
    knowledge_document = {"schema_version": "1.0", "video_id": video_id, "units": []}
    relationship_document = {
        "schema_version": "1.0",
        "video_id": video_id,
        "relationships": [],
    }
    coverage = create_pending_coverage(captions, video_id)

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(transcript_path, raw_dir / f"source{transcript_path.suffix.lower()}")
    write_json(raw_dir / "transcript.json", transcript_document)
    (raw_dir / "transcript.md").write_text(
        _transcript_markdown(captions, video_id), encoding="utf-8"
    )
    write_json(run_dir / "metadata.json", metadata)
    write_json(run_dir / "transcript.json", transcript_document)
    write_json(run_dir / "segments.json", segment_document)
    write_json(run_dir / "knowledge_units.json", knowledge_document)
    write_json(run_dir / "relationships.json", relationship_document)
    write_json(run_dir / "coverage.json", coverage)
    write_json(run_dir / "graph.json", {"nodes": [], "edges": []})
    write_json(
        run_dir / "validation.json",
        {
            "transcript": integrity,
            "knowledge_units": validate_knowledge_units(knowledge_document),
            "relationships": validate_relationships(relationship_document, set()),
            "coverage": validate_coverage(coverage, metadata["duration_sec"]),
        },
    )
    (run_dir / "report.md").write_text(
        _initial_report(metadata, integrity, len(segments)), encoding="utf-8"
    )
    return run_dir


def prepare_inbox(
    inbox_root: Path, video_id: str, video_url: str | None = None
) -> Path:
    video_id = _safe_identifier(video_id)
    inbox = inbox_root.expanduser().resolve() / video_id
    inbox.mkdir(parents=True, exist_ok=True)
    instructions = f"""# Transcript needed

Add one timestamped transcript file here:

- `transcript.vtt`
- `transcript.srt`
- `transcript.json`
- `transcript.txt` with `[HH:MM:SS - HH:MM:SS]` headers

Video ID: `{video_id}`
Video URL: {video_url or 'not provided'}

Plain text without timestamps cannot pass strict provenance and coverage checks.
Whisper and WhisperX are intentionally disabled.
"""
    (inbox / "README.md").write_text(instructions, encoding="utf-8")
    return inbox


def validate_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    try:
        transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
        segments = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        knowledge = json.loads((run_dir / "knowledge_units.json").read_text(encoding="utf-8"))
        relationships = json.loads((run_dir / "relationships.json").read_text(encoding="utf-8"))
        coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Missing canonical output: {exc.filename}") from exc
    captions = transcript.get("captions", [])
    integrity = transcript_integrity(captions)
    units = knowledge.get("units", []) if isinstance(knowledge, dict) else []
    unit_ids = {unit.get("id") for unit in units if isinstance(unit, dict) and unit.get("id")}
    result = {
        "transcript": integrity,
        "knowledge_units": validate_knowledge_units(knowledge),
        "provenance": validate_provenance(
            knowledge, transcript, segments, metadata.get("video_id", "")
        ),
        "relationships": validate_relationships(relationships, unit_ids),
        "coverage": validate_coverage(
            coverage, max((caption.get("end_sec", 0) for caption in captions), default=0)
        ),
    }
    validators_pass = all(section["status"] == "PASS" for section in result.values())
    if not validators_pass:
        result["status"] = "FAIL"
    elif coverage.get("status") != "PASS":
        result["status"] = "PARTIAL"
    else:
        result["status"] = "PASS"
    write_json(run_dir / "validation.json", result)
    return result
