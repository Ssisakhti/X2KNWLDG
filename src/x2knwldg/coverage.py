from __future__ import annotations

import math
from typing import Any

from .constants import COVERAGE_WINDOW_SEC


def spans_overlap(
    span_start: float,
    span_end: float,
    start: float,
    end: float,
    *,
    tolerance: float = 0.0,
) -> bool:
    """Does ``[span_start, span_end]`` share real time with the window ``[start, end)``?

    One statement of "does this thing fall inside that window", because there
    used to be two and they had already drifted apart. This function was the
    body of :func:`caption_in_window` — a strict half-open test with no epsilon
    — while ``validators.validate_coverage_links`` asked the same question as
    ``unit_end > start - TIME_TOLERANCE_SEC and unit_start < end +
    TIME_TOLERANCE_SEC``. The second spelling applies the epsilon in the
    **permissive** direction: it widens the window by a hundredth of a second at
    each edge, so a unit that merely *touches* an edge from outside counts as
    evidence inside it. On the committed ``bsmUh5bTNZ4`` run that let a window
    spanning 509.599–639.92 — 130 seconds and 444 spoken words — be reported
    ``covered``, anchored by a unit ending at exactly 509.599 and one starting at
    exactly 639.92, neither of which contributes a single second of the evidence
    the window claims. ``x2knwldg validate`` returned six PASS sections and exit
    ``0`` over it.

    *tolerance* is how much overlap is required rather than how much slack is
    granted, so the epsilon can only ever make the test **stricter**. Each caller
    passes what its own inputs justify:

    * ``0.0`` for captions, because ``create_pending_coverage`` mints the window
      edges from the very caption timings it is placing, so the two sides of the
      comparison are the same numbers and an epsilon would only misplace a
      caption that sits exactly on a boundary.
    * ``TIME_TOLERANCE_SEC`` for a knowledge unit's evidence, whose bounds are
      authored by a model pass and round-tripped through JSON, and where an
      overlap thinner than the epsilon is indistinguishable from no overlap at
      all. Requiring more than the epsilon is what refuses an edge-touching
      citation; granting it was the defect.
    """
    return span_end > start + tolerance and span_start < end - tolerance


def caption_in_window(caption: dict[str, Any], start: float, end: float, is_last: bool) -> bool:
    """Does this caption belong to the window ``[start, end)``?

    A zero-length caption — which a json3 event with no ``dDurationMs`` used to
    mint — satisfies no strict overlap at all, so ``end_sec > start`` orphaned it
    from every window and its content was never audited. Zero-length captions are
    placed by position instead; the final window owns its own right edge so
    nothing falls off the end.

    The overlap itself is :func:`spans_overlap` at zero tolerance, which is the
    predicate this function has always applied — see that docstring for why the
    validator's copy of it needs a different one and why that difference is
    stated rather than left to two implementations to keep in step.
    """
    caption_start = caption["start_sec"]
    caption_end = caption["end_sec"]
    if caption_end <= caption_start:
        return start <= caption_start < end or (is_last and caption_start == end)
    return spans_overlap(caption_start, caption_end, start, end)


def create_pending_coverage(
    captions: list[dict[str, Any]],
    video_id: str,
    window_sec: float = COVERAGE_WINDOW_SEC,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """The unaudited coverage document for a run, one window per *window_sec*.

    D-168: *duration_sec* is the **media's** length when it is known, and the
    windows are minted over that rather than over the caption span. A caption
    track covering the first ten minutes of a two-hour talk used to produce five
    windows and a fully covered timeline, because the scaffold, the reported
    duration and the completeness check all derived from the same truncated
    number — so no comparison between them could ever detect the truncation.
    Minted over the video, the same run produces twenty-four windows and
    twenty-two of them have no captions to audit, which is the honest picture.
    """
    caption_end = max((caption["end_sec"] for caption in captions), default=0)
    duration = caption_end
    if duration_sec is not None and duration_sec > caption_end:
        duration = duration_sec
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

