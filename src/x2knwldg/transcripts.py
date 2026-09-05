from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypeGuard

from .constants import MAX_CAPTION_GAP_SEC
from .io import is_finite_seconds


class TranscriptError(ValueError):
    """Raised when a transcript cannot satisfy the canonical timing contract."""


# D-165: the fraction was capped at three digits, so `00:00:01,0000` matched
# nothing, every timing line in such a file fell through to body text, and the
# file was rejected as "No timestamped cues were found" — contradicting the
# promise below that a damaged timing line reaches `parse_timestamp` and is
# reported. It is read as a decimal fraction of a second (`float("0." + digits)`),
# which is well defined at any length, so accepting more digits accepts more
# real files and misreads none.
_TIMESTAMP = re.compile(
    r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2})"
    r"(?P<fraction>[.,]\d+)?$"
)
# The same grammar without the capture names, so the cue-timing detector below
# cannot drift from the parser that then has to accept what it found. Their
# agreement is asserted in tests/test_transcripts_hardening.py.
_TIMESTAMP_TOKEN = r"(?:\d+:)?\d{1,2}:\d{1,2}(?:[.,]\d+)?"
# A cue timing line is one whose **left side** is a timestamp. Judging it by the
# bare presence of ``-->`` read ``The mapping A --> B is important.`` as a
# timing line and rejected the entire file with ``Invalid timestamp: 'The'``
# (D-076). Only the left side is anchored: a line that really is a cue timing
# line but has a damaged *end* must still reach ``parse_timestamp`` and be
# reported, rather than silently becoming body text.
_CUE_TIMING = re.compile(rf"^\s*{_TIMESTAMP_TOKEN}\s*-->")
# A timed-text header is ``[HH:MM:SS - HH:MM:SS]``. The groups are restricted to
# timestamp shapes so that ordinary bracketed caption text — ``[Applause - laughter]``
# — is read as text instead of being mistaken for a header, which used to reject
# the whole file.
#
# ``_TIMESTAMP_TOKEN``, not a fourth spelling of the same grammar. This used to
# be its own pattern allowing **four** leading digits where the parser allows
# two, so ``[1234:56 - 1300:00]`` was *detected* as a header and then refused by
# ``parse_timestamp``, rejecting the whole file — where the comment's stated
# intent is that a bracket which is not a timestamp reads as text. The detector
# and the parser have to accept the same thing here for the same reason
# ``_CUE_TIMING`` does; their agreement is asserted in
# tests/test_transcripts_hardening.py.
_TIMED_TEXT = re.compile(
    rf"^\[\s*(?P<start>{_TIMESTAMP_TOKEN})\s*(?:-->|[-–—])\s*"
    rf"(?P<end>{_TIMESTAMP_TOKEN})\s*\]\s*(?P<text>.*)$"
)
# Caption markup only. A blanket ``<[^>]+>`` also ate every inequality, threshold
# and generic in the transcript (``if x < 5 and y > 3`` -> ``if x 3``), and this
# function feeds transcript.json, the canonical extraction input.
_CAPTION_MARKUP = re.compile(
    r"""
    </?(?:v|c|lang|b|i|u|ruby|rt)      # WebVTT voice/class/lang and styling tags
        (?:\.[^\s<>./]+)*              # class annotations: <c.yellow.bg_blue>
        (?:[ \t][^<>]*)?               # an annotation such as <v Speaker> or <lang en>
    >
    |
    <\d{1,4}:\d{1,2}(?::\d{1,2})?[.,]\d{1,3}>   # cue timestamp tag: <00:00:01.000>
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Lines that head a WebVTT file or a non-cue block, and so can never be a cue
# identifier.
_HEADER_LINE = re.compile(
    r"^(?:WEBVTT\b.*|X-[A-Z0-9-]+\s*[:=].*|NOTE(?:\s.*)?|STYLE|REGION)$", re.IGNORECASE
)
# json3 events carry ``dDurationMs`` only sometimes. A missing duration used to
# mint a zero-length caption, which then fell out of every coverage window.
_JSON3_FALLBACK_DURATION_SEC = 2.0
_JSON3_MAX_INFERRED_DURATION_SEC = 10.0


def _is_finite_number(value: Any) -> TypeGuard[float]:
    """Module-local alias for ``io.is_finite_seconds``; see it for the rule."""
    return is_finite_seconds(value)


def _finite(value: Any, message: str) -> float:
    """Coerce ``value`` to a finite float or raise :class:`TranscriptError`.

    NaN and Infinity used to survive every check, crash the import, and reach
    canonical JSON that no other language can parse.
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TranscriptError(message) from exc
    if not math.isfinite(number):
        raise TranscriptError(f"{message}: {value!r} is not a finite number")
    return number


def json3_duration(start_sec: float, next_start_sec: float | None) -> float:
    """Extent for a json3 event whose ``dDurationMs`` is missing or non-positive.

    Zero length is not a sane extent: it orphans the caption from every coverage
    window, so the event runs up to the next one (capped) or takes a short
    default. One home for the rule — :mod:`youtube` mints the same events off the
    yt-dlp path and calls this too.
    """
    if (
        next_start_sec is not None
        and math.isfinite(next_start_sec)
        and next_start_sec > start_sec
    ):
        return min(next_start_sec - start_sec, _JSON3_MAX_INFERRED_DURATION_SEC)
    return _JSON3_FALLBACK_DURATION_SEC


def parse_timestamp(value: str) -> float:
    parts = value.strip().split()
    if not parts:
        raise TranscriptError("Invalid timestamp: empty value")
    value = parts[0]
    match = _TIMESTAMP.match(value)
    if not match:
        raise TranscriptError(f"Invalid timestamp: {value!r}")
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    fraction = match.group("fraction")
    milliseconds = float(f"0.{fraction[1:]}" if fraction else 0)
    return hours * 3600 + minutes * 60 + seconds + milliseconds


def clean_text(value: str) -> str:
    """Strip caption markup, leaving ordinary text — ``<`` and ``>`` included — alone.

    A **parse-time** cleaner, applied once, when a cue is first read. It is not
    idempotent and cannot be: ``html.unescape`` is a *decoding* step, and
    decoding an already-decoded string decodes it again. A cue whose authored
    text reads ``the token is &amp;amp; and ...`` is stored canonically as
    ``the token is &amp; and ...``, and cleaning that a second time yields
    ``the token is & and ...`` — a third string that appears in no file of the
    run. :func:`comparable_text` is what compares two already-cleaned strings;
    see its docstring for the excerpt this let through.
    """
    value = _CAPTION_MARKUP.sub("", value)
    # Before the fold, and never again afterwards: unescaping can *produce* an
    # angle bracket (``&lt;b&gt;`` becomes ``<b>``), and a second markup pass
    # over the result would eat text the source really wrote.
    value = html.unescape(value)
    return _fold_invisibles(value)


def _fold_invisibles(value: str) -> str:
    """Drop zero-width characters and collapse whitespace. Idempotent by construction."""
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(value.split()).strip()


def comparable_text(value: str) -> str:
    """*value* normalised for comparing two strings that are **already canonical**.

    :func:`clean_text` minus its one non-idempotent step, and that subtraction
    is the whole point. ``validators.validate_provenance`` used to run the full
    ``clean_text`` over both the evidence excerpt and the segment text it was
    matched against — but a segment's text was cleaned once already, when
    ``_canonical_caption`` parsed the cue it was assembled from. The second
    ``html.unescape`` therefore decoded it twice: a source that says ``the token
    is &amp;amp; and nothing else`` is stored as ``the token is &amp; and
    nothing else``, and an excerpt reading ``the token is & and nothing else``
    — a string present in no canonical file of the run — became a substring of
    the doubly-decoded segment and was reported as proven provenance. Two
    canonical strings may only be compared through a normalisation that is
    idempotent, or the comparison is not about the files.

    Markup stripping and the whitespace fold stay, because both *are*
    idempotent and because they are what forgives a quotation the line break or
    the stray ``<i>`` a model wraps around real content. Entity decoding is the
    only step removed.
    """
    return _fold_invisibles(_CAPTION_MARKUP.sub("", value))


def _canonical_caption(
    index: int,
    start: Any,
    end: Any,
    duration: Any,
    text: Any,
    source: str,
    language: str,
    original_id: Any = None,
    speaker: Any = None,
) -> dict[str, Any] | None:
    """Build one canonical caption.

    A cue whose text cleans away is *kept*, marked ``non_speech``, because
    dropping it used to shrink the reported ``duration_sec`` and the audited
    coverage windows with it — one 600 second video reported 5.0 seconds and
    audited only 0–5s. Only an entry with neither text nor a usable start time
    is discarded: that is not a cue at all.
    """
    text_value = clean_text(str(text or ""))
    if not text_value:
        try:
            _finite(start, "")
        except TranscriptError:
            return None

    start_value = _finite(start, f"Caption {index} has no valid start time")
    if end is not None:
        end_value = _finite(end, f"Caption {index} has an invalid end time")
    elif duration is not None:
        end_value = start_value + _finite(
            duration, f"Caption {index} has an invalid duration"
        )
    else:
        raise TranscriptError(f"Caption {index} needs end_sec or duration")

    result: dict[str, Any] = {
        "segment_id": f"cap_{index:06d}",
        "start_sec": round(start_value, 3),
        "end_sec": round(end_value, 3),
        "duration_sec": round(end_value - start_value, 3),
        "text": text_value,
        "source": source,
        "language": language,
    }
    if not text_value:
        result["non_speech"] = True
    if original_id not in (None, ""):
        result["original_id"] = str(original_id)
    if speaker not in (None, ""):
        result["speaker"] = str(speaker)
    return result


def _cue_chunks(block: str) -> Iterable[tuple[str | None, str, list[str]]]:
    """Yield ``(identifier, timing_line, body_lines)`` for every cue in one block.

    A block is located by its ``-->`` lines rather than by its first line. Judging
    a block by ``lines[0]`` lost real cues two ways: a ``WEBVTT`` header not
    separated from the first cue by a blank line (the usual HLS shape) took that
    cue down with it, and a cue whose identifier merely started with
    ``NOTE``/``STYLE``/``REGION`` was discarded outright.

    A block may hold several cues when the separator line between them carried
    stray whitespace, so every timing line in the block starts a cue.

    A *timing line* is one matching ``_CUE_TIMING``, not merely one containing
    ``-->``: a caption whose text says ``The mapping A --> B is important.``
    used to be read as a cue timing and took the whole file down with it.
    """
    lines = block.split("\n")
    timing_indexes = [index for index, line in enumerate(lines) if _CUE_TIMING.match(line)]
    consumed_until = 0
    for position, timing_index in enumerate(timing_indexes):
        next_timing = (
            timing_indexes[position + 1]
            if position + 1 < len(timing_indexes)
            else len(lines)
        )
        body = lines[timing_index + 1 : next_timing]
        # A blank-ish line followed by one non-blank line, immediately before the
        # next timing line, is that next cue's identifier \u2014 not this cue's text.
        #
        # D-165: that was the *only* rule, and it needs the blank line. SRT
        # written without blank separators is ordinary output from real muxers,
        # and there `body[-2]` is the previous cue's own text, so the guard
        # never fired and every cue absorbed the next cue's index number:
        # `'One. 2'`, `'Two. 3'`. The corruption landed in the canonical
        # `transcript.json` \u2014 the extraction input \u2014 and, through the
        # segments, in the text evidence excerpts are matched against. A bare
        # integer on the line immediately before a timing line is an SRT
        # sequence number by the format's own grammar; nothing else in a cue's
        # text sits there alone.
        if next_timing < len(lines) and body and body[-1].strip():
            if len(body) >= 2 and not body[-2].strip():
                body = body[:-2]
            elif body[-1].strip().isdigit():
                body = body[:-1]
        identifier = None
        if timing_index > 0 and timing_index - 1 >= consumed_until:
            candidate = lines[timing_index - 1].strip()
            if candidate and not _CUE_TIMING.match(candidate) and not _HEADER_LINE.match(candidate):
                identifier = candidate
        consumed_until = timing_index + 1 + len(body)
        yield identifier, lines[timing_index], body


def _parse_srt_or_vtt(text: str, source: str, language: str) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    # Split on truly empty lines only: a whitespace-only line inside a cue used
    # to split the block, and the remainder \u2014 carrying no ``-->`` \u2014 was dropped.
    blocks = re.split(r"\n{2,}", normalized)
    captions: list[dict[str, Any]] = []
    for block in blocks:
        for identifier, timing, body_lines in _cue_chunks(block):
            start_raw, _, end_raw = timing.partition("-->")
            end_parts = end_raw.split()
            body = " ".join(line.strip() for line in body_lines if line.strip())
            caption = _canonical_caption(
                len(captions) + 1,
                parse_timestamp(start_raw),
                parse_timestamp(end_parts[0] if end_parts else ""),
                None,
                body,
                source,
                language,
                original_id=identifier,
            )
            if caption:
                captions.append(caption)
    if not captions:
        raise TranscriptError("No timestamped cues were found in the subtitle file")
    return captions


def _json_items(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise TranscriptError("Transcript JSON must be an object or an array")
    for key in ("captions", "segments", "transcript", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    if isinstance(data.get("events"), list):
        events = []
        timed = [
            event
            for event in data["events"]
            if isinstance(event, dict) and "tStartMs" in event
        ]
        for position, event in enumerate(timed):
            start_sec = _finite(
                event["tStartMs"], f"json3 event {position + 1} has an invalid tStartMs"
            ) / 1000
            duration_sec = 0.0
            if event.get("dDurationMs") is not None:
                duration_sec = (
                    _finite(
                        event["dDurationMs"],
                        f"json3 event {position + 1} has an invalid dDurationMs",
                    )
                    / 1000
                )
            if duration_sec <= 0:
                next_start: float | None = None
                for later in timed[position + 1 :]:
                    try:
                        next_start = float(later["tStartMs"]) / 1000
                    except (TypeError, ValueError):
                        continue
                    break
                duration_sec = json3_duration(start_sec, next_start)
            events.append(
                {
                    "start_sec": start_sec,
                    "duration": duration_sec,
                    "text": "".join(
                        str(segment.get("utf8", ""))
                        for segment in event.get("segs", [])
                        if isinstance(segment, dict)
                    ),
                }
            )
        return events
    raise TranscriptError("Transcript JSON contains no recognized caption list")


def _parse_json(text: str, source: str, language: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"Invalid transcript JSON: {exc}") from exc
    return captions_from_items(
        _json_items(data),
        source,
        language,
        empty_message="Transcript JSON contains no usable timestamped captions",
    )


def captions_from_items(
    items: Iterable[dict[str, Any]],
    source: str,
    language: str,
    *,
    empty_message: str = "No usable timestamped captions were supplied",
) -> list[dict[str, Any]]:
    """The one loop that turns supplied items into canonical captions.

    Every JSON-shaped input path goes through here — the file parser and the
    yt-dlp path both — so the field aliases and the drop rule have one home.
    """
    captions: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        caption = _canonical_caption(
            len(captions) + 1,
            item.get("start_sec", item.get("start")),
            item.get("end_sec", item.get("end")),
            item.get("duration_sec", item.get("duration")),
            item.get("text", item.get("content")),
            str(item.get("source") or source),
            str(item.get("language") or language),
            original_id=item.get("segment_id", item.get("id")),
            speaker=item.get("speaker"),
        )
        if caption:
            captions.append(caption)
    if not captions:
        raise TranscriptError(empty_message)
    return captions


def _parse_timed_text(text: str, source: str, language: str) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for raw_line in text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _TIMED_TEXT.match(line)
        if match:
            if pending:
                caption = _canonical_caption(
                    len(captions) + 1,
                    pending["start"],
                    pending["end"],
                    None,
                    pending["text"],
                    source,
                    language,
                )
                if caption:
                    captions.append(caption)
            pending = {
                "start": parse_timestamp(match.group("start")),
                "end": parse_timestamp(match.group("end")),
                "text": match.group("text"),
            }
        elif pending:
            pending["text"] = f"{pending['text']} {line}".strip()
    if pending:
        caption = _canonical_caption(
            len(captions) + 1,
            pending["start"],
            pending["end"],
            None,
            pending["text"],
            source,
            language,
        )
        if caption:
            captions.append(caption)
    if not captions:
        raise TranscriptError(
            "Plain text is accepted only with [HH:MM:SS - HH:MM:SS] timing headers"
        )
    return captions


def parse_transcript_file(
    path: Path, language: str = "unknown", source: str | None = None
) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    inferred_source = source or {
        ".srt": "imported_srt",
        ".vtt": "imported_vtt",
        ".json": "imported_json",
        ".txt": "imported_timed_text",
        ".md": "imported_timed_text",
    }.get(suffix, "imported_file")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TranscriptError("Transcript file must be UTF-8 encoded") from exc
    if suffix in {".srt", ".vtt"}:
        return _parse_srt_or_vtt(text, inferred_source, language)
    if suffix == ".json":
        return _parse_json(text, inferred_source, language)
    if suffix in {".txt", ".md"}:
        return _parse_timed_text(text, inferred_source, language)
    raise TranscriptError(f"Unsupported transcript format: {suffix or '(no extension)'}")


def transcript_end_sec(captions: Any) -> float:
    """Where the transcript ends: the largest finite ``end_sec`` among *captions*.

    Defect D-077: this expression existed four times — in ``transcript_integrity``
    below, ``validators.validate_provenance``, ``pipeline.validate_run`` and
    ``artifacts.apply_extraction_bundle`` — at three different guard levels. The
    strictest filtered non-finite values; the other three were
    ``max((c.get("end_sec", 0) for c in captions), default=0)``, which raises
    ``AttributeError`` on a caption that is a string and ``TypeError`` on one
    whose ``end_sec`` is ``null``, because ``max`` then compares ``None`` with a
    float. Both escaped as raw tracebacks from ``validate`` and ``finalize``.

    Tolerant on purpose, and the only tolerant thing here: this answers "how
    long is the medium" for callers that go on to *report* what is wrong with
    the document. Whether a damaged caption is an error is
    ``transcript_integrity``'s decision, and it is not made twice.
    """
    if not isinstance(captions, list):
        return 0.0
    return float(
        max(
            (
                caption["end_sec"]
                for caption in captions
                if isinstance(caption, dict) and is_finite_seconds(caption.get("end_sec"))
            ),
            default=0.0,
        )
    )


def transcript_integrity(
    captions: list[dict[str, Any]], max_gap_sec: float = MAX_CAPTION_GAP_SEC
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    previous_start = -1.0
    previous_end = 0.0
    previous_text = ""
    duplicate_count = 0
    if not isinstance(captions, list):
        # D-077: `for caption in captions` iterated a dict's keys and raised on
        # anything else. A transcript.json whose `captions` is not an array is
        # a finding to report, not a traceback.
        return {
            "status": "FAIL",
            "errors": [{"code": "captions_not_array"}],
            "warnings": [],
            "stats": {
                "caption_count": 0,
                "duration_sec": 0.0,
                "character_count": 0,
                "adjacent_duplicate_count": 0,
            },
        }
    for index, caption in enumerate(captions):
        if not isinstance(caption, dict):
            # D-077: `caption.get(...)` on a string caption was an
            # `AttributeError` out of the middle of `validate`.
            errors.append({"code": "caption_not_object", "caption": index})
            continue
        caption_id = caption.get("segment_id")
        start = caption.get("start_sec")
        end = caption.get("end_sec")
        text = str(caption.get("text") or "").strip()
        if not text and not caption.get("non_speech"):
            errors.append({"code": "empty_text", "caption_id": caption_id})
        # NaN and Infinity are floats, so an isinstance check alone let them
        # through into canonical JSON no other language can read back.
        if not _is_finite_number(start) or not _is_finite_number(end):
            errors.append({"code": "invalid_timing", "caption_id": caption_id})
            continue
        if start < 0 or end < start:
            errors.append({"code": "invalid_timing", "caption_id": caption_id})
        if start < previous_start:
            errors.append({"code": "non_monotonic_start", "caption_id": caption_id})
        gap = start - previous_end
        # ``previous_end`` starts at the beginning of the media, and 0.0 is
        # falsy: guarding on it hid an hour of silence before the first caption.
        if gap > max_gap_sec:
            warnings.append(
                {
                    "code": "large_gap",
                    "start_sec": round(previous_end, 3),
                    "end_sec": round(start, 3),
                    "duration_sec": round(gap, 3),
                }
            )
        normalized_text = text.casefold()
        if normalized_text and normalized_text == previous_text:
            duplicate_count += 1
            warnings.append({"code": "adjacent_duplicate", "caption_id": caption_id})
        previous_start = start
        previous_end = max(previous_end, end)
        previous_text = normalized_text
    character_count = sum(
        len(str(c.get("text") or "")) for c in captions if isinstance(c, dict)
    )
    if captions and character_count == 0:
        # D-167: a transcript with timing and no words at all. `character_count`
        # was already computed here and read by nothing, so the signal existed
        # and nothing looked at it. The way in is a caption source that renames
        # its text field: `item.get("text")` returns `None`,
        # `_canonical_caption` cleans that to `""` and marks the cue
        # `non_speech` — the `[music]` concession — and `empty_text` above is
        # disarmed by exactly that flag. Six snippets carrying their text under
        # `.content` therefore produced `character_count: 0`,
        # `validation.transcript: PASS` and exit `0`: a run with full-length
        # coverage windows over nothing anyone said.
        #
        # A cue is allowed to be non-speech. A whole transcript is not: there is
        # no video whose entire caption track is `[music]`, and if there were,
        # it carries no knowledge to extract and must not be imported as though
        # it did.
        errors.append({"code": "transcript_has_no_text", "caption_count": len(captions)})
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "caption_count": len(captions),
            "duration_sec": round(transcript_end_sec(captions), 3),
            "character_count": character_count,
            "adjacent_duplicate_count": duplicate_count,
        },
    }
