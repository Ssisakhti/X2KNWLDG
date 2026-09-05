"""Bounded, deterministic candidate discovery for cross-source synthesis (`T-253`).

Risk **R28** is that comparing sources grows quadratically: an all-pairs walk
over *n* sources is ``n(n-1)`` ordered comparisons, and each one is a model pass
over two whole knowledge-unit sets. Measured on this project's corpus by
``tools/measure_source_bounds.py``, that is already thousands of unit pairs at a
dozen sources. So a pair is compared because **something specific pointed at
it**, never because it exists.

Two discovery routes are implemented, and both are deterministic — the same
corpus produces the same candidates, in the same order, on every machine:

``explicit_reference``
    One run's canonical artifacts name another run. Today that means a Twitter
    capture's ``external_references``, whose ``post_id`` is an id the other run
    holds. This route is **directional**: a quote post references the post it
    quotes, and not the other way round.

``shared_concept``
    Two runs contribute occurrences to one canonical concept in
    ``output/library/concepts.json``. Symmetric, so it proposes both directions.

**What is deliberately not implemented.** ``SOURCE_MAP_SPEC.md`` §4 also permits
local FTS retrieval over source knowledge as a third route. It is not here, and
its absence is reported rather than hidden: :attr:`CandidateReport.routes` names
every route and says whether it was able to run, so "no candidates" never has to
be read as "nothing is related". A pair that shares no concept and carries no
reference is not proposed, and the report's ``pairs_in_corpus`` is what lets a
reader see how many pairs that was.

**Rank is not meaning.** Candidates are ordered so the bound is deterministic,
and the ordering is by how many independent routes fired and then by id. That is
a statement about *discovery*, not about the sources: nothing here is a
similarity score, and no number from this module may reach a ``SourceRelation``
as strength, importance or confidence (D-247). The ordering exists to make
"which 25" reproducible, and for no other purpose.

Read-only and stdlib-only. It opens canonical files and counts.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ids, synthesis
from .constants import MAX_SOURCE_CANDIDATES
from .io import LIBRARY_DIR_NAME, discover_run_dirs

#: The discovery routes, in the order they are reported.
ROUTE_EXPLICIT_REFERENCE = "explicit_reference"
ROUTE_SHARED_CONCEPT = "shared_concept"
ROUTES = (ROUTE_EXPLICIT_REFERENCE, ROUTE_SHARED_CONCEPT)

#: Named so the report can say it is absent rather than silently producing
#: nothing. ``SOURCE_MAP_SPEC.md`` §4 permits it; `T-253` did not implement it.
ROUTE_LOCAL_RETRIEVAL = "local_retrieval"


@dataclass(frozen=True)
class Source:
    """One acquired run, as candidate discovery needs to see it."""

    source_id: str
    run_dir: Path
    #: Every knowledge-unit id this run holds. The gate checks basis ownership
    #: against exactly this set.
    unit_ids: frozenset[str]
    #: Ids that name this source from another run's artifacts — its own external
    #: id plus, for a thread, every post id in its capture.
    reference_ids: frozenset[str]
    #: What this run's artifacts say they reference.
    references: frozenset[str]
    #: ``synthesis.run_digest`` — what a relation records for this endpoint.
    digest: str
    status: str


@dataclass(frozen=True)
class Candidate:
    """One ordered pair a comparison pass may look at, and why."""

    from_source_id: str
    to_source_id: str
    routes: tuple[str, ...]
    #: Global ids of the canonical concepts both endpoints contribute to. Given
    #: to the comparison pass as *context*, never as evidence: a shared concept
    #: is a reason to look, and overlap alone can never establish response,
    #: influence or critique (D-247).
    shared_concepts: tuple[str, ...] = ()

    @property
    def pair(self) -> tuple[str, str]:
        return (self.from_source_id, self.to_source_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_source_id": self.from_source_id,
            "to_source_id": self.to_source_id,
            "routes": list(self.routes),
            "shared_concepts": list(self.shared_concepts),
        }


@dataclass(frozen=True)
class CandidateReport:
    """What discovery proposed, what the bound kept, and what it left out."""

    sources: tuple[Source, ...]
    considered: tuple[Candidate, ...]
    omitted: tuple[Candidate, ...]
    routes: Mapping[str, str]
    bound: int = MAX_SOURCE_CANDIDATES
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pairs_in_corpus(self) -> int:
        """Every ordered pair that *could* have been compared.

        The number that keeps an empty result honest: ``considered: 3`` on its
        own cannot distinguish "three pairs were compared and none related" from
        a corpus of three sources, and this is the difference.
        """
        count = len(self.sources)
        return count * (count - 1)

    @property
    def counts(self) -> dict[str, int]:
        """The ``candidates`` block a synthesis container must carry.

        ``omitted`` is what the **bound** left out, exactly as
        ``schemas/synthesis/v1/source_relations.schema.json`` froze it in
        `T-251`. ``pairs_in_corpus`` is the additive field `T-253` needed and did
        not have: pairs no route proposed are not "omitted by the bound", and
        widening ``omitted`` to cover them would have been changing the meaning
        of a frozen field, which the versioning doctrine reserves for a v2.
        """
        return {
            "considered": len(self.considered),
            "omitted": len(self.omitted),
            "bound": self.bound,
            "pairs_in_corpus": self.pairs_in_corpus,
        }

    @property
    def considered_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(candidate.pair for candidate in self.considered)

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.source_id == source_id), None)

    def candidate(self, from_source_id: str, to_source_id: str) -> Candidate | None:
        return next(
            (c for c in self.considered if c.pair == (from_source_id, to_source_id)),
            None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": synthesis.SCHEMA_VERSION,
            "sources": [
                {"source_id": s.source_id, "status": s.status, "run_digest": s.digest}
                for s in self.sources
            ],
            "routes": dict(self.routes),
            "candidates": [candidate.as_dict() for candidate in self.considered],
            "omitted": [candidate.as_dict() for candidate in self.omitted],
            "counts": self.counts,
            "notes": list(self.notes),
        }


def _read(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _unit_ids(run_dir: Path) -> frozenset[str]:
    document = _read(run_dir / "knowledge_units.json")
    units = document.get("units") if isinstance(document, dict) else None
    if not isinstance(units, list):
        return frozenset()
    return frozenset(
        unit["id"]
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("id"), str) and unit["id"]
    )


def _capture_post_ids(run_dir: Path) -> frozenset[str]:
    """Every post id this run holds, so a reference to any of them finds it.

    A self-thread is anchored at its last post and holds ten more; a quote
    naming the seventh of them is naming *this* run, and matching on the anchor
    alone would miss it.
    """
    document = _read(run_dir / "capture.json")
    items = document.get("items") if isinstance(document, dict) else None
    if not isinstance(items, list):
        return frozenset()
    return frozenset(
        item["post_id"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("post_id"), str)
    )


def _references(metadata: Mapping[str, Any]) -> frozenset[str]:
    """The ids this run's artifacts say it references.

    Today this reads a Twitter capture's ``external_references``, which is the
    only canonical field in the project that records one source naming another.
    A YouTube run has no counterpart, so this route contributes nothing for a
    YouTube from-endpoint — stated in the report rather than left to be inferred
    from an empty result.
    """
    entries = metadata.get("external_references")
    if not isinstance(entries, list):
        return frozenset()
    return frozenset(
        entry["post_id"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("post_id"), str)
    )


def _sources(output_root: Path) -> Iterator[Source]:
    for run_dir in discover_run_dirs(output_root)[0]:
        metadata = _read(run_dir / "metadata.json")
        if not isinstance(metadata, dict):
            continue
        external_id = metadata.get("video_id")
        try:
            source_id = ids.make_source_id(
                ids.declared_source_type(metadata), external_id
            ).value
        except ids.IdError:
            # A run whose id the model cannot carry is not a candidate endpoint.
            # It is skipped rather than crashing discovery, the way every other
            # reader in this project skips an unmappable run and says so.
            continue
        validation = _read(run_dir / "validation.json")
        stated = validation.get("status") if isinstance(validation, dict) else None
        # The same word `adapters.base` uses for a missing or unreadable
        # verdict, and for the same reason: nothing is guessed.
        status = stated if isinstance(stated, str) else "UNKNOWN"
        reference_ids = frozenset({str(external_id)}) | _capture_post_ids(run_dir)
        yield Source(
            source_id=source_id,
            run_dir=run_dir,
            unit_ids=_unit_ids(run_dir),
            reference_ids=reference_ids,
            references=_references(metadata),
            digest=synthesis.run_digest(run_dir),
            status=status,
        )


def _shared_concepts(
    output_root: Path, sources: tuple[Source, ...]
) -> tuple[dict[tuple[str, str], tuple[str, ...]], str]:
    """``{(a, b): concept ids}`` for every unordered pair, plus a route note.

    ``occurrences`` are library ids — ``<external-id>:<unit-id>`` — so the
    external id is read through ``ids.parse_library_id`` rather than split by
    hand, and a source type is recovered by matching the external id against the
    corpus. Two runs of *different* media that share a concept are a candidate
    exactly like two of the same medium; that is the whole point of a canonical
    concept.
    """
    document = _read(output_root / LIBRARY_DIR_NAME / "concepts.json")
    concepts = document.get("concepts") if isinstance(document, dict) else None
    if not isinstance(concepts, list):
        return {}, (
            "unavailable: output/library/concepts.json is absent or unreadable, so "
            "no shared-concept candidate was proposed. Run x2knwldg rebuild-library"
        )

    by_external: dict[str, list[str]] = {}
    for source in sources:
        by_external.setdefault(ids.parse_source_id(source.source_id).external_id, []).append(
            source.source_id
        )

    shared: dict[tuple[str, str], set[str]] = {}
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        global_id = concept.get("global_id") or concept.get("id")
        owners: set[str] = set()
        for occurrence in concept.get("occurrences") or []:
            if not isinstance(occurrence, str):
                continue
            try:
                external_id, _ = ids.parse_library_id(occurrence)
            except ids.IdError:
                continue
            owners.update(by_external.get(external_id, ()))
        for first in sorted(owners):
            for second in sorted(owners):
                if first < second and isinstance(global_id, str):
                    shared.setdefault((first, second), set()).add(global_id)

    return (
        {pair: tuple(sorted(values)) for pair, values in shared.items()},
        f"available: {len(concepts)} canonical concepts read",
    )


def discover(output_root: Path, *, bound: int = MAX_SOURCE_CANDIDATES) -> CandidateReport:
    """Every pair worth comparing, bounded per source and counted.

    Takes the **output root** — the directory holding the runs — the way
    ``status``, ``rebuild-library`` and ``search`` do. Not a project root plus a
    directory name: that is two ways to say one thing, and D-039 removed the
    second reading of a root from this package once already.

    The bound is **per from-source**, which is what ``MAX_SOURCE_CANDIDATES``
    means: "the most candidate counterpart sources one source's synthesis pass
    compares". Bounding the whole corpus instead would let one heavily-connected
    source consume the budget and silently starve every other.
    """
    output_root = Path(output_root).expanduser().resolve()
    sources = tuple(sorted(_sources(output_root), key=lambda s: s.source_id))

    shared, concept_note = _shared_concepts(output_root, sources)
    by_id = {source.source_id: source for source in sources}

    proposed: dict[tuple[str, str], tuple[set[str], tuple[str, ...]]] = {}

    for source in sources:
        for other in sources:
            if source.source_id == other.source_id:
                continue
            if source.references & other.reference_ids:
                proposed.setdefault(
                    (source.source_id, other.source_id), (set(), ())
                )[0].add(ROUTE_EXPLICIT_REFERENCE)

    for (first, second), concepts in shared.items():
        for pair in ((first, second), (second, first)):
            routes, _ = proposed.setdefault(pair, (set(), ()))
            routes.add(ROUTE_SHARED_CONCEPT)
            proposed[pair] = (routes, concepts)

    candidates = [
        Candidate(
            from_source_id=pair[0],
            to_source_id=pair[1],
            routes=tuple(route for route in ROUTES if route in routes),
            shared_concepts=concepts,
        )
        for pair, (routes, concepts) in proposed.items()
    ]
    # Deterministic, and by discovery signal rather than by anything that could
    # be read as similarity: more independent routes first, then more shared
    # concepts, then by id so the order is total on every machine.
    candidates.sort(
        key=lambda c: (-len(c.routes), -len(c.shared_concepts), c.from_source_id, c.to_source_id)
    )

    considered: list[Candidate] = []
    omitted: list[Candidate] = []
    taken: dict[str, int] = {}
    for candidate in candidates:
        used = taken.get(candidate.from_source_id, 0)
        if used < bound:
            taken[candidate.from_source_id] = used + 1
            considered.append(candidate)
        else:
            omitted.append(candidate)

    notes: list[str] = []
    if not any(source.references for source in sources):
        notes.append(
            "no run in this corpus records an external reference, so the "
            "explicit_reference route proposed nothing"
        )
    unresolved = sorted(
        reference
        for source in sources
        for reference in source.references
        if not any(reference in other.reference_ids for other in by_id.values())
    )
    if unresolved:
        notes.append(
            "these referenced ids name no acquired run and were not proposed: "
            + ", ".join(unresolved)
        )

    return CandidateReport(
        sources=sources,
        considered=tuple(considered),
        omitted=tuple(omitted),
        routes={
            ROUTE_EXPLICIT_REFERENCE: (
                "available: read from each run's external_references"
            ),
            ROUTE_SHARED_CONCEPT: concept_note,
            ROUTE_LOCAL_RETRIEVAL: (
                "not implemented: SOURCE_MAP_SPEC.md §4 permits it and T-253 did not "
                "build it, so a pair sharing no concept and carrying no reference is "
                "not proposed"
            ),
        },
        bound=bound,
        notes=tuple(notes),
    )
