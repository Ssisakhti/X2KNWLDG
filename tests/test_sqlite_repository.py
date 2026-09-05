"""``SqliteRepository`` against the reference it must be indistinguishable from.

``tests/test_repository.py`` says why this file exists: the seam's behaviour
tests are written "because ``T-101``–``T-104`` will write one over SQLite and
``T-105``–``T-108`` must not be able to tell the difference." So the headline
test here builds **the same records** into ``MemoryRepository`` and
:class:`~x2knwldg.index.repository.SqliteRepository` and walks every page of
every paged method at three page sizes across the filter space, asserting the
two agree item for item, page for page, and *token for token* — the last one
being the point of ``page_from_window`` living in the seam rather than in either
implementation.

Four records are added to the fixtures on purpose, because the committed runs
cannot express what the sharp cases need:

* an entity that states **no** confidence, and one whose confidence is the
  string ``"high"``. ``matches_entity`` fails both, while a bare SQL
  ``confidence >= 0.5`` drops the first silently and *returns* the second —
  SQLite sorts TEXT above every number. One test asserts that disagreement
  directly, in SQL, so the claim is measured rather than described.
* six entities and five relations with ids long enough that a page boundary
  cannot fit a whole order key in the contract's 512 characters. The cursor then
  carries a 200-character prefix plus a digest, the seek bound is a partial id
  five rows share, and ``Cursor.tail`` refuses a position it cannot see. An
  ``IndexedRelation.id`` is 1300 characters by schema, so a walk that broke
  there would break on real data and no small fixture would notice.

The index is populated with direct SQL here rather than through the scanner:
this module is about the *reader*, and a reader tested through the writer cannot
say which of the two was wrong. The committed fixtures are copied into
``tmp_path`` and never edited.

Stdlib only, so this runs in the zero-dependency CI job (ADR 0001 invariant 5).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import library
from x2knwldg.adapters import ADAPTERS, IndexRecords, adapt_project
from x2knwldg.index import schema
from x2knwldg.index.errors import SchemaTooNew
from x2knwldg.index.repository import SearchCandidates, SqliteRepository
from x2knwldg.repository import (
    MAX_CURSOR_LENGTH,
    EntityQuery,
    GraphQuery,
    IndexRepository,
    IndexUnavailable,
    InvalidId,
    InvalidQuery,
    MemoryRepository,
    NeighborhoodQuery,
    RelationQuery,
    SearchQuery,
    SourceQuery,
    content_digest,
    decode_cursor,
    encode_cursor,
    identity,
    order_key,
)

# Not on the package surface: the prefix budget is an internal of the cursor
# encoding, and this file asserts which branch of it a page boundary took.
from x2knwldg.repository.base import CURSOR_PREFIX_LENGTH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"

PASS_SOURCE = "youtube:fixture-pass"
PARTIAL_SOURCE = "youtube:fixture-partial"
FAIL_SOURCE = "youtube:fixture-fail"
UNKNOWN_SOURCE = "youtube:never-ingested"

#: The synthetic entities and relations live under this source id. It has no
#: ``Source`` record, which is deliberate: nothing here may need one.
LONG_SOURCE = "youtube:longids"

#: The oracle for the three committed fixtures once ``rebuild_library`` has run:
#: the seventh entity is the canonical concept, which belongs to no source
#: (D-016), and the three extra relations are its ``expresses_concept`` edges,
#: which name no run (D-025).
FIXTURE_COUNTS = {"sources": 3, "artifacts": 54, "entities": 7, "relations": 9}
FIXTURE_COUNTS_WITHOUT_LIBRARY = {"sources": 3, "artifacts": 54, "entities": 6, "relations": 6}

BUILT_AT = "2026-02-03T04:05:06+00:00"

_HAS_FTS5 = schema.has_fts5(sqlite3.connect(":memory:"))
requires_fts5 = pytest.mark.skipif(
    not _HAS_FTS5,
    reason="the migrations declare FTS5 tables, so a build needs an FTS5-enabled SQLite",
)


# --------------------------------------------------------------------------
# 1. Building an index by hand
# --------------------------------------------------------------------------


def _fixture_project(root: Path, *, rebuild_library: bool = True) -> IndexRecords:
    """Copy the committed runs into *root* and adapt them. Never edits fixtures."""
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    for run in sorted(FIXTURE_RUNS.iterdir()):
        if run.is_dir() and not run.name.startswith("__"):
            shutil.copytree(run, output / run.name)
    if rebuild_library:
        library.rebuild_library(output)
    return adapt_project(root)


def _entity(
    global_id: str,
    *,
    source_id: str | None,
    kind: str = "principle",
    provenance_class: str = "source",
    confidence: Any = 0.9,
    with_confidence: bool = True,
) -> dict[str, Any]:
    source_type, external_id, local_id = global_id.split(":", 2)
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "global_id": global_id,
        "source_type": source_type,
        "external_id": external_id,
        "local_id": local_id,
        "library_id": f"{external_id}:{local_id}",
        "source_id": source_id,
        "entity_type": "knowledge_unit",
        "provenance_class": provenance_class,
        "kind": kind,
        "label": f"synthetic entity {local_id}",
    }
    if with_confidence:
        record["confidence"] = confidence
    return record


def _relation(from_id: str, to_id: str, *, vocabulary: str, source_id: str | None) -> dict[str, Any]:
    relation = "supports" if vocabulary == "canonical" else "derived_from"
    return {
        "schema_version": "1.0",
        "id": f"{from_id}|{relation}|{to_id}",
        "from_id": from_id,
        "to_id": to_id,
        "relation": relation,
        "relation_vocabulary": vocabulary,
        "provenance_class": "derived",
        "confidence": 0.8,
        "source_id": source_id,
    }


def _long_global_id(number: int) -> str:
    """A global id near the 600-character ceiling ``ids.py`` sets.

    The variable part is at the very end, so every id built here shares its
    first 200 characters — which is exactly what makes a prefix cursor's seek
    bound ambiguous.
    """
    local_id = "KU-" + "L" * 250 + f"-{number:02d}"
    return f"{LONG_SOURCE}:{local_id}"


def _sharp_records(records: IndexRecords) -> IndexRecords:
    """The fixtures plus the four cases no committed run can express."""
    entities = [
        _entity(
            f"{PASS_SOURCE}:KU-NOCONF",
            source_id=PASS_SOURCE,
            with_confidence=False,
        ),
        _entity(f"{PASS_SOURCE}:KU-TEXTCONF", source_id=PASS_SOURCE, confidence="high"),
    ]
    relations: list[dict[str, Any]] = []
    long_ids = [_long_global_id(number) for number in range(1, 7)]
    for global_id in long_ids:
        entities.append(
            _entity(
                global_id,
                source_id=LONG_SOURCE,
                kind="synthesis",
                provenance_class="derived",
                confidence=0.7,
            )
        )
    # Pairwise, so the shorter sequence is the intended stop.
    for left, right in zip(long_ids, long_ids[1:], strict=False):
        relations.append(
            _relation(left, right, vocabulary="canonical", source_id=LONG_SOURCE)
        )
    return IndexRecords(
        sources=list(records.sources),
        artifacts=list(records.artifacts),
        entities=[*records.entities, *entities],
        relations=[*records.relations, *relations],
    )


#: How each family's narrowing columns are filled. The scanner owns this for
#: real; here it is spelled out so a test never depends on the sibling module,
#: and so the ``"high"`` confidence lands in the ``REAL`` column exactly as a
#: faithful extraction would put it there.
def _columns(model: str, record: Mapping[str, Any]) -> dict[str, Any]:
    if model == "source":
        status = record.get("status")
        overall = status.get("overall") if isinstance(status, Mapping) else None
        return {"source_type": record.get("source_type"), "status_overall": overall}
    if model == "artifact":
        return {"source_id": record.get("source_id")}
    if model == "entity_ref":
        return {
            "source_id": record.get("source_id"),
            "provenance_class": record.get("provenance_class"),
            "kind": record.get("kind"),
            "confidence": record.get("confidence"),
        }
    return {
        "source_id": record.get("source_id"),
        "relation_vocabulary": record.get("relation_vocabulary"),
        "from_id": record.get("from_id"),
        "to_id": record.get("to_id"),
    }


_MODEL_TABLES = {
    "source": "sources",
    "artifact": "artifacts",
    "entity_ref": "entities",
    "indexed_relation": "relations",
}


def write_index(
    root: Path,
    records: IndexRecords,
    *,
    state: str = "ready",
    built_at: str | None = BUILT_AT,
    message: str | None = None,
) -> Path:
    """Migrate an index at *root* and insert *records* directly.

    Direct SQL on purpose: the reader under test must not be tested through the
    writer, or a disagreement between them cannot be attributed.
    """
    path = schema.database_path(root)
    connection = schema.connect(path)
    try:
        schema.migrate(connection)
        with connection:
            connection.execute(
                "INSERT INTO index_state (id, state, built_at, message) VALUES (1, ?, ?, ?)",
                (state, built_at, message),
            )
            for model, rows in records.by_model().items():
                table = _MODEL_TABLES[model]
                for record in rows:
                    columns = _columns(model, record)
                    names = ["identity", "digest", "doc", *columns]
                    placeholders = ", ".join("?" * len(names))
                    connection.execute(
                        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})",
                        (
                            identity(record, model),
                            content_digest(record),
                            json.dumps(record, sort_keys=True),
                            *columns.values(),
                        ),
                    )
    finally:
        connection.close()
    return path


# --------------------------------------------------------------------------
# 2. Walking, and the fixtures every parity test shares
# --------------------------------------------------------------------------


def walk(method: Callable[[Any], Any], query_type, *, limit: int, **filters) -> list[Any]:
    """Every page a paged method yields, walked to the end.

    Mirrors ``tests/test_repository.py``'s helper, and refuses to loop forever:
    a cursor that never terminates is the failure this file exists to catch.
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


