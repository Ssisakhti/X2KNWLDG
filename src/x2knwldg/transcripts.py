from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Iterable


class TranscriptError(ValueError):
    """Raised when a transcript cannot satisfy the canonical timing contract."""


_TIMESTAMP = re.compile(
    r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2})"
    r"(?P<fraction>[.,]\d{1,3})?$"
)
_TIMED_TEXT = re.compile(
    r"^\[(?P<start>[^\]]+?)\s*(?:-->|-)\s*(?P<end>[^\]]+?)\]\s*(?P<text>.*)$"
)
_TAG = re.compile(r"<[^>]+>")


def parse_timestamp(value: str) -> float:
    value = value.strip().split()[0]
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
    value = _TAG.sub("", value)
    value = html.unescape(value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(value.split()).strip()


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
    text_value = clean_text(str(text or ""))
    if not text_value:
        return None
    try:
        start_value = float(start)
    except (TypeError, ValueError) as exc:
        raise TranscriptError(f"Caption {index} has no valid start time") from exc

    if end is not None:
        try:
            end_value = float(end)
        except (TypeError, ValueError) as exc:
            raise TranscriptError(f"Caption {index} has an invalid end time") from exc
    elif duration is not None:
        try:
            end_value = start_value + float(duration)
        except (TypeError, ValueError) as exc:
            raise TranscriptError(f"Caption {index} has an invalid duration") from exc
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
    if original_id not in (None, ""):
        result["original_id"] = str(original_id)
    if speaker not in (None, ""):
        result["speaker"] = str(speaker)
    return result


def _parse_srt_or_vtt(text: str, source: str, language: str) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", normalized)
    captions: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        timing = lines[timing_index]
        start_raw, end_raw = [part.strip() for part in timing.split("-->", 1)]
        end_raw = end_raw.split()[0]
        original_id = lines[timing_index - 1] if timing_index > 0 else None
        body = " ".join(lines[timing_index + 1 :])
        caption = _canonical_caption(
            len(captions) + 1,
            parse_timestamp(start_raw),
            parse_timestamp(end_raw),
            None,
            body,
            source,
            language,
            original_id=original_id,
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
        for event in data["events"]:
            if not isinstance(event, dict) or "tStartMs" not in event:
                continue
            events.append(
                {
                    "start_sec": float(event["tStartMs"]) / 1000,
                    "duration": float(event.get("dDurationMs", 0)) / 1000,
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
    captions: list[dict[str, Any]] = []
    for item in _json_items(data):
        if not isinstance(item, dict):
            continue
        start = item.get("start_sec", item.get("start"))
        end = item.get("end_sec", item.get("end"))
        duration = item.get("duration_sec", item.get("duration"))
        caption = _canonical_caption(
            len(captions) + 1,
            start,
            end,
            duration,
            item.get("text", item.get("content")),
            str(item.get("source") or source),
            str(item.get("language") or language),
            original_id=item.get("segment_id", item.get("id")),
            speaker=item.get("speaker"),
        )
        if caption:
            captions.append(caption)
    if not captions:
        raise TranscriptError("Transcript JSON contains no usable timestamped captions")
    return captions


def captions_from_items(
    items: Iterable[dict[str, Any]], source: str, language: str
) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for item in items:
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
        raise TranscriptError("No usable timestamped captions were supplied")
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


def transcript_integrity(captions: list[dict[str, Any]], max_gap_sec: float = 120) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    previous_start = -1.0
    previous_end = 0.0
    previous_text = ""
    duplicate_count = 0
    for caption in captions:
        caption_id = caption.get("segment_id")
        start = caption.get("start_sec")
        end = caption.get("end_sec")
        text = str(caption.get("text") or "").strip()
        if not text:
            errors.append({"code": "empty_text", "caption_id": caption_id})
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append({"code": "invalid_timing", "caption_id": caption_id})
            continue
        if start < 0 or end < start:
            errors.append({"code": "invalid_timing", "caption_id": caption_id})
        if start < previous_start:
            errors.append({"code": "non_monotonic_start", "caption_id": caption_id})
        gap = start - previous_end
        if previous_end and gap > max_gap_sec:
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
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "caption_count": len(captions),
            "duration_sec": round(max((c["end_sec"] for c in captions), default=0), 3),
            "character_count": sum(len(c["text"]) for c in captions),
            "adjacent_duplicate_count": duplicate_count,
        },
    }
