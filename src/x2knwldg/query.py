"""Ranked search over the canonical files of one or more runs.

The unit of work is a :class:`SearchDocument`: one searchable thing — a
knowledge unit or a transcript caption — carrying both the hit it becomes and
the text it matches on, folded and tokenised **once**, when the run is read.

That split matters to more than tidiness. ``search_knowledge`` reads and rescores
every canonical file on every call, which is correct for a CLI or an MCP tool
that asks one question and exits, and ruinous for a paged API that asks the same
question once per page. :class:`~x2knwldg.repository.memory.MemoryRepository`
builds its documents once from the runs the index holds and ranks against them,
so the two share the scoring rule and the hit shape without sharing the cost.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .io import timestamp_url
from .pipeline import resolve_run_dir

#: A caption match is worth half a knowledge-unit match at the same score: the
#: unit is the extracted knowledge, the caption is the fallback to raw evidence.
CAPTION_WEIGHT = 0.5


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"\w+", value.casefold(), flags=re.UNICODE) if len(token) > 1}


@dataclass(frozen=True)
class SearchDocument:
    """One searchable thing, and the hit it becomes when it matches.

    ``folded`` and ``tokens`` are derived from the searchable text at
    construction. Scoring the same corpus twice must give the same answer, and
    re-deriving them per query is the whole of the per-page cost.
    """

    #: The result dict this document yields when it scores. Never mutated here.
    hit: Mapping[str, Any]
    #: The searchable text, case-folded, for the phrase bonus.
    folded: str
    #: Its word tokens, for the overlap score.
    tokens: frozenset[str]
    #: What a match on this document is worth relative to a knowledge unit.
    weight: float = 1.0

    @classmethod
    def of(
        cls, hit: Mapping[str, Any], text: str, *, weight: float = 1.0
    ) -> "SearchDocument":
        return cls(hit=hit, folded=text.casefold(), tokens=frozenset(_tokens(text)), weight=weight)

    def score(self, folded_query: str, query_tokens: frozenset[str] | set[str]) -> float:
        """This document's score for an already-folded, already-tokenised query."""
        if not folded_query:
            return 0
        overlap = len(query_tokens & self.tokens)
        phrase_bonus = 5 if folded_query in self.folded else 0
        return self.weight * (phrase_bonus + overlap / max(1, len(query_tokens)))


def run_documents(run_dir: Path, *, include_transcript: bool = True) -> list[SearchDocument]:
    """Every searchable document one canonical run holds, in canonical order.

    A run without ``metadata.json`` or ``knowledge_units.json`` is not a run
    this can search, and yields nothing. A file that *is* there and cannot be
    parsed raises: an unreadable canonical file is not the same fact as an empty
    one, and the caller has to be able to tell them apart before it reports a
    count (``PageInfo.total`` is null for unknown, and never zero for it).
    """
    knowledge_path = run_dir / "knowledge_units.json"
    metadata_path = run_dir / "metadata.json"
    if not knowledge_path.exists() or not metadata_path.exists():
        return []
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))

    documents: list[SearchDocument] = []
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
        start = source.get("start_sec")
        hit = {
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
            hit["start_sec"] = start
            hit["source_url"] = timestamp_url(metadata["video_id"], start)
        if unit.get("source_class") == "derived":
            hit["derived_from"] = unit.get("derived_from", [])
        documents.append(SearchDocument.of(hit, searchable))

    if include_transcript:
        transcript_path = run_dir / "transcript.json"
        if transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            for caption in transcript.get("captions", []):
                text = str(caption.get("text") or "")
                start = caption.get("start_sec", 0)
                documents.append(
                    SearchDocument.of(
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
                        text,
                        weight=CAPTION_WEIGHT,
                    )
                )
    return documents


def rank_documents(
    documents: Iterable[SearchDocument], query: str, *, limit: int | None = None
) -> list[Mapping[str, Any]]:
    """*documents* that score, best first, ties in the order they were given.

    The hits are the documents' own, not copies: ``search_knowledge`` builds a
    fresh set on every call and a repository copies the page it hands out. A
    caller that keeps a corpus alive and mutates a returned hit is editing its
    own index, which is why every hand-out boundary copies.
    """
    folded = query.casefold().strip()
    tokens = frozenset(_tokens(query))
    scored: list[tuple[float, Mapping[str, Any]]] = []
    for document in documents:
        score = document.score(folded, tokens)
        if not score:
            continue
        scored.append((score, document.hit))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    ranked = [hit for _, hit in scored]
    return ranked if limit is None else ranked[:limit]


def search_knowledge(
    output_root: Path,
    query: str,
    *,
    video_id: str | None = None,
    limit: int = 10,
    include_transcript_fallback: bool = True,
) -> list[dict[str, Any]]:
    output_root = output_root.expanduser().resolve()
    # A caller-supplied id is never joined raw onto a path (risk R14).
    run_dirs = (
        [resolve_run_dir(output_root, video_id)]
        if video_id
        else sorted(output_root.glob("*"))
    )
    documents: list[SearchDocument] = []
    for run_dir in run_dirs:
        documents.extend(
            run_documents(run_dir, include_transcript=include_transcript_fallback)
        )
    return [dict(hit) for hit in rank_documents(documents, query, limit=max(1, limit))]