def items(pages) -> list[dict[str, Any]]:
    return [item for page in pages for item in page.items]


def shape(pages) -> list[tuple[Any, ...]]:
    """Items, token and count per page — everything a client can observe."""
    return [(page.items, page.next_cursor, page.total, page.limit) for page in pages]


def graph_shape(pages) -> list[tuple[Any, ...]]:
    return [(page.payload(), page.page_info()) for page in pages]


SOURCE_FILTERS: tuple[dict[str, Any], ...] = (
    {},
    {"source_type": "youtube"},
    {"source_type": "vimeo"},
    {"status": "PASS"},
    {"status": "PARTIAL"},
    {"status": "FAIL"},
    {"status": "UNKNOWN"},
    {"source_type": "youtube", "status": "PASS"},
    {"source_type": "vimeo", "status": "PASS"},
)

ENTITY_FILTERS: tuple[dict[str, Any], ...] = (
    {},
    {"source_id": PASS_SOURCE},
    {"source_id": PARTIAL_SOURCE},
    {"source_id": FAIL_SOURCE},
    {"source_id": LONG_SOURCE},
    {"source_id": UNKNOWN_SOURCE},
    {"provenance_class": "source"},
    {"provenance_class": "derived"},
    {"provenance_class": "user"},
    {"kind": "principle"},
    {"kind": "synthesis"},
    {"kind": "canonical_concept"},
    {"min_confidence": 0.5},
    {"min_confidence": 0.8},
    {"min_confidence": 1.0},
    {"source_id": PASS_SOURCE, "provenance_class": "source", "kind": "principle"},
    {"source_id": PASS_SOURCE, "min_confidence": 0.75},
    {"provenance_class": "derived", "kind": "canonical_concept", "min_confidence": 0.1},
)

RELATION_FILTERS: tuple[dict[str, Any], ...] = (
    {},
    {"source_id": PASS_SOURCE},
    {"source_id": PARTIAL_SOURCE},
    {"source_id": FAIL_SOURCE},
    {"source_id": LONG_SOURCE},
    {"source_id": UNKNOWN_SOURCE},
    {"relation_vocabulary": "canonical"},
    {"relation_vocabulary": "library_synthetic"},
    {"relation_vocabulary": "user"},
    {"source_id": PASS_SOURCE, "relation_vocabulary": "canonical"},
    {"source_id": PASS_SOURCE, "relation_vocabulary": "library_synthetic"},
)

GRAPH_FILTERS: tuple[dict[str, Any], ...] = (
    {},
    {"source_id": PASS_SOURCE},
    {"source_id": PARTIAL_SOURCE},
    {"source_id": FAIL_SOURCE},
    {"source_id": LONG_SOURCE},
    {"source_id": UNKNOWN_SOURCE},
    {"provenance_class": "source"},
    {"provenance_class": "derived"},
    {"relation_vocabulary": "canonical"},
    {"relation_vocabulary": "library_synthetic"},
    {"source_id": PASS_SOURCE, "provenance_class": "source"},
    {"source_id": PASS_SOURCE, "relation_vocabulary": "library_synthetic"},
)

LIMITS = (1, 2, 50)


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    """A project root holding copies of the three committed runs and a library."""
    root = tmp_path_factory.mktemp("indexed-project")
    records = _sharp_records(_fixture_project(root))
    write_index(root, records)
    return root


@pytest.fixture(scope="module")
def records(project: Path) -> IndexRecords:
    return _sharp_records(_fixture_project(project.parent / "oracle-records"))


@pytest.fixture(scope="module")
def memory(records: IndexRecords, project: Path) -> MemoryRepository:
    """The oracle: the same records, with no index at all behind them."""
    return MemoryRepository(records, project_root=project)


@pytest.fixture(scope="module")
def sqlite_repo(project: Path, memory: MemoryRepository):
    """The implementation under test, with retrieval wired to the oracle's.

    Only :meth:`SqliteRepository.search`'s *retrieval* is borrowed — the
    offset, the window, the probe row, the token and the unknown total are the
    implementation's own, and those are what the search parity test compares.
    """
    repo = SqliteRepository.open(project, search=_oracle_retrieval(memory))
    yield repo
    repo.close()


