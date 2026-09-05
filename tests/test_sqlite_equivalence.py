"""Rebuild-equivalence (``T-104``): three paths to one answer, page for page.

The thesis, in one sentence: **a full rebuild, an incremental refresh, and the
canonical files read with no cache at all must be the same answer** — not the
same counts, the same *pages*, down to the cursor token.

That is Phase 1's stated acceptance criterion ("deleting the index and
rebuilding produces an equivalent result") and ADR 0001 invariant 3, which says
the index is a rebuildable cache and deleting it must lose nothing. A cache is
disposable only if a rebuild is provably the same thing; and an incremental
update is honest only if it reaches the state a rebuild would. So every test
here compares two repositories over one tree:

* ``SqliteRepository`` after :func:`~x2knwldg.index.build_index`,
* ``SqliteRepository`` after :func:`~x2knwldg.index.refresh_index`,
* ``MemoryRepository`` — the oracle with no cache whatsoever
  (``repository/README.md``: "Track A gets an oracle").

Eight scenarios, §3 to §9, and the sharp one is §7: a run *removed*. Orphaned
artifacts, entities, relations and search documents are the classic incremental
bug, and they are invisible to a count that only ever grows.

**Why token equality is fair and load-bearing.** The cursor MAC key is random
per process (``repository.base`` on ``_CURSOR_KEY``: "Two implementations in one
process therefore still mint identical tokens for identical positions, which is
what ``T-104``'s page-for-page comparison needs"). So a token mismatch is never
a keying artefact — it means the two disagree about the position or about the
record's content digest.

**Why the oracle is rebuilt for every comparison.** ``MemoryRepository``'s
search corpus is a per-instance lazy cache that is never invalidated (D-042),
and ``docs/PROJECT_MANAGEMENT.md`` states the consequence for this task
directly: "``T-104`` must construct a fresh ``MemoryRepository`` per
comparison." :func:`compare` therefore takes *factories*, and calls them.

**What is excluded from the status comparison, and why.**
``repository/README.md`` requires the SQLite path to "report ``index_version``
from the migration table, and ``built_at`` from the last completed build", while
``MemoryRepository`` reports ``None`` for both "because it has no persisted
index — stating a version there would claim a durable artifact that does not
exist". A frozen document forces the two to differ, so those two fields are
dropped from the compared payload and asserted separately
(:func:`_assert_build_facts`) — non-null, an ``int`` equal to
``SCHEMA_VERSION``, and a parseable UTC timestamp.

Nothing here writes to ``tests/fixtures/`` or to ``output/``. Every project is a
copy under ``tmp_path``, and §12 proves it by stat.

Stdlib only (``sqlite3`` ships with Python), so this runs in the zero-dependency
CI job — ADR 0001 invariant 5.
"""

from __future__ import annotations

