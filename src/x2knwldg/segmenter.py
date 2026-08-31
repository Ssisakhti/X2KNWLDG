from __future__ import annotations

from typing import Any


def _ends_thought(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "؟", ":", ";"))


def create_segments(
    captions: list[dict[str, Any]],
    target_sec: float = 240,
    min_sec: float = 120,
    max_sec: float = 360,
    overlap_sec: float = 15,
) -> list[dict[str, Any]]:
    """Create deterministic, time-aware segments with boundary preference.

    This is the non-LLM baseline. A later extraction agent may refine boundaries,
    but it may never lose the original caption IDs or source span.
    """
    if not captions:
        return []
    if not (0 <= overlap_sec < min_sec <= target_sec <= max_sec):
        raise ValueError("Expected 0 <= overlap < min <= target <= max")

    segments: list[dict[str, Any]] = []
    start_index = 0
    while start_index < len(captions):
        start_time = captions[start_index]["start_sec"]
        candidates: list[tuple[float, int]] = []
        last_index = start_index
        for index in range(start_index, len(captions)):
            duration = captions[index]["end_sec"] - start_time
            last_index = index
            if duration >= min_sec:
                boundary_bonus = 30 if _ends_thought(captions[index]["text"]) else 0
                score = abs(duration - target_sec) - boundary_bonus
                candidates.append((score, index))
            if duration >= max_sec:
                break

        if candidates:
            end_index = min(candidates, key=lambda candidate: candidate[0])[1]
        else:
            end_index = last_index

        selected = captions[start_index : end_index + 1]
        segment_end = selected[-1]["end_sec"]
        segments.append(
            {
                "segment_id": f"seg_{len(segments) + 1:04d}",
                "start_sec": selected[0]["start_sec"],
                "end_sec": segment_end,
                "caption_ids": [caption["segment_id"] for caption in selected],
                "text": " ".join(caption["text"] for caption in selected),
            }
        )

        if end_index >= len(captions) - 1:
            break
        overlap_boundary = segment_end - overlap_sec
        next_index = end_index + 1
        for index in range(start_index + 1, end_index + 1):
            if captions[index]["end_sec"] > overlap_boundary:
                next_index = index
                break
        start_index = max(start_index + 1, next_index)
    return segments

