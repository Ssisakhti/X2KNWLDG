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
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .io import timestamp_url
from .pipeline import PipelineError, resolve_run_dir

#: A caption match is worth half a knowledge-unit match at the same score: the
#: unit is the extracted knowledge, the caption is the fallback to raw evidence.
CAPTION_WEIGHT = 0.5

#: Scripts written without spaces between words. ``\w+`` takes a whole run of
#: them as one token, so "機械学習" and a query of "機械 学習" share nothing —
#: these are split per character and per adjacent pair instead.
_SCRIPTLESS = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)


class UnsearchableRun(ValueError):
    """A run whose canonical files cannot yield a hit the contract can carry.

    A ``ValueError``, so the repository seam — which already treats a canonical
    file that is present and unparseable as *unreadable* rather than empty —
    records the source and carries on instead of failing the whole search.
    """


def _fold(value: str) -> str:
    """*value* normalised and case-folded, once, the same way on both sides.

    NFKC first: without it a full-width or decomposed spelling of a word is a
    different string from its composed form, so it matches neither by phrase nor
    by token, and the search reports zero results for text it holds.
    """
    return unicodedata.normalize("NFKC", value).casefold()


def _tokens(value: str) -> set[str]:
    """The match tokens of *value*, folded.

    Single-character tokens are kept. Dropping them made a query composed only
    of short words unanswerable — it returned nothing and said nothing about
    why — and the score already divides by the query's token count, so a common
    one-character token ranks below any real match rather than displacing it.
    """
    tokens: set[str] = set()
    for word in re.findall(r"\w+", _fold(value), flags=re.UNICODE):
        if _SCRIPTLESS.search(word):
            tokens.add(word)
            tokens.update(word)
            tokens.update(word[i : i + 2] for i in range(len(word) - 1))
        else:
            tokens.add(word)
    return tokens


def _seconds(value: Any) -> float | None:
    """*value* as a timing, or ``None`` when it does not state one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


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
        return cls(hit=hit, folded=_fold(text), tokens=frozenset(_tokens(text)), weight=weight)

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

    Nothing here invents a value to fill a field. A unit that states no numeric
    ``start_sec`` gets neither a timing nor a deep link, which is what the
    contract means by "absent, not zero". A caption cannot be handled that way —
    the frozen contract requires ``start_sec`` *and* ``source_url`` on every
    caption hit — so a caption that states no usable timing raises
    :class:`UnsearchableRun` rather than being filed at second 0 with a
    ``&t=0s`` link to a moment nothing happened at. Canonical captions always
    carry a timing (``transcripts._canonical_caption`` refuses to write one
    without), so this is damage, and damage is reported.
    """
    knowledge_path = run_dir / "knowledge_units.json"
    metadata_path = run_dir / "metadata.json"
    if not knowledge_path.exists() or not metadata_path.exists():
        return []
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    video_id = metadata.get("video_id")
    title = metadata.get("title")
    # A deep link needs an id to point at. Read once, never indexed directly:
    # ``metadata["video_id"]`` used to raise a bare ``KeyError`` that escaped
    # the D-030 taxonomy and reached the client as a 500 with no error body.
    addressable = isinstance(video_id, str) and bool(video_id)

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
        start = _seconds(source.get("start_sec"))
        hit = {
            "type": "knowledge_unit",
            "video_id": video_id,
            "title": title,
            "id": unit.get("id"),
            "kind": unit.get("kind"),
            "source_class": unit.get("source_class"),
            "content": unit.get("content"),
            "confidence": unit.get("confidence"),
        }
        if start is not None:
            hit["start_sec"] = start
            if addressable:
                hit["source_url"] = timestamp_url(video_id, start)
        if unit.get("source_class") == "derived":
            hit["derived_from"] = unit.get("derived_from", [])
        documents.append(SearchDocument.of(hit, searchable))

    # Every caption hit the contract accepts carries a `source_url`, and there
    # is no honest one for a run whose metadata states no `video_id`. Its units
    # still search — they need no link — and its captions are left out rather
    # than pointed at a guess.
    if include_transcript and addressable:
        transcript_path = run_dir / "transcript.json"
        if transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            for caption in transcript.get("captions", []):
                text = str(caption.get("text") or "")
                start = _seconds(caption.get("start_sec"))
                if start is None:
                    raise UnsearchableRun(
                        f"caption {caption.get('segment_id')!r} in {run_dir.name} "
                        "states no start_sec, and a caption hit cannot be built "
                        "without one"
                    )
                documents.append(
                    SearchDocument.of(
                        {
                            "type": "transcript_caption",
                            "video_id": video_id,
                            "title": title,
                            "caption_id": caption.get("segment_id"),
                            "content": caption.get("text"),
                            "start_sec": start,
                            "end_sec": caption.get("end_sec"),
                            "source_url": timestamp_url(video_id, start),
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
    folded = _fold(query).strip()
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
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise PipelineError(f"limit must be an integer, got {type(limit).__name__}")
    if limit < 1:
        # `max(1, limit)` used to turn a limit of 0 into 1, answering a question
        # the caller did not ask. There is no ceiling here on purpose: the corpus
        # is what bounds a local search, and the HTTP page bound belongs to the
        # frozen contract, enforced at the repository seam.
        raise PipelineError(f"limit must be at least 1, got {limit}")
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
    return [dict(hit) for hit in rank_documents(documents, query, limit=limit)]