import itertools
import json
import re
import shutil
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import query as query_module
from x2knwldg.adapters import AdapterError
from x2knwldg.index import (
    DATABASE_DIRNAME,
    HIT_TYPES,
    SCHEMA_VERSION,
    TRANSCRIPT_CAPTION_HIT,
    SqliteRepository,
    build_index,
    connect,
    database_path,
    has_fts5,
    migrate,
    refresh_index,
)
from x2knwldg.index.search import document_indexer, search_retrieval
from x2knwldg.library import rebuild_library
from x2knwldg.repository import (
    MAX_LIMIT,
    EntityQuery,
    GraphQuery,
    MemoryRepository,
    NeighborhoodQuery,
    RelationQuery,
    SearchQuery,
    SourceGraphQuery,
    SourceNeighborhoodQuery,
    SourceQuery,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
ALL_FIXTURES = ("pass-run", "partial-run", "fail-run")

SAMPLE_ID = "pqlWNihgdjI"
SAMPLE_DIR = PROJECT_ROOT / "output" / SAMPLE_ID
LIBRARY_DIR = PROJECT_ROOT / "output" / "library"

#: The fixture runs by the ``video_id`` their metadata *declares*. A fixture's
#: directory name deliberately differs from it — ``pass-run/`` declares
#: ``fixture-pass`` — so nothing here may assume the two match.
PASS_SOURCE = "youtube:fixture-pass"
PARTIAL_SOURCE = "youtube:fixture-partial"
FAIL_SOURCE = "youtube:fixture-fail"

#: Well-formed and naming nothing. Absence is a return value, not an exception
#: (``repository/README.md`` rule 4), so every implementation must answer these
#: identically rather than raise.
UNKNOWN_SOURCE = "youtube:never-ingested"
UNKNOWN_ENTITY = f"{UNKNOWN_SOURCE}:KU-000001"
UNKNOWN_ARTIFACT = f"{UNKNOWN_SOURCE}:metadata"

#: The three committed fixtures with ``library/`` rebuilt over them. The seventh
#: entity is the one canonical concept, which belongs to no source (D-016), and
#: three of the nine relations are its ``expresses_concept`` edges, which name no
#: run (D-025).
FIXTURE_COUNTS = {"sources": 3, "artifacts": 54, "entities": 7, "relations": 9}

#: The same three runs with no ``library/`` at all.
FIXTURE_COUNTS_WITHOUT_LIBRARY = {
    "sources": 3,
    "artifacts": 54,
    "entities": 6,
    "relations": 6,
}

#: ``partial-run`` and ``fail-run`` only, with a library rebuilt over them —
#: what §7's eviction has to arrive at, and §6's addition has to start from.
TWO_RUN_COUNTS = {"sources": 2, "artifacts": 36, "entities": 5, "relations": 6}

#: The real sample plus the committed ``output/library/``, measured.
SAMPLE_COUNTS = {"sources": 1, "artifacts": 85, "entities": 86, "relations": 118}

#: Measured on the real sample, read off the cache-free oracle. A token-only
#: FTS index returns 3, 10 and 162 for these (see ``index/search`` on the
#: ``機習`` recall hole and the two disjuncts of ``SearchDocument.score``).
#: `the` moved 253 -> 258 when `derivation_note` joined the searchable field
#: set (D-047). `learning` and `model` are unmoved, which is the point: the
#: widening added 25 tokens out of 1095, not a new corpus.
SAMPLE_SEARCH_TOTALS = {"learning": 4, "model": 19, "the": 258}

def searchable_tokens(value: object) -> set[str]:
    """The tokens ``query.rank_documents`` matches on, for a measurement.

    ``query._fold`` is private and is reached for deliberately: the two
    measurements below are *about* that function's notion of a word, so
    reimplementing the folding here would measure a different one.
    """
    return set(re.findall(r"\w+", query_module._fold(str(value or "")), re.UNICODE))


requires_sample = pytest.mark.skipif(
    not (SAMPLE_DIR / "metadata.json").exists(),
    reason="output/ is gitignored; the real sample is present only on a machine that ingested it",
)

_HAS_FTS5 = has_fts5(sqlite3.connect(":memory:"))
requires_fts5 = pytest.mark.skipif(
    not _HAS_FTS5,
    reason="the migrations declare FTS5 tables, so a build needs an FTS5-enabled SQLite",
)


# --------------------------------------------------------------------------
# 1. The corpus, and the two ways to index it
# --------------------------------------------------------------------------


def project(root: Path, *names: str, library: bool = True) -> Path:
    """A writable project root holding *copies* of the named fixture runs.

    The committed fixtures are evidence: they are copied, never edited in place,
    so every scenario that mutates a canonical file mutates its own copy.
    """
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    for name in names or ALL_FIXTURES:
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    if library:
        rebuild_library(output)
    return root


def add_run(root: Path, name: str) -> None:
    """Copy one more committed run into an existing project, library included.

    ``rebuild_library`` runs because ``library/graph.json`` is a projection over
    the runs: leaving it behind would make the new run's concept edges missing
    rather than the addition being what is under test.
    """
    shutil.copytree(FIXTURE_RUNS / name, root / "output" / name)
    rebuild_library(root / "output")


def built(root: Path) -> Any:
    """A full build: every run re-adapted, nothing carried over."""
    return build_index(root, index_documents=document_indexer(root))


def refreshed(root: Path) -> Any:
    """An incremental scan: only what changed is re-adapted."""
    return refresh_index(root, index_documents=document_indexer(root))


def edit(path: Path, mutate: Callable[[dict], None]) -> None:
    """Rewrite one canonical JSON file of a *copy* under ``tmp_path``."""
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def sqlite_factory(root: Path) -> Callable[[], SqliteRepository]:
    return lambda: SqliteRepository.open(root, search=search_retrieval)


def memory_factory(root: Path) -> Callable[[], MemoryRepository]:
    """A *fresh* oracle per call — D-042's per-instance corpus cache."""
    return lambda: MemoryRepository.from_project(root)


@contextmanager
def opened(factory: Callable[[], Any]) -> Iterator[Any]:
    """Open a repository and close it if it has a ``close``.

    ``MemoryRepository`` has none; ``SqliteRepository.close`` is construction,
    not contract, so this is the one place that has to know the difference.
    """
    repo = factory()
    try:
        yield repo
    finally:
        close = getattr(repo, "close", None)
        if close is not None:
            close()


# --------------------------------------------------------------------------
# 2. Walking every page, and comparing them
# --------------------------------------------------------------------------


def walk(method: Callable[[Any], Any], query_type: Any, *, limit: int, **filters: Any) -> list[Any]:
    """Every *page* a paged method yields, walked to the end.

    Mirrors ``tests/test_repository.py::walk`` and refuses to loop for ever: a
    cursor that never terminates is one of the failures this file exists to
    catch, and a hung test reports nothing.
    """
    pages: list[Any] = []
    cursor: str | None = None
    for _ in range(1000):
        page = method(query_type(limit=limit, cursor=cursor, **filters))
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            return pages
    raise AssertionError("pagination did not terminate")


def page_shapes(pages: Sequence[Any]) -> list[tuple[Any, ...]]:
    """Everything a client can observe of a paged walk.

    ``items`` element-wise and in order, then the whole of ``PageInfo``:
    ``limit``, ``total`` and ``next_cursor`` as an exact token string. ``total``
    is compared as-is, so ``None`` and ``0`` are *different* values — the
    contract says null means unknown and never zero, and in Python
    ``None != 0``. §12 proves this comparison can actually tell them apart.
    """
    return [(list(page.items), page.limit, page.total, page.next_cursor) for page in pages]


def graph_shapes(pages: Sequence[Any]) -> list[tuple[Any, ...]]:
    """``nodes`` in order, ``edges`` in order and ``truncated``, plus the page.

    Also what a source-graph walk is compared by: :class:`SourceGraphPage`
    exposes the same two methods, and the payload it builds carries its own
    ``counts`` — so comparing the payload compares ``relations_omitted`` too,
    which is the number a bounded body must not get wrong quietly.
    """
    return [(page.payload(), page.page_info()) for page in pages]


LIMITS = (1, 2, 50)
"""``limit=1`` matters most: it maximises page boundaries, and a boundary is
where a non-total order deletes a record while ``total`` goes on counting it."""

SOURCE_TYPES = (None, "youtube", "vimeo")
STATUSES = (None, "PASS", "PARTIAL", "FAIL", "UNKNOWN")
SOURCE_IDS = (None, PASS_SOURCE, PARTIAL_SOURCE, FAIL_SOURCE, UNKNOWN_SOURCE)
PROVENANCE = (None, "source", "derived", "user")
KINDS = (None, "principle", "synthesis", "canonical_concept")
CONFIDENCES = (None, 0.0, 0.8, 1.0)
"""The fixtures state 0.7 and 0.9, so 0.8 splits them, 0.0 keeps both and 1.0
keeps neither. ``None`` is the filter's absence, which is not the same question
as ``>= 0`` (``matches_entity`` fails a unit that states no confidence at all)."""
VOCABULARIES = (None, "canonical", "library_synthetic", "user")
NEIGHBOURHOOD_VOCABULARIES = (None, "canonical", "library_synthetic")
DEPTHS = (1, 2, 3)
NEIGHBOURHOOD_LIMITS = (1, 50)


def crossed(dimensions: Mapping[str, Sequence[Any]]) -> tuple[dict[str, Any], ...]:
    """The whole cross product of *dimensions* — every filter against every other."""
    names = list(dimensions)
    return tuple(
        # `strict`: one value per named dimension, which `product` guarantees —
        # asserted rather than assumed.
        dict(zip(names, values, strict=True))
        for values in itertools.product(*(dimensions[name] for name in names))
    )


def one_at_a_time(dimensions: Mapping[str, Sequence[Any]]) -> tuple[dict[str, Any], ...]:
    """No filter, then every filter on its own.

    The sampled plan §10 uses on the real corpus. The cross product is exhausted
    on the fixtures, where it is affordable; on 86 entities and 118 relations it
    is not, and a cheaper *lie* would be worse than a stated sample.
    """
    unfiltered = {name: None for name in dimensions}
    plan = [dict(unfiltered)]
    for name, values in dimensions.items():
        for value in values:
            if value is not None:
                plan.append({**unfiltered, name: value})
    return tuple(plan)


def source_dimensions() -> dict[str, Sequence[Any]]:
    return {"source_type": SOURCE_TYPES, "status": STATUSES}


def entity_dimensions(source_ids: Sequence[Any]) -> dict[str, Sequence[Any]]:
    return {
        "source_id": source_ids,
        "provenance_class": PROVENANCE,
        "kind": KINDS,
        "min_confidence": CONFIDENCES,
    }


def relation_dimensions(source_ids: Sequence[Any]) -> dict[str, Sequence[Any]]:
    return {"source_id": source_ids, "relation_vocabulary": VOCABULARIES}


def graph_dimensions(source_ids: Sequence[Any]) -> dict[str, Sequence[Any]]:
    return {
        "source_id": source_ids,
        "provenance_class": PROVENANCE,
        "relation_vocabulary": VOCABULARIES,
    }


SOURCE_FILTERS = crossed(source_dimensions())
ENTITY_FILTERS = crossed(entity_dimensions(SOURCE_IDS))
RELATION_FILTERS = crossed(relation_dimensions(SOURCE_IDS))
GRAPH_FILTERS = crossed(graph_dimensions(SOURCE_IDS))

#: Every query is here to make the two paths disagree if they can, and the
#: comment says how. The fixture text is "A knowledge unit must carry the
#: evidence it rests on." / "Evidence-bearing units are what make a run
#: auditable.", with captions adding "Coverage is audited window by window …".
SEARCH_QUERIES = (
    "the",              # the commonest token in the corpus; the widest hit list
    "knowledge",        # a whole token of a knowledge unit
    "auditable",        # a whole token of a *derived* unit
    "principle",        # a `kind`, which run_documents folds into the text
    "synthesis",        # the other kind
    "coverage",         # caption-only: include_transcript decides whether it hits
    "window",           # caption-only, and *segment* text is not indexed at all
    "restates",         # `derivation_note` only — the named T-103 deferral
    "auditab",          # a truncated token: reachable only by the substring path
    "eviden",           # ... and another, across a word boundary
    "ab",               # under three characters: trigram MATCH returns 0 rows
    "on",               # ... and a real substring of "on." at that
    "a",                # one character, which is a legal query
    "機習",              # scriptless: no substring holds it, no unicode61 token equals it
    "100%",             # `%` is a LIKE wildcard. It must not be one here
    "a_b",              # `_` likewise
    "*",                # GLOB metacharacters, escaped rather than honoured
    "?",
    "[",
    "[a]",
    "-the",             # an FTS5 operator, searched *for* rather than executed
    'the "quoted"',
    "NEAR(a b)",
)

SEARCH_SCOPES = (None, PASS_SOURCE, UNKNOWN_SOURCE)


class Probes:
    """The ids every snapshot interrogates, unioned over both repositories.

    Taking the union rather than one side's list is deliberate: an id only one
    of the two holds is then asked of *both*, so the one that does not hold it
    has to answer ``None`` out loud instead of the question never being put.
    """

    def __init__(self, sources: Sequence[str], entities: Sequence[str], artifacts: Sequence[str]):
        self.sources = tuple(sorted({*sources, UNKNOWN_SOURCE}))
        self.entities = tuple(sorted({*entities, UNKNOWN_ENTITY}))
        self.artifacts = tuple(sorted({*artifacts, UNKNOWN_ARTIFACT}))


def probes_of(*repos: Any) -> Probes:
    sources: set[str] = set()
    entities: set[str] = set()
    artifacts: set[str] = set()
    for repo in repos:
        for source in repo.list_sources(SourceQuery(limit=MAX_LIMIT)).items:
            sources.add(source["id"])
            artifacts.update(source.get("artifact_ids") or ())
        for entity in repo.list_entities(EntityQuery(limit=MAX_LIMIT)).items:
            entities.add(entity["global_id"])
    return Probes(sorted(sources), sorted(entities), sorted(artifacts))


def _label(filters: Mapping[str, Any]) -> str:
    return ",".join(f"{key}={value!r}" for key, value in sorted(filters.items()))


@dataclass(frozen=True)
class Plan:
    """Which questions a snapshot asks. One place, so a narrowing is visible.

    ``FIXTURE_PLAN`` exhausts the filter cross product at three page sizes over
    the committed runs. ``SAMPLE_PLAN`` narrows deliberately and says how, for
    the one corpus where exhausting it costs minutes rather than seconds.
    """

    limits: Sequence[int] = LIMITS
    source_filters: Sequence[Mapping[str, Any]] = SOURCE_FILTERS
    entity_filters: Sequence[Mapping[str, Any]] = ENTITY_FILTERS
    relation_filters: Sequence[Mapping[str, Any]] = RELATION_FILTERS
    graph_filters: Sequence[Mapping[str, Any]] = GRAPH_FILTERS
    depths: Sequence[int] = DEPTHS
    neighbourhood_limits: Sequence[int] = NEIGHBOURHOOD_LIMITS
    neighbourhood_vocabularies: Sequence[Any] = NEIGHBOURHOOD_VOCABULARIES
    search_queries: Sequence[str] = SEARCH_QUERIES
    search_scopes: Sequence[Any] = SEARCH_SCOPES
    search_limits: Sequence[int] = (1, 50)
    #: Take every n-th probed id. ``1`` is every one of them.
    center_stride: int = 1
    artifact_stride: int = 1


FIXTURE_PLAN = Plan()


def snapshot(repo: Any, probes: Probes, plan: Plan = FIXTURE_PLAN) -> dict[str, Any]:
    """Everything the frozen contract lets a client observe, as one mapping.

    Keyed by a label that names the exact question, so a failure says *which*
    page disagreed rather than dumping two structures side by side. The keys are
    a function of *probes* and *plan* alone, so two snapshots always have the
    same keys and the diff is a value diff.
    """
    seen: dict[str, Any] = {}
    centers = probes.entities[:: plan.center_stride]
    artifacts = probes.artifacts[:: plan.artifact_stride]

    status = repo.status().payload()
    # Three fields are excluded here and asserted separately, each because a
    # frozen document requires the two implementations to differ:
    #
    # `built_at` and `index_version` — `repository/README.md` requires the
    # SQLite path to report them from the migration table and the last build,
    # and `MemoryRepository` to report None for both, because "stating a version
    # there would claim a durable artifact that does not exist".
    #
    # `runs` — optional by contract (D-050) and reported only by an
    # implementation that actually scanned a filesystem. `MemoryRepository`
    # omits it rather than claiming `skipped: []`, which would assert it looked.
    #
    # Every other field of the payload must agree exactly.
    seen["status"] = {
        key: value for key, value in status.items() if key not in ("index", "runs")
    }
    seen["status.index.state"] = status["index"]["state"]

    for filters, limit in itertools.product(plan.source_filters, plan.limits):
        seen[f"list_sources({_label(filters)}) limit={limit}"] = page_shapes(
            walk(repo.list_sources, SourceQuery, limit=limit, **filters)
        )
    for filters, limit in itertools.product(plan.entity_filters, plan.limits):
        seen[f"list_entities({_label(filters)}) limit={limit}"] = page_shapes(
            walk(repo.list_entities, EntityQuery, limit=limit, **filters)
        )
    for filters, limit in itertools.product(plan.relation_filters, plan.limits):
        seen[f"list_relations({_label(filters)}) limit={limit}"] = page_shapes(
            walk(repo.list_relations, RelationQuery, limit=limit, **filters)
        )
    for filters, limit in itertools.product(plan.graph_filters, plan.limits):
        seen[f"graph({_label(filters)}) limit={limit}"] = graph_shapes(
            walk(repo.graph, GraphQuery, limit=limit, **filters)
        )

    # `T-254`. The source layer through the same machinery, so every scenario
    # below — a run edited, added, removed, a library rebuilt, a cache deleted —
    # proves the Source Map rebuilds to the same answer, and does it without a
    # second comparison harness that could disagree with this one.
    for limit in plan.limits:
        seen[f"source_graph() limit={limit}"] = graph_shapes(
            walk(repo.source_graph, SourceGraphQuery, limit=limit)
        )
    for source_id, limit in itertools.product(
        probes.sources, plan.neighbourhood_limits
    ):
        found = repo.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_id, limit=limit)
        )
        seen[f"source_neighborhood({source_id},{limit})"] = (
            None if found is None else found.payload()
        )

    for entity_id, depth, limit, vocabulary in itertools.product(
        centers, plan.depths, plan.neighbourhood_limits, plan.neighbourhood_vocabularies
    ):
        found = repo.neighborhood(
            NeighborhoodQuery(
                entity_id=entity_id,
                depth=depth,
                limit=limit,
                relation_vocabulary=vocabulary,
            )
        )
        seen[f"neighborhood({entity_id},{depth},{limit},{vocabulary!r})"] = (
            None if found is None else found.payload()
        )

    for query, scope, include_transcript in itertools.product(
        plan.search_queries, plan.search_scopes, (True, False)
    ):
        for limit in plan.search_limits:
            seen[f"search({query!r},{scope!r},{include_transcript},{limit})"] = page_shapes(
                walk(
                    repo.search,
                    SearchQuery,
                    limit=limit,
                    q=query,
                    source_id=scope,
                    include_transcript=include_transcript,
                )
            )

    for source_id in probes.sources:
        detail = repo.get_source(source_id)
        seen[f"get_source({source_id})"] = None if detail is None else detail.payload()
    for entity_id in centers:
        seen[f"get_entity({entity_id})"] = repo.get_entity(entity_id)
    for artifact_id in artifacts:
        seen[f"get_artifact({artifact_id})"] = repo.get_artifact(artifact_id)

    return seen


