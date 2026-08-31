from __future__ import annotations

import math
from typing import Any


def create_pending_coverage(
    captions: list[dict[str, Any]], video_id: str, window_sec: float = 300
) -> dict[str, Any]:
    duration = max((caption["end_sec"] for caption in captions), default=0)
    window_count = max(1, math.ceil(duration / window_sec))
    windows: list[dict[str, Any]] = []
    for index in range(window_count):
        start = index * window_sec
        end = duration if index == window_count - 1 else min(duration, (index + 1) * window_sec)
        caption_ids = [
            caption["segment_id"]
            for caption in captions
            if caption["end_sec"] > start and caption["start_sec"] < end
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
        "window_size_sec": window_sec,
        "windows": windows,
        "summary": {
            "total_windows": len(windows),
            "covered_windows": 0,
            "pending_windows": len(windows),
            "unresolved_important_items": len(windows),
        },
    }

