"""Deterministic, time-aware segmentation of a caption list.

What this module promises, precisely — the previous docstring promised less
than the signature appeared to, and the code delivered less than either:

* **No caption is lost.** Every caption id appears in at least one segment,
  and segments are emitted in order.
* **A segment is at least ``min_sec`` long**, except the last one, which ends
  where the transcript ends.
* **A segment is at most ``max_sec`` long** whenever the caption boundaries
  offer any end at all inside ``[min_sec, max_sec]``. ``max_sec`` is a bound,
  not a preference: an end that respects it always beats a better-scoring one
  that does not. The exception is forced rather than chosen — a long caption,
  or a long silence, can take the running span from under ``min_sec`` straight
  past ``max_sec``, leaving no legal end to pick. Then the shortest overrun
  wins, and the segment minus its final caption is always shorter than
  ``min_sec``: that is the invariant to hold the code to. Captions are atomic
  here, so splitting one to fit would invent a boundary and a caption id no
  transcript states.
* **The four bounds are coupled**, and ``create_segments`` re-checks the
  relation it is given rather than assuming the defaults:
  ``0 <= overlap_sec < min_sec <= target_sec <= max_sec``. Lowering
  ``target_sec`` below ``min_sec`` therefore means lowering ``min_sec`` too;
  the error names the pair that disagrees instead of restating the chain.
* **``overlap_sec`` is a floor, quantised to caption boundaries, not an exact
  overlap.** The next segment begins at the first caption that ends after
  ``segment_end - overlap_sec``, so the realised overlap runs from
  ``overlap_sec`` up to ``overlap_sec`` plus the length of one caption.
* **A segment made of a single caption has no overlap with its successor**,
  whatever ``overlap_sec`` says. Overlap is re-emitted captions, and the only
  caption available to re-emit is the one the segment is; re-emitting it would
  mean the next segment started where this one did and the walk would not
  advance. This is documented rather than fixed because there is nothing to
  fix at caption granularity — it is the honest consequence of atomic
  captions, and ``tests/test_segmenter_hardening.py`` pins it so it cannot
  become an accident.

``target_sec`` is a preference, not a bound: the chosen end is the candidate
whose length is nearest ``target_sec``, with ``BOUNDARY_BONUS_SEC`` seconds of
credit for ending on a sentence boundary. Ties go to the earliest candidate,
so the output is a function of the input alone.

This is the non-LLM baseline. A later extraction agent may refine boundaries,
but it may never lose the original caption ids or source span.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    SEGMENT_MAX_SEC,
    SEGMENT_MIN_SEC,
    SEGMENT_OVERLAP_SEC,
    SEGMENT_TARGET_SEC,
)
from .io import require_seconds

#: Seconds of score credit a candidate end earns for landing on a sentence
#: boundary. Expressed in the same units as the distance from ``target_sec``
#: so the two are comparable: a boundary is worth up to 30s of drift.
BOUNDARY_BONUS_SEC = 30


def _ends_thought(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "؟", ":", ";"))


def _require_seconds(value: Any, label: str) -> float:
    """A bound is a finite, non-negative real number of seconds.

    D-185: ``io.require_seconds``, in this module's exception type. It was a
    byte-for-byte copy of ``ids._require_seconds`` apart from that type, and
    both were copies of a rule ``io`` already stated.
    """
    return require_seconds(value, label)


def _check_bounds(
    target_sec: Any, min_sec: Any, max_sec: Any, overlap_sec: Any
) -> tuple[float, float, float, float]:
    target = _require_seconds(target_sec, "target_sec")
    minimum = _require_seconds(min_sec, "min_sec")
    maximum = _require_seconds(max_sec, "max_sec")
    overlap = _require_seconds(overlap_sec, "overlap_sec")
    if not overlap < minimum:
        raise ValueError(
            f"overlap_sec ({overlap}) must be less than min_sec ({minimum}); "
            "a segment cannot re-emit more than it contains"
        )
    if not minimum <= target:
        raise ValueError(
            f"min_sec ({minimum}) must not exceed target_sec ({target}); "
            "to aim shorter, lower min_sec as well"
        )
    if not target <= maximum:
        raise ValueError(
            f"target_sec ({target}) must not exceed max_sec ({maximum}); "
            "to aim longer, raise max_sec as well"
        )
    return target, minimum, maximum, overlap


def create_segments(
    captions: list[dict[str, Any]],
    target_sec: float = SEGMENT_TARGET_SEC,
    min_sec: float = SEGMENT_MIN_SEC,
    max_sec: float = SEGMENT_MAX_SEC,
    overlap_sec: float = SEGMENT_OVERLAP_SEC,
) -> list[dict[str, Any]]:
    """Create deterministic, time-aware segments with boundary preference.

    See the module docstring for the contract this honours. ``ValueError`` names
    the two bounds that disagree, or the one bound that is not a finite,
    non-negative number.
    """
    if not captions:
        return []
    target, minimum, maximum, overlap = _check_bounds(
        target_sec, min_sec, max_sec, overlap_sec
    )

    segments: list[dict[str, Any]] = []
    start_index = 0
    while start_index < len(captions):
        start_time = captions[start_index]["start_sec"]
        # (score, index, duration) — duration is carried so max_sec can be
        # applied as a filter on the candidate set rather than as a hint.
        candidates: list[tuple[float, int, float]] = []
        last_index = start_index
        for index in range(start_index, len(captions)):
            duration = captions[index]["end_sec"] - start_time
            last_index = index
            if duration >= minimum:
                boundary_bonus = (
                    BOUNDARY_BONUS_SEC if _ends_thought(captions[index]["text"]) else 0
                )
                score = abs(duration - target) - boundary_bonus
                candidates.append((score, index, duration))
            if duration >= maximum:
                break

        within_bound = [candidate for candidate in candidates if candidate[2] <= maximum]
        if within_bound:
            # Nearest to target among the ends that respect max_sec. The key
            # includes the index so a tie resolves to the earliest candidate,
            # which is what min() already did over an ordered list — stated
            # rather than inherited, so it survives a reordering.
            end_index = min(within_bound, key=lambda candidate: (candidate[0], candidate[1]))[1]
        elif candidates:
            # Every end that reaches min_sec also overruns max_sec: the span
            # jumped from under min_sec straight past max_sec, so the caption
            # boundaries offer no legal end. Take the shortest overrun rather
            # than the best-scoring one — the bound is unreachable, so honour
            # it as closely as caption granularity allows.
            end_index = min(candidates, key=lambda candidate: (candidate[2], candidate[1]))[1]
        else:
            # The transcript ended before min_sec was reached.
            end_index = last_index

        selected = captions[start_index : end_index + 1]
        segment_end = selected[-1]["end_sec"]
        caption_ids = [caption["segment_id"] for caption in selected]
        # D-098: a long non-speech cue could make the walk emit a segment whose
        # captions are a *subset* of the previous segment's and whose text is
        # empty — an input segment with nothing in it to extract from, offered
        # to passes 1 and 4 as though it held content. The specific shape is a
        # `[music]` cue long enough to reach `max_sec` on its own: the previous
        # segment already ended on it, and `start_index` advances by one, so
        # the next span is the tail of the one just emitted.
        #
        # Skipped rather than merged, and only when it is a **subset**: those
        # captions are already carried by the previous segment, so nothing is
        # lost — which is what keeps the no-caption-loss invariant true. A
        # text-empty segment that covers captions no other segment does is
        # still emitted, because dropping it *would* lose them.
        previous_ids = set(segments[-1]["caption_ids"]) if segments else set()
        redundant = (
            bool(segments)
            and set(caption_ids) <= previous_ids
            and not " ".join(caption["text"] for caption in selected).strip()
        )
        if not redundant:
            segments.append(
                {
                    "segment_id": f"seg_{len(segments) + 1:04d}",
                    "start_sec": selected[0]["start_sec"],
                    "end_sec": segment_end,
                    "caption_ids": caption_ids,
                    "text": " ".join(caption["text"] for caption in selected),
                }
            )

        if end_index >= len(captions) - 1:
            break
        # Overlap is re-emitted captions. The scan starts at start_index + 1
        # because the next segment must begin strictly later than this one or
        # the walk does not advance — which is why a single-caption segment
        # carries no overlap at all (module docstring).
        overlap_boundary = segment_end - overlap
        next_index = end_index + 1
        for index in range(start_index + 1, end_index + 1):
            if captions[index]["end_sec"] > overlap_boundary:
                next_index = index
                break
        start_index = max(start_index + 1, next_index)
    return segments