def compare(
    left_name: str,
    left: Callable[[], Any],
    right_name: str,
    right: Callable[[], Any],
    plan: Plan = FIXTURE_PLAN,
) -> int:
    """Snapshot both repositories over the same probes and diff them.

    Returns the number of observations compared, so a caller can assert the
    comparison was not vacuous. Both factories are called *here*: the oracle
    must be fresh per comparison (D-042).
    """
    with opened(left) as one, opened(right) as two:
        probes = probes_of(one, two)
        first = snapshot(one, probes, plan)
        second = snapshot(two, probes, plan)
    assert first.keys() == second.keys()
    differences = [key for key in first if first[key] != second[key]]
    assert not differences, (
        f"{len(differences)} of {len(first)} observations differ between "
        f"{left_name} and {right_name}; the first three:\n"
        + "\n".join(
            f"  {key}\n    {left_name}: {first[key]!r}\n    {right_name}: {second[key]!r}"
            for key in differences[:3]
        )
    )
    return len(first)


def _assert_build_facts(root: Path) -> None:
    """What the status comparison had to drop, asserted rather than skipped."""
    with opened(sqlite_factory(root)) as repo:
        index = repo.status().payload()["index"]
    assert index["state"] == "ready"
    assert index["index_version"] == SCHEMA_VERSION
    assert isinstance(index["index_version"], int) and not isinstance(
        index["index_version"], bool
    )
    assert isinstance(index["built_at"], str) and index["built_at"]
    stamped = datetime.fromisoformat(index["built_at"])
    assert stamped.tzinfo is not None, "built_at must carry an offset, not a local guess"

    with opened(memory_factory(root)) as oracle:
        oracle_index = oracle.status().payload()["index"]
    assert oracle_index["built_at"] is None
    assert oracle_index["index_version"] is None


