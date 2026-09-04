"""The smallest registration that keeps the project projectable (T-227).

``T-228`` owns the Twitter adapter: Source, Artifact, Locator and Entity
records, the SQLite rebuild and the read surfaces. This is not that. It exists
because ``T-227`` made a Twitter run **discoverable** — ``io.run_dirs`` globs
``output/*/metadata.json`` — and an unregistered source type is refused by
``get_adapter``, so a single acquired post took the whole project's projection
down with it: the ``MemoryRepository`` oracle, the library, search and the Map,
for every YouTube run as well.

That refusal is load-bearing and was not weakened to fix this. ``adapt_project``
raising is what ``strict=True`` reproduces for ``T-104``'s equivalence proof
(D-043, D-078), and it is also what keeps a run from claiming the reserved
``library:concepts`` namespace — a run declaring ``source_type: "library"`` is
refused precisely because nothing is registered for it. Making unregistered
types skippable would have quietly removed that guard.

So the fix is to register, and to register **only what needs no decision
``T-228`` owns**. One ``Source`` record per run, from fields
``twitter.extract`` already writes. Deliberately no ``Artifact``, ``Entity`` or
``IndexedRelation`` records:

* An **Entity** carries a ``Locator``, and no locator branch can express a
  Twitter claim — ``schemas/v1/locator.schema.json`` reserves ``post_id`` with
  no span fields and ``text_span`` with no post id. D-212 hands that widening to
  ``T-228`` in as many words, so minting entities here would mean inventing the
  locator shape ``T-228`` is supposed to decide.
* An **Artifact** would name ``capture.json`` and ``raw/`` as readable files,
  which is a Reader question rather than an index question.

The result is honest rather than complete: a Twitter run appears as a source
with no knowledge attached, which is exactly what it is until ``T-228`` projects
its units. ``adapter_metadata`` says so, so nobody reads the emptiness as a
damaged run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ids import make_source_id
from .base import (
    MAX_TITLE_LENGTH,
    MAX_URL_LENGTH,
    SCHEMA_VERSION,
    IndexRecords,
    SourceAdapter,
    copied_text,
    copied_timestamp,
    read_optional_json,
)


def _counts(run_dir: Path, metadata: dict[str, Any]) -> dict[str, int]:
    """Cached counts, every one reproducible from the canonical files.

    The schema is explicit that a stale count "is a bug, never a data
    achievement", so these are read from the files rather than carried from
    anywhere: a run whose extraction has not happened counts zero units, and
    says so.
    """
    knowledge = read_optional_json(run_dir / "knowledge_units.json")
    relationships = read_optional_json(run_dir / "relationships.json")
    units = knowledge.get("units") if isinstance(knowledge, dict) else None
    units = [unit for unit in units if isinstance(unit, dict)] if isinstance(units, list) else []
    edges = relationships.get("relationships") if isinstance(relationships, dict) else None
    edges = [edge for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []
    item_count = metadata.get("item_count")
    counts = {
        "knowledge_units": len(units),
        "source_units": sum(1 for unit in units if unit.get("source_class") == "source"),
        "derived_units": sum(1 for unit in units if unit.get("source_class") == "derived"),
        "relationships": len(edges),
    }
    if isinstance(item_count, int) and not isinstance(item_count, bool) and item_count >= 0:
        counts["segments"] = item_count
    return counts


class TwitterAdapter(SourceAdapter):
    """Maps a Twitter run onto one ``Source`` record and nothing else."""

    source_type = "twitter"
    #: ``0.1`` and not ``1.0``: the shape is deliberately partial, and a
    #: re-index has to be forced when ``T-228`` completes it.
    version = "0.1"

    def detect(self, run_dir: Path) -> bool:
        metadata = read_optional_json(run_dir / "metadata.json")
        if not isinstance(metadata, dict):
            return False
        return metadata.get("source_type") == self.source_type

    def adapt_run(self, run_dir: Path, *, hash_artifacts: bool = False) -> IndexRecords:
        run_dir = run_dir.expanduser().resolve()
        metadata = read_optional_json(run_dir / "metadata.json")
        if not isinstance(metadata, dict):
            return IndexRecords()
        source_id = make_source_id(self.source_type, metadata.get("video_id"))
        return IndexRecords(sources=[self._source(run_dir, metadata, source_id, source_id.value)])

    def _source(
        self,
        run_dir: Path,
        metadata: dict[str, Any],
        source_id: Any,
        owner: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.value,
            "source_type": source_id.source_type,
            "external_id": source_id.external_id,
            "url": copied_text(
                metadata.get("source_url"),
                owner=owner,
                field="source_url",
                max_length=MAX_URL_LENGTH,
                allow_empty=False,
            ),
            "title": copied_text(
                metadata.get("title"), owner=owner, field="title", max_length=MAX_TITLE_LENGTH
            ),
            # The generic model's publisher field. A YouTube channel, a Medium
            # byline and an X handle all land here.
            "author": copied_text(
                metadata.get("author_username"),
                owner=owner,
                field="author_username",
                max_length=MAX_TITLE_LENGTH,
            ),
            "language": copied_text(
                metadata.get("language"), owner=owner, field="language", max_length=64
            ),
            # No duration: a post is not a time-based medium, and `0` would be a
            # measurement rather than an absence.
            "duration_sec": None,
            "imported_at": copied_timestamp(
                metadata.get("imported_at"), owner=owner, field="imported_at"
            ),
            "extracted_at": copied_timestamp(
                metadata.get("acquired_at"), owner=owner, field="acquired_at"
            ),
            "canonical_dir": self.relative(run_dir),
            # The base class's builder, not a second one: `status` is a
            # structured record — three verbatim copies, two paths, a bounded
            # `audit_attempts` — and this adapter's first version wrote a bare
            # string into it. There is no branch anywhere in it that can turn a
            # stated PARTIAL or FAIL into anything else (ADR 0001 invariant 2).
            "status": self._status(run_dir, []),
            # The six keys `schemas/v1/source.schema.json` defines, and only
            # those: `counts` is `additionalProperties: false`. `segments` is
            # the item count, which is the one mapping that is *exactly* right
            # here — a post is the segment. `captions` is omitted rather than
            # zeroed: there are none, and `0` would say a count was taken.
            "counts": _counts(run_dir, metadata),
            "artifact_ids": [],
            "adapter": self.ref,
            "adapter_metadata": {
                "projection": "source_only",
                "note": (
                    "T-227 registers this source type so one acquired post cannot refuse "
                    "the whole project's projection. Entities, artifacts and relations "
                    "are T-228's, which owns the locator widening D-212 records: no "
                    "locator branch can carry a post id and a span together yet."
                ),
                "item_count": metadata.get("item_count"),
                "capture_coverage_status": metadata.get("capture_coverage_status"),
            },
        }
