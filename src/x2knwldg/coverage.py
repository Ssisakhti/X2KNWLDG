from __future__ import annotations

import math
from typing import Any

from .constants import COVERAGE_WINDOW_SEC


def caption_in_window(caption: dict[str, Any], start: float, end: float, is_last: bool) -> bool:
    """Does this caption belong to the window ``[start, end)``?

    A zero-length caption — which a json3 event with no ``dDurationMs`` used to
    mint — satisfies no strict overlap at all, so ``end_sec > start`` orphaned it
    from every window and its content was never audited. Zero-length captions are
    placed by position instead; the final window owns its own right edge so
    nothing falls off the end.
    """
    caption_start = caption["start_sec"]
    caption_end = caption["end_sec"]
    if caption_end <= caption_start:
        return start <= caption_start < end or (is_last and caption_start == end)
    return caption_end > start and caption_start < end


def create_pending_coverage(
    captions: list[dict[str, Any]], video_id: str, window_sec: float = COVERAGE_WINDOW_SEC
) -> dict[str, Any]:
    duration = max((caption["end_sec"] for caption in captions), default=0)
    window_count = max(1, math.ceil(duration / window_sec))
    windows: list[dict[str, Any]] = []
    for index in range(window_count):
        start = index * window_sec
        is_last = index == window_count - 1
        # D-097: this was `min(duration, (index + 1) * window_sec)`, and the
        # `min` could never bind — `window_count = ceil(duration / window_sec)`,
        # so for every index below the last, `(index + 1) * window_sec` is
        # strictly less than `duration` by construction. A guard that cannot
        # fire reads as a bound the caller has to think about, and there is
        # exactly one real edge here: the final window, which owns whatever
        # remains and is handled on the other branch.
        end = duration if is_last else (index + 1) * window_sec
        caption_ids = [
            caption["segment_id"]
            for caption in captions
            if caption_in_window(caption, start, end, is_last)
        ]
        windows.append(
            {
                "window_id": f"CW-{index + 1:04d}",
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "caption_ids": caption_ids,
                "status": "pending",
                "knowledge_units": [],
                "omitted_items": [],
                "unresolved_items": [
                    {
                        "type": "coverage_not_audited",
                        "note": "Knowledge extraction and coverage audit have not run yet.",
                    }
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "video_id": video_id,
        "status": "PARTIAL",
        # No audit has run yet. validators.py requires the count and accepts 0
        # only while the document does not claim PASS, so a fresh run is
        # honest rather than silently unaudited.
        "audit_attempts": 0,
        "window_size_sec": window_sec,
        "windows": windows,
        "summary": {
            "total_windows": len(windows),
            "covered_windows": 0,
            "pending_windows": len(windows),
            "unresolved_important_items": len(windows),
        },
    }