def counts(root: Path) -> dict[str, int]:
    with opened(sqlite_factory(root)) as repo:
        return repo.status().payload()["counts"]


def totals_for(root: Path, query: str) -> int | None:
    with opened(sqlite_factory(root)) as repo:
        return repo.search(SearchQuery(q=query, limit=MAX_LIMIT)).total


# --------------------------------------------------------------------------
# 3. Scenario 1 — a full build is the canonical files
# --------------------------------------------------------------------------


@requires_fts5
def test_a_full_build_answers_exactly_what_the_canonical_files_do(tmp_path: Path) -> None:
    """The whole point of the cache: it may be faster, never different."""
    root = project(tmp_path)
    report = built(root)
    assert report.payload()["counts"] == FIXTURE_COUNTS
    assert counts(root) == FIXTURE_COUNTS
    assert compare(
        "sqlite(build)", sqlite_factory(root), "memory", memory_factory(root)
    ) > 75, "the comparison must be a superset of the 75 already verified by hand"
    _assert_build_facts(root)


@requires_fts5
def test_the_corpus_holds_the_records_the_sharp_cases_need(tmp_path: Path) -> None:
    """The facts every scenario below leans on, measured once rather than assumed."""
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        entities = repo.list_entities(EntityQuery(limit=MAX_LIMIT)).items
        relations = repo.list_relations(RelationQuery(limit=MAX_LIMIT)).items
        status = repo.status().payload()

    concepts = [entity for entity in entities if entity.get("source_id") is None]
    assert [entity["global_id"] for entity in concepts] == ["library:concepts:30ba07eea6c0"]
    assert concepts[0]["kind"] == "canonical_concept"

    unowned = [relation for relation in relations if relation.get("source_id") is None]
    assert len(unowned) == 3, "the concept's expresses_concept edges name no run (D-025)"
    vocabularies: dict[str, int] = {}
    for relation in relations:
        vocabularies[relation["relation_vocabulary"]] = (
            vocabularies.get(relation["relation_vocabulary"], 0) + 1
        )
    assert vocabularies == {"canonical": 3, "library_synthetic": 6}
    assert status["sources_by_status"] == {"FAIL": 1, "PARTIAL": 1, "PASS": 1, "UNKNOWN": 0}

    # A fixture's directory name is deliberately not its declared `video_id`:
    # `pass-run/` declares `fixture-pass`, so nothing may assume they match.
    assert (root / "output" / "pass-run").is_dir()
    assert not (root / "output" / "fixture-pass").exists()
    assert {entity["source_id"] for entity in entities if entity["source_id"]} == {
        PASS_SOURCE,
        PARTIAL_SOURCE,
        FAIL_SOURCE,
    }
    # The whole filter space the fixtures can express, so a filter above that
    # matches nothing does so on purpose rather than by accident.
    assert {entity["kind"] for entity in entities} == {
        "principle",
        "synthesis",
        "canonical_concept",
    }
    assert {entity["provenance_class"] for entity in entities} == {"source", "derived"}
    # 0.7 and 0.9, so `min_confidence=0.8` splits them — and the concept states
    # `None`, which `matches_entity` fails for *every* threshold while a bare SQL
    # `confidence >= 0.8` would drop it silently for a different reason.
    assert {entity["confidence"] for entity in entities} == {None, 0.7, 0.9}


# --------------------------------------------------------------------------
# 4. Scenario 2 — the incremental path must reach the full state from nothing
# --------------------------------------------------------------------------


@requires_fts5
def test_a_refresh_from_no_index_at_all_is_a_full_build(tmp_path: Path) -> None:
    """A refresh against an index that never reached ``ready`` is a full build."""
    incremental = project(tmp_path / "incremental")
    whole = project(tmp_path / "whole")
    assert not database_path(incremental).exists()

    report = refreshed(incremental)
    assert report.runs_unchanged == 0, "nothing can be carried over from nothing"
    assert report.runs_indexed == 3
    built(whole)

    assert compare(
        "sqlite(refresh from absent)",
        sqlite_factory(incremental),
        "sqlite(build)",
        sqlite_factory(whole),
    )
    assert compare(
        "sqlite(refresh from absent)", sqlite_factory(incremental), "memory", memory_factory(whole)
    )


@requires_fts5
def test_a_refresh_from_a_migrated_but_empty_index_is_a_full_build(tmp_path: Path) -> None:
    """An empty index and an unbuilt one are different answers (D-030) — and both
    have to end up at the same place as a rebuild."""
    root = project(tmp_path)
    connection = connect(database_path(root))
    try:
        assert migrate(connection) == SCHEMA_VERSION
    finally:
        connection.close()
    assert database_path(root).exists()

    report = refreshed(root)
    assert report.runs_unchanged == 0
    assert counts(root) == FIXTURE_COUNTS
    assert compare(
        "sqlite(refresh from empty)", sqlite_factory(root), "memory", memory_factory(root)
    )


# --------------------------------------------------------------------------
# 5. Scenario 3 — a no-op refresh changes nothing at all
# --------------------------------------------------------------------------


@requires_fts5
def test_a_refresh_that_finds_nothing_changed_changes_no_page(tmp_path: Path) -> None:
    """The cheap path may skip work; it may not skip *reporting*, and it may not
    quietly produce a different index."""
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        before = snapshot(repo, probes)

    report = refreshed(root)
    assert report.runs_discovered == 3
    assert report.runs_indexed == 3
    assert report.runs_unchanged == 3, "every run was reported unchanged"
    assert report.runs_reindexed == 0
    assert report.runs_evicted == 0
    assert report.library_reindexed is False
    assert report.library_skipped_reason is None

    with opened(sqlite_factory(root)) as repo:
        after = snapshot(repo, probes)
    differing = [key for key in before if before[key] != after[key]]
    assert not differing, f"a no-op refresh changed {len(differing)} observations: {differing[:3]}"
    assert compare("sqlite(no-op refresh)", sqlite_factory(root), "memory", memory_factory(root))


# --------------------------------------------------------------------------
# 6. Scenarios 4 and 5 — a run edited, and a run added
# --------------------------------------------------------------------------


@requires_fts5
def test_a_refresh_after_one_run_was_edited_equals_a_rebuild(tmp_path: Path) -> None:
    """A re-run rewrites ``knowledge_units.json`` and leaves everything else
    alone, which is the change a digest over one file would miss."""
    root = project(tmp_path)
    built(root)
    assert totals_for(root, "reindexed") == 0

    units = root / "output" / "pass-run" / "knowledge_units.json"

    def rewrite(document: dict) -> None:
        # Ids untouched: the library's `expresses_concept` edges name them, and
        # a stale library is scenario 7's subject, not this one. Content, kind
        # and confidence all move, so the record, its extracted columns and its
        # searchable text change together.
        document["units"][0]["content"] = "A reindexed unit carries new evidence."
        document["units"][0]["normalized_statement"] = "A reindexed unit carries new evidence."
        document["units"][0]["confidence"] = 0.75
        document["units"][1]["kind"] = "definition"

    edit(units, rewrite)

    report = refreshed(root)
    assert report.runs_unchanged == 2, "only the edited run is re-adapted"
    assert report.runs_reindexed == 1
    assert report.library_reindexed is True, "library/ is a projection over the runs"
    assert counts(root) == FIXTURE_COUNTS
    assert totals_for(root, "reindexed") == 1, "the edit reached the search corpus"

    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        incremental = snapshot(repo, probes)
    assert compare(
        "sqlite(refresh after edit)", sqlite_factory(root), "memory", memory_factory(root)
    )

    built(root)  # the same tree, from scratch, over the same database file
    with opened(sqlite_factory(root)) as repo:
        rebuilt = snapshot(repo, probes)
    differing = [key for key in incremental if incremental[key] != rebuilt[key]]
    assert not differing, f"refresh and rebuild disagree on {len(differing)}: {differing[:3]}"


