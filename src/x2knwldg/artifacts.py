from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import constants, ids
from .ids import declared_source_type, is_id_part
from .io import (
    JsonReadError,
    dumps_json,
    format_timestamp,
    read_json,
    timestamp_url,
    write_group,
)
from .pipeline import PipelineError, VerdictRefusal, run_duration_sec, validate_run
from .twitter.extract import CAPTURE_FILENAME, post_url
from .twitter.extract import SOURCE_TYPE as TWITTER_SOURCE_TYPE
from .twitter.extract import apply_extraction_bundle as apply_twitter_bundle
from .twitter.extract import initialize_run as initialize_twitter_run
from .twitter.extract import validate_run as validate_twitter_run
from .validators import (
    bundle_shape_error,
    validate_coverage,
    validate_coverage_links,
    validate_knowledge_units,
    validate_provenance,
    validate_relationships,
)

#: Report sections, in the order they are printed, and the kinds each collects.
#: The *order* is an editorial decision and lives here; the *vocabulary* does
#: not — it lives in ``constants.KNOWLEDGE_KINDS`` and is checked against this
#: table at import time by :func:`_check_section_order`.
#:
#: **Tuples, not sets, and that is the whole point.** These were sets, and
#: ``finalize_run`` iterates them — ``for kind in kinds for unit in
#: grouped.get(kind, [])`` — so the order of units inside every multi-kind
#: section was Python's set iteration order over interned strings, which
#: changes with ``PYTHONHASHSEED`` and therefore from one process to the next.
#: ``report.md`` was **not reproducible**: finalizing the same run twice
#: produced two files whose sections held the same units in different orders,
#: with no validator looking at it and nothing in the suite pinning it (the
#: committed ``output/pqlWNihgdjI/report.md`` disagrees with a fresh finalize
#: for this reason alone). Found by `T-230`, whose acceptance clause requires
#: the YouTube sample's report to be byte-identical to what it produces today —
#: a clause that cannot be *checked* against a nondeterministic file, let alone
#: met. The order within each group is now the one the author typed.
SECTION_ORDER: list[tuple[str, tuple[str, ...]]] = [
    ("Core Thesis", ("claim", "principle")),
    ("Evidence", ("evidence",)),
    ("Concepts & Definitions", ("concept", "definition")),
    ("Frameworks & Mental Models", ("framework", "mental_model", "diagnostic_model")),
    ("Processes / How-To", ("process", "instruction")),
    ("Examples & Case Studies", ("example", "case_study", "analogy")),
    ("Facts & Statistics", ("fact", "statistic")),
    ("Recommendations", ("recommendation", "actionable_experiment")),
    ("Caveats & Limitations", ("caveat", "limitation", "assumption", "counterargument")),
    ("Open Questions", ("question", "open_problem", "hypothesis")),
    ("Derived Synthesis", ("relationship", "implication", "generalized_rule", "synthesis")),
    ("References & Quotes", ("reference", "quote")),
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
        covered |= set(kinds)
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

@dataclass(frozen=True)
class MediumProfile:
    """Everything one medium does differently on the way to a finished run.

    `T-230`: ``finalize_run``, ``_obsidian_files``, ``_unit_markdown`` and
    ``_coverage_markdown`` were YouTube-shaped in six places, and a Twitter run
    therefore ended at ``validation.json`` — no ``graph.json``, no ``report.md``,
    no vault note (D-234). This table is the generalization, and it is sized for
    the four media the user ordered rather than for the second one: adding
    Medium/articles, books or website links is a row here, and the code that
    reads it does not change.

    Data where a medium differs by a *name* and a callable where it differs by a
    *rule*. The three callables are pure — they build strings and write nothing
    — which is what lets ``finalize_run`` keep its whole-set-before-first-write
    discipline while dispatching inside it: a medium that refuses to render
    refuses before ``write_group`` is reached, not half way through it.

    There is deliberately no second ``finalize_run``. D-185 is about exactly the
    shape this would otherwise have taken.
    """

    #: ``type:`` in the source note's frontmatter. This is what the acceptance
    #: clause means by the note naming the medium it came from, and it is why no
    #: separate ``source_type:`` line is added: ``type: video`` and ``type:
    #: post`` already say it, and a YouTube note has to stay byte-identical.
    note_type: str
    #: The vault subtree the source note lives in, and the subtree finalize
    #: prunes for this medium (D-090 names the subtrees, not ``vault/``).
    note_dir: str
    #: Frontmatter key naming the run's own id, in the source note and in every
    #: unit note. YouTube says ``video_id``; a Twitter run's id is its anchor.
    id_key: str
    #: How a unit note links back to its source. "Source video", "Source post".
    backlink_label: str
    #: The ``metadata.json`` field holding the source URL. The note prints it
    #: under the key ``source_url`` for every medium; the field it is *read*
    #: from is per-medium, because a Twitter run already carries ``source_url``
    #: and a YouTube run carries ``video_url``.
    url_field: str
    #: What the coverage pointer in ``report.md`` calls the audit's unit.
    coverage_noun: str
    #: ``metadata.json`` fields that must be non-empty strings before anything
    #: is written. Checked as a set rather than assumed, because ``report.md``
    #: and the vault subscript them directly (D-077's lesson, per medium).
    required_metadata: tuple[str, ...]
    #: The ``## Metadata`` rows of ``report.md``, after the source URL.
    metadata_lines: Callable[[Mapping[str, Any]], list[str]]
    #: A source claim's citation line(s). Takes the unit's ``source`` block and
    #: the run id; returns the ``**Source:**`` line. The shared evidence-excerpt
    #: line stays in ``_unit_markdown`` — it is not per-medium.
    provenance_lines: Callable[[Mapping[str, Any], str, str], list[str]]
    #: The body of the coverage report: one section per window, or per item.
    coverage_sections: Callable[[Mapping[str, Any]], list[str]]
    #: The validator that produces the standing verdict, section for section.
    #: ``pipeline.validate_run`` reads a transcript and segments and would fail
    #: a Twitter run for not having them, so the *seventh* YouTube-shaped place
    #: in this path was the refusal itself: finalize would have refused every
    #: Twitter run before reaching anything the six other places got wrong.
    #: Both write ``validation.json`` and return the same shape (D-225), which
    #: is what lets one profile field stand in for both.
    validate: Callable[[Path], dict[str, Any]]
    #: The apply gate a model's extraction goes through. Added by `T-229` for
    #: the same reason ``validate`` was: the CLI needs to reach it, and the
    #: alternative to one more row here is a second dispatch table somewhere
    #: else (D-243). Both gates share the bundle's top-level contract outright
    #: (``validators.bundle_shape_error``) and differ only in what the bundle is
    #: checked against.
    apply_bundle: Callable[[Path, Path], dict[str, Any]]


def _youtube_metadata_lines(metadata: Mapping[str, Any]) -> list[str]:
    return [
        f"- Channel: {metadata['channel']}",
        f"- Language: `{metadata['language']}`",
        f"- Transcript hash: `{metadata['transcript_hash']}`",
    ]


def _twitter_capture_hash(metadata: Mapping[str, Any]) -> str:
    """The digest recorded over ``capture.json``, refused if it is absent.

    A Twitter run's integrity row is not ``transcript_hash``: there is no
    transcript, and the capture is the one canonical document extraction reads
    (``twitter.extract.SEALED_CANONICAL_FILES``). The digest lives one level
    down, in ``canonical_hashes``, so the string ``_checked_metadata`` can check
    is not there to check — which is why this refuses here instead, and why it
    is reached while ``report.md`` is still being *built*.
    """
    hashes = metadata.get("canonical_hashes")
    digest = hashes.get(CAPTURE_FILENAME) if isinstance(hashes, Mapping) else None
    if not isinstance(digest, str) or not digest:
        raise PipelineError(
            "metadata.json states no digest for "
            f"canonical_hashes[{CAPTURE_FILENAME!r}], which is the integrity "
            "row report.md prints for this medium. Re-initialize the run from "
            "its capture rather than filling the field in by hand."
        )
    return digest


def _twitter_metadata_lines(metadata: Mapping[str, Any]) -> list[str]:
    return [
        f"- Author: {metadata['channel']}",
        f"- Language: `{metadata['language']}`",
        f"- Capture hash: `{_twitter_capture_hash(metadata)}`",
    ]


def _youtube_provenance_lines(
    source: Mapping[str, Any], run_id: str, unit_id: str
) -> list[str]:
    """A timestamp range, linked into the video at its start.

    The ``start_sec`` default of ``0`` is left exactly as it was. It is
    unreachable through this function — ``validate_provenance`` requires the
    field for a YouTube claim and ``finalize_run`` refuses a ``FAIL`` run before
    reaching here — and removing it would change YouTube rendering, which
    `T-230`'s acceptance clause pins byte-for-byte. The Twitter renderer below
    refuses rather than defaults, because *there* the default was reachable: it
    was reached by this function being the only one there was.
    """
    start = source.get("start_sec", 0)
    end = source.get("end_sec", start)
    return [
        f"**Source:** [{format_timestamp(start)}–{format_timestamp(end)}]"
        f"({timestamp_url(run_id, start)})"
    ]


def _twitter_provenance_lines(
    source: Mapping[str, Any], run_id: str, unit_id: str
) -> list[str]:
    """The post the claim was taken from, and the span inside it.

    Codepoints, never seconds, and the post's own canonical URL rather than the
    run's: a claim in a ten-post thread cites the post it came from, which is
    the artifact ``TwitterAdapter._post_artifacts`` mints for that item (D-233,
    D-237). ``twitter.extract.post_url`` is the one implementation of that URL,
    so the note and the capture cannot spell it two ways.

    The coordinate wording matches what the Reader renders for the same claim
    (D-239) — "characters n–m" — so a unit read in the vault and the same unit
    read in the app do not describe their provenance differently.

    Missing fields are refused rather than defaulted. ``validate_post_provenance``
    requires all three and ``finalize_run`` refuses a ``FAIL`` run, so this arm
    is unreachable through the pipeline; it exists because the YouTube renderer's
    equivalent arm silently invented a timestamp and a watch URL for exactly the
    input this one names.
    """
    post_id = source.get("post_id")
    start = source.get("start_char")
    end = source.get("end_char")
    if not isinstance(post_id, str) or not post_id:
        raise PipelineError(
            f"Knowledge unit {unit_id!r} is a source claim with no post_id, so "
            "its provenance line would cite no artifact. Re-apply the extraction "
            "bundle through twitter.extract.apply_extraction_bundle, which "
            "refuses this."
        )
    if not isinstance(start, int) or not isinstance(end, int):
        raise PipelineError(
            f"Knowledge unit {unit_id!r} cites post {post_id} with no character "
            f"span (start_char={start!r}, end_char={end!r}). A span is not "
            "defaulted: an invented one would read as a measurement."
        )
    return [f"**Source:** [post `{post_id}`, characters {start}–{end}]({post_url(post_id)})"]


def _window_sections(coverage: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
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
        lines.extend(_audit_note_lines(window))
        lines.append("")
    return lines


def _item_sections(coverage: Mapping[str, Any]) -> list[str]:
    """One section per capture item, which is what a Twitter run's audit counts.

    An item-based ``coverage.json`` has no ``windows`` and no seconds (D-225), so
    the window renderer produced a coverage report holding its header and nothing
    else — an audit that reported on nothing while looking complete.
    """
    lines: list[str] = []
    for item in coverage.get("items", []):
        lines.extend(
            [
                f"## {item.get('item_id')}",
                "",
                f"- Post: `{item.get('post_id')}`",
                f"- Status: `{item.get('status')}`",
                f"- Knowledge units: {', '.join(item.get('knowledge_units', [])) or 'none'}",
            ]
        )
        lines.extend(_audit_note_lines(item))
        lines.append("")
    return lines


def _audit_note_lines(unit: Mapping[str, Any]) -> list[str]:
    """The omissions and unresolved items an audit unit records.

    Shared by both renderers: what a window and an item each *say* about their
    gaps has the same shape, and only what they are keyed by differs.
    """
    lines: list[str] = []
    for omission in unit.get("omitted_items", []):
        lines.append(f"- Omitted `{omission.get('type')}`: {omission.get('note', '')}")
    for unresolved in unit.get("unresolved_items", []):
        lines.append(f"- Unresolved `{unresolved.get('type')}`: {unresolved.get('note', '')}")
    return lines


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


def _carry_coverage_scaffold_forward(run_dir: Path, coverage: dict[str, Any]) -> None:
    """Restore the fields the scaffolded ``coverage.json`` knows and a bundle does not.

    D-164: the bundle's coverage document *replaced* the scaffolded one, adding
    back only ``schema_version`` and ``video_id``. So ``window_size_sec`` — what
    ``constants.py`` calls part of the file format, and what makes a window's
    span checkable — plus ``summary`` and every window's ``caption_ids`` were
    silently dropped on the first apply, and every run that had ever had a
    bundle applied was missing the very fields the coverage audit is checked
    against.

    ``window_size_sec`` and ``caption_ids`` are carried forward, because they
    are facts about the transcript that no model pass can know better than the
    scaffold did. ``summary`` is **recomputed** rather than carried, because it
    is derived from the windows the bundle just supplied: carrying the
    scaffold's would restate ``covered_windows: 0`` over a document in which
    every window is covered.

    ``window_size_sec`` is carried **unconditionally**, and that word is the
    whole guard. `validators.validate_coverage` measures every window against
    the value the audited document itself carries, so while the scaffold's was
    restored only when the bundle omitted it, a bundle that *stated* a wider
    one set its own bound and the check measured it against itself. That is
    D-164's bypass reopened one field along: an identical single ``[0, 1795]``
    window over a 1795-second run is ``FAIL`` with the scaffold's 300 and
    ``PASS`` with a declared 1795 — a claim of completion over 29 of 30
    minutes that were never audited, which is the one thing `WORKFLOW.md` §4
    and `AGENTS.md` forbid outright. An audit may subdivide a scaffolded
    window; nothing it can write may widen one.
    """
    scaffold = run_dir / "coverage.json"
    previous: Any = None
    if scaffold.is_file():
        try:
            previous = read_json(scaffold)
        except (JsonReadError, OSError):
            previous = None
    if isinstance(previous, dict):
        if "window_size_sec" in previous:
            coverage["window_size_sec"] = previous["window_size_sec"]
        captions_by_window = {
            window.get("window_id"): window.get("caption_ids")
            for window in previous.get("windows", [])
            if isinstance(window, dict) and isinstance(window.get("caption_ids"), list)
        }
        for window in coverage.get("windows", []):
            if not isinstance(window, dict) or "caption_ids" in window:
                continue
            carried = captions_by_window.get(window.get("window_id"))
            if carried is not None:
                window["caption_ids"] = list(carried)
    else:
        # No readable scaffold -- a damaged run, or one whose `coverage.json`
        # was removed. The bundle must still not name its own bound: the widest
        # window the format allows is `COVERAGE_WINDOW_SEC`, which is what
        # `create_pending_coverage` would have minted.
        stated = coverage.get("window_size_sec")
        if not isinstance(stated, (int, float)) or isinstance(stated, bool):
            coverage["window_size_sec"] = constants.COVERAGE_WINDOW_SEC
        elif stated > constants.COVERAGE_WINDOW_SEC:
            coverage["window_size_sec"] = constants.COVERAGE_WINDOW_SEC

    windows = coverage.get("windows")
    if not isinstance(windows, list):
        return
    statuses = [
        window.get("status") if isinstance(window, dict) else None for window in windows
    ]
    coverage["summary"] = {
        "total_windows": len(windows),
        "covered_windows": sum(1 for status in statuses if status == "covered"),
        "pending_windows": sum(1 for status in statuses if status == "pending"),
        "unresolved_important_items": sum(
            len(window.get("unresolved_items") or [])
            for window in windows
            if isinstance(window, dict) and isinstance(window.get("unresolved_items"), list)
        ),
    }


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


def _checked_metadata(
    metadata: dict[str, Any], profile: MediumProfile
) -> dict[str, Any]:
    """``metadata.json``, refused unless it carries the fields *this medium* prints.

    The field list is per-medium (``MediumProfile.required_metadata``) because the
    report's ``## Metadata`` block is: a Twitter run carries ``source_url`` where a
    YouTube run carries ``video_url``, and has no ``transcript_hash`` at all. The
    old single list demanded all five of every medium, which is the first of the
    six places a Twitter finalize stopped.
    """
    missing = [
        field
        for field in profile.required_metadata
        if not isinstance(metadata.get(field), str) or not metadata[field]
    ]
    if missing:
        raise PipelineError(
            f"metadata.json lacks the fields the final report states for a "
            f"{profile.note_type}: {missing}"
        )
    return metadata


def _slug(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\t\n\r]", "_", value).strip().rstrip(".")
    return value or "untitled"


def apply_extraction_bundle(run_dir: Path, bundle_path: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    bundle = _read(bundle_path.expanduser().resolve())
    # The bundle's top-level contract, checked once for both media
    # (`validators.bundle_shape_error`): the `units` misspelling of D-073, the
    # three required keys and the silent `relationships` default of D-169, the
    # unknown-key refusal, and `extraction_metadata` being an object.
    shape_error = bundle_shape_error(bundle)
    if shape_error:
        raise PipelineError(shape_error)
    metadata = _read(run_dir / "metadata.json")
    # D-077: `metadata["video_id"]` raised a bare `KeyError` for a
    # metadata.json that had lost the key. `finalize_run` already read it
    # through `_checked_video_id`; apply-bundle did not.
    video_id = _checked_video_id(metadata)
    units_document = {
        "schema_version": "1.0",
        "video_id": video_id,
        "units": bundle["knowledge_units"],
    }
    relationships_document = {
        "schema_version": "1.0",
        "video_id": units_document["video_id"],
        "relationships": bundle["relationships"],
    }
    coverage_document = bundle["coverage"]
    coverage_document.setdefault("schema_version", "1.0")
    coverage_document.setdefault("video_id", units_document["video_id"])
    _carry_coverage_scaffold_forward(run_dir, coverage_document)

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
    # D-168: the run's recorded duration, which is the video's own length when
    # yt-dlp reported one. `validate_run` reaches the same number the same way,
    # so the gate and the standing verdict cannot disagree about how long the
    # run is.
    coverage_validation = validate_coverage(
        coverage_document, run_duration_sec(metadata, transcript.get("captions"))
    )
    errors = {
        "knowledge_units": unit_validation["errors"],
        "provenance": provenance_validation["errors"],
        "relationships": relationship_validation["errors"],
        "coverage": coverage_validation["errors"],
    }
    if any(errors.values()):
        raise PipelineError(f"Extraction bundle failed validation: {json.dumps(errors, ensure_ascii=False)}")

    # D-164: this was a partial copy of `pipeline._coverage_link_errors` —
    # unknown references and unaccounted source units, and neither of them
    # tying a window's citations to its own span. Both callers now share one
    # implementation, so a rule added in one place cannot be missing in the
    # other, and this is where it matters most: `apply-bundle` is the gate a
    # model's output goes through.
    link_errors = validate_coverage_links(coverage_document, units_document["units"])
    if link_errors:
        raise PipelineError(
            f"Coverage does not match the knowledge units: "
            f"{json.dumps(link_errors, ensure_ascii=False)}"
        )

    extraction_metadata = bundle.get("extraction_metadata")
    if extraction_metadata is not None:
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


#: One row per medium. Two exist because two media exist — a row for a medium
#: with no capture contract, no extraction and no adapter would be an invented
#: output format, not a generalization. The seam is what `T-230` delivers for
#: all four (D-234, D-240); Medium/articles, books and website links each add a
#: row when their adapter does. `T-229` added ``validate`` and ``apply_bundle``
#: to the row rather than starting a second table somewhere else, so this is
#: also what ``x2knwldg validate`` and ``apply-bundle`` dispatch on (D-243).
MEDIUM_PROFILES: dict[str, MediumProfile] = {
    ids.DEFAULT_SOURCE_TYPE: MediumProfile(
        note_type="video",
        note_dir="videos",
        id_key="video_id",
        backlink_label="Source video",
        url_field="video_url",
        coverage_noun="window-by-window",
        required_metadata=("title", "video_url", "channel", "language", "transcript_hash"),
        metadata_lines=_youtube_metadata_lines,
        provenance_lines=_youtube_provenance_lines,
        coverage_sections=_window_sections,
        validate=validate_run,
        apply_bundle=apply_extraction_bundle,
    ),
    TWITTER_SOURCE_TYPE: MediumProfile(
        note_type="post",
        note_dir="posts",
        id_key="anchor_post_id",
        backlink_label="Source post",
        url_field="source_url",
        coverage_noun="post-by-post",
        # `transcript_hash` has no counterpart and `canonical_hashes` is an
        # object, so the integrity row is checked by the renderer that reads it
        # (`_twitter_capture_hash`) rather than by the string check here.
        required_metadata=("title", "source_url", "channel", "language"),
        metadata_lines=_twitter_metadata_lines,
        provenance_lines=_twitter_provenance_lines,
        coverage_sections=_item_sections,
        validate=validate_twitter_run,
        apply_bundle=apply_twitter_bundle,
    ),
}


def _profile_for(metadata: Mapping[str, Any]) -> MediumProfile:
    """The medium's profile, or a refusal naming the media that have one.

    ``validators.validate_provenance`` *defaults* an unknown source type to
    YouTube and records an error; this refuses. The difference is what the two
    do next: that function goes on to report, and this one goes on to write
    files whose names and frontmatter come from the answer.
    """
    source_type = declared_source_type(metadata)
    profile = MEDIUM_PROFILES.get(source_type)
    if profile is None:
        raise PipelineError(
            f"metadata.json declares source_type {source_type!r}, which no "
            "medium profile describes, so this run cannot be validated, applied "
            "to or finalized. The media that have one are "
            f"{sorted(MEDIUM_PROFILES)}; add a row to artifacts.MEDIUM_PROFILES "
            "rather than a second pipeline (D-240, D-243)."
        )
    return profile


def _unit_markdown(
    unit: dict[str, Any], video_id: str, profile: MediumProfile
) -> list[str]:
    lines = [f"### {unit['id']} — {unit['kind']}", "", f"**Statement:** {unit['content']}"]
    if unit.get("normalized_statement"):
        lines.append(f"**Normalized:** {unit['normalized_statement']}")
    if unit.get("source_class") == "source":
        source = unit.get("source", {})
        # The citation is per-medium; the excerpt beneath it is not. Splitting
        # them this way is why a second medium adds a renderer rather than a
        # branch through this function.
        lines.extend(profile.provenance_lines(source, video_id, unit["id"]))
        if source.get("evidence_excerpt"):
            lines.append(f"**Evidence excerpt:** “{source['evidence_excerpt']}”")
    else:
        derived = ", ".join(unit.get("derived_from", []))
        lines.append(f"**Derived from:** {derived}")
        lines.append(f"**Derivation:** {unit.get('derivation_note', '')}")
    lines.extend([f"**Confidence:** {unit.get('confidence')}", ""])
    return lines


def _coverage_markdown(coverage: dict[str, Any], profile: MediumProfile) -> str:
    """The coverage audit as Markdown, over whatever unit this medium audits.

    The header is shared and the body is dispatched: windows for a video, items
    for a capture. It used to iterate ``windows`` unconditionally, so an
    item-based document rendered the header alone.
    """
    lines = ["# Coverage Audit", "", f"**Coverage: {coverage.get('status', 'UNKNOWN')}**", ""]
    lines.extend(profile.coverage_sections(coverage))
    return "\n".join(lines)


def _obsidian_files(
    run_dir: Path,
    metadata: dict[str, Any],
    units: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    coverage: dict[str, Any],
    video_id: str,
    profile: MediumProfile,
) -> list[tuple[Path, str]]:
    """Build the vault as ``(path, text)`` pairs. It writes nothing.

    *video_id* has already passed :func:`_checked_video_id`. It arrives as a
    parameter rather than being re-read from *metadata* so that the unchecked
    value cannot reach a path from inside this function.

    Building every file before any of them is written is what lets
    :func:`finalize_run` fail without having half-replaced a vault.
    """
    vault = run_dir / "vault"
    # `vault/videos/<id>.md` for a video, `vault/posts/<id>.md` for a post. The
    # note's *identity* is per-medium (D-234): a run's note is a note about the
    # thing the run is, not about a video that happens to be its second medium.
    video_path = vault / profile.note_dir / f"{video_id}.md"
    unit_links = [f"- [[{unit['id']}]] — {unit['content']}" for unit in units]
    files: list[tuple[Path, str]] = [
        (
            video_path,
            "\n".join(
                [
                    "---",
                    f"type: {profile.note_type}",
                    f"{profile.id_key}: {video_id}",
                    f"source_url: \"{metadata[profile.url_field]}\"",
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
            f"{profile.id_key}: {video_id}",
            "---",
            "",
            f"# {unit['id']}",
            "",
            unit["content"],
            "",
            f"{profile.backlink_label}: [[{video_id}]]",
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
    files.append(
        (vault / "reports" / f"{video_id}-coverage.md", _coverage_markdown(coverage, profile))
    )
    return files


def validate_any_run(run_dir: Path) -> dict[str, Any]:
    """Validate a run of any medium, choosing the validator from what it declares.

    `T-229`: ``x2knwldg validate`` called ``pipeline.validate_run`` outright, so
    it reported a Twitter run as broken for having no transcript — the same
    seventh YouTube-shaped place D-240 found inside ``finalize_run``, in the
    command instead of the function. Dispatching here rather than in the CLI is
    what keeps the medium out of the command: ``cli.main`` should not know how
    many media there are (D-243).
    """
    run_dir = run_dir.expanduser().resolve()
    return _profile_for(_read(run_dir / "metadata.json")).validate(run_dir)


def apply_bundle_to_any_run(run_dir: Path, bundle_path: Path) -> dict[str, Any]:
    """Apply an extraction bundle to a run of any medium, through that medium's gate.

    A gate in the same sense for both: a bundle that fails validation is refused
    rather than written, so a run cannot reach the disk in a state its own
    validators reject (D-229, D-230).
    """
    run_dir = run_dir.expanduser().resolve()
    profile = _profile_for(_read(run_dir / "metadata.json"))
    return profile.apply_bundle(run_dir, bundle_path)


def initialize_capture_run(run_dir: Path) -> dict[str, Any]:
    """Turn an acquired capture into an initialized run.

    Re-exported here so the CLI reaches one module for the whole journey rather
    than importing ``twitter.extract`` directly and thereby naming a medium.
    ``initialize_run`` refuses a run that already has canonical outputs, so
    calling it twice is safe and the second call says why it declined.
    """
    return initialize_twitter_run(run_dir)


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
    # Which medium this run is, before anything is checked in its name — and
    # before it is validated, because *which validator* is one of the things
    # the medium decides. The two refusals D-234 required be kept are both
    # below and both unchanged; what they look for now comes from the profile.
    metadata = _read(run_dir / "metadata.json")
    video_id = _checked_video_id(metadata)
    profile = _profile_for(metadata)
    validation = profile.validate(run_dir)
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
    _checked_metadata(metadata, profile)
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
        f"- Source: {metadata[profile.url_field]}",
        *profile.metadata_lines(metadata),
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
            lines.extend(_unit_markdown(unit, video_id, profile))
    remaining = [unit for unit in units if unit["id"] not in included]
    if remaining:
        lines.extend(["## Other Knowledge", ""])
        for unit in remaining:
            lines.extend(_unit_markdown(unit, video_id, profile))
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
            f"See `coverage.json` and `vault/reports/{video_id}-coverage.md` for the {profile.coverage_noun} audit.",
            "",
        ]
    )
    obsidian_files = _obsidian_files(
        run_dir, metadata, units, relationships, coverage, video_id, profile
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
            # This medium's own note subtree, not every medium's: pruning
            # `vault/videos` for a Twitter run would delete notes this finalize
            # never owned, and pruning nothing would leave a retracted note
            # behind (D-090).
            run_dir / "vault" / profile.note_dir,
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
