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

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .errors import Fts5Unavailable, SchemaTooNew

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

#: ``(version, statements)`` in ascending order. The tuple is the ledger.
MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = ((1, _MIGRATION_1),)

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
    applied_at = datetime.now(timezone.utc).isoformat()
    for version, statements in MIGRATIONS:
        if version <= current:
            continue
        # One transaction per migration, so a failure half way through leaves
        # the previous version intact rather than a partially-migrated schema.
        with connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, applied_at),
            )
    return schema_version(connection)