def _oracle_retrieval(memory: MemoryRepository):
    def retrieve(connection: sqlite3.Connection, query: SearchQuery) -> SearchCandidates:
        pages = walk(
            memory.search,
            SearchQuery,
            limit=500,
            q=query.q,
            source_id=query.source_id,
            include_transcript=query.include_transcript,
        )
        return SearchCandidates(hits=items(pages), complete=True)

    return retrieve


# --------------------------------------------------------------------------
# 3. The contract surface
# --------------------------------------------------------------------------


@requires_fts5
def test_the_sqlite_repository_answers_the_whole_protocol_and_nothing_more(sqlite_repo):
    assert isinstance(sqlite_repo, IndexRepository)
    protocol = {name for name in dir(IndexRepository) if not name.startswith("_")}
    assert protocol == {
        "status",
        "list_sources",
        "get_source",
        "list_entities",
        "list_relations",
        "get_entity",
        "get_artifact",
        "search",
        "graph",
        "neighborhood",
        # `T-254`. The protocol widened here and only here: ADR 0002 invariant 3
        # says no *implementation* may widen it, so the Source Map's two reads
        # are a contract change first and a method second. Spelled out rather
        # than counted, so adding a third is a deliberate edit to this list.
        "source_graph",
        "source_neighborhood",
    }
    public = {
        name
        for name in dir(sqlite_repo)
        if not name.startswith("_") and callable(getattr(sqlite_repo, name))
    }
    # `open` and `close` are construction, not contract; nothing else is added.
    assert public - protocol == {"open", "close"}


# --------------------------------------------------------------------------
# 4. The headline: page for page, token for token, against the oracle
# --------------------------------------------------------------------------


@requires_fts5
@pytest.mark.parametrize("limit", LIMITS)
def test_walking_sources_matches_the_memory_repository(sqlite_repo, memory, limit):
    for filters in SOURCE_FILTERS:
        expected = walk(memory.list_sources, SourceQuery, limit=limit, **filters)
        actual = walk(sqlite_repo.list_sources, SourceQuery, limit=limit, **filters)
        assert shape(actual) == shape(expected), filters


@requires_fts5
@pytest.mark.parametrize("limit", LIMITS)
def test_walking_entities_matches_the_memory_repository(sqlite_repo, memory, limit):
    for filters in ENTITY_FILTERS:
        expected = walk(memory.list_entities, EntityQuery, limit=limit, **filters)
        actual = walk(sqlite_repo.list_entities, EntityQuery, limit=limit, **filters)
        assert shape(actual) == shape(expected), filters


@requires_fts5
@pytest.mark.parametrize("limit", LIMITS)
def test_walking_relations_matches_the_memory_repository(sqlite_repo, memory, limit):
    for filters in RELATION_FILTERS:
        expected = walk(memory.list_relations, RelationQuery, limit=limit, **filters)
        actual = walk(sqlite_repo.list_relations, RelationQuery, limit=limit, **filters)
        assert shape(actual) == shape(expected), filters


@requires_fts5
@pytest.mark.parametrize("limit", LIMITS)
def test_walking_the_graph_matches_the_memory_repository(sqlite_repo, memory, limit):
    for filters in GRAPH_FILTERS:
        expected = walk(memory.graph, GraphQuery, limit=limit, **filters)
        actual = walk(sqlite_repo.graph, GraphQuery, limit=limit, **filters)
        assert graph_shape(actual) == graph_shape(expected), filters


@requires_fts5
@pytest.mark.parametrize("limit", LIMITS)
def test_walking_search_matches_the_memory_repository(sqlite_repo, memory, limit):
    for query_string in ("evidence", "knowledge unit", "zzzz-no-such-term"):
        for source_id in (None, PASS_SOURCE, UNKNOWN_SOURCE):
            for include_transcript in (True, False):
                filters = {
                    "q": query_string,
                    "source_id": source_id,
                    "include_transcript": include_transcript,
                }
                expected = walk(memory.search, SearchQuery, limit=limit, **filters)
                actual = walk(sqlite_repo.search, SearchQuery, limit=limit, **filters)
                assert shape(actual) == shape(expected), filters


@requires_fts5
def test_every_neighborhood_matches_the_memory_repository(sqlite_repo, memory, records):
    centers = [entity["global_id"] for entity in records.entities]
    centers.append(f"{PASS_SOURCE}:KU-NOT-A-REAL-UNIT")
    for center in centers:
        for depth in (1, 2, 3):
            for limit in LIMITS:
                for vocabulary in (None, "canonical", "library_synthetic", "user"):
                    query = NeighborhoodQuery(
                        entity_id=center,
                        depth=depth,
                        limit=limit,
                        relation_vocabulary=vocabulary,
                    )
                    expected = memory.neighborhood(query)
                    actual = sqlite_repo.neighborhood(query)
                    if expected is None:
                        assert actual is None
                    else:
                        assert actual is not None
                        assert actual.payload() == expected.payload(), (center, depth, limit)


@requires_fts5
def test_every_single_record_lookup_matches_the_memory_repository(
    sqlite_repo, memory, records
):
    for source in [*records.sources, _source_stub()]:
        expected = memory.get_source(source["id"])
        actual = sqlite_repo.get_source(source["id"])
        if expected is None:
            assert actual is None
        else:
            assert actual is not None
            assert actual.payload() == expected.payload()
    for entity in records.entities:
        assert sqlite_repo.get_entity(entity["global_id"]) == memory.get_entity(
            entity["global_id"]
        )
    for artifact in records.artifacts:
        assert sqlite_repo.get_artifact(artifact["id"]) == memory.get_artifact(
            artifact["id"]
        )


def _source_stub() -> dict[str, Any]:
    return {"id": UNKNOWN_SOURCE}


# --------------------------------------------------------------------------
# 5. The cursor cases a small fixture would never reach
# --------------------------------------------------------------------------


@requires_fts5
def test_a_walk_completes_over_relation_ids_too_long_to_carry_whole(sqlite_repo, memory):
    """A prefix cursor's seek bound is a partial id several rows share.

    ``Cursor.tail`` refuses a position it cannot find in the window it is given,
    so the seek must widen until the row that digests to the cursor is in hand.
    Six relations share their first 200 characters here, and ``limit=1`` walks
    the boundary across every one of them.
    """
    long_relations = [
        relation
        for relation in items(walk(sqlite_repo.list_relations, RelationQuery, limit=50))
        if relation["from_id"].startswith(f"{LONG_SOURCE}:")
    ]
    assert len(long_relations) == 5

    query = RelationQuery(limit=1)
    prefixed = 0
    for page in walk(sqlite_repo.list_relations, RelationQuery, limit=1):
        if page.next_cursor is None:
            continue
        cursor = decode_cursor(page.next_cursor, query.fingerprint)
        if cursor.digest is not None:
            prefixed += 1
            assert cursor.key is None
            assert len(cursor.prefix) == CURSOR_PREFIX_LENGTH
            assert len(page.next_cursor) <= MAX_CURSOR_LENGTH
    assert prefixed >= 4, "the prefix+digest branch was never taken"

    walked = items(walk(sqlite_repo.list_relations, RelationQuery, limit=1))
    assert [record["id"] for record in walked] == [
        record["id"] for record in items(walk(memory.list_relations, RelationQuery, limit=1))
    ]
    assert len({record["id"] for record in walked}) == len(walked)


