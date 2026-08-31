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
from .constants import SEGMENT_OVERLAP_SEC, SEGMENT_TARGET_SEC
from .coverage import create_pending_coverage
from .ids import ID_PART_MAX_LENGTH, is_id_part
from .io import (
    JsonReadError,
    format_timestamp,
    read_json,
    sha256_file,
    timestamp_url,
    write_json,
)
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


class RunAlreadyExists(PipelineError):
    """A run already occupies this video id.

    Its own type because ``cli._run_process`` cannot otherwise tell it apart
    from "YouTube has no captions for this video". Those need opposite
    answers: the second asks the user for a transcript file, the first would
    reject that transcript for the same reason it rejected the fetch.
    """


#: Hosts that carry the video id in the *path*: ``https://youtu.be/<id>``.
YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})

#: Hosts that carry the video id in the ``v=`` query parameter, or in a
#: ``/shorts/`` or ``/embed/`` path.
YOUTUBE_WATCH_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)

#: Every host this pipeline will treat as YouTube itself.
YOUTUBE_HOSTS = YOUTUBE_SHORT_HOSTS | YOUTUBE_WATCH_HOSTS

_VIDEO_ID_RE = re.compile(r"[0-9A-Za-z_-]{11}")
_LOCAL_ID_RE = re.compile(r"[0-9A-Za-z_-]{6,64}")
_YOUTUBE_PATH_ID_RE = re.compile(r"/(?:shorts|embed)/([0-9A-Za-z_-]{11})")


def _normalize_host(host: str | None) -> str | None:
    """Lower-case *host* and drop one trailing dot, or ``None`` for no host.

    ``urlparse`` already lower-cases the host and drops any ``user:pass@``
    userinfo, so ``https://youtube.com@evil.example/watch?v=…`` reports
    ``evil.example`` — the host a client would actually connect to, not the
    one the URL is dressed up to look like. A single trailing dot is the
    absolute-DNS spelling of the same name (``youtube.com.``) and is removed;
    anything else is left exactly as written, so it can only match a
    legitimate host by *being* one.
    """
    if not host:
        return None
    host = host.lower()
    return host[:-1] if host.endswith(".") else host


def _parse_url(value: str) -> tuple[Any, str | None]:
    """``(parsed, normalized_host)`` for *value*, tolerating a malformed URL."""
    if not isinstance(value, str):
        return None, None
    try:
        parsed = urlparse(value)
        host = _normalize_host(parsed.hostname)
    except ValueError:  # e.g. an unparsable IPv6 literal in the netloc
        return None, None
    return parsed, host


def is_youtube_url(value: str) -> bool:
    """Whether *value* is a URL served by YouTube itself.

    Exact host membership, never a substring test. ``"youtube.com" in host``
    admitted ``youtube.com.evil.example`` and ``notyoutube.com``, and
    ``cli._run_process`` read a non-``None`` :func:`extract_video_id` as proof
    that the *whole URL* was safe to hand to ``yt_dlp``, whose generic
    extractor will happily fetch an arbitrary host. That is an SSRF, and worse
    for this project it is provenance poisoning: captions fetched from an
    attacker's host were filed under a real 11-character YouTube id.
    """
    return _parse_url(value)[1] in YOUTUBE_HOSTS


