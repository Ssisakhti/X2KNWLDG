from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io import timestamp_url


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"\w+", value.casefold(), flags=re.UNICODE) if len(token) > 1}


def _score(query: str, value: str) -> float:
    query_folded = query.casefold().strip()
    value_folded = value.casefold()
    if not query_folded:
        return 0
    query_tokens = _tokens(query)
    value_tokens = _tokens(value)
    overlap = len(query_tokens & value_tokens)
    phrase_bonus = 5 if query_folded in value_folded else 0
    return phrase_bonus + overlap / max(1, len(query_tokens))


def search_knowledge(
    output_root: Path,
    query: str,
    *,
    video_id: str | None = None,
    limit: int = 10,
    include_transcript_fallback: bool = True,
) -> list[dict[str, Any]]:
    output_root = output_root.expanduser().resolve()
    run_dirs = [output_root / video_id] if video_id else sorted(output_root.glob("*"))
    results: list[tuple[float, dict[str, Any]]] = []
    for run_dir in run_dirs:
        knowledge_path = run_dir / "knowledge_units.json"
        metadata_path = run_dir / "metadata.json"
        if not knowledge_path.exists() or not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
        for unit in knowledge.get("units", []):
            source = unit.get("source", {})
            searchable = " ".join(
                str(value or "")
                for value in (
                    unit.get("content"),
                    unit.get("normalized_statement"),
                    source.get("evidence_excerpt"),
                    unit.get("kind"),
                )
            )
            score = _score(query, searchable)
            if not score:
                continue
            start = source.get("start_sec")
            result = {
                "type": "knowledge_unit",
                "video_id": metadata.get("video_id"),
                "title": metadata.get("title"),
                "id": unit.get("id"),
                "kind": unit.get("kind"),
                "source_class": unit.get("source_class"),
                "content": unit.get("content"),
                "confidence": unit.get("confidence"),
            }
            if isinstance(start, (int, float)):
                result["start_sec"] = start
                result["source_url"] = timestamp_url(metadata["video_id"], start)
            if unit.get("source_class") == "derived":
                result["derived_from"] = unit.get("derived_from", [])
            results.append((score, result))

        if include_transcript_fallback:
            transcript_path = run_dir / "transcript.json"
            if transcript_path.exists():
                transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                for caption in transcript.get("captions", []):
                    score = _score(query, str(caption.get("text") or ""))
                    if not score:
                        continue
                    start = caption.get("start_sec", 0)
                    results.append(
                        (
                            score * 0.5,
                            {
                                "type": "transcript_caption",
                                "video_id": metadata.get("video_id"),
                                "title": metadata.get("title"),
                                "caption_id": caption.get("segment_id"),
                                "content": caption.get("text"),
                                "start_sec": start,
                                "end_sec": caption.get("end_sec"),
                                "source_url": timestamp_url(metadata["video_id"], start),
                            },
                        )
                    )
    results.sort(key=lambda pair: pair[0], reverse=True)
    return [result for _, result in results[: max(1, limit)]]

