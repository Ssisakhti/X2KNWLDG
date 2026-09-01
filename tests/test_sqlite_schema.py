"""The SQLite schema and its migrations (``T-101``).

``tests/test_index_schemas.py`` is about ``schemas/v1/`` — the JSON Schema
record shapes — and is unrelated to this file despite the similar name. This one
asks what the *database* guarantees: that a migration is explicit and versioned
(canvas plan §9.4), that applying it twice changes nothing, that a database from
the future is refused rather than misread, and that the table shape cannot
quietly lose the two properties paging depends on.

Stdlib only, so these run in the zero-dependency CI job — which is the install
ADR 0001 invariant 5 is about, and the one this package must work on because
``sqlite3`` is the only thing it needs.

No canonical file is read or written anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from x2knwldg.index import (
    DATABASE_DIRNAME,
    DATABASE_FILENAME,
    MIGRATIONS,
    SCHEMA_VERSION,
    Fts5Unavailable,
    IndexCorrupt,
    SchemaTooNew,
    StoreError,
    connect,
    database_path,
    has_fts5,
    migrate,
    require_fts5,
    schema_version,
)
from x2knwldg.repository import RepositoryError
from x2knwldg.repository.base import ORDER_KEY_SEPARATOR

FAMILY_TABLES = ("sources", "artifacts", "entities", "relations")


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """A migrated index in its own throwaway root."""
    connection = connect(database_path(tmp_path))
    migrate(connection)
    return connection


def _ddl(connection: sqlite3.Connection, name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    assert row is not None, f"{name} does not exist"
    return row["sql"] or ""


# --------------------------------------------------------------------------
# 1. The migration ledger is a ledger
# --------------------------------------------------------------------------


def test_migrations_are_contiguous_and_ascending_from_one() -> None:
    versions = [version for version, _ in MIGRATIONS]
    assert versions == list(range(1, len(versions) + 1)), (
        "migration versions must start at 1 and leave no gap; a gap makes "
        "'the version on disk' ambiguous about which statements ran"
    )


def test_schema_version_is_derived_from_the_ledger_not_typed_twice() -> None:
    assert SCHEMA_VERSION == MIGRATIONS[-1][0]


def test_the_ledger_is_immutable() -> None:
    # A list would let a caller append at runtime, which is a schema that
    # differs between two processes reporting the same version.
    assert isinstance(MIGRATIONS, tuple)
    for _, statements in MIGRATIONS:
        assert isinstance(statements, tuple)
        assert statements, "a migration with no statements is a version that means nothing"


# --------------------------------------------------------------------------
# 2. Applying them
# --------------------------------------------------------------------------


def test_an_unmigrated_database_reports_version_zero(tmp_path: Path) -> None:
    connection = connect(database_path(tmp_path))
    # Zero, not None and not an exception: the frozen contract types
    # index_version as integer|null with minimum 0, and a file that exists but
    # has never been migrated is honestly at 0.
    assert schema_version(connection) == 0


def test_migrating_reaches_the_current_version(tmp_path: Path) -> None:
    connection = connect(database_path(tmp_path))
    assert migrate(connection) == SCHEMA_VERSION
    assert schema_version(connection) == SCHEMA_VERSION


def test_migrating_twice_applies_nothing_the_second_time(db: sqlite3.Connection) -> None:
    before = db.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert migrate(db) == SCHEMA_VERSION
    after = db.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert [tuple(row) for row in before] == [tuple(row) for row in after], (
        "migrate() is called on every open, so a second run must be a no-op "
        "rather than a second row claiming the same version"
    )


def test_every_migration_is_recorded_with_a_timestamp(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version").fetchall()
    assert [row["version"] for row in rows] == [version for version, _ in MIGRATIONS]
    for row in rows:
        # An offset is required by common.schema.json's isoTimestamp, and a
        # naive local timestamp is not a point in time.
        assert row["applied_at"].endswith("+00:00")


def test_a_database_from_the_future_is_refused_not_misread(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION + 1, "2026-01-01T00:00:00+00:00"),
    )
    db.commit()
    with pytest.raises(SchemaTooNew) as caught:
        migrate(db)
    # The message has to name the fix, because the fix is safe and non-obvious:
    # the index holds nothing that is not derivable from the canonical files.
    assert "rebuild" in str(caught.value)


# --------------------------------------------------------------------------
# 3. Opening
# --------------------------------------------------------------------------


def test_the_index_lives_in_the_cache_directory(tmp_path: Path) -> None:
    path = database_path(tmp_path)
    assert path.parent.name == DATABASE_DIRNAME
    assert path.name == DATABASE_FILENAME
    # Canvas plan §9.3 fixes this location and .gitignore already covers it, so
    # a build never dirties the working tree.
    assert path.relative_to(tmp_path).as_posix() == f"{DATABASE_DIRNAME}/{DATABASE_FILENAME}"


def test_opening_without_create_refuses_to_invent_an_index(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connect(database_path(tmp_path), create=False)
    # And it did not leave one behind as a side effect of refusing.
    assert not database_path(tmp_path).exists()


def test_opening_creates_the_cache_directory_but_nothing_else(tmp_path: Path) -> None:
    connect(database_path(tmp_path))
    assert [p.name for p in tmp_path.iterdir()] == [DATABASE_DIRNAME]


# --------------------------------------------------------------------------
# 4. FTS5 is required, and its absence is named
# --------------------------------------------------------------------------


def test_fts5_is_available_on_this_interpreter(db: sqlite3.Connection) -> None:
    # Not a tautology: if this fails, every search test below is meaningless,
    # and the failure should say so here rather than as a confusing error later.
    assert has_fts5(db) is True
    require_fts5(db)


def test_the_fts5_probe_leaves_no_table_behind(db: sqlite3.Connection) -> None:
    has_fts5(db)
    has_fts5(db)
    leftovers = [
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_temp_master WHERE type = 'table'")
    ]
    assert leftovers == [], "the probe must be repeatable, so it cleans up after itself"


def test_the_substring_index_is_declared_over_the_stored_text_once(db: sqlite3.Connection) -> None:
    ddl = _ddl(db, "documents_trigrams")
    assert "trigram" in ddl
    # External content: the searchable text is stored in `documents` and this is
    # an index over it, not a second copy of it.
    assert "content='documents'" in ddl
    assert "content_rowid='rowid'" in ddl


def test_the_token_index_is_a_plain_table_not_an_fts5_tokenizer(db: sqlite3.Connection) -> None:
    # The overlap disjunct is served by query._tokens' own output stored as
    # rows. An FTS5 tokenizer cannot stand in for it -- see the next test.
    ddl = " ".join(_ddl(db, "document_tokens").split())
    assert "PRIMARY KEY (token, document_id)" in ddl
    assert "VIRTUAL" not in ddl
    names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master")}
    assert "documents_tokens" not in names, (
        "a unicode61 FTS5 index was removed on purpose: it is not query._tokens"
    )


def test_no_fts5_tokenizer_reproduces_the_scorers_token_set() -> None:
    """The measurement that chose a plain token table over ``unicode61``.

    This is the defect the schema shape exists to avoid, pinned so nobody
    "simplifies" the token table back into an FTS5 index.
    """
    from x2knwldg import query

    document, needle = "\u6a5f\u68b0\u5b66\u7fd2\u306e\u30e2\u30c7\u30eb", "\u6a5f\u7fd2"
    scored = query.SearchDocument.of({"type": "knowledge_unit"}, document)
    folded = query._fold(needle)
    # The scorer finds it: both characters are tokens of the document.
    assert scored.score(folded, query._tokens(needle)) > 0

    probe = sqlite3.connect(":memory:")
    probe.execute("CREATE VIRTUAL TABLE tok USING fts5(body, tokenize='unicode61')")
    probe.execute("CREATE VIRTUAL TABLE tri USING fts5(body, tokenize='trigram')")
    probe.execute("INSERT INTO tok(rowid, body) VALUES (1, ?)", (query._fold(document),))
    probe.execute("INSERT INTO tri(rowid, body) VALUES (1, ?)", (query._fold(document),))
    matched = probe.execute(
        "SELECT count(*) FROM tok WHERE tok MATCH ?", ('"' + folded + '"',)
    ).fetchone()[0]
    globbed = probe.execute(
        "SELECT count(*) FROM tri WHERE body GLOB ?", ("*" + folded + "*",)
    ).fetchone()[0]
    # Neither finds it: the two characters are not adjacent, so there is no
    # substring, and unicode61 does not split the CJK run into characters.
    assert matched == 0
    assert globbed == 0


def test_the_substring_path_uses_glob_because_like_treats_the_query_as_a_pattern(
    db: sqlite3.Connection,
) -> None:
    rows = [
        (1, "s", "knowledge_unit", "{}", "growth was 100 percent", 1.0, 0),
        (2, "s", "knowledge_unit", "{}", "growth was 100%", 1.0, 1),
    ]
    db.executemany("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    db.executemany(
        "INSERT INTO documents_trigrams (rowid, folded) VALUES (?, ?)",
        [(row[0], row[4]) for row in rows],
    )
    liked = {
        r["rowid"]
        for r in db.execute("SELECT rowid FROM documents_trigrams WHERE folded LIKE ?", ("%100%%",))
    }
    globbed = {
        r["rowid"]
        for r in db.execute("SELECT rowid FROM documents_trigrams WHERE folded GLOB ?", ("*100%*",))
    }
    # A user searching for "100%" means the literal string. LIKE reads the `%`
    # as a wildcard and invents a hit; GLOB does not.
    assert liked == {1, 2}
    assert globbed == {2}


# --------------------------------------------------------------------------
# 5. The two properties paging depends on
# --------------------------------------------------------------------------


@pytest.mark.parametrize("table", FAMILY_TABLES)
def test_every_family_keys_on_identity(table: str, db: sqlite3.Connection) -> None:
    ddl = _ddl(db, table)
    assert "identity TEXT NOT NULL PRIMARY KEY" in " ".join(ddl.split())
    # The UNIQUE guarantee the seam's README asks for. Without it the order is
    # not total, and a tie across a page boundary drops a record from the paged
    # output while `total` keeps counting it.
    db.execute(
        f"INSERT INTO {table} (identity, digest, doc) VALUES ('x', 'd', '{{}}')"
        if table != "relations"
        else f"INSERT INTO {table} (identity, digest, doc, from_id, to_id) "
        "VALUES ('x', 'd', '{}', 'a', 'b')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            f"INSERT INTO {table} (identity, digest, doc) VALUES ('x', 'other', '{{}}')"
            if table != "relations"
            else f"INSERT INTO {table} (identity, digest, doc, from_id, to_id) "
            "VALUES ('x', 'other', '{}', 'a', 'b')"
        )


@pytest.mark.parametrize("table", FAMILY_TABLES)
def test_the_order_key_is_two_columns_so_no_nul_reaches_sqlite(
    table: str, db: sqlite3.Connection
) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    assert {"identity", "digest"} <= columns
    assert "order_key" not in columns, (
        "repository.order_key joins identity and digest with a NUL byte. Storing "
        "the joined form would put a NUL in a TEXT column; page_from_window "
        "rebuilds the token from the record, so it is never needed."
    )
    assert ORDER_KEY_SEPARATOR == "\x00"


def test_records_are_stored_verbatim_rather_than_normalised(db: sqlite3.Connection) -> None:
    # ADR 0002 invariant 2: the repository never supplies a value the canonical
    # files do not carry. A sparse record must survive a round trip with its
    # absences intact -- not filled in, not zeroed.
    import json

    sparse = {"schema_version": "1.0", "id": "youtube:x", "counts": {}}
    db.execute(
        "INSERT INTO sources (identity, digest, doc) VALUES (?, ?, ?)",
        ("youtube:x", "d", json.dumps(sparse)),
    )
    stored = db.execute("SELECT doc FROM sources WHERE identity = 'youtube:x'").fetchone()["doc"]
    assert json.loads(stored) == sparse


def test_the_state_table_holds_exactly_one_row(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO index_state (id, state) VALUES (1, 'building')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO index_state (id, state) VALUES (2, 'ready')")


# --------------------------------------------------------------------------
# 6. The errors stay inside the frozen taxonomy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("error", [StoreError, Fts5Unavailable, SchemaTooNew, IndexCorrupt])
def test_store_errors_carry_the_seams_codes_rather_than_inventing_one(error: type) -> None:
    assert issubclass(error, RepositoryError)
    # D-030 and D-044 fixed the code vocabulary in a ledger under docs/, which
    # no track agent owns. Inheriting means Track B routes on a code it already
    # has a branch for.
    assert error.code == "internal"
    assert error.http_status == 500