@requires_fts5
def test_a_cursor_issued_for_one_filter_is_refused_by_another(sqlite_repo):
    page = sqlite_repo.list_entities(EntityQuery(limit=1))
    assert page.next_cursor is not None
    with pytest.raises(InvalidQuery):
        sqlite_repo.list_entities(EntityQuery(limit=1, cursor=page.next_cursor, kind="synthesis"))


@requires_fts5
def test_a_prefix_cursor_naming_a_record_the_collection_lost_is_refused(sqlite_repo):
    """The refusal that keeps a resumed walk from skipping a record in silence.

    Only a *prefix* cursor can be refused this way: it names its row by digest
    rather than by key, so a row that is gone is detectable. The widening seek
    must therefore exhaust the collection before it refuses — a refusal issued
    merely because the first window was too small would break every long-id walk.
    """
    real = [
        relation["id"]
        for relation in items(walk(sqlite_repo.list_relations, RelationQuery, limit=50))
        if relation["from_id"].startswith(f"{LONG_SOURCE}:")
    ]
    phantom = real[0][:-1] + "9"
    assert phantom not in real
    query = RelationQuery(limit=1)
    token = encode_cursor(query.fingerprint, order_key({"id": phantom}, "indexed_relation"))
    assert decode_cursor(token, query.fingerprint).digest is not None

    with pytest.raises(InvalidQuery):
        sqlite_repo.list_relations(RelationQuery(limit=1, cursor=token))


# --------------------------------------------------------------------------
# 6. The filters are the Python predicates, not the SQL
# --------------------------------------------------------------------------


@requires_fts5
def test_min_confidence_excludes_an_entity_that_states_no_confidence(sqlite_repo):
    unfiltered = {
        entity["global_id"]
        for entity in items(walk(sqlite_repo.list_entities, EntityQuery, limit=50))
    }
    assert f"{PASS_SOURCE}:KU-NOCONF" in unfiltered

    filtered = {
        entity["global_id"]
        for entity in items(
            walk(sqlite_repo.list_entities, EntityQuery, limit=50, min_confidence=0.5)
        )
    }
    # A unit that states no confidence is not confident enough (ADR 0001
    # invariant 2): nothing is invented for it, so it is out.
    assert f"{PASS_SOURCE}:KU-NOCONF" not in filtered
    assert f"{PASS_SOURCE}:KU-000001" in filtered


@requires_fts5
def test_min_confidence_excludes_the_non_numeric_confidence_sql_would_return(
    sqlite_repo, project
):
    """The disagreement ADR 0002 invariant 5 exists to settle, measured.

    ``confidence`` has ``REAL`` affinity, so a stored ``"high"`` stays TEXT —
    and SQLite sorts TEXT above every number, which makes
    ``confidence >= 0.5`` **true** for it. ``matches_entity`` rejects it. The
    repository must answer as the predicate does.
    """
    connection = schema.connect(schema.database_path(project), create=False)
    try:
        sql_ids = {
            row["identity"]
            for row in connection.execute(
                "SELECT identity FROM entities WHERE confidence >= 0.5"
            )
        }
    finally:
        connection.close()
    assert f"{PASS_SOURCE}:KU-TEXTCONF" in sql_ids, "the SQL trap did not fire"
    assert f"{PASS_SOURCE}:KU-NOCONF" not in sql_ids

    answered = {
        entity["global_id"]
        for entity in items(
            walk(sqlite_repo.list_entities, EntityQuery, limit=50, min_confidence=0.5)
        )
    }
    assert f"{PASS_SOURCE}:KU-TEXTCONF" not in answered


@requires_fts5
def test_a_sources_graph_shows_every_relation_its_relations_list_shows(sqlite_repo):
    """D-035/D-041: the two views may not disagree about one fact.

    A join on ``relations.source_id`` would lose the ``expresses_concept`` edges,
    which name no run — 118 edges against 101 over the real sample.
    """
    for source_id in (PASS_SOURCE, PARTIAL_SOURCE, FAIL_SOURCE):
        listed = {
            relation["id"]
            for relation in items(
                walk(sqlite_repo.list_relations, RelationQuery, limit=50, source_id=source_id)
            )
        }
        drawn: set[str] = set()
        for page in walk(sqlite_repo.graph, GraphQuery, limit=1, source_id=source_id):
            drawn.update(edge["id"] for edge in page.edges)
        assert drawn == listed, source_id
        assert any("expresses_concept" in relation_id for relation_id in listed)


# --------------------------------------------------------------------------
# 7. Truncation, absence, malformation, state
# --------------------------------------------------------------------------


@requires_fts5
def test_the_graph_reports_truncated_only_while_a_page_is_a_slice(sqlite_repo):
    whole = sqlite_repo.graph(GraphQuery(limit=500))
    assert whole.truncated is False
    assert whole.next_cursor is None

    sliced = sqlite_repo.graph(GraphQuery(limit=1))
    assert sliced.truncated is True
    assert len(sliced.nodes) == 1

    last = walk(sqlite_repo.graph, GraphQuery, limit=2)[-1]
    assert last.next_cursor is None
    # A last page with no cursor is still a slice of a larger graph.
    assert last.truncated is (len(last.nodes) < (whole.total or 0))


@requires_fts5
def test_a_neighborhood_is_truncated_by_a_limit_and_never_by_a_depth(sqlite_repo):
    center = f"{PASS_SOURCE}:KU-000001"
    cut = sqlite_repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=3, limit=1))
    assert cut is not None
    assert cut.truncated is True
    assert len(cut.nodes) == 1

    shallow = sqlite_repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=1, limit=500))
    assert shallow is not None
    assert shallow.truncated is False
    deep = sqlite_repo.neighborhood(NeighborhoodQuery(entity_id=center, depth=3, limit=500))
    assert deep is not None
    assert deep.truncated is False
    assert len(deep.nodes) >= len(shallow.nodes)


@requires_fts5
def test_a_well_formed_id_naming_nothing_is_absence_rather_than_an_error(sqlite_repo):
    assert sqlite_repo.get_source(UNKNOWN_SOURCE) is None
    assert sqlite_repo.get_entity(f"{PASS_SOURCE}:KU-999999") is None
    assert sqlite_repo.get_artifact(f"{PASS_SOURCE}:no-such-artifact") is None
    assert (
        sqlite_repo.neighborhood(
            NeighborhoodQuery(entity_id=f"{PASS_SOURCE}:KU-999999", depth=1)
        )
        is None
    )
    empty = sqlite_repo.list_entities(EntityQuery(source_id=UNKNOWN_SOURCE))
    assert empty.items == []
    assert empty.total == 0
    assert empty.next_cursor is None