@requires_fts5
def test_a_refresh_after_a_run_was_added_equals_a_rebuild(tmp_path: Path) -> None:
    root = project(tmp_path, "partial-run", "fail-run")
    built(root)
    assert counts(root) == TWO_RUN_COUNTS

    add_run(root, "pass-run")
    report = refreshed(root)
    assert report.runs_discovered == 3
    assert report.runs_reindexed == 1, "the two already indexed are carried over"
    assert report.runs_unchanged == 2
    assert counts(root) == FIXTURE_COUNTS

    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        incremental = snapshot(repo, probes)
    assert compare(
        "sqlite(refresh after add)", sqlite_factory(root), "memory", memory_factory(root)
    )

    built(root)
    with opened(sqlite_factory(root)) as repo:
        rebuilt = snapshot(repo, probes)
    differing = [key for key in incremental if incremental[key] != rebuilt[key]]
    assert not differing, f"refresh and rebuild disagree on {len(differing)}: {differing[:3]}"


# --------------------------------------------------------------------------
# 7. Scenario 6 — a run removed, which is where an incremental index rots
# --------------------------------------------------------------------------
#
# Orphaned artifacts, entities, relations and search documents are the classic
# incremental bug, and a count that only grows cannot see them. Two variants,
# because deleting a run leaves `library/graph.json` naming knowledge units
# nothing carries any more:
#
#   a. the library left stale — the scanner drops the fragment *whole* and names
#      it, while `adapt_project` refuses the project outright, so the oracle
#      cannot be built and the comparison is refresh against rebuild;
#   b. `rebuild_library` re-run, which is what a user would do — and then all
#      three paths are comparable again.


@requires_fts5
def test_a_refresh_after_a_run_was_removed_equals_a_rebuild(tmp_path: Path) -> None:
    root = project(tmp_path)
    built(root)
    before_the = totals_for(root, "the")
    assert before_the == 15

    shutil.rmtree(root / "output" / "pass-run")
    report = refreshed(root)
    assert report.runs_discovered == 2
    assert report.runs_evicted == 1
    assert counts(root) == {"sources": 2, "artifacts": 36, "entities": 4, "relations": 4}

    # The fragment is dropped whole and named, and the reason names the edge
    # that no longer resolves — never filtered down to a thinner graph nobody
    # reported (D-043).
    assert report.library_reindexed is True
    assert report.library_skipped_reason is not None
    assert f"{PASS_SOURCE}:KU-000001" in report.library_skipped_reason
    assert [entry["relative_path"] for entry in report.skipped_runs] == ["output/library"]

    # No orphan survives eviction: not a record, and not a search document.
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        incremental = snapshot(repo, probes)
        for query in ("the", "knowledge", "auditable", "coverage"):
            page = repo.search(SearchQuery(q=query, limit=MAX_LIMIT))
            assert all(hit.get("source_id") != PASS_SOURCE for hit in page.items), (
                f"the removed run still returns hits for {query!r}"
            )
            assert all(hit.get("video_id") != "fixture-pass" for hit in page.items)
        after_the = repo.search(SearchQuery(q="the", limit=MAX_LIMIT)).total
    assert after_the is not None and before_the is not None
    assert after_the < before_the, "total kept counting the evicted run's documents"
    assert after_the == 10

    built(root)
    with opened(sqlite_factory(root)) as repo:
        rebuilt = snapshot(repo, probes)
    differing = [key for key in incremental if incremental[key] != rebuilt[key]]
    assert not differing, f"refresh and rebuild disagree on {len(differing)}: {differing[:3]}"


def test_the_oracle_refuses_the_project_the_scanner_survives(tmp_path: Path) -> None:
    """The one documented divergence, asserted so it cannot become a surprise.

    ``scanner``'s module docstring states it: ``adapt_project`` propagates
    ``AdapterError`` and refuses the **whole project** when a run is unmappable
    or the library is stale, while the scanner skips that fragment and names it.
    Skip-and-name is right per D-043, but it means the two disagree about a
    *damaged* project, so §7's first variant compares refresh against rebuild
    rather than against the oracle. This is that fact, not an exception.
    """
    root = project(tmp_path)
    shutil.rmtree(root / "output" / "pass-run")
    with pytest.raises(AdapterError) as raised:
        MemoryRepository.from_project(root)
    assert f"{PASS_SOURCE}:KU-000001" in str(raised.value)


@requires_fts5
def test_a_refresh_after_a_removal_and_a_library_rebuild_equals_both_others(
    tmp_path: Path,
) -> None:
    """The same eviction with the library brought back in step — so the
    cache-free oracle is available and all three paths are compared."""
    root = project(tmp_path)
    built(root)

    shutil.rmtree(root / "output" / "pass-run")
    rebuild_library(root / "output")
    report = refreshed(root)
    assert report.runs_evicted == 1
    assert report.library_skipped_reason is None
    assert counts(root) == TWO_RUN_COUNTS

    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        incremental = snapshot(repo, probes)
    assert compare(
        "sqlite(refresh after removal)", sqlite_factory(root), "memory", memory_factory(root)
    )

    built(root)
    with opened(sqlite_factory(root)) as repo:
        rebuilt = snapshot(repo, probes)
    differing = [key for key in incremental if incremental[key] != rebuilt[key]]
    assert not differing, f"refresh and rebuild disagree on {len(differing)}: {differing[:3]}"


# --------------------------------------------------------------------------
# 8. Scenario 7 — the library alone, which belongs to no run
# --------------------------------------------------------------------------


@requires_fts5
def test_a_refresh_after_only_the_library_was_rebuilt_equals_a_rebuild(tmp_path: Path) -> None:
    """No run's digest moves here, so the fragment's own ``runs`` row is the only
    thing that can notice. Without it a ``rebuild_library`` that changed no run
    would leave the previous scan's answer standing — cheap and stale."""
    root = project(tmp_path, library=False)
    built(root)
    assert counts(root) == FIXTURE_COUNTS_WITHOUT_LIBRARY

    rebuild_library(root / "output")
    report = refreshed(root)
    assert report.runs_unchanged == 3, "not one run changed"
    assert report.runs_reindexed == 0
    assert report.library_reindexed is True, "the fragment's own digest moved"
    assert counts(root) == FIXTURE_COUNTS

    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        incremental = snapshot(repo, probes)
    assert compare(
        "sqlite(refresh after library rebuild)",
        sqlite_factory(root),
        "memory",
        memory_factory(root),
    )

    # The concept and its `expresses_concept` edges belong to no run, so this is
    # also the check that a cross-source record survives an incremental pass.
    with opened(sqlite_factory(root)) as repo:
        concept = repo.get_entity("library:concepts:30ba07eea6c0")
        assert concept is not None and concept["source_id"] is None
        edges = repo.list_relations(RelationQuery(limit=MAX_LIMIT, source_id=PASS_SOURCE)).items
        assert any(edge["relation"] == "expresses_concept" for edge in edges)

    built(root)
    with opened(sqlite_factory(root)) as repo:
        rebuilt = snapshot(repo, probes)
    differing = [key for key in incremental if incremental[key] != rebuilt[key]]
    assert not differing, f"refresh and rebuild disagree on {len(differing)}: {differing[:3]}"


