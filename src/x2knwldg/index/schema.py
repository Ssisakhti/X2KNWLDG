"""The SQLite schema and its explicit, versioned migrations (``T-101``).

This module is the only place in the package that writes DDL. Canvas plan §9.4
requires migrations to be "explicit and versioned", and the frozen
``StatusPayload.index.index_version`` describes itself as the "Migration version
of the SQLite schema (``T-101``)" — so the version a build reports is read from
:data:`MIGRATIONS`, never hard-coded beside it.

Three shape decisions worth stating, because each one closes a defect that would
otherwise be invisible until it had already produced a wrong answer.

**Records are stored verbatim as JSON.** ADR 0002 invariant 2 forbids the
repository supplying a value the canonical files do not carry, and the v1
records are deliberately sparse: ``Source.counts`` omits a key whose file was
unreadable rather than zeroing it, and ``adapter_metadata.unreadable_files`` is
absent rather than empty when there is nothing to report. A normalised column
per field would have to choose a representation for every one of those
absences, and every choice would be an invention. So the record round-trips
byte-for-byte and the extracted columns exist *only* to narrow candidates.

**The extracted columns are not the filters.** ADR 0002 invariant 5 is explicit:
``matches_source``, ``matches_entity``, ``matches_relation`` and
``relation_belongs_to_source`` are the definition of each filter, and "where a
SQL ``WHERE`` clause disagrees with them, they are right". ``min_confidence`` is
the sharp example — ``matches_entity`` fails a missing or non-numeric confidence
on purpose ("a unit that states no confidence is not confident enough"), while
SQL's ``NULL >= 0.5`` is ``NULL``, which is not ``false`` and does not filter.
The columns here are indexes, and the Python predicates are the specification.

**The order key is stored as two columns, never one.** ``repository.order_key``
joins the identity and the content digest with ``ORDER_KEY_SEPARATOR``, which is
a NUL byte. ``identity`` and ``digest`` are stored separately and ordered as a
pair, so no NUL is ever handed to SQLite, and ``page_from_window`` rebuilds the
token from the record itself. The ``PRIMARY KEY`` on ``identity`` is also the
``UNIQUE`` guarantee the seam's README asks for: it makes the order total, so a
tie across a page boundary cannot delete a record from the paged output while
``total`` keeps counting it.

The two FTS5 tables are **external-content** indexes over ``documents``, so the
searchable text is stored once rather than three times. ``search.py`` owns what
goes into them; this module owns only their declaration.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .errors import Fts5Unavailable, IndexCorrupt, SchemaTooNew

__all__ = [
    "DATABASE_DIRNAME",
    "DATABASE_FILENAME",
    "MIGRATIONS",
    "SCHEMA_VERSION",
    "database_path",
    "connect",
    "migrate",
    "schema_version",
    "require_fts5",
    "has_fts5",
]

#: The rebuildable cache directory, fixed by canvas plan §9.3 and already
#: gitignored. Deleting it must lose nothing (ADR 0001 invariant 3).
DATABASE_DIRNAME = ".x2knwldg"

#: Prefix of the ``runs.problems`` entry that records a source whose searchable
#: text could not be read. Declared here, beside the table whose column holds
#: it, because three modules write or read it: ``search`` sets and clears it,
#: ``search.unreadable_sources`` matches on it so ``PageInfo.total`` can be
#: ``null`` rather than ``0``, and ``scanner`` folds it into the scan report of
#: the pass that produced it. A prefix spelled out in three files is three
#: prefixes.
SEARCH_PROBLEM_PREFIX = "search: "
DATABASE_FILENAME = "index.sqlite"


# --------------------------------------------------------------------------
# 1. The migrations
#
# Forward-only, appended and never edited. An edited migration is a schema
# that differs between two machines which both report the same version, and
# nothing downstream could detect that. Adding a column means adding a
# version, even when the old one has only ever run here.
# --------------------------------------------------------------------------

_MIGRATION_1 = (
    # The version ledger itself. `applied_at` is evidence about the cache, not
    # about any video, so it is generated here rather than copied from a run.
    """
    CREATE TABLE schema_migrations (
        version    INTEGER PRIMARY KEY,
        applied_at TEXT    NOT NULL
    )
    """,
    # One row, enforced by the CHECK. `state` is one of repository.INDEX_STATES;
    # a build writes `ready` only when it finished, so a crash reopens as
    # `building` rather than as a half-full index that claims to be complete.
    """
    CREATE TABLE index_state (
        id       INTEGER PRIMARY KEY CHECK (id = 1),
        state    TEXT    NOT NULL,
        built_at TEXT,
        message  TEXT
    )
    """,
    # What the scanner remembers about each run so it can decide "unchanged"
    # without re-adapting it. Keyed by the project-relative canonical_dir,
    # which is the handle the Source record itself carries -- no id is ever
    # joined onto a path (D-042, ADR 0003).
    #
    # `problems` and `skipped_reason` are the two tiers rebuild_library
    # established under D-043: a run indexed with named gaps, and a run that
    # could not be indexed at all. Both are recorded, so a count never omits a
    # run without saying so.
    """
    CREATE TABLE runs (
        canonical_dir  TEXT    NOT NULL PRIMARY KEY,
        source_id      TEXT,
        digest         TEXT    NOT NULL,
        scanned_at     TEXT    NOT NULL,
        problems       TEXT    NOT NULL DEFAULT '[]',
        skipped_reason TEXT
    )
    """,
    # The four record families. `identity` is the ORDER_KEYS value for the
    # model; `digest` is repository.content_digest, which breaks a tie and makes
    # the order total; `doc` is the record, verbatim.
    """
    CREATE TABLE sources (
        identity       TEXT NOT NULL PRIMARY KEY,
        digest         TEXT NOT NULL,
        doc            TEXT NOT NULL,
        source_type    TEXT,
        status_overall TEXT
    )
    """,
    """
    CREATE TABLE artifacts (
        identity  TEXT NOT NULL PRIMARY KEY,
        digest    TEXT NOT NULL,
        doc       TEXT NOT NULL,
        source_id TEXT
    )
    """,
    """
    CREATE TABLE entities (
        identity         TEXT NOT NULL PRIMARY KEY,
        digest           TEXT NOT NULL,
        doc              TEXT NOT NULL,
        source_id        TEXT,
        provenance_class TEXT,
        kind             TEXT,
        confidence       REAL
    )
    """,
    """
    CREATE TABLE relations (
        identity            TEXT NOT NULL PRIMARY KEY,
        digest              TEXT NOT NULL,
        doc                 TEXT NOT NULL,
        source_id           TEXT,
        relation_vocabulary TEXT,
        from_id             TEXT NOT NULL,
        to_id               TEXT NOT NULL
    )
    """,
    # Membership and filter indexes. Every one of these narrows candidates for
    # a predicate in repository/base.py; none of them *is* that predicate.
    #
    # What `repository._narrow` actually issues is
    # `(source_id = ? OR source_id IS NULL)` — the `OR` admits the rows whose
    # column was never extracted, which is the only way the narrowing stays a
    # superset of its filter (ADR 0002 invariant 5). So these three are read by
    # SQLite as a two-branch `MULTI-INDEX OR`, one index search per disjunct,
    # not as the single search a plain equality gets. That is still an index
    # seek and still cheap; what it costs is the index's *ordering*, so the
    # keyset walk's `ORDER BY identity, digest` becomes a temporary B-tree
    # where plain equality would sort on the index. `tests/test_sqlite_schema.py`
    # pins the plan, because "this index narrows the seek" is a claim a query
    # planner can quietly stop honouring.
    "CREATE INDEX artifacts_by_source ON artifacts (source_id, identity)",
    "CREATE INDEX entities_by_source ON entities (source_id, identity)",
    "CREATE INDEX relations_by_source ON relations (source_id, identity)",
    # relation_belongs_to_source's second disjunct is a prefix test on either
    # endpoint, because the library's expresses_concept edges carry
    # source_id: null (D-034/D-041). These two indexes are what make that
    # prefix scan cheap; the disjunction itself stays in Python.
    "CREATE INDEX relations_by_from ON relations (from_id)",
    "CREATE INDEX relations_by_to ON relations (to_id)",
    # The searchable corpus. `folded` is the NFKC-casefolded text query.py
    # matches on; `hit` is the frozen result shape, stored whole so no field is
    # rebuilt (and so D-028's two shapes cannot drift). `ordinal` preserves
    # canonical file order, which is what breaks a scoring tie: rank_documents
    # sorts stably, so ties keep the order the documents were produced in.
    """
    CREATE TABLE documents (
        rowid     INTEGER PRIMARY KEY,
        source_id TEXT    NOT NULL,
        hit_type  TEXT    NOT NULL,
        hit       TEXT    NOT NULL,
        folded    TEXT    NOT NULL,
        weight    REAL    NOT NULL,
        ordinal   INTEGER NOT NULL
    )
    """,
    "CREATE INDEX documents_by_source ON documents (source_id, ordinal)",
    # SearchDocument.score has two disjuncts and each needs its own index,
    # because `score > 0` iff the query's tokens intersect the document's OR
    # the folded query is a substring of the folded text.
    #
    # The token half is a plain table, NOT an FTS5 `unicode61` index, and that
    # is a correctness decision rather than a preference. FTS5's tokenizers are
    # not `query._tokens`: `unicode61` splits on `_` where Python's `\w+` does
    # not, and it does not split scriptless CJK at all, while `_tokens` expands
    # a CJK run into single characters and adjacent bigrams. Measured: for the
    # query `機習` against `機械学習のモデル` the scorer returns 0.667 (the two
    # characters are both present as tokens) while `unicode61 MATCH` and a
    # trigram substring scan BOTH return nothing -- the characters are not
    # adjacent, so no substring exists to match. Every such disagreement is a
    # silently missing hit. Storing `_tokens`'s own output as rows makes the
    # overlap disjunct exact by construction instead of approximately right.
    """
    CREATE TABLE document_tokens (
        token       TEXT    NOT NULL,
        document_id INTEGER NOT NULL,
        PRIMARY KEY (token, document_id)
    ) WITHOUT ROWID
    """,
    # The forward direction answers "which documents hold this token"; the
    # reverse answers "which tokens does this document hold", which rescoring
    # needs to rebuild a SearchDocument's `tokens` frozenset.
    "CREATE INDEX document_tokens_by_document ON document_tokens (document_id, token)",
    # The substring half. Queried with GLOB and never with MATCH: trigram
    # MATCH silently returns zero rows for a needle under three characters,
    # and LIKE is wrong outright because `%` and `_` in a user's query are
    # LIKE wildcards -- a search for `100%` would match `100 percent`, and
    # `a_b` would match `axb`. GLOB is byte-exact (both sides are already
    # NFKC-casefolded by query._fold) and keeps the trigram index: the plan
    # reads `INDEX 0:G0`. Escape `*`, `?` and `[` in the needle.
    """
    CREATE VIRTUAL TABLE documents_trigrams USING fts5(
        folded,
        content='documents',
        content_rowid='rowid',
        tokenize='trigram'
    )
    """,
)

# --------------------------------------------------------------------------
# Migration 2 — the source layer (`T-254`)
#
# Three tables, appended rather than folded into the four above, and that
# separation is D-251 made durable. `entities` feeds `/api/graph`,
# `/api/sources/{id}/entities`, the `/api/status` counts and every entity total
# in the project, and none of those filters on `entity_type`; a source node
# stored there would move all of them, which D-249 forbids in as many words. A
# table nothing existing reads cannot leak into a payload at all.
#
# All three are rebuildable from canonical files and hold nothing that is not:
# `source_entities` from the adapters, `source_briefs` from each run's
# `source_knowledge.json` through `synthesis.brief_state`, and
# `source_relations` from `output/synthesis/source_relations.json`. ADR 0001
# invariant 3 therefore still holds of the whole cache: deleting it loses
# nothing.
# --------------------------------------------------------------------------

_MIGRATION_2 = (
    # One row per acquired source. `identity` is the node's three-part global
    # id — `repository.ORDER_KEYS["source_entity"]` — and `digest` is its
    # content digest, the pair the keyset walk orders by, exactly as the four
    # record tables store them.
    """
    CREATE TABLE source_entities (
        identity  TEXT NOT NULL PRIMARY KEY,
        digest    TEXT NOT NULL,
        doc       TEXT NOT NULL,
        source_id TEXT NOT NULL
    )
    """,
    "CREATE INDEX source_entities_by_source ON source_entities (source_id)",
    # The readable brief, and what is true about it. `state` and `reason` are
    # `synthesis.brief_state`'s own two fields, stored as it computed them at
    # scan time rather than re-derived on read: the gate, the adapter and this
    # answer "is this brief current" with one implementation.
    #
    # `doc` is NULL exactly when there is no document to show. A run with no
    # brief still gets a row — `unavailable` with a reason is an answer about
    # the source, and a missing row would make "not indexed" and "no brief"
    # indistinguishable.
    """
    CREATE TABLE source_briefs (
        source_id TEXT NOT NULL PRIMARY KEY,
        state     TEXT NOT NULL,
        reason    TEXT,
        doc       TEXT
    )
    """,
    # The accepted cross-source synthesis. Keyed by the deterministic
    # `SR-`-prefixed id (D-252), which is what makes a second pass that finds
    # another ground update one record rather than mint a second.
    #
    # The two endpoint columns are extracted for the same reason `relations`
    # extracts `from_id` and `to_id`: they narrow a seek. They are not the
    # filter — which endpoints a neighbourhood carries is decided in Python,
    # against the ids the seam parsed.
    """
    CREATE TABLE source_relations (
        identity       TEXT NOT NULL PRIMARY KEY,
        digest         TEXT NOT NULL,
        doc            TEXT NOT NULL,
        from_source_id TEXT NOT NULL,
        to_source_id   TEXT NOT NULL
    )
    """,
    "CREATE INDEX source_relations_by_from ON source_relations (from_source_id)",
    "CREATE INDEX source_relations_by_to ON source_relations (to_source_id)",
)

# --------------------------------------------------------------------------
# Migration 3 — what the stored rows were written *by*
#
# The incremental scan asked one question — "did any file move?" — and treated
# the answer as the whole of "is the index current". It is not. Migration 2
# created `source_entities`, `source_briefs` and `source_relations` **empty**
# beside a populated schema-1 index, and `index_state` was untouched by it: the
# next `refresh_index` hashed identical files, called every run `unchanged`,
# and committed `ready` over three empty tables. Measured — `discovered=3
# indexed=3 unchanged=3 skipped=0`, `state: ready`, `message: None`, while
# `/api/source-graph` answered 0 nodes and `source_neighborhood(...)` returned
# `None`. A healthy report over an empty layer is the silent zero D-043
# forbids, and the only escape was knowing to delete the cache directory.
#
# The same class, one step further out: a run whose records are carried over
# unchanged was adapted by the code of *some earlier pass*, so bumping an
# adapter's `version` or `adapters.base.SCHEMA_VERSION` leaves those records at
# the old shape while `/api/status.adapters` reports the new version, read live
# from the class. Two columns, so the answer is "the rows were written by this
# schema and these adapters" rather than "no file moved since".
#
# `ALTER TABLE ... ADD COLUMN` rather than a new table: the singleton
# `index_state` row is already the one thing a scan reads before deciding, and
# a second table would be a second thing that can be stale. Both are nullable,
# because every database migrating up to here has rows written by code that
# recorded neither — and `NULL` compares unequal to every current version,
# which is precisely the full build such a database needs.
# --------------------------------------------------------------------------

_MIGRATION_3 = (
    "ALTER TABLE index_state ADD COLUMN schema_version INTEGER",
    "ALTER TABLE index_state ADD COLUMN adapter_versions TEXT",
)

#: ``(version, statements)`` in ascending order. The tuple is the ledger.
MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, _MIGRATION_1),
    (2, _MIGRATION_2),
    (3, _MIGRATION_3),
)

#: The version a fresh database reaches. Derived, never typed twice.
SCHEMA_VERSION = MIGRATIONS[-1][0]


# --------------------------------------------------------------------------
# 2. Opening a database
# --------------------------------------------------------------------------


def database_path(project_root: Path) -> Path:
    """Where the index lives for *project_root*.

    One rule, so the scanner and the repository cannot disagree about which
    file is "the index".
    """
    return Path(project_root) / DATABASE_DIRNAME / DATABASE_FILENAME


def has_fts5(connection: sqlite3.Connection) -> bool:
    """Whether this SQLite build can create an FTS5 table.

    Probed by creating one in ``temp`` and dropping it, rather than by reading
    ``PRAGMA compile_options``: that pragma is empty on some builds, so a
    missing ``ENABLE_FTS5`` there is not evidence either way. Attempting the
    thing is.
    """
    try:
        connection.execute("CREATE VIRTUAL TABLE temp.x2knwldg_fts5_probe USING fts5(probe)")
    except sqlite3.OperationalError:
        return False
    connection.execute("DROP TABLE temp.x2knwldg_fts5_probe")
    return True


def require_fts5(connection: sqlite3.Connection) -> None:
    """Refuse a build on a SQLite without FTS5, naming the cause."""
    if not has_fts5(connection):
        raise Fts5Unavailable(
            "this SQLite build has no FTS5, so the search index cannot be built "
            f"(SQLite {sqlite3.sqlite_version}). The index is a rebuildable cache: "
            "nothing is lost, but search cannot be served from it on this interpreter."
        )


#: How long a connection waits for another writer before deciding the index
#: cannot be read (D-159). Long enough to outlast a commit of a project-sized
#: index, short enough that a genuinely stuck writer is still reported rather
#: than hung on: the endpoints answer in milliseconds, and a reader that waits
#: five seconds has learned something real about the store.
BUSY_TIMEOUT_MS = 5000


def connect(
    path: Path, *, create: bool = True, multithreaded: bool = False
) -> sqlite3.Connection:
    """Open the index at *path* with the settings the whole package assumes.

    ``create=False`` refuses to bring a database into existence, which is how a
    reader distinguishes "no index yet" from "an index I just made empty".

    ``multithreaded=True`` lifts ``sqlite3``'s same-thread check. It exists for
    one caller — :class:`~x2knwldg.index.repository.SqliteRepository`, which a
    web server reaches from a thread pool — and it is **not** a claim that the
    connection is safe to share. The driver's check is the only thing stopping
    two threads from interleaving on one connection, so whoever lifts it takes
    on serialising access; ``SqliteRepository`` does that with a lock around
    every one of its ten methods. A writer must leave this alone: builds are
    single-threaded, and a lifted check with no lock is a corrupt index waiting
    for a second thread.

    ``isolation_level`` is left at the classic default and transactions are
    explicit. ``Connection.autocommit`` would read better and arrived in Python
    3.12; ``requires-python`` is 3.10 and CI runs 3.10 as its floor, so it is
    not available. (For the same reason nothing here reads ``sqlite3.version``,
    which was *removed* in 3.14 — the interpreter in daily use on this project.)
    """
    path = Path(path)
    if not create and not path.exists():
        raise FileNotFoundError(f"no index at {path}")
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=not multithreaded)
    connection.row_factory = sqlite3.Row
    # Referential integrity is checked in Python against the same predicates the
    # seam uses, but the pragma costs nothing and closes the gap where a future
    # migration adds a real foreign key and nobody notices it is unenforced.
    connection.execute("PRAGMA foreign_keys = ON")
    # D-159. These two were missing, and their absence was visible on the one
    # endpoint that exists to be honest. In the classic rollback journal a
    # writer takes an exclusive lock over the whole database, so a reader
    # during a build gets `database is locked` — which `_index_state` maps to
    # `state='error'` with no counts, and `payload()` renders as
    # `sources: 0, artifacts: 0`. Two `x2knwldg ui` processes are enough:
    # the second one's startup `refresh_index` holds the lock at commit while
    # the first answers `/api/status`. WAL lets readers read the last committed
    # generation *while* a build writes, which is both faster and truthful —
    # the rows they see are a real, complete generation. The busy timeout is
    # the belt to that brace: a writer waiting on another writer waits rather
    # than immediately declaring the index broken.
    #
    # `journal_mode` is persistent in the file, so it is set once and inherited;
    # it is executed on every connect anyway because a fresh clone, a deleted
    # cache and a database created by an older version all reach this line.
    # `busy_timeout` is per connection and must be.
    #
    # D-159's own remedy could reproduce D-159's symptom. Converting a database
    # that is not already in WAL needs an exclusive lock on it, so this
    # statement raises `database is locked` whenever another connection holds a
    # write transaction — measured: `journal_mode=delete` on disk plus a writer
    # in `BEGIN IMMEDIATE` made `connect` raise, and `SqliteRepository.open`
    # answer `state: error, message: the index cannot be opened: database is
    # locked`. That is exactly the honest-endpoint failure WAL was introduced to
    # remove, arriving out of the line that introduces it. `busy_timeout` is no
    # help and is not a reordering away from being one: SQLite fails a
    # journal-mode transition immediately rather than waiting, measured at
    # 0.000s with the pragma set before it.
    #
    # So a failed conversion is *tolerated*. The mode is persistent, so the
    # next connect that meets an idle database converts it and every connect
    # after that inherits it; until then the classic rollback journal serves
    # reads correctly, only less concurrently. Reporting the index broken
    # because it could not be made faster would trade a performance property
    # for the one property this project will not trade.
    try:
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return connection


# --------------------------------------------------------------------------
# 3. Migrating
# --------------------------------------------------------------------------


def schema_version(connection: sqlite3.Connection) -> int:
    """The highest applied migration, or ``0`` for a database with none.

    ``0`` is the honest answer for a file that exists but has never been
    migrated, and it is distinguishable from ``1``: the frozen contract types
    ``index_version`` as ``integer | null`` with ``minimum: 0``.
    """
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if tables is None:
        return 0
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    version = row["version"] if row is not None else None
    return int(version) if version is not None else 0


def _refuse_half_migrated(connection: sqlite3.Connection, current: int) -> None:
    """Refuse a database whose tables exist and whose migrations do not.

    A version of this code that committed its DDL in autocommit could be
    killed after a ``CREATE TABLE`` and before the ``schema_migrations``
    insert. ``schema_version`` then reads ``0``, so every later run replays the
    migration and dies on ``table ... already exists`` — a raw
    ``OperationalError`` out of the middle of a scan — while ``status()``
    answers ``absent``, so the UI says "build the index" and building crashes.
    Deleting the cache directory was the only escape and nothing said so.

    The transaction in :func:`migrate` is what stops this arising; this is for
    the databases already on disk. The index is a rebuildable cache (ADR 0001
    invariant 3), so naming the escape is the whole fix.
    """
    existing = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    unrecorded = sorted(
        name
        for version, statements in MIGRATIONS
        if version > current
        for statement in statements
        if (name := _created_name(statement)) is not None and name in existing
    )
    if unrecorded:
        raise IndexCorrupt(
            "the index is half-migrated: it already holds "
            f"{', '.join(unrecorded)} while recording no applied migration, so it "
            f"cannot be built or read. Delete the {DATABASE_DIRNAME}/ cache "
            "directory and rebuild — it holds nothing that is not derivable from "
            "the canonical files."
        )


_CREATE_NAME = re.compile(
    r"^\s*CREATE\s+(?:VIRTUAL\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[\"'`\[]?(?P<name>\w+)",
    re.IGNORECASE,
)


def _created_name(statement: str) -> str | None:
    """The table or view a ``CREATE`` statement names, or ``None``.

    Indexes and triggers are deliberately not matched: a migration creates them
    with ``IF NOT EXISTS`` or after the table, so their presence is not the
    signal that a migration was interrupted.
    """
    match = _CREATE_NAME.match(statement)
    return match.group("name") if match else None


def migrate(connection: sqlite3.Connection) -> int:
    """Apply every migration this code knows and *path* has not had.

    Returns the version reached. Idempotent: running it twice applies nothing
    the second time, which is what makes it safe to call on every open.

    A database already **newer** than :data:`SCHEMA_VERSION` raises
    :class:`~x2knwldg.index.errors.SchemaTooNew` rather than being opened. A
    forward-only list can describe what version 4 did to 3; it cannot describe
    what 5 did, so proceeding would mean answering from a schema this code does
    not understand.
    """
    current = schema_version(connection)
    if current > SCHEMA_VERSION:
        raise SchemaTooNew(
            f"the index was written at schema version {current}, but this code knows "
            f"only up to {SCHEMA_VERSION}. Delete the cache directory and rebuild — "
            "it holds nothing that is not derivable from the canonical files."
        )
    if current == SCHEMA_VERSION:
        return current

    require_fts5(connection)
    _refuse_half_migrated(connection, current)
    applied_at = datetime.now(timezone.utc).isoformat()
    for version, statements in MIGRATIONS:
        if version <= current:
            continue
        # One transaction per migration, so a failure half way through leaves
        # the previous version intact rather than a partially-migrated schema.
        #
        # `BEGIN IMMEDIATE` explicitly, **not** `with connection:`. Python's
        # `sqlite3` at the classic `isolation_level` only auto-begins before
        # DML, and a migration is almost entirely DDL — so every `CREATE TABLE`
        # committed in autocommit and the context manager had no transaction to
        # roll back. Killing a scan mid-migration therefore left the tables in
        # place while `schema_migrations` stayed empty: `schema_version` reads
        # `0`, every later run replays migration 1, and the first `CREATE TABLE`
        # dies on `table ... already exists` — an index that reports itself
        # `absent`, so the UI says "build the index", and building crashes.
        # SQLite's DDL *is* transactional, so an explicit transaction makes the
        # comment above true.
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, applied_at),
            )
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
    return schema_version(connection)