@requires_fts5
@pytest.mark.parametrize(
    "method, bad_id",
    [
        ("get_source", "not-a-source-id"),
        ("get_source", "youtube:fixture-pass:extra"),
        ("get_entity", "youtube:fixture-pass"),
        ("get_entity", ""),
        ("get_artifact", "youtube::empty"),
        ("get_artifact", "YOUTUBE:fixture-pass:metadata"),
    ],
)
def test_a_malformed_id_is_refused_as_malformed(sqlite_repo, method, bad_id):
    with pytest.raises(InvalidId) as raised:
        getattr(sqlite_repo, method)(bad_id)
    assert raised.value.code == "invalid_id"
    assert raised.value.http_status == 400


@requires_fts5
def test_an_index_that_is_not_ready_refuses_every_question_but_its_status(tmp_path):
    """D-162: ``building`` and *no* ``built_at`` — no build has ever finished."""
    records = _fixture_project(tmp_path)
    write_index(
        tmp_path,
        records,
        state="building",
        built_at=None,
        message="a build is in flight",
    )
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        assert status.state == "building"
        assert status.payload()["index"]["state"] == "building"

        refusals = {
            "list_sources": lambda: repo.list_sources(SourceQuery()),
            "get_source": lambda: repo.get_source(PASS_SOURCE),
            "list_entities": lambda: repo.list_entities(EntityQuery()),
            "list_relations": lambda: repo.list_relations(RelationQuery()),
            "get_entity": lambda: repo.get_entity(f"{PASS_SOURCE}:KU-000001"),
            "get_artifact": lambda: repo.get_artifact(f"{PASS_SOURCE}:metadata"),
            "search": lambda: repo.search(SearchQuery(q="evidence")),
            "graph": lambda: repo.graph(GraphQuery()),
            "neighborhood": lambda: repo.neighborhood(
                NeighborhoodQuery(entity_id=f"{PASS_SOURCE}:KU-000001")
            ),
        }
        assert len(refusals) == 9
        for name, call in refusals.items():
            with pytest.raises(IndexUnavailable) as raised:
                call()
            assert raised.value.state == "building", name
            assert raised.value.http_status == 503
            assert "a build is in flight" in str(raised.value)
    finally:
        repo.close()


@requires_fts5
def test_a_killed_build_still_serves_the_generation_it_left_intact(tmp_path):
    """D-162. SIGKILL a refresh and the tables still hold the whole previous
    index — every write ``_apply`` makes is in one transaction, so the rollback
    is complete. Clearing ``built_at`` on the way in threw that away: the state
    said ``building`` forever, every endpoint answered ``503``, and getting the
    library back cost a full rebuild of a cache that was never damaged.
    """
    records = _fixture_project(tmp_path)
    write_index(tmp_path, records, state="building", message="a build is in flight")
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        # Honest about what it is: still `building`, and it says why.
        assert status.state == "building"
        assert status.built_at == BUILT_AT
        assert status.message == "a build is in flight"
        # And answerable, from the generation `built_at` names.
        assert repo.list_sources(SourceQuery()).items
        assert repo.get_source(PASS_SOURCE) is not None
        assert repo.graph(GraphQuery()).payload()["nodes"]
    finally:
        repo.close()


@requires_fts5
def test_a_reader_answers_honestly_while_a_writer_holds_the_index(tmp_path):
    """D-159. Without WAL a writer locks the whole database.

    A reader during a build then got `database is locked`, which `_index_state`
    maps to `state='error'` with no counts — and `payload()` renders an absent
    count as `0`. So the one endpoint that exists to be honest reported
    `state: error, sources: 0, artifacts: 0` about an index that was intact and
    whose stored row said `building`. Two `x2knwldg ui` processes reach it:
    the second one's startup `refresh_index` holds the lock at commit while the
    first answers `/api/status`.
    """
    records = _fixture_project(tmp_path)
    write_index(tmp_path, records, state="ready")

    repo = SqliteRepository.open(tmp_path)
    writer = schema.connect(schema.database_path(tmp_path))
    try:
        assert (
            writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        ), "the mode this test is about"
        # A writer mid-transaction, holding everything it is going to hold.
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("DELETE FROM sources")

        status = repo.status()
        assert status.state == "ready", "not 'error': the index is fine, it is busy"
        assert status.payload()["counts"]["sources"] > 0, "no fabricated zero"
        # And the rows it serves are the last committed generation, whole —
        # not the writer's uncommitted deletion.
        assert repo.list_sources(SourceQuery()).items
    finally:
        writer.rollback()
        writer.close()
        repo.close()


def test_an_unopenable_index_file_reports_error_rather_than_failing_to_open(tmp_path):
    """D-160: `SqliteRepository.open` caught only `FileNotFoundError`.

    A file at the index path that cannot be opened at all raises
    `sqlite3.OperationalError`, which escaped with no `code` and no
    `http_status` out of `build_repository` and out of `create_app` — so the
    application failed to *construct* and there was no reader left to say why.
    """
    path = schema.database_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # a directory where the database should be

    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        # `error`, not `absent`: there is something here, and it cannot be read.
        assert status.state == "error"
        assert status.message and "cannot be opened" in status.message
        with pytest.raises(IndexUnavailable) as raised:
            repo.list_sources(SourceQuery())
        assert raised.value.state == "error"
        assert raised.value.http_status == 503
    finally:
        repo.close()


def test_an_absent_database_reports_absent_and_brings_none_into_existence(tmp_path):
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        assert status.state == "absent"
        assert status.index_version is None
        assert status.built_at is None
        assert status.payload()["counts"] == {
            "sources": 0,
            "artifacts": 0,
            "entities": 0,
            "relations": 0,
        }
        with pytest.raises(IndexUnavailable) as raised:
            repo.list_sources(SourceQuery())
        assert raised.value.state == "absent"
    finally:
        repo.close()
    assert not schema.database_path(tmp_path).exists()
    assert not (tmp_path / schema.DATABASE_DIRNAME).exists()


@requires_fts5
def test_a_database_written_by_a_newer_schema_is_refused_rather_than_read(tmp_path):
    write_index(tmp_path, _fixture_project(tmp_path))
    connection = schema.connect(schema.database_path(tmp_path), create=False)
    try:
        with connection:
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (schema.SCHEMA_VERSION + 5, BUILT_AT),
            )
    finally:
        connection.close()
    with pytest.raises(SchemaTooNew):
        SqliteRepository.open(tmp_path)


@requires_fts5
def test_search_says_retrieval_is_unwired_rather_than_reporting_no_matches(project):
    """The one seam left for ``T-103``. Silence would look like an empty library."""
    repo = SqliteRepository.open(project)
    try:
        with pytest.raises(NotImplementedError) as raised:
            repo.search(SearchQuery(q="evidence"))
        assert "search_candidates" in str(raised.value)
        # The page shape around retrieval still answers what it can decide
        # alone: a source id naming nothing has nothing to search.
        empty = repo.search(SearchQuery(q="evidence", source_id=UNKNOWN_SOURCE))
        assert empty.items == []
        assert empty.total == 0
    finally:
        repo.close()