# --------------------------------------------------------------------------
# 9. Scenario 8 — deleting the cache directory must lose nothing
# --------------------------------------------------------------------------


@requires_fts5
def test_deleting_the_cache_directory_and_rebuilding_loses_nothing(tmp_path: Path) -> None:
    """Phase 1's acceptance criterion, and ADR 0001 invariant 3, executable."""
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        before = snapshot(repo, probes)

    shutil.rmtree(root / DATABASE_DIRNAME)
    assert not database_path(root).exists()

    built(root)
    with opened(sqlite_factory(root)) as repo:
        after = snapshot(repo, probes)
    differing = [key for key in before if before[key] != after[key]]
    assert not differing, (
        f"a rebuild from a deleted cache differs on {len(differing)} observations: "
        f"{differing[:3]}"
    )
    _assert_build_facts(root)


@requires_fts5
def test_a_refresh_against_a_deleted_cache_directory_rebuilds_it(tmp_path: Path) -> None:
    """The likelier gesture — delete the directory and carry on working."""
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        before = snapshot(repo, probes)

    shutil.rmtree(root / DATABASE_DIRNAME)
    report = refreshed(root)
    assert report.runs_unchanged == 0, "there is nothing left to carry over"
    with opened(sqlite_factory(root)) as repo:
        after = snapshot(repo, probes)
    assert [key for key in before if before[key] != after[key]] == []


# --------------------------------------------------------------------------
# 9b. Scenario 9 — the source layer, over a corpus that actually has one
#
# The eight scenarios above run over ``project()``, which copies runs and
# nothing else: no run there has a brief and no synthesis file exists, so their
# source-graph observations prove the *nodes* rebuild and say nothing about the
# other two record families. `T-254` stores three, and two of them come from
# documents no run fixture carries.
#
# ``source_map_corpus`` is that corpus — four runs across both media, three
# briefs generated from those runs' own digests, one ``FAIL`` run with none, and
# the committed cross-medium relation. Every claim below is about what a
# *rebuild* of it produces, because ADR 0001 invariant 3 is the whole reason the
# index may be deleted at all.
# --------------------------------------------------------------------------


def source_map_project(root: Path, *, relations: bool = True) -> Path:
    """The `T-254` corpus, built under *root*."""
    import source_map_corpus

    return source_map_corpus.build(root / "project", relations=relations).project_root


@requires_fts5
def test_the_source_layer_reads_the_same_through_the_index_as_through_the_files(
    tmp_path: Path,
) -> None:
    """A build, a refresh and the cache-free oracle, over a corpus with all three families."""
    root = source_map_project(tmp_path)
    built(root)
    compared = compare("sqlite", sqlite_factory(root), "oracle", memory_factory(root))
    assert compared > 100, "the comparison must not be vacuous"
    refreshed(root)
    compare("refreshed", sqlite_factory(root), "oracle", memory_factory(root))


@requires_fts5
def test_the_corpus_carries_the_records_the_source_layer_needs(tmp_path: Path) -> None:
    """A guard on the fixture, not on the code.

    Every assertion in this section is worthless if the corpus quietly stops
    holding a brief or a relation — the comparison would go on passing over two
    empty answers. Measured here so that is a failure.
    """
    import source_map_corpus

    root = source_map_project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        page = repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
        assert len(page.nodes) == len(source_map_corpus.SOURCE_IDS)
        assert [relation["id"] for relation in page.relations] == [
            source_map_corpus.RELATION_ID
        ]
        states = {
            source_id: repo.source_neighborhood(
                SourceNeighborhoodQuery(source_id=source_id)
            ).source_knowledge["state"]
            for source_id in source_map_corpus.SOURCE_IDS
        }
    assert sorted(states.values()) == ["available", "available", "available", "unavailable"]


@requires_fts5
def test_deleting_the_cache_loses_no_brief_and_no_relation(tmp_path: Path) -> None:
    """The three source tables are rebuildable, so the cache may still be deleted."""
    root = source_map_project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        before = snapshot(repo, probes)

    shutil.rmtree(root / DATABASE_DIRNAME)
    assert not database_path(root).exists()

    built(root)
    with opened(sqlite_factory(root)) as repo:
        after = snapshot(repo, probes)
    differing = [key for key in before if before[key] != after[key]]
    assert not differing, (
        f"a rebuild from a deleted cache differs on {len(differing)} observations: "
        f"{differing[:3]}"
    )


@requires_fts5
def test_a_re_extracted_run_makes_its_brief_stale_on_both_paths(tmp_path: Path) -> None:
    """The one thing a stored brief could get wrong: staleness the scan did not see.

    ``SqliteRepository`` reads the state the scan stored; the oracle recomputes
    it from the run. They can only agree if a run whose knowledge moved is
    re-read — which is what the run digest is for — so this is the scenario that
    proves the stored copy is a cache rather than a second opinion.
    """
    import source_map_corpus

    root = source_map_project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        fresh = repo.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_map_corpus.YOUTUBE_PASS)
        )
    assert fresh.source_knowledge["state"] == "available"

    edit(
        root / "output" / "pass-run" / "knowledge_units.json",
        lambda document: document["units"][0].update({"confidence": 0.55}),
    )
    refreshed(root)
    with opened(sqlite_factory(root)) as repo, opened(memory_factory(root)) as oracle:
        stored = repo.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_map_corpus.YOUTUBE_PASS)
        )
        read = oracle.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_map_corpus.YOUTUBE_PASS)
        )
    assert stored.source_knowledge["state"] == "stale"
    assert stored.payload() == read.payload()
    assert stored.source_knowledge["brief"] is not None, (
        "a stale brief is carried with the state saying so, not withheld"
    )


@requires_fts5
def test_a_relation_whose_endpoint_left_the_corpus_is_counted_rather_than_drawn(
    tmp_path: Path,
) -> None:
    """An edge to a node the page will not show asserts a node that does not exist.

    Removing one endpoint run is the way that happens in life: the synthesis
    file still names the pair it was applied against, and one half of it is
    gone. Counted in ``relations_omitted`` on both paths, and drawn on neither.
    """
    import source_map_corpus

    root = source_map_project(tmp_path)
    built(root)
    shutil.rmtree(root / "output" / "twitter-quote")
    rebuild_library(root / "output")
    refreshed(root)

    for label, factory in (("sqlite", sqlite_factory(root)), ("oracle", memory_factory(root))):
        with opened(factory) as repo:
            page = repo.source_graph(SourceGraphQuery(limit=MAX_LIMIT))
        assert page.relations == [], label
        assert page.payload()["counts"]["relations_omitted"] == 1, label
        assert page.payload()["counts"]["sources_total"] == (
            len(source_map_corpus.SOURCE_IDS) - 1
        ), label


# --------------------------------------------------------------------------
# 10. The real sample, when the machine has one
# --------------------------------------------------------------------------


def _sample_project(root: Path) -> Path:
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SAMPLE_DIR, output / SAMPLE_ID)
    if LIBRARY_DIR.exists():
        shutil.copytree(LIBRARY_DIR, output / "library")
    return root


SAMPLE_SOURCE = f"youtube:{SAMPLE_ID}"