def extract_video_id(value: str) -> str | None:
    parsed, host = _parse_url(value)
    if parsed is None:
        return None
    if host in YOUTUBE_SHORT_HOSTS:
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if _VIDEO_ID_RE.fullmatch(candidate) else None
    if host in YOUTUBE_WATCH_HOSTS:
        candidate = parse_qs(parsed.query).get("v", [None])[0]
        if candidate and _VIDEO_ID_RE.fullmatch(candidate):
            return candidate
        path_match = _YOUTUBE_PATH_ID_RE.search(parsed.path)
        return path_match.group(1) if path_match else None
    if host is not None:
        # Some other host. A URL is never a bare identifier, so it must not
        # fall through to the branch below and come back with an id lifted
        # out of a string the attacker chose.
        return None
    return value if _LOCAL_ID_RE.fullmatch(value) else None


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
    """Check a caller-supplied id before a run is *created* at it. Never rewrite.

    This used to normalise: ``my.video.2024`` became ``my_video_2024``, and
    ``../other`` became ``_other``. Every path that looks a run up afterwards —
    :func:`resolve_run_dir`, ``ids.is_id_part``, ``schemas/v1/common``, the
    HTTP path parameters of D-030 — *rejects* those ids instead, so a rewrite
    filed the run at an address nothing could ever retrieve it by, and two
    distinct ids could normalise onto one directory and collide in silence.

    D-020 says a lookup must fail rather than resolve to something else. The
    creating side has to agree with it, or the two rules disagree about which
    runs exist. So this is the same predicate as the resolver, and the answer
    is yes or an error — never a different id.
    """
    if not isinstance(value, str) or not is_id_part(value):
        raise PipelineError(
            f"Invalid video ID: {value!r}. Use letters, digits, '.', '_' or '-' "
            f"(1-{ID_PART_MAX_LENGTH} characters, and not starting with '.')"
        )
    return value


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
    target_segment_sec: float = SEGMENT_TARGET_SEC,
    overlap_sec: float = SEGMENT_OVERLAP_SEC,
) -> Path:
    transcript_path = transcript_path.expanduser().resolve()
    if not transcript_path.is_file():
        raise PipelineError(f"Transcript file not found: {transcript_path}")
    video_id = _safe_identifier(video_id)
    # The same resolver every lookup uses (D-020), so a run is created at the
    # address it will later be read back from, and only there.
    run_dir = resolve_run_dir(output_root, video_id)
    if (run_dir / "transcript.json").exists():
        raise RunAlreadyExists(
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
    # `raw/` is immutable evidence *of a run that exists*. The guard above has
    # already established that this run has no canonical `transcript.json`, so
    # anything here is the debris of an import that was interrupted between
    # `mkdir` and the first canonical write — not evidence of anything. It used
    # to make every retry, even one with a perfectly good transcript, die on
    # FileExistsError with no way forward but a manual `rm -rf`. Clearing it is
    # deferred to here, after parsing and the integrity check have passed, so a
    # retry with a *bad* file destroys nothing.
    if raw_dir.is_dir():
        shutil.rmtree(raw_dir)
    elif raw_dir.exists() or raw_dir.is_symlink():
        raw_dir.unlink()
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


def _coverage_link_errors(
    coverage: Any, units: list[Any], unit_ids: set[str]
) -> list[dict[str, Any]]:
    """Errors from cross-checking ``coverage.json`` against ``knowledge_units.json``.

    ``validate_coverage`` only ever reads ``coverage.json``, so it can confirm
    that a window *names* knowledge units without knowing whether any of them
    exist. Emptying the unit store while leaving coverage claiming ``covered``
    therefore left the run reporting ``PASS`` — coverage asserting evidence
    that is not there, which is precisely the fabrication AGENTS.md forbids.

    ``artifacts.apply_extraction_bundle`` already refuses both of these at
    write time; they are re-checked here because ``validation.json`` is the
    run's standing verdict and the canonical files can be edited after a
    bundle is applied.
    """
    errors: list[dict[str, Any]] = []
    if not isinstance(coverage, dict) or not isinstance(coverage.get("windows"), list):
        # validate_coverage already reports the shape failure.
        return errors
    referenced: set[str] = set()
    for index, window in enumerate(coverage["windows"]):
        if not isinstance(window, dict):
            continue
        named = window.get("knowledge_units") or []
        if not isinstance(named, list):
            errors.append({"code": "window_knowledge_units_not_array", "window": index})
            continue
        for unit_id in named:
            if isinstance(unit_id, str):
                referenced.add(unit_id)
            if unit_id not in unit_ids:
                errors.append(
                    {
                        "code": "coverage_references_unknown_unit",
                        "window": index,
                        "window_id": window.get("window_id"),
                        "value": unit_id,
                    }
                )
    if coverage.get("status") == "PASS":
        unaccounted = sorted(
            unit["id"]
            for unit in units
            if isinstance(unit, dict)
            and unit.get("source_class") == "source"
            and isinstance(unit.get("id"), str)
            and unit["id"] not in referenced
        )
        if unaccounted:
            errors.append(
                {"code": "coverage_pass_omits_source_units", "units": unaccounted}
            )
    return errors


def _read_canonical(path: Path) -> dict[str, Any]:
    """One canonical file, or a :class:`PipelineError` naming what is wrong.

    A corrupt or unreadable canonical file used to leave ``json.JSONDecodeError``
    to escape as a raw traceback from every caller — the CLI, the MCP server,
    and ``finalize_run``.
    """
    try:
        document = read_json(path)
    except JsonReadError as exc:
        raise PipelineError(f"Canonical output: {exc}") from exc
    if not isinstance(document, dict):
        raise PipelineError(f"Canonical output must be a JSON object: {path}")
    return document


def validate_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    transcript = _read_canonical(run_dir / "transcript.json")
    segments = _read_canonical(run_dir / "segments.json")
    metadata = _read_canonical(run_dir / "metadata.json")
    knowledge = _read_canonical(run_dir / "knowledge_units.json")
    relationships = _read_canonical(run_dir / "relationships.json")
    coverage = _read_canonical(run_dir / "coverage.json")
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
    # The one check no single-file validator can make: coverage.json and
    # knowledge_units.json describing the same run.
    link_errors = _coverage_link_errors(coverage, units, unit_ids)
    if link_errors:
        result["coverage"]["errors"] = list(result["coverage"]["errors"]) + link_errors
        result["coverage"]["status"] = "FAIL"

    validators_pass = all(section["status"] == "PASS" for section in result.values())
    coverage_status = coverage.get("status") if isinstance(coverage, dict) else None
    if not validators_pass:
        # Any section failing is a failed run. Never softened to PARTIAL:
        # PARTIAL means "honestly incomplete", not "invalid but tolerable".
        result["status"] = "FAIL"
    elif coverage_status != "PASS":
        # Every validator passed and coverage says so itself: an honest
        # PARTIAL (WORKFLOW.md §4.5), which is a deliverable but not a pass.
        result["status"] = "PARTIAL"
    else:
        result["status"] = "PASS"
    write_json(run_dir / "validation.json", result)
    return result