# --------------------------------------------------------------------------
# 8. Status, and the promise that nothing is written
# --------------------------------------------------------------------------


@requires_fts5
def test_status_reports_the_store_and_never_a_recomputed_number(tmp_path):
    records = _fixture_project(tmp_path)
    assert {
        "sources": len(records.sources),
        "artifacts": len(records.artifacts),
        "entities": len(records.entities),
        "relations": len(records.relations),
    } == FIXTURE_COUNTS
    write_index(tmp_path, records)
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        assert status.state == "ready"
        assert status.built_at == BUILT_AT
        assert status.index_version == schema.SCHEMA_VERSION
        assert status.payload()["counts"] == FIXTURE_COUNTS
        assert status.payload()["sources_by_status"] == {
            "FAIL": 1,
            "PARTIAL": 1,
            "PASS": 1,
            "UNKNOWN": 0,
        }
        assert status.payload()["adapters"] == [
            {"name": adapter.source_type, "version": adapter.version}
            for adapter in sorted(ADAPTERS.values(), key=lambda cls: cls.source_type)
        ]
    finally:
        repo.close()


@requires_fts5
def test_a_run_indexed_without_the_library_is_counted_without_it(tmp_path):
    """The library's concept and its edges are records, not a correction."""
    records = _fixture_project(tmp_path, rebuild_library=False)
    write_index(tmp_path, records)
    repo = SqliteRepository.open(tmp_path)
    try:
        assert repo.status().payload()["counts"] == FIXTURE_COUNTS_WITHOUT_LIBRARY
    finally:
        repo.close()


@requires_fts5
def test_answering_every_question_writes_nothing_at_all(tmp_path):
    records = _sharp_records(_fixture_project(tmp_path))
    database = write_index(tmp_path, records)
    watched = [database, *sorted(p for p in (tmp_path / "output").rglob("*") if p.is_file())]
    before = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in watched}

    repo = SqliteRepository.open(tmp_path, search=lambda connection, query: SearchCandidates())
    try:
        repo.status()
        walk(repo.list_sources, SourceQuery, limit=1)
        walk(repo.list_entities, EntityQuery, limit=1)
        walk(repo.list_relations, RelationQuery, limit=1)
        walk(repo.graph, GraphQuery, limit=1)
        walk(repo.search, SearchQuery, limit=1, q="evidence")
        repo.get_source(PASS_SOURCE)
        repo.get_entity(f"{PASS_SOURCE}:KU-000001")
        repo.get_artifact(f"{PASS_SOURCE}:metadata")
        repo.neighborhood(NeighborhoodQuery(entity_id=f"{PASS_SOURCE}:KU-000001", depth=3))
    finally:
        repo.close()

    after = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in watched}
    assert after == before
    # A journal or a WAL sidecar would be a write too.
    assert sorted(p.name for p in database.parent.iterdir()) == [schema.DATABASE_FILENAME]


@requires_fts5
def test_records_handed_out_cannot_reach_the_stored_ones(sqlite_repo):
    """ADR 0002 invariant 6, for free: every record is parsed fresh per call."""
    first = sqlite_repo.get_source(PASS_SOURCE)
    assert first is not None
    first.source["status"]["overall"] = "PASS-FOREVER"
    first.source["id"] = "tampered"
    again = sqlite_repo.get_source(PASS_SOURCE)
    assert again is not None
    assert again.source["id"] == PASS_SOURCE
    assert again.source["status"]["overall"] == "PASS"

    page = sqlite_repo.list_entities(EntityQuery(limit=50))
    page.items[0]["confidence"] = 1.0
    assert sqlite_repo.list_entities(EntityQuery(limit=50)).items[0]["confidence"] != 1.0


@requires_fts5
def test_a_database_with_no_build_recorded_reports_absent_rather_than_error(tmp_path):
    """The state machine stays monotone: less built is never worse than broken."""
    connection = schema.connect(schema.database_path(tmp_path))
    connection.close()
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        assert status.state == "absent"
        # A file that exists is at version 0, which the contract types as a
        # legal answer (`integer | null`, `minimum: 0`) and distinguishes from
        # the absent file's null.
        assert status.index_version == 0
        assert status.payload()["counts"]["sources"] == 0
    finally:
        repo.close()

    migrated = schema.connect(schema.database_path(tmp_path))
    try:
        schema.migrate(migrated)
    finally:
        migrated.close()
    repo = SqliteRepository.open(tmp_path)
    try:
        # Migrated, but no build has claimed it. Still absent, and now the
        # counts are real zeros rather than unknown ones.
        assert repo.status().state == "absent"
        assert repo.status().index_version == schema.SCHEMA_VERSION
        assert repo.status().payload()["counts"]["sources"] == 0
    finally:
        repo.close()


def test_a_file_that_is_not_a_database_reports_error_and_still_answers_status(tmp_path):
    path = schema.database_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a SQLite database, it is a note")
    repo = SqliteRepository.open(tmp_path)
    try:
        status = repo.status()
        assert status.state == "error"
        assert status.payload()["counts"] == {
            "sources": 0,
            "artifacts": 0,
            "entities": 0,
            "relations": 0,
        }
        with pytest.raises(IndexUnavailable) as raised:
            repo.graph(GraphQuery())
        assert raised.value.state == "error"
    finally:
        repo.close()


@requires_fts5
def test_a_corpus_that_could_not_be_read_whole_reports_an_unknown_total(project):
    """``total=None`` means unknown and never zero (frozen ``PageInfo``)."""
    hits = [{"type": "knowledge_unit", "id": "KU-000001", "score": 1.0}]

    def partial(connection: sqlite3.Connection, query: SearchQuery) -> SearchCandidates:
        return SearchCandidates(hits=hits, complete=False)

    repo = SqliteRepository.open(project, search=partial)
    try:
        page = repo.search(SearchQuery(q="evidence", limit=50))
        assert page.items == hits
        assert page.total is None
        assert page.next_cursor is None
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# One walk, one pass (D-188)
# ---------------------------------------------------------------------------


def _many_entities(count: int) -> IndexRecords:
    return IndexRecords(
        entities=[
            {
                "schema_version": "1.0",
                "global_id": f"youtube:s:KU-{index:06d}",
                "source_id": "youtube:s",
                "source_type": "youtube",
                "local_id": f"KU-{index:06d}",
                "kind": "principle",
                "provenance_class": "source",
                "label": f"Node {index}",
            }
            for index in range(count)
        ]
    )


def _walk(repo, **filters):
    """Every page of one filtered walk, and the totals each page reported."""
    cursor, pages, totals = None, 0, []
    while True:
        page = repo.list_entities(EntityQuery(limit=50, cursor=cursor, **filters))
        pages += 1
        totals.append(page.total)
        cursor = page.next_cursor
        if cursor is None:
            return pages, totals