#: What the real corpus is asked, and it is a **sample** rather than the whole
#: cross product — stated here rather than quietly narrowed. Exhausting the
#: fixture plan over 86 entities, 118 relations and 578 searchable documents
#: costs about twenty seconds, against an eight-second suite, and it would prove
#: nothing the fixture corpus has not already exhausted: the filter *logic* is
#: shared code (``matches_entity`` and friends), so what is left to check on real
#: data is scale — more records than a page holds, more edges than a
#: neighbourhood walks, and a hit list 253 long.
#:
#: So: every filter on its own instead of every combination; page sizes 5 and 50
#: instead of 1, 2 and 50 (``limit=1`` is exhausted above, and here it would mean
#: 253 single-hit search pages); every ninth entity as a neighbourhood centre and
#: every fifth artifact, both by deterministic stride so the same ids are
#: compared on every run; and the six search queries that reach a different code
#: path from each other.
SAMPLE_PLAN = Plan(
    limits=(5, 50),
    source_filters=one_at_a_time(source_dimensions()),
    entity_filters=one_at_a_time(entity_dimensions((None, SAMPLE_SOURCE, UNKNOWN_SOURCE))),
    relation_filters=one_at_a_time(relation_dimensions((None, SAMPLE_SOURCE, UNKNOWN_SOURCE))),
    graph_filters=one_at_a_time(graph_dimensions((None, SAMPLE_SOURCE, UNKNOWN_SOURCE))),
    search_queries=("learning", "model", "the", "機習", "100%", "ab"),
    search_scopes=(None, SAMPLE_SOURCE),
    search_limits=(50,),
    center_stride=9,
    artifact_stride=5,
)


@requires_fts5
@requires_sample
def test_the_real_sample_reads_the_same_through_the_index_as_through_the_files(
    tmp_path: Path,
) -> None:
    root = _sample_project(tmp_path)
    report = built(root)
    assert report.payload()["counts"] == SAMPLE_COUNTS

    with opened(sqlite_factory(root)) as repo:
        page = repo.graph(GraphQuery(limit=MAX_LIMIT))
        assert (len(page.nodes), len(page.edges), page.truncated) == (86, 118, False)
        for query, total in SAMPLE_SEARCH_TOTALS.items():
            assert repo.search(SearchQuery(q=query, limit=MAX_LIMIT)).total == total
        probes = probes_of(repo)
        indexed = snapshot(repo, probes, SAMPLE_PLAN)

    with opened(memory_factory(root)) as oracle:
        oracle_view = snapshot(oracle, probes, SAMPLE_PLAN)
    differing = [key for key in indexed if indexed[key] != oracle_view[key]]
    assert not differing, (
        f"the index and the canonical files disagree on {len(differing)} of "
        f"{len(indexed)} observations: {differing[:3]}"
    )


@requires_fts5
@requires_sample
def test_the_real_sample_survives_a_refresh_and_a_cache_deletion(tmp_path: Path) -> None:
    root = _sample_project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        before = snapshot(repo, probes, SAMPLE_PLAN)

    report = refreshed(root)
    assert report.runs_unchanged == 1
    with opened(sqlite_factory(root)) as repo:
        assert snapshot(repo, probes, SAMPLE_PLAN) == before

    shutil.rmtree(root / DATABASE_DIRNAME)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        after = snapshot(repo, probes, SAMPLE_PLAN)
    assert [key for key in before if before[key] != after[key]] == []


# --------------------------------------------------------------------------
# 11. The named deferrals, executable rather than merely written down
# --------------------------------------------------------------------------


@requires_fts5
def test_the_field_set_is_the_same_on_both_paths(tmp_path: Path) -> None:
    """What is searchable, and what is not, is one decision for both readers.

    Field parity is what makes ``MemoryRepository`` an oracle at all: a widening
    that reached only one of the two would break this proof rather than improve
    search. ``index.search`` builds its corpus from ``query.run_documents``
    rather than re-deriving the field set, so the two cannot drift (D-046).

    ``derivation_note`` **is** searchable (D-047): a phrase a reader can see in
    the Reader is a phrase they can search for. Segment text is **not** stored
    (D-048), and ``context`` is **not** indexed — the next two tests measure why
    each of those costs nothing.
    """
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo, opened(memory_factory(root)) as oracle:
        for reader in (repo, oracle):
            # Each fixture's derived unit says "Restates KU-000001 as the
            # property it gives the run." — findable since D-047.
            assert reader.search(SearchQuery(q="restates", limit=MAX_LIMIT)).total == 3

            # Segment text is not stored at all. "window" appears in a caption
            # *and* in `segments.json`'s concatenated segment text; only the
            # caption is a hit, because D-028 freezes exactly two hit shapes.
            page = reader.search(SearchQuery(q="window", limit=MAX_LIMIT))
            assert page.total == 3, "one caption per run, and no segment document"
            assert {hit["type"] for hit in page.items} == {TRANSCRIPT_CAPTION_HIT}
            assert all(hit["type"] in HIT_TYPES for hit in page.items)
            blind = reader.search(
                SearchQuery(q="window", limit=MAX_LIMIT, include_transcript=False)
            )
            assert blind.total == 0, "the only 'window' text is in the transcript"


@requires_sample
def test_not_indexing_context_costs_no_reachable_word() -> None:
    """D-047's other half, as a measurement rather than an assertion of faith.

    ``context`` is left out of the searchable field set, and the reason is that
    it is fully redundant: every token it holds already appears in the unit's
    own ``content`` or ``normalized_statement``. Measured on the real sample,
    where **9** units carry one, the set difference is empty — so there exists
    no query that indexing ``context`` would newly answer.

    This is the test that turns the deferral from an opinion into a fact, and it
    is the one that will speak up if that stops being true: a future extraction
    whose ``context`` carries vocabulary of its own makes this fail, and the
    deferral then has a real cost to weigh rather than none.
    """
    units = json.loads((SAMPLE_DIR / "knowledge_units.json").read_text(encoding="utf-8"))
    captions = json.loads((SAMPLE_DIR / "transcript.json").read_text(encoding="utf-8"))

    searchable: set[str] = set()
    for caption in captions.get("captions", []):
        searchable |= searchable_tokens(caption.get("text"))
    carried = 0
    context_tokens: set[str] = set()
    for unit in units.get("units", []):
        source = unit.get("source") or {}
        searchable |= (
            searchable_tokens(unit.get("content"))
            | searchable_tokens(unit.get("normalized_statement"))
            | searchable_tokens(source.get("evidence_excerpt"))
            | searchable_tokens(unit.get("kind"))
            | searchable_tokens(unit.get("derivation_note"))
        )
        if unit.get("context"):
            carried += 1
            context_tokens |= searchable_tokens(unit.get("context"))

    assert carried, "the sample is expected to carry `context` on some units"
    assert context_tokens - searchable == set(), (
        "`context` now holds vocabulary nothing else does, so leaving it out of "
        "the field set has a cost — re-weigh D-047 rather than deleting this test"
    )


@requires_sample
def test_not_storing_segment_text_costs_no_reachable_word() -> None:
    """D-048, likewise measured: a segment holds no word its captions do not.

    ``segments.json`` text is the concatenation of the captions it spans, which
    are already indexed, so a ``transcript_segment`` hit shape would make
    nothing newly findable — it would only change the granularity of a hit, and
    that is a question for the Reader rather than for the frozen contract.
    """
    segments = json.loads((SAMPLE_DIR / "segments.json").read_text(encoding="utf-8"))
    captions = json.loads((SAMPLE_DIR / "transcript.json").read_text(encoding="utf-8"))

    caption_tokens: set[str] = set()
    for caption in captions.get("captions", []):
        caption_tokens |= searchable_tokens(caption.get("text"))
    segment_tokens: set[str] = set()
    for segment in segments.get("segments", []):
        segment_tokens |= searchable_tokens(segment.get("text"))

    assert segment_tokens, "the sample is expected to carry segment text"
    assert segment_tokens - caption_tokens == set(), (
        "a segment now holds vocabulary its captions do not, so D-048's "
        "'nothing newly findable' no longer holds — re-weigh it"
    )


