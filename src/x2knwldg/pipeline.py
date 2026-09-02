from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
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
    dumps_json,
    format_timestamp,
    is_finite_seconds,
    read_json,
    sha256_file,
    sha256_text,
    timestamp_url,
    write_group,
    write_json,
    write_text,
)
from .segmenter import create_segments
from .transcripts import parse_transcript_file, transcript_end_sec, transcript_integrity
from .validators import (
    validate_coverage,
    validate_coverage_links,
    validate_knowledge_units,
    validate_provenance,
    validate_relationships,
)


class PipelineError(RuntimeError):
    pass


class VerdictRefusal(PipelineError):
    """A command refused *because a run validated as failing*, not because it broke.

    Defect D-082: `finalize_run` refuses a `FAIL` run with a `PipelineError`,
    which `cli.main` maps to `EXIT_ERROR` (`1`, "the command refused or
    failed"). The same run, read from the same `validation.json`, exits `4`
    through `validate`. `VERDICT_EXIT_CODES` exists so the three commands
    cannot disagree about what a verdict is worth, and the refusal path went
    around it — so a wrapper read "broken install" for a run that simply
    validated as failing.

    Carries the verdict so the CLI can map it through the one table rather
    than restate the mapping at the refusal site.
    """

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


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
    metadata_error: str | None = None,
    canonical_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
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
    if canonical_hashes:
        # D-163. `transcript_hash` covers the *preserved original*; these cover
        # the canonical documents extraction actually reads. Additive, and
        # absent rather than empty on a run that recorded none, so
        # `_evidence_integrity` can tell "no digests were taken" from "the
        # digests do not match" — the first is an older run, the second is
        # tampering.
        document["canonical_hashes"] = dict(canonical_hashes)
    if metadata_error:
        # D-099: `title` and `channel` fall back to "Unknown ...", and without
        # this there was no way to tell an unknown title from a fetch that
        # failed — the two look identical in `metadata.json`. Absent when
        # nothing went wrong; never an empty string.
        document["metadata_error"] = metadata_error
    return document


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
    metadata_error: str | None = None,
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
            "type": _SEGMENT_STRATEGY,
            "target_sec": target_segment_sec,
            "overlap_sec": overlap_sec,
        },
        "segments": segments,
    }
    # Serialised here rather than at the `write_group` below, because the
    # digests recorded in `metadata.json` must be over exactly the bytes that
    # reach disk — and `metadata.json` is written in the same group (D-163).
    transcript_text = dumps_json(transcript_document)
    segment_text = dumps_json(segment_document)
    canonical_hashes = {
        "transcript.json": sha256_text(transcript_text),
        "segments.json": sha256_text(segment_text),
    }

    metadata = _metadata(
        video_id,
        video_url,
        title,
        channel,
        language,
        transcript_source,
        transcript_hash,
        integrity,
        metadata_error,
        canonical_hashes=canonical_hashes,
    )

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
    # D-089: the same shape `validate_run` writes, verdict and all. This used
    # to omit both the top-level `status` and the `provenance` section, so
    # `adapters.base.read_status` reported `UNKNOWN` for a run the pipeline had
    # just validated. A fresh import is an honest `PARTIAL`: every validator
    # passes over an empty unit set, and `coverage.json` says `PARTIAL` about
    # itself because nothing has been audited yet.
    initial_validation: dict[str, Any] = {
        "transcript": integrity,
        "evidence": _evidence_integrity(
            run_dir,
            metadata,
            transcript_document,
            segment_document,
            # The files are written below, in one group, so the check runs over
            # the text that group will write rather than over a directory that
            # does not hold it yet.
            canonical_text={
                "transcript.json": transcript_text,
                "segments.json": segment_text,
                "raw/transcript.json": transcript_text,
            },
        ),
        "knowledge_units": validate_knowledge_units(knowledge_document),
        "provenance": validate_provenance(
            knowledge_document, transcript_document, segment_document, video_id
        ),
        "relationships": validate_relationships(relationship_document, set()),
        "coverage": validate_coverage(coverage, metadata["duration_sec"]),
    }
    initial_validation["status"] = _run_verdict(initial_validation, coverage)

    # D-090: these eleven files *are* the run, and they used to be written one
    # at a time. A failure part way through left a directory that could be
    # neither validated — `Missing JSON file: segments.json` — nor re-imported,
    # because `RunAlreadyExists` keys on `transcript.json` and that was the
    # second file written. Only a manual `rm -rf` recovered. `io.write_group`
    # is the mechanism that already existed for exactly this, and every
    # document is serialised before the first write, so a value that cannot be
    # represented fails with nothing on disk changed.
    #
    # `report.md` and `raw/transcript.md` go through it too, which also stops
    # them being written through a text-mode handle whose `newline=None`
    # rewrites every `\n` as `os.linesep`.
    write_group(
        [
            (raw_dir / "transcript.json", transcript_text),
            (raw_dir / "transcript.md", _transcript_markdown(captions, video_id)),
            (run_dir / "metadata.json", dumps_json(metadata)),
            (run_dir / "transcript.json", transcript_text),
            (run_dir / "segments.json", segment_text),
            (run_dir / "knowledge_units.json", dumps_json(knowledge_document)),
            (run_dir / "relationships.json", dumps_json(relationship_document)),
            (run_dir / "coverage.json", dumps_json(coverage)),
            (run_dir / "graph.json", dumps_json({"nodes": [], "edges": []})),
            (run_dir / "validation.json", dumps_json(initial_validation)),
            (run_dir / "report.md", _initial_report(metadata, integrity, len(segments))),
        ]
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
    # D-102: through `io.write_text`, like every other file this package
    # writes. A text-mode handle's `newline=None` rewrites every `\n` as
    # `os.linesep`, and the write was not atomic — invisible on macOS, certain
    # on Windows. `raw/transcript.md` and `report.md` were the other two and
    # joined `write_group` with D-090.
    write_text(inbox / "README.md", instructions)
    return inbox


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


#: The segmentation strategy this code implements, named in every
#: ``segments.json`` it writes. A run recording a different one cannot be
#: re-derived here, which is a fact about this code and not about that run.
_SEGMENT_STRATEGY = "time_aware_with_boundary_preference"

#: The canonical documents a digest is recorded over at import (D-163). Not
#: every canonical file: these two are the ones extraction *reads* and evidence
#: is matched against, and they are the two the pipeline itself never rewrites
#: after import, so a digest over them stays valid for the life of the run.
#: ``knowledge_units.json``, ``relationships.json`` and ``coverage.json`` are
#: rewritten by ``apply-bundle`` on purpose and cannot be pinned this way.
SEALED_CANONICAL_FILES = ("transcript.json", "segments.json")


def _evidence_integrity(
    run_dir: Path,
    metadata: Any,
    transcript: Any,
    segments: Any = None,
    *,
    canonical_text: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Does the evidence still hash to what the run recorded — all of it?

    ``metadata.transcript_hash`` was written once, at import, over the file the
    caller supplied — the file preserved as ``raw/source.<ext>``. Recomputing it
    is where this check started, and it is still the first thing below.

    It was not enough, and the gap was the whole promise. The hash covered
    ``raw/source.<ext>`` and was then compared to *that same file*; the second
    comparison was against ``transcript.json``'s **copy of the same string**.
    Nothing hashed the canonical documents themselves. So editing
    ``segments.json`` to contain a sentence the speaker never said — leaving
    ``raw/`` untouched, which no attacker has any reason to touch — produced a
    run where ``apply-bundle`` returned ``PASS``, this section returned
    ``{"status": "PASS", "errors": []}``, and the invented quotation was printed
    into ``report.md`` while being absent from the preserved original.
    ``segments.json`` is the file that matters most here: ``validate_provenance``
    matches every evidence excerpt against a *segment's* text, not against the
    captions.

    Three checks now stand between a fabricated quotation and ``PASS``, and they
    are deliberately independent — each covers what the others cannot:

    1. **The recorded digests** (D-163). ``metadata.canonical_hashes`` pins the
       exact bytes of each :data:`SEALED_CANONICAL_FILES` entry as written at
       import. Exact and cheap, and the only one of the three that would survive
       a change to the segmenter.
    2. **The preserved copy.** ``raw/transcript.json`` is written at import
       beside ``raw/source.<ext>`` and is evidence in the same sense, so the
       canonical ``transcript.json`` must still equal it byte for byte. This
       holds for every run ever imported, including those recorded before the
       digests existed.
    3. **Recomputation.** ``segments.json`` is a pure function of the captions
       and the strategy it records, so it is recomputed and compared. This is
       what covers ``segments.json`` on a run with no recorded digests, and it
       is what catches an edit that also rewrites the digest in
       ``metadata.json``. It is skipped, with a warning rather than an error,
       when the run records a segmentation strategy this code does not
       implement — a future strategy is not a tampered run.

    A run whose evidence no longer matches its own record cannot be finalized,
    because every downstream artifact would cite a transcript the repository can
    no longer produce.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    recorded = metadata.get("transcript_hash") if isinstance(metadata, dict) else None
    sources = sorted((run_dir / "raw").glob("source.*")) if (run_dir / "raw").is_dir() else []
    if not isinstance(recorded, str) or not recorded:
        errors.append({"code": "transcript_hash_missing"})
    if not sources:
        errors.append({"code": "raw_source_missing", "expected": "raw/source.<ext>"})
    elif len(sources) > 1:
        # Two candidate originals is not evidence; it is a question.
        errors.append(
            {"code": "raw_source_ambiguous", "files": [path.name for path in sources]}
        )
    elif isinstance(recorded, str) and recorded:
        actual = sha256_file(sources[0])
        if actual != recorded:
            errors.append(
                {
                    "code": "transcript_hash_mismatch",
                    "file": f"raw/{sources[0].name}",
                    "recorded": recorded,
                    "actual": actual,
                }
            )
    stated = transcript.get("transcript_hash") if isinstance(transcript, dict) else None
    if isinstance(stated, str) and isinstance(recorded, str) and stated != recorded:
        # The two canonical files disagree about the same fact.
        errors.append(
            {"code": "transcript_hash_disagreement", "metadata": recorded, "transcript": stated}
        )

    def text_of(name: str) -> str | None:
        """*name*'s bytes as text, from the group being written or from disk."""
        if canonical_text is not None:
            return canonical_text.get(name)
        path = run_dir / name
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    # 1. The recorded digests.
    sealed = metadata.get("canonical_hashes") if isinstance(metadata, dict) else None
    if not isinstance(sealed, dict) or not sealed:
        # Every run imported before D-163. Named, not silently excused: checks 2
        # and 3 below still stand over it, and re-importing from the preserved
        # original is what upgrades it to the exact check.
        warnings.append(
            {
                "code": "canonical_hashes_not_recorded",
                "note": (
                    "this run predates the canonical digests; its canonical files are "
                    "checked against the preserved copy and by recomputation instead. "
                    "Re-import from raw/source.<ext> to record them."
                ),
            }
        )
    else:
        for name in SEALED_CANONICAL_FILES:
            expected = sealed.get(name)
            if not isinstance(expected, str) or not expected:
                errors.append({"code": "canonical_hash_missing", "file": name})
                continue
            content = text_of(name)
            if content is None:
                errors.append({"code": "canonical_file_unreadable", "file": name})
                continue
            actual = sha256_text(content)
            if actual != expected:
                errors.append(
                    {
                        "code": "canonical_hash_mismatch",
                        "file": name,
                        "recorded": expected,
                        "actual": actual,
                    }
                )

    # 2. The preserved copy of the transcript.
    canonical_transcript = text_of("transcript.json")
    preserved_transcript = text_of("raw/transcript.json")
    if preserved_transcript is None:
        errors.append({"code": "raw_transcript_missing", "expected": "raw/transcript.json"})
    elif canonical_transcript is None:
        errors.append({"code": "canonical_file_unreadable", "file": "transcript.json"})
    elif canonical_transcript != preserved_transcript:
        errors.append(
            {
                "code": "canonical_transcript_disagrees_with_evidence",
                "file": "transcript.json",
                "evidence": "raw/transcript.json",
            }
        )

    # 3. Recomputation of the segments.
    errors.extend(_segment_recomputation_errors(transcript, segments, warnings))

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
    }


def _segment_recomputation_errors(
    transcript: Any, segments: Any, warnings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """``segments.json`` re-derived from the captions, and compared.

    Evidence excerpts are matched against segment *text*, so this is the file a
    fabricated quotation has to live in. It states the strategy that produced
    it, and that strategy is a pure function of the captions, so the honest
    check is to run it again.
    """
    if segments is None:
        # `import_transcript` before D-163 passed no segments; nothing else does.
        return []
    if not isinstance(segments, dict) or not isinstance(segments.get("segments"), list):
        return [{"code": "segments_not_an_object"}]
    strategy = segments.get("strategy")
    strategy_type = strategy.get("type") if isinstance(strategy, dict) else None
    if strategy_type != _SEGMENT_STRATEGY:
        # A run written by a future segmenter, or one that records no strategy
        # at all. Reported, and not treated as tampering: this code cannot
        # reproduce what it does not implement.
        warnings.append(
            {
                "code": "segments_strategy_not_recomputable",
                "strategy": strategy_type,
                "known": _SEGMENT_STRATEGY,
            }
        )
        return []
    captions = transcript.get("captions") if isinstance(transcript, dict) else None
    if not isinstance(captions, list):
        return [{"code": "segments_unverifiable", "reason": "transcript.json has no captions"}]
    assert isinstance(strategy, dict)
    target = strategy.get("target_sec")
    overlap = strategy.get("overlap_sec")
    if not is_finite_seconds(target) or not is_finite_seconds(overlap):
        return [
            {"code": "segments_strategy_incomplete", "target_sec": target, "overlap_sec": overlap}
        ]
    try:
        again = create_segments(captions, target_sec=float(target), overlap_sec=float(overlap))
    except (PipelineError, ValueError) as exc:
        return [{"code": "segments_unverifiable", "reason": str(exc)}]
    if dumps_json(again) != dumps_json(segments["segments"]):
        return [
            {
                "code": "segments_disagree_with_transcript",
                "file": "segments.json",
                "note": (
                    "the segments on disk are not what this transcript segments to; "
                    "an evidence excerpt matched against them is not matched against "
                    "the preserved original"
                ),
            }
        ]
    return []




def _run_verdict(sections: dict[str, Any], coverage: Any) -> str:
    """The run's overall status, from its sections and coverage's own claim.

    Defect D-089: this lived only inside :func:`validate_run`, and
    :func:`import_transcript` wrote a ``validation.json`` with **no top-level
    ``status``** at all — keys ``['transcript', 'evidence', 'knowledge_units',
    'relationships', 'coverage']`` and nothing else. ``adapters.base.read_status``
    reads the top-level ``status``, so every imported run reported
    ``overall: UNKNOWN`` until somebody happened to run ``validate`` — a run
    the pipeline had just checked, describing itself as unchecked. Extracted so
    the two writers of that file cannot disagree about what its sections mean.
    """
    if not all(section["status"] == "PASS" for section in sections.values()):
        # Any section failing is a failed run. Never softened to PARTIAL:
        # PARTIAL means "honestly incomplete", not "invalid but tolerable".
        return "FAIL"
    coverage_status = coverage.get("status") if isinstance(coverage, dict) else None
    if coverage_status != "PASS":
        # Every validator passed and coverage says so itself: an honest
        # PARTIAL (WORKFLOW.md section 4.5), a deliverable but not a pass.
        return "PARTIAL"
    return "PASS"


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
    # D-114: `str` rather than "anything truthy". A non-string id is already a
    # failing run — `validate_knowledge_units` emits `missing_id` for it — so
    # narrowing here changes no verdict and lets the set say what it holds.
    unit_ids = {
        unit["id"]
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("id"), str) and unit["id"]
    }
    result: dict[str, Any] = {
        "transcript": integrity,
        "evidence": _evidence_integrity(run_dir, metadata, transcript, segments),
        "knowledge_units": validate_knowledge_units(knowledge),
        "provenance": validate_provenance(
            knowledge, transcript, segments, metadata.get("video_id", "")
        ),
        "relationships": validate_relationships(relationships, unit_ids),
        "coverage": validate_coverage(coverage, transcript_end_sec(captions)),
    }
    # The one check no single-file validator can make: coverage.json and
    # knowledge_units.json describing the same run.
    # D-164: one implementation, shared with `apply-bundle`, which used to
    # carry a partial copy of the same rules.
    link_errors = validate_coverage_links(coverage, units)
    if link_errors:
        result["coverage"]["errors"] = list(result["coverage"]["errors"]) + link_errors
        result["coverage"]["status"] = "FAIL"

    result["status"] = _run_verdict(result, coverage)
    write_json(run_dir / "validation.json", result)
    return result