def test_a_filtered_walk_scans_the_table_once_rather_than_once_per_page(tmp_path):
    """`_total` restarted from row zero on **every** page, parsing every row.

    `/api/sources/{id}/entities` always supplies a `source_id`, so this was the
    common path rather than an edge: 80 pages over 4000 entities meant 324,158
    rows read and JSON-parsed, for a number that is the same on every page of
    the walk — as `_total`'s own docstring says.
    """
    write_index(tmp_path, _many_entities(4000))
    repo = SqliteRepository.open(tmp_path)
    try:
        passes = 0
        real_scan = repo._scan_total

        def counting(*args, **kwargs):
            nonlocal passes
            passes += 1
            return real_scan(*args, **kwargs)

        repo._scan_total = counting  # type: ignore[method-assign]
        pages, totals = _walk(repo, source_id="youtube:s")
        assert pages == 80
        assert set(totals) == {4000}, "the total is the same on every page, and true"
        assert passes == 1, f"the table was scanned {passes} times for one walk"
    finally:
        repo.close()


def test_the_memo_is_dropped_when_the_index_changes_under_the_reader(tmp_path):
    """Correctness comes from the generation key, not from hoping."""
    write_index(tmp_path, _many_entities(100))
    repo = SqliteRepository.open(tmp_path)
    try:
        first = repo.list_entities(EntityQuery(source_id="youtube:s", limit=10))
        assert first.total == 100

        # A rebuild lands: fewer records, a new `built_at`.
        connection = schema.connect(schema.database_path(tmp_path))
        try:
            with connection:
                connection.execute("DELETE FROM entities WHERE identity > ?", ("youtube:s:KU-000049",))
                connection.execute(
                    "INSERT OR REPLACE INTO index_state (id, state, built_at) VALUES (1, 'ready', ?)",
                    ("2026-02-02T00:00:00+00:00",),
                )
        finally:
            connection.close()

        again = repo.list_entities(EntityQuery(source_id="youtube:s", limit=10))
        assert again.total == 50, "a stale count is a wrong count"
    finally:
        repo.close()


def test_a_graph_walk_builds_the_collection_once(tmp_path):
    """The one public method that was not wrapped in the per-walk memo.

    The whole entity and relation set is the same on every page of one walk —
    the cursor only says where in ``nodes`` to resume — and it was re-selected
    and re-parsed each time. Measured on 4,000 entities: 63,992 JSON rows
    across 8 pages, 7,999 per page, all identical. This is the Map's primary
    walk, where pages accumulate until the graph is whole.
    """
    write_index(tmp_path, _many_entities(4000))
    repo = SqliteRepository.open(tmp_path)
    try:
        built = 0
        real_collection = repo._graph_collection

        def counting(*args, **kwargs):
            nonlocal built
            built += 1
            return real_collection(*args, **kwargs)

        repo._graph_collection = counting  # type: ignore[method-assign]

        cursor, pages, seen = None, 0, []
        while True:
            page = repo.graph(GraphQuery(limit=500, cursor=cursor))
            pages += 1
            seen.extend(node["global_id"] for node in page.nodes)
            assert page.total == 4000
            cursor = page.next_cursor
            if cursor is None:
                break
        assert pages == 8
        assert len(seen) == len(set(seen)) == 4000, "a full walk shows every node once"
        assert built == 1, f"the collection was built {built} times for one walk"
    finally:
        repo.close()


def test_a_graph_page_hands_out_no_record_the_memo_holds(tmp_path):
    """ADR 0002 invariant 6, which the memo could have quietly broken.

    Before the memo every page parsed its records fresh, so there was nothing
    for a caller to alias; now the collection is held between pages and the
    edges have to be copied on the way out, as ``MemoryRepository`` already
    does.
    """
    write_index(
        tmp_path,
        IndexRecords(
            entities=[
                {
                    "schema_version": "1.0",
                    "global_id": f"youtube:s:KU-{index:06d}",
                    "source_id": "youtube:s",
                    "source_type": "youtube",
                    "local_id": f"KU-{index:06d}",
                    "kind": "principle",
                    "provenance_class": "source",
                    "label": f"Node {index}",
                }
                for index in range(2)
            ],
            relations=[
                {
                    "schema_version": "1.0",
                    "id": "youtube:s:REL-000001",
                    "source_id": "youtube:s",
                    "from_id": "youtube:s:KU-000000",
                    "to_id": "youtube:s:KU-000001",
                    "relation": "supports",
                    "relation_vocabulary": "canonical",
                    "provenance_class": "source",
                    "confidence": None,
                }
            ],
        ),
    )
    repo = SqliteRepository.open(tmp_path)
    try:
        first = repo.graph(GraphQuery(limit=500))
        assert first.edges
        first.edges[0]["relation"] = "MUTATED"
        first.nodes[0]["label"] = "MUTATED"

        again = repo.graph(GraphQuery(limit=500))
        assert again.edges[0]["relation"] == "supports"
        assert again.nodes[0]["label"] != "MUTATED"
    finally:
        repo.close()


@requires_fts5
def test_a_search_walk_ranks_the_corpus_once(tmp_path):
    """Every page re-ran the whole FTS retrieval and re-ranked every hit.

    The offset then discarded all but `limit` of it — reintroducing per page
    the cost ADR 0004's D-042 removed from the oracle, whose own words are
    "Search costs one pass over the library per repository, not one per page."
    """
    hits = [
        {"type": "knowledge_unit", "id": f"KU-{index:06d}", "score": 1.0 - index / 1000}
        for index in range(200)
    ]
    calls = 0

    def counting_search(connection, query):
        nonlocal calls
        calls += 1
        return SearchCandidates(hits=hits, complete=True)

    write_index(tmp_path, _many_entities(10))
    repo = SqliteRepository.open(tmp_path, search=counting_search)
    try:
        cursor, pages = None, 0
        while True:
            page = repo.search(SearchQuery(q="evidence", limit=20, cursor=cursor))
            pages += 1
            assert page.total == 200
            cursor = page.next_cursor
            if cursor is None:
                break
        assert pages == 10
        assert calls == 1, f"the corpus was ranked {calls} times for one walk"
    finally:
        repo.close()


# --------------------------------------------------------------------------
# The unsearchable-source note counts the same set the endpoint honours
# --------------------------------------------------------------------------


def _write_run_rows(root: Path, rows: Mapping[str, list[str]]) -> None:
    """One ``runs`` row per ``source_id -> problems``, written directly.

    Direct SQL for the same reason ``write_index`` uses it: the reader under
    test must not be exercised through the writer.
    """
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        with connection:
            for index, (source_id, problems) in enumerate(rows.items()):
                connection.execute(
                    "INSERT INTO runs (canonical_dir, source_id, digest, scanned_at, "
                    "problems, skipped_reason) VALUES (?, ?, ?, ?, ?, NULL)",
                    (
                        f"output/run-{index}",
                        source_id,
                        "a:b",
                        BUILT_AT,
                        json.dumps(problems),
                    ),
                )
    finally:
        connection.close()