@requires_fts5
def test_a_run_the_scanner_skipped_is_named_over_http(tmp_path: Path) -> None:
    """A run that produced no ``Source`` is reported, not merely absent (D-050).

    This test used to assert the opposite. A skipped run had a ``runs`` row and
    a ``ScanReport`` entry and nothing in ``IndexStatus``, so ``/api/status``
    described a project of two sources where three run directories existed —
    and the payload gave a reader no way to know the difference between "two
    runs" and "two of three". The `runs` field closed that, additively.

    What matters is the shape of the honesty: `discovered` accounts for every
    run directory, `indexed` for those that became a `Source`, and the
    remainder is **named** with a reason. A count alone would say something is
    missing without saying what, which is not actionable.
    """
    root = project(tmp_path, "partial-run", "fail-run")
    broken = root / "output" / "broken-run"
    broken.mkdir()
    (broken / "metadata.json").write_text("{ this is not json", encoding="utf-8")
    (broken / "knowledge_units.json").write_text("{}", encoding="utf-8")

    report = built(root)
    assert report.runs_discovered == 3
    assert report.runs_skipped == 1
    assert [entry["relative_path"] for entry in report.skipped_runs] == ["output/broken-run"]

    with opened(sqlite_factory(root)) as repo:
        payload = repo.status().payload()
        assert payload["counts"]["sources"] == 2, "the skipped run has no Source record"
        assert sum(payload["sources_by_status"].values()) == 2

        runs = payload["runs"]
        assert runs["discovered"] == 3, "every run directory is accounted for"
        assert runs["indexed"] == 2
        assert runs["discovered"] == runs["indexed"] + len(runs["skipped"])
        assert [entry["relative_path"] for entry in runs["skipped"]] == ["output/broken-run"]
        reason = runs["skipped"][0]["reason"]
        assert reason, "a skipped run without a reason is a count wearing a name"
        assert str(tmp_path) not in reason, "no host path reaches a status body (D-030)"

        # The library fragment carries a `runs` row of its own and no
        # `source_id`, and it is not an ingested run. Counting it would inflate
        # `discovered` past the directories on disk and report the library as a
        # failure on every successful build.
        assert not any(
            entry["relative_path"].endswith("/library") for entry in runs["skipped"]
        )


def test_a_project_whose_runs_all_index_reports_nothing_skipped(tmp_path: Path) -> None:
    """The other half: an empty ``skipped`` is emitted, not omitted.

    A reader has to be able to tell "nothing was skipped" from "this server does
    not report skipped runs", so the list is always present on an
    implementation that scans. That is D-043's rule for ``videos.json``'s
    ``problems: []`` applied to a payload, and it is why the field is optional
    in the schema but unconditional here.
    """
    root = project(tmp_path)
    built(root)
    with opened(sqlite_factory(root)) as repo:
        runs = repo.status().payload()["runs"]
    assert runs == {"discovered": 3, "indexed": 3, "skipped": []}


def test_the_oracle_omits_the_runs_field_rather_than_claiming_it_looked(
    tmp_path: Path,
) -> None:
    """``MemoryRepository`` reports no ``runs``, for the reason it reports no version.

    It has no scan to report. Emitting ``skipped: []`` would assert that it
    looked at the filesystem and found nothing wrong, which is a claim it cannot
    make — the same reasoning that makes it report ``index_version: null``
    rather than a number. The contract therefore makes the field optional.
    """
    root = project(tmp_path)
    built(root)
    with opened(memory_factory(root)) as oracle:
        assert "runs" not in oracle.status().payload()
    with opened(sqlite_factory(root)) as repo:
        assert "runs" in repo.status().payload()


# --------------------------------------------------------------------------
# 12. The comparison itself, and the files it must never touch
# --------------------------------------------------------------------------

#: The canonical files, statted at import so that the final test can speak for
#: everything this module did — the copies are made under ``tmp_path``, and a
#: build that reached back into the originals would show up here.
def _canonical_files() -> list[Path]:
    """Every committed fixture file, and the real ``output/`` when there is one."""
    roots = [FIXTURE_RUNS]
    if (PROJECT_ROOT / "output").is_dir():
        roots.append(PROJECT_ROOT / "output")
    return sorted(path for root in roots for path in root.rglob("*") if path.is_file())


_CANONICAL_BEFORE = {
    path: (path.stat().st_mtime_ns, path.stat().st_size) for path in _canonical_files()
}


def test_one_snapshot_compares_far_more_than_the_seventy_five_already_verified(
    tmp_path: Path,
) -> None:
    """A comparison that asked few questions would pass for the wrong reason."""
    root = project(tmp_path)
    with opened(memory_factory(root)) as oracle:
        probes = probes_of(oracle)
        observed = snapshot(oracle, probes)
    assert len(observed) > 1000
    for prefix in (
        "status",
        "list_sources(",
        "list_entities(",
        "list_relations(",
        "graph(",
        "neighborhood(",
        "search(",
        "get_source(",
        "get_entity(",
        "get_artifact(",
    ):
        assert any(key.startswith(prefix) for key in observed), f"nothing exercises {prefix}"


def test_the_comparison_can_tell_a_null_total_from_a_zero_one() -> None:
    """A rule nothing can violate is not a rule (the tautology check).

    ``PageInfo.total`` is null for *unknown* and never zero for it, so a
    comparison that treated the two as equal would let an implementation report
    "no results" where the other reports "I could not count".
    """

    class _Page:
        def __init__(self, total: int | None) -> None:
            self.items: list[dict[str, Any]] = []
            self.limit = 50
            self.total = total
            self.next_cursor = None

    assert page_shapes([_Page(None)]) != page_shapes([_Page(0)])
    assert page_shapes([_Page(0)]) == page_shapes([_Page(0)])


def test_the_walk_refuses_to_loop_for_ever() -> None:
    """The helper's own failure mode, which a hung test would never report."""

    class _Never:
        items: list[dict[str, Any]] = []
        limit = 1
        total = None
        next_cursor = "always"

    with pytest.raises(AssertionError, match="pagination did not terminate"):
        walk(lambda _query: _Never(), SourceQuery, limit=1)


@requires_fts5
def test_no_build_no_refresh_and_no_query_touched_a_canonical_file(tmp_path: Path) -> None:
    """The index is a cache, so a byte or an mtime under ``output/`` moving would
    have made the evidence depend on it (mirrors
    ``test_answering_every_question_does_not_touch_the_runs``).

    ``_CANONICAL_BEFORE`` was taken at import, so this covers every scenario in
    this module as well as the cycle below.
    """
    root = project(tmp_path)
    built(root)
    refreshed(root)
    edit(
        root / "output" / "partial-run" / "knowledge_units.json",
        lambda document: document["units"][0].update({"confidence": 0.85}),
    )
    refreshed(root)
    with opened(sqlite_factory(root)) as repo:
        probes = probes_of(repo)
        snapshot(repo, probes)

    after = {
        path: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in _CANONICAL_BEFORE
    }
    changed = [str(path) for path in _CANONICAL_BEFORE if _CANONICAL_BEFORE[path] != after[path]]
    assert not changed, f"the canonical files moved: {changed[:5]}"


def test_the_twin_global_id_helpers_answer_identically(tmp_path: Path) -> None:
    """The two functions T-104's equivalence claim rests on.

    ``parse_source_id`` sat **outside** the ``try`` in
    ``repository.memory._unit_global_id`` and **inside** it in
    ``index.search._unit_global_id``, so an unparseable stored ``source_id``
    raised ``IdError`` out of one twin and returned ``None`` from the other.
    Unreachable today — every stored id was built by ``ids.py`` — but a
    coincidence is not an invariant, and this is the pair the whole equivalence
    proof is built on.
    """
    from x2knwldg.index.search import _unit_global_id as indexed
    from x2knwldg.repository.memory import _unit_global_id as oracle

    cases = [
        (None, "KU-000001"),
        ("youtube:vid1", "KU-000001"),
        ("youtube:vid1", None),
        ("youtube:vid1", ""),
        ("youtube:vid1", "not a local id"),
        # The divergence: a stored id no parser accepts.
        ("not-a-source-id", "KU-000001"),
        ("", "KU-000001"),
        ("a:b:c", "KU-000001"),
        (":", "KU-000001"),
    ]
    for source_id, local_id in cases:
        assert oracle(source_id, local_id) == indexed(source_id, local_id), (
            source_id,
            local_id,
        )