def _unsearchable_note_count(root: Path) -> tuple[int, int]:
    """``(counted by status, held by search)`` for the index at *root*."""
    from x2knwldg.index.search import unreadable_sources

    repo = SqliteRepository.open(root)
    try:
        counted = repo._unsearchable_source_count()
    finally:
        repo.close()
    connection = schema.connect(schema.database_path(root), create=False)
    try:
        return counted, len(unreadable_sources(connection))
    finally:
        connection.close()


@pytest.mark.parametrize(
    "label,problems",
    [
        (
            "a problem that merely quotes the prefix",
            # `unmappable_artifacts` reasons are free text copied out of the
            # adapter, so a note whose *name* contains the marker is a shape
            # production can produce.
            ['unmappable_artifacts: notes.md: cannot parse "search: not a marker"'],
        ),
        (
            "the marker in the wrong case",
            # SQLite's LIKE is ASCII case-insensitive; `startswith` is not.
            [f'{schema.SEARCH_PROBLEM_PREFIX.upper()}shouted, and not a marker'],
        ),
        (
            "the marker not at the start of its element",
            [f"unreadable_files: a.json: {schema.SEARCH_PROBLEM_PREFIX}quoted"],
        ),
    ],
)
def test_the_status_note_counts_no_source_the_endpoint_still_totals(
    tmp_path: Path, label: str, problems: list[str]
) -> None:
    """``index.message`` may not claim damage ``PageInfo.total`` does not honour.

    The count was ``problems LIKE '%"search: %'`` — a substring test over the
    *serialised list*, so the marker matched anywhere inside any element, and
    ASCII-case-insensitively at that. ``search.unreadable_sources`` does a
    per-element ``startswith``, so the two disagreed: the status line reported
    more unreadable sources than the set that actually makes a search total
    ``null``, and a reader had no way to reconcile the two.
    """
    write_index(tmp_path, _many_entities(1))
    _write_run_rows(tmp_path, {"youtube:one": problems})

    counted, held = _unsearchable_note_count(tmp_path)
    assert held == 0, f"the premise: {label} is not an unreadable source"
    assert counted == held, f"the status note counted {label}"


def test_the_status_note_does_count_a_real_marker(tmp_path: Path) -> None:
    """The other half: narrowing the match must not lose the case it is for."""
    write_index(tmp_path, _many_entities(1))
    _write_run_rows(
        tmp_path,
        {
            "youtube:one": [f"{schema.SEARCH_PROBLEM_PREFIX}transcript.json cannot be read"],
            "youtube:two": ["unreadable_files: work/bundle.json: absent"],
        },
    )

    counted, held = _unsearchable_note_count(tmp_path)
    assert (counted, held) == (1, 1)

    repo = SqliteRepository.open(tmp_path)
    try:
        message = repo.status().message
    finally:
        repo.close()
    assert message is not None and "1 indexed source could not be read" in message


def test_a_source_with_no_brief_row_answers_what_the_oracle_answers(tmp_path: Path) -> None:
    """The twin of ``test_both_repositories_say_the_same_thing_about_a_source_with_no_brief``.

    A run the scanner skipped has a node from no pass and a brief from no pass.
    This branch and ``MemoryRepository``'s said different sentences about that
    one fact; they now read the same constant.
    """
    from x2knwldg import synthesis

    write_index(tmp_path, _many_entities(1))
    repo = SqliteRepository.open(tmp_path)
    try:
        answer = repo._brief("youtube:never-scanned")
    finally:
        repo.close()
    assert answer == {
        "state": synthesis.BRIEF_UNAVAILABLE,
        "brief": None,
        "reason": synthesis.NO_BRIEF_REASON,
    }


# --------------------------------------------------------------------------
# The edge cap bounds the work, not only the answer
# --------------------------------------------------------------------------


def _star(spokes: int) -> IndexRecords:
    """One hub with *spokes* neighbours, and an edge to each."""
    hub = "youtube:s:KU-000000"
    entities = [_entity(hub, source_id="youtube:s")]
    relations = []
    for index in range(1, spokes + 1):
        spoke = f"youtube:s:KU-{index:06d}"
        entities.append(_entity(spoke, source_id="youtube:s"))
        relations.append(
            _relation(hub, spoke, vocabulary="canonical", source_id="youtube:s")
        )
    return IndexRecords(entities=entities, relations=relations)


def _counting_documents(repo: SqliteRepository) -> list[str]:
    """Record the table of every stored row this repository parses."""
    parsed: list[str] = []
    original = repo._document

    def counting(row: Any, table: str) -> dict[str, Any]:
        parsed.append(table)
        return original(row, table)

    repo._document = counting  # type: ignore[method-assign]
    return parsed


def test_the_adjacency_seek_parses_a_relation_only_as_it_is_asked_for(
    tmp_path: Path,
) -> None:
    """``_relations_touching`` returned a list, so every touching edge was built.

    ``neighborhood`` then handed the lot to ``bounded_edges``, which kept
    ``MAX_GRAPH_EDGES`` — so the cap bounded the response and nothing bounded
    the work behind it. A hub node in a large library paid for every edge it has
    in parsed dictionaries to return a hundred.
    """
    write_index(tmp_path, _star(20))
    repo = SqliteRepository.open(tmp_path)
    try:
        parsed = _counting_documents(repo)
        walk = repo._relations_touching(["youtube:s:KU-000000"])
        assert next(walk)["from_id"] == "youtube:s:KU-000000"
        assert next(walk)
        assert parsed.count("relations") == 2, (
            f"two relations were asked for and {parsed.count('relations')} were built"
        )
    finally:
        repo.close()


def test_a_neighborhood_stops_one_past_the_edge_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One past, because that is what tells ``bounded_edges`` the list was cut.

    The cap is patched down rather than the corpus grown up to it: 5000 edges
    would make this a slow test of the same one fact.
    """
    from x2knwldg.index import repository as index_repository
    from x2knwldg.repository import base as repository_base

    monkeypatch.setattr(index_repository, "MAX_GRAPH_EDGES", 3)
    monkeypatch.setattr(repository_base, "MAX_GRAPH_EDGES", 3)

    write_index(tmp_path, _star(20))
    repo = SqliteRepository.open(tmp_path)
    try:
        parsed = _counting_documents(repo)
        hood = repo.neighborhood(
            NeighborhoodQuery(entity_id="youtube:s:KU-000000", depth=1, limit=50)
        )
    finally:
        repo.close()

    assert hood is not None
    assert len(hood.edges) == 3 and hood.truncated is True
    # The breadth-first round reads every touching relation — it has to, to find
    # the neighbours — and the edge pass then stops at four. Twenty plus four,
    # never twenty plus twenty.
    assert parsed.count("relations") == 24, (
        f"the edge pass built {parsed.count('relations') - 20} of 20 relations "
        "after the cap was already met"
    )
