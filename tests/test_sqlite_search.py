"""FTS5 candidate retrieval (``T-103``) — and the one thing it must never change.

``x2knwldg.index.search`` exists to make search fast. Every test here exists to
prove it did not also make search *different*. The load-bearing one is
:func:`test_the_ranked_hit_list_is_the_one_query_py_produces`: for the same
corpus and the same query, retrieval-plus-``rank_documents`` must return the
identical list of hit dicts, in the identical order, that ranking the whole
corpus returns. It runs over every query below, and the list is chosen to hold
every way the two could have come apart:

* **Substring-only matches.** ``SearchDocument.score``'s phrase bonus is a raw
  substring test, so ``model`` scores a document that only says ``models``. A
  token index alone returns 10 hits for ``model`` on the real sample where the
  truth is 19.
* **Scriptless writing.** ``query._tokens`` expands a CJK run into single
  characters and adjacent bigrams, so ``機習`` scores ``機械学習のモデル`` — while
  no substring of it contains ``機習`` and no FTS5 ``unicode61`` token equals
  ``機``. That hit is retrievable only from a token table holding ``_tokens``'s
  own output.
* **Pattern metacharacters in the query.** A user may type ``100%``, ``a_b``,
  ``*`` or ``[``. Under ``LIKE`` the first two are wildcards — ``100%`` would
  match "100 percent" — so the retrieval uses ``GLOB`` and escapes it.
* **FTS5 operators in the query.** ``"``, ``-foo``, ``NEAR(x y)``, ``col:val``
  and a bare ``AND`` are all valid things to search *for*. None of them reaches
  a ``MATCH`` expression here, and a malformed-query crash reaching the API as a
  500 would be a defect.

Two corpora, so nothing is proved only against text that happens to be tame:
the three committed fixture runs, and a synthetic run holding the CJK, the
wildcards, and a NUL. Both are copied into ``tmp_path`` first — no test here
writes to ``tests/fixtures/`` or to ``output/``.

Stdlib only, so these run in the zero-dependency CI job.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from x2knwldg.index import (
    SqliteRepository,
    build_index,
    connect,
    database_path,
    migrate,
    refresh_index,
)
from x2knwldg.index.errors import StoreError
from x2knwldg.index.search import (
    HIT_TYPES,
    TRANSCRIPT_CAPTION_HIT,
    as_api_hit,
    clear_source_documents,
    document_indexer,
    index_documents,
    search_candidates,
    search_retrieval,
    unreadable_sources,
)
from x2knwldg.query import rank_documents, run_documents
from x2knwldg.repository import SearchQuery
from x2knwldg.repository.memory import MemoryRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
FIXTURE_NAMES = ("pass-run", "partial-run", "fail-run")
SAMPLE_ID = "pqlWNihgdjI"
SAMPLE_DIR = PROJECT_ROOT / "output" / SAMPLE_ID

requires_sample = pytest.mark.skipif(
    not (SAMPLE_DIR / "metadata.json").exists(),
    reason="output/ is gitignored; the real sample is present only on a machine that ingested it",
)

#: The measured hit counts for the real sample, read off ``MemoryRepository`` —
#: the cache-free oracle. A token-only index returns 3, 10 and 162.
#: `the` is 258 rather than 253 because `derivation_note` joined the
#: searchable field set under D-047; `learning` and `model` are unmoved.
SAMPLE_TOTALS = {"learning": 4, "model": 19, "the": 258}

#: The text of the synthetic run. Every line is here to fail a specific wrong
#: implementation, and the comment says which.
SYNTHETIC_TEXTS = (
    "機械学習のモデルについて",       # `機習` scores this; no substring holds it
    "growth was 100 percent",         # LIKE '%100%%' would match this. GLOB must not
    "growth was 100% exactly",        # ... and this is the only honest `100%` hit
    "axb here",                       # LIKE '%a_b%' would match this
    "a_b here",                       # ... and this is the only honest `a_b` hit
    "a star * and a ? and a [set]",   # GLOB metacharacters in the *document*
    "the models of modeling",         # substring-only matches for `model`
    "before" + chr(0) + "after",      # GLOB cannot see past a NUL (see the module)
    "Ｍｏｄｅｌ and café and İstanbul",  # NFKC folding on both sides
)

#: Every query the parity test runs. Grouped by what each group would break.
QUERIES = (
    # Ordinary words, and words that only appear inside longer ones.
    "knowledge",
    "evidence",
    "coverage",
    "model",
    "the",
    "odel",
    "overag",
    "fter",
    # Multi-word, where the phrase bonus and the token overlap disagree.
    "knowledge unit",
    "audited window by window",
    "evidence it rests on",
    "unit evidence coverage",
    # Single characters, which `_tokens` deliberately keeps.
    "a",
    "e",
    "0",
    "機",
    # Scriptless writing: whole run, bigram, non-adjacent pair, spaced.
    "機械学習",
    "機械",
    "機習",
    "学習 機械",
    "モデル",
    # Normalisation, on both sides.
    "THE",
    "Ｍｏｄｅｌ",
    "café",
    "İstanbul",
    # Pattern metacharacters a user may legally type.
    "100%",
    "a_b",
    "0% p",
    "100% exactly",
    "%",
    "_",
    "*",
    "?",
    "[",
    "]",
    "[set]",
    "a*b",
    "\\",
    # FTS5 operators, all of which are things to search for and not with.
    '"',
    '""',
    '"quoted"',
    "a OR b",
    "a AND b",
    "NOT a",
    "NEAR(x y)",
    "-foo",
    "col:val",
    "^start",
    "(",
    ")",
    "a*",
    # Nothing, and everything: `MAX_QUERY_LENGTH` is 512.
    " ",
    ".",
    "x" * 512,
    ("the " * 128)[:512],
    "zzzzzzzz-no-such-text",
)


# --------------------------------------------------------------------------
# Corpora
# --------------------------------------------------------------------------


def _copy_fixture_runs(root: Path) -> Path:
    """The three committed runs, copied into *root*. The originals are never touched."""
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    for name in FIXTURE_NAMES:
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    return output


def _write_synthetic_run(output: Path, video_id: str = "synthetic") -> Path:
    """A canonical run holding exactly the text the pinned cases need.

    Written rather than copied because no committed fixture contains CJK, a
    GLOB metacharacter or a NUL — and a parity test over tame text proves the
    tame half only. The shape is what ``query.run_documents`` reads: a
    ``metadata.json``, a ``knowledge_units.json``, and a ``transcript.json``
    whose captions all carry a timing, because a caption without one is refused
    (and that refusal is tested separately).
    """
    run_dir = output / video_id
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(
        json.dumps({"video_id": video_id, "title": "Synthetic"}), encoding="utf-8"
    )
    (run_dir / "knowledge_units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "id": f"KU-{index:06d}",
                        "kind": "claim",
                        "source_class": "source",
                        "content": text,
                        "confidence": 0.9,
                        "source": {
                            "segment_id": f"SEG-{index:06d}",
                            "start_sec": float(index),
                            "evidence_excerpt": text,
                        },
                    }
                    for index, text in enumerate(SYNTHETIC_TEXTS)
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "transcript.json").write_text(
        json.dumps(
            {
                "captions": [
                    {
                        "segment_id": f"cap_{index:06d}",
                        "text": text,
                        "start_sec": float(index),
                        "end_sec": float(index) + 1.0,
                    }
                    for index, text in enumerate(SYNTHETIC_TEXTS)
                ]
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _fresh_index(root: Path) -> sqlite3.Connection:
    connection = connect(database_path(root))
    migrate(connection)
    return connection


def _source_row(connection: sqlite3.Connection, source_id: str) -> None:
    """A minimal ``sources`` row, so scope resolution can find the source.

    Scope resolves against ``sources`` and not against ``documents``, because a
    source with nothing searchable in it is a different answer from a source the
    index does not hold. These tests index documents without running a scan, so
    the row is written directly.
    """
    connection.execute(
        "INSERT OR REPLACE INTO sources (identity, digest, doc) VALUES (?, 'd', '{}')",
        (source_id,),
    )


@pytest.fixture
def corpus(tmp_path: Path) -> dict[str, Any]:
    """The four runs, indexed with their raw ``query.run_documents`` hits.

    Raw on purpose: this fixture is for parity against ``query.py`` itself, so
    nothing here adds D-028's two API fields. The repository path — which does
    add them — is tested against ``MemoryRepository`` further down.
    """
    output = _copy_fixture_runs(tmp_path)
    _write_synthetic_run(output)
    connection = _fresh_index(tmp_path)
    documents = []
    for name in sorted([*FIXTURE_NAMES, "synthetic"]):
        source_id = f"youtube:{name}"
        _source_row(connection, source_id)
        found = run_documents(output / name)
        index_documents(connection, source_id, found)
        documents.extend(found)
    connection.commit()
    return {"connection": connection, "documents": documents, "output": output}


@pytest.fixture
def fixture_project(tmp_path: Path) -> Path:
    """A project root holding copies of the three committed runs."""
    _copy_fixture_runs(tmp_path)
    return tmp_path


def _retrieved(corpus: Mapping[str, Any], q: str) -> list[Mapping[str, Any]]:
    found = search_candidates(corpus["connection"], q)
    return rank_documents(found.documents, q)


def _all_pages(
    repo: Any, q: str, **kwargs: Any
) -> tuple[list[dict[str, Any]], int | None]:
    """Every hit *repo* returns for *q*, walked page by page. Also the total."""
    hits: list[dict[str, Any]] = []
    cursor: str | None = None
    total: int | None = None
    while True:
        page = repo.search(SearchQuery(q=q, limit=13, cursor=cursor, **kwargs))
        hits.extend(page.items)
        total = page.total
        cursor = page.next_cursor
        if cursor is None:
            return hits, total


# --------------------------------------------------------------------------
# 1. The parity that T-104 depends on
# --------------------------------------------------------------------------


@pytest.mark.parametrize("q", QUERIES)
def test_the_ranked_hit_list_is_the_one_query_py_produces(
    corpus: dict[str, Any], q: str
) -> None:
    """Retrieval narrows the corpus. It must not change the answer.

    Same hits, same order, same dicts, as ranking every document in the library.
    This is the whole contract of the module: FTS5 is candidate retrieval and
    ``query.rank_documents`` is ranking, so an index that changed a single
    position would be a wrong answer served faster.
    """
    assert _retrieved(corpus, q) == rank_documents(corpus["documents"], q)


@pytest.mark.parametrize("q", QUERIES)
def test_no_query_a_user_may_type_can_raise(corpus: dict[str, Any], q: str) -> None:
    """An FTS5 operator or a GLOB metacharacter is text, not syntax.

    Separate from the parity test above even though it would catch the same
    exception, because the two failures mean different things: a crash here
    reaches the API as a 500 for a request that was perfectly well formed.
    """
    found = search_candidates(corpus["connection"], q)
    assert isinstance(found.documents, tuple)


def test_a_query_of_the_maximum_length_is_answered(corpus: dict[str, Any]) -> None:
    """``MAX_QUERY_LENGTH`` characters of CJK expand past SQLite's parameter cap.

    ``_tokens`` turns a 512-character scriptless run into over a thousand tokens,
    and ``SQLITE_LIMIT_VARIABLE_NUMBER`` is 999 on builds still in support — which
    is why the query's tokens are bound through a TEMP table rather than an
    ``IN (?, ?, ?, …)`` list.
    """
    q = "機械学習" * 128
    assert len(q) == 512
    assert _retrieved(corpus, q) == rank_documents(corpus["documents"], q)


# --------------------------------------------------------------------------
# 2. The three recall holes a plausible implementation has
# --------------------------------------------------------------------------


def test_a_token_index_alone_would_miss_the_substring_matches(
    corpus: dict[str, Any]
) -> None:
    """``model`` must find ``models`` — the phrase bonus is a raw substring test."""
    hits = _retrieved(corpus, "model")
    contents = [hit.get("content") for hit in hits]
    assert "the models of modeling" in contents
    assert "機械学習のモデルについて" not in contents


def test_non_adjacent_scriptless_characters_still_score(corpus: dict[str, Any]) -> None:
    """The ``機習`` case: token overlap with no substring anywhere.

    ``機`` and ``習`` are both tokens of ``機械学習のモデルについて`` because
    ``_tokens`` splits a scriptless run per character, so the scorer returns a
    non-zero score. No substring of the document contains ``機習``, and FTS5's
    ``unicode61`` takes the whole run as one token, so neither a trigram scan
    nor a token *tokenizer* can retrieve it — only a table holding ``_tokens``'s
    own output.
    """
    hits = _retrieved(corpus, "機習")
    assert [hit.get("content") for hit in hits] == [
        "機械学習のモデルについて",
        "機械学習のモデルについて",
    ]
    assert hits == rank_documents(corpus["documents"], "機習")


def test_a_scriptless_needle_under_three_characters_is_still_found(
    corpus: dict[str, Any]
) -> None:
    """Trigram ``MATCH`` returns zero rows for a needle this short. GLOB does not."""
    for q in ("機", "機械", "モデル"):
        assert _retrieved(corpus, q), f"{q!r} found nothing"


def test_a_document_holding_a_nul_is_still_found_by_a_substring(
    corpus: dict[str, Any]
) -> None:
    """GLOB compares NUL-terminated strings, so the index cannot see past one.

    ``fter`` is not a token of anything; the only way to score
    ``"before\\x00after"`` is the substring disjunct, and in SQL that disjunct is
    blind to everything after the NUL. The document is marked at index time so
    every search treats it as a candidate and the Python rescore decides.
    """
    hits = _retrieved(corpus, "fter")
    assert any(hit.get("content", "").startswith("before") for hit in hits)
    assert hits == rank_documents(corpus["documents"], "fter")


# --------------------------------------------------------------------------
# 3. GLOB metacharacters in the query are neutralised
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q,wildcard_victim",
    [
        # `%` spans "0 percent"; the only literal "0% p" is nowhere in the corpus.
        ("0% p", "growth was 100 percent"),
        # `_` spans the "x"; the only literal "a_b" is in its own document.
        ("a_b", "axb here"),
    ],
)
def test_a_like_wildcard_in_the_query_matches_nothing_it_should_not(
    corpus: dict[str, Any], q: str, wildcard_victim: str
) -> None:
    """The measured LIKE defect, and the proof it is a defect rather than a worry.

    Each query below has **no** token in common with its victim document, so the
    only way it could score is the substring disjunct — and the substring is not
    there. The test first shows that ``LIKE`` really would have matched it, by
    running that comparison against the stored text, and then asserts that the
    victim is not among the hits. Without the ``GLOB`` switch the second
    assertion fails and a user searching for ``0% p`` is handed a document about
    100 percent.
    """
    connection = corpus["connection"]
    fooled = [
        row["folded"]
        for row in connection.execute(
            "SELECT folded FROM documents WHERE folded LIKE ?", (f"%{q}%",)
        )
    ]
    assert any(wildcard_victim in folded for folded in fooled), "LIKE was not fooled"
    contents = [hit.get("content") for hit in _retrieved(corpus, q)]
    assert wildcard_victim not in contents


def test_a_pattern_character_still_finds_its_literal_self(
    corpus: dict[str, Any]
) -> None:
    """Escaped, not stripped: ``100%`` and ``a_b`` are searchable strings."""
    assert "growth was 100% exactly" in [
        hit.get("content") for hit in _retrieved(corpus, "100% exactly")
    ]
    assert "a_b here" in [hit.get("content") for hit in _retrieved(corpus, "a_b")]


@pytest.mark.parametrize("q", ["*", "?", "[", "[set]", "a*b"])
def test_a_glob_metacharacter_matches_itself(corpus: dict[str, Any], q: str) -> None:
    """A pattern character in the query is escaped, so it cannot match everything."""
    hits = _retrieved(corpus, q)
    assert hits == rank_documents(corpus["documents"], q)
    assert len(hits) < len(corpus["documents"]), f"{q!r} matched the whole corpus"


# --------------------------------------------------------------------------
# 4. What retrieval rebuilds, and what it must not invent
# --------------------------------------------------------------------------


def test_a_rebuilt_document_is_the_one_run_documents_produced(
    corpus: dict[str, Any]
) -> None:
    """Hit, folded text, tokens and weight all come back off the row.

    Nothing is recomputed — ``_fold`` is not idempotent for every string, so
    re-deriving tokens from the stored ``folded`` column would be a different
    set — and the NUL marker this module writes is not leaked back as a token.
    """
    found = search_candidates(corpus["connection"], "the")
    # Keyed on the whole hit, not on the folded text: the three fixture runs say
    # the same sentences and differ only by `video_id`.
    def key(hit: Mapping[str, Any]) -> str:
        return json.dumps(dict(hit), sort_keys=True, ensure_ascii=False)

    originals = {key(document.hit): document for document in corpus["documents"]}
    assert len(originals) == len(corpus["documents"])
    assert found.documents
    for document in found.documents:
        original = originals[key(document.hit)]
        assert document.tokens == original.tokens
        assert document.weight == original.weight
        assert document.folded == original.folded


def test_a_caption_match_is_worth_half_a_unit_match(corpus: dict[str, Any]) -> None:
    """``CAPTION_WEIGHT`` survives the round trip, so a unit still outranks a caption."""
    hits = _retrieved(corpus, "evidence it rests on")
    assert hits[0]["type"] == "knowledge_unit"
    assert any(hit["type"] == TRANSCRIPT_CAPTION_HIT for hit in hits)


def test_a_unit_with_no_timing_gets_neither_a_timing_nor_a_link(
    tmp_path: Path
) -> None:
    """Absent, not zero — and the index stores the hit whole, so it stays absent."""
    output = tmp_path / "output"
    output.mkdir()
    run_dir = output / "vid"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"video_id": "vid", "title": "t"}), encoding="utf-8"
    )
    (run_dir / "knowledge_units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "id": "KU-000001",
                        "kind": "claim",
                        "source_class": "source",
                        "content": "a claim with no timing at all",
                        "confidence": 0.5,
                        "source": {"segment_id": "SEG-000001"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    connection = _fresh_index(tmp_path)
    _source_row(connection, "youtube:vid")
    index_documents(connection, "youtube:vid", run_documents(run_dir))
    connection.commit()

    hits = _retrieved({"connection": connection}, "timing")
    assert len(hits) == 1
    assert "start_sec" not in hits[0]
    assert "source_url" not in hits[0]


def test_a_third_hit_shape_is_refused_rather_than_stored(tmp_path: Path) -> None:
    """D-028 freezes two shapes; a third is an ``openapi.json`` change first."""
    from x2knwldg.query import SearchDocument

    connection = _fresh_index(tmp_path)
    document = SearchDocument.of({"type": "transcript_segment", "id": "x"}, "text")
    with pytest.raises(StoreError) as excinfo:
        index_documents(connection, "youtube:x", [document])
    assert "transcript_segment" in str(excinfo.value)
    for name in HIT_TYPES:
        assert name in str(excinfo.value)
    assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


# --------------------------------------------------------------------------
# 5. Ordering, and the tie that ordinal breaks
# --------------------------------------------------------------------------


def test_ties_keep_canonical_file_order_across_sources(corpus: dict[str, Any]) -> None:
    """``rank_documents`` sorts stably, so feed order is the tiebreak.

    Fed back in ``(source_id, ordinal)`` order and not by rowid: a full rebuild
    happens to assign rowids that way, but an incremental re-index of one source
    appends at the end of the table, so rowid order would silently diverge
    between a rebuild and a refresh.
    """
    found = search_candidates(corpus["connection"], "evidence")
    order = [document.hit.get("video_id") for document in found.documents]
    assert order == sorted(order), order


def test_re_indexing_one_source_does_not_change_the_order(
    corpus: dict[str, Any]
) -> None:
    """The rowid order of a re-indexed source diverges. The reported order must not."""
    connection = corpus["connection"]
    before = _retrieved(corpus, "evidence")
    first = min(
        row["source_id"]
        for row in connection.execute("SELECT DISTINCT source_id FROM documents")
    )
    name = first.split(":", 1)[1]
    index_documents(connection, first, run_documents(corpus["output"] / name))
    connection.commit()
    assert _retrieved(corpus, "evidence") == before


# --------------------------------------------------------------------------
# 6. Re-indexing is idempotent
# --------------------------------------------------------------------------


def _counts(connection: sqlite3.Connection) -> tuple[int, int, int]:
    return (
        connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM document_tokens").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM documents_trigrams").fetchone()[0],
    )


def test_indexing_the_same_source_twice_leaves_one_corpus(
    corpus: dict[str, Any]
) -> None:
    """A doubled corpus doubles ``total`` and returns every hit twice."""
    connection = corpus["connection"]
    before = _counts(connection)
    hits = _retrieved(corpus, "the")
    for name in sorted([*FIXTURE_NAMES, "synthetic"]):
        index_documents(
            connection, f"youtube:{name}", run_documents(corpus["output"] / name)
        )
    connection.commit()
    assert _counts(connection) == before
    assert _retrieved(corpus, "the") == hits


def test_clearing_a_source_retires_its_rows_from_the_external_index(
    corpus: dict[str, Any]
) -> None:
    """``documents_trigrams`` never sees a ``DELETE`` on its content table.

    Its rows have to be retired explicitly with the *old* text. If they are not,
    the index goes on describing text the table no longer holds, and the next
    substring query does not mislead — it *raises*: ``fts5: missing row 1 from
    content table``, an ``sqlite3.DatabaseError`` reaching the API as a 500 on a
    perfectly good request.
    """
    connection = corpus["connection"]
    removed = clear_source_documents(connection, "youtube:synthetic")
    connection.commit()
    assert removed > 0
    assert not _retrieved(corpus, "機習")
    assert all(
        row["source_id"] != "youtube:synthetic"
        for row in connection.execute("SELECT DISTINCT source_id FROM documents")
    )
    # The index itself, probed directly rather than through retrieval: a row
    # left behind is still in it, and `MATCH` reads the index without consulting
    # the content table, so it is what shows the leftover. (FTS5's own
    # `integrity-check` does not: measured, it passes over an orphan on an
    # external-content table.)
    assert not connection.execute(
        "SELECT rowid FROM documents_trigrams WHERE documents_trigrams MATCH ?",
        ('"exactly"',),
    ).fetchall()


# --------------------------------------------------------------------------
# 7. Scope, and the two ways a count can be wrong
# --------------------------------------------------------------------------


def test_one_source_can_be_searched_alone(corpus: dict[str, Any]) -> None:
    found = search_candidates(corpus["connection"], "the", source_ids=["youtube:pass-run"])
    assert found.documents
    assert {document.hit.get("video_id") for document in found.documents} == {
        "fixture-pass"
    }
    assert found.complete


def test_a_source_id_naming_no_indexed_source_is_a_fact_not_an_unknown(
    corpus: dict[str, Any]
) -> None:
    """Empty, with a complete count. Zero here is an answer, not a missing one."""
    found = search_candidates(
        corpus["connection"], "the", source_ids=["youtube:no-such-source"]
    )
    assert found.documents == ()
    assert found.unknown == ("youtube:no-such-source",)
    assert found.complete is True


def test_an_unreadable_source_makes_the_count_unknown_and_never_zero(
    corpus: dict[str, Any]
) -> None:
    """ADR 0004 invariant 6: hits for a source that cannot be read are unknown."""
    found = search_candidates(
        corpus["connection"], "the", unreadable=["youtube:pass-run"]
    )
    assert found.unreadable == ("youtube:pass-run",)
    assert found.complete is False
    assert not any(
        document.hit.get("video_id") == "fixture-pass" for document in found.documents
    )


def test_dropping_the_transcript_drops_only_the_caption_hits(
    corpus: dict[str, Any]
) -> None:
    found = search_candidates(corpus["connection"], "the", include_transcript=False)
    assert found.documents
    assert not any(
        document.hit.get("type") == TRANSCRIPT_CAPTION_HIT
        for document in found.documents
    )
    assert rank_documents(found.documents, "the") == rank_documents(
        [
            document
            for document in corpus["documents"]
            if document.hit.get("type") != TRANSCRIPT_CAPTION_HIT
        ],
        "the",
    )


def test_unreadable_sources_reads_both_tiers_of_damage(tmp_path: Path) -> None:
    """A skipped run, and a run indexed with a search-shaped gap."""
    connection = _fresh_index(tmp_path)
    connection.executemany(
        "INSERT INTO runs (canonical_dir, source_id, digest, scanned_at, problems, "
        "skipped_reason) VALUES (?, ?, 'd', 'now', ?, ?)",
        [
            ("output/a", "youtube:a", "[]", "could not be adapted"),
            ("output/b", "youtube:b", json.dumps(["search: unparseable"]), None),
            ("output/c", "youtube:c", json.dumps(["hash: unreadable file"]), None),
            ("output/d", None, "[]", None),
        ],
    )
    connection.commit()
    assert unreadable_sources(connection) == frozenset({"youtube:a", "youtube:b"})


def test_recording_a_search_gap_keeps_the_problems_the_scan_recorded(
    tmp_path: Path
) -> None:
    """``runs.problems`` is shared. This module adds and removes only its own.

    A pass that cleared the column would delete the scan's own findings — an
    unhashable file, an adapter's named gap — and those are what
    ``ScanReport.incomplete_runs`` reports to the user. A pass that never
    cleared its *own* entry would leave a healed source reported as unknown for
    ever, so both directions are asserted.
    """
    output = _copy_fixture_runs(tmp_path)
    connection = _fresh_index(tmp_path)
    connection.execute(
        "INSERT INTO runs (canonical_dir, source_id, digest, scanned_at, problems) "
        "VALUES ('output/pass-run', 'youtube:pass-run', 'd', 'now', ?)",
        (json.dumps(["hash: raw/audio.m4a: cannot be read to hash it"]),),
    )
    _source_row(connection, "youtube:pass-run")
    indexer = document_indexer(tmp_path)

    class _Records:
        def __init__(self, canonical_dir: str) -> None:
            self.sources = [
                {"id": "youtube:pass-run", "canonical_dir": canonical_dir}
            ]

    def problems() -> list[str]:
        return json.loads(
            connection.execute(
                "SELECT problems FROM runs WHERE source_id = 'youtube:pass-run'"
            ).fetchone()["problems"]
        )

    # A directory outside the project: unsearchable, and the scan's finding stays.
    indexer(connection, _Records("../elsewhere"))
    assert [p.split(":")[0] for p in problems()] == ["hash", "search"]

    # Readable again: this module's entry goes, and only this module's.
    assert (output / "pass-run").is_dir()
    indexer(connection, _Records("output/pass-run"))
    assert [p.split(":")[0] for p in problems()] == ["hash"]
    assert unreadable_sources(connection) == frozenset()


# --------------------------------------------------------------------------
# 8. The read path leaves the connection as it found it
# --------------------------------------------------------------------------


def test_a_search_leaves_no_transaction_open(corpus: dict[str, Any]) -> None:
    """A read path holding a transaction open holds a lock the build waits on."""
    connection = corpus["connection"]
    assert not connection.in_transaction
    search_candidates(connection, "the")
    assert not connection.in_transaction


def test_a_search_inside_a_build_does_not_undo_the_build(tmp_path: Path) -> None:
    """Only a transaction the search itself started is rolled back."""
    output = _copy_fixture_runs(tmp_path)
    connection = _fresh_index(tmp_path)
    _source_row(connection, "youtube:pass-run")
    index_documents(
        connection, "youtube:pass-run", run_documents(output / "pass-run")
    )
    assert connection.in_transaction
    assert search_candidates(connection, "evidence").documents
    assert connection.in_transaction
    connection.commit()
    assert search_candidates(connection, "evidence").documents


# --------------------------------------------------------------------------
# 9. The write hook: whole projects, and the runs that leave them
# --------------------------------------------------------------------------


def test_the_hook_indexes_every_source_a_scan_committed(fixture_project: Path) -> None:
    report = build_index(fixture_project, index_documents=document_indexer(fixture_project))
    assert report.runs_indexed == len(FIXTURE_NAMES)
    connection = connect(database_path(fixture_project), create=False)
    assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 15
    assert {
        row["source_id"]
        for row in connection.execute("SELECT DISTINCT source_id FROM documents")
    } == {"youtube:fixture-pass", "youtube:fixture-partial", "youtube:fixture-fail"}


def test_a_removed_run_stops_contributing_hits(fixture_project: Path) -> None:
    """The scanner never touches ``documents``, so the hook must prune them itself.

    Without this a deleted run's hits go on being returned for ever, with
    ``total`` counting them — the index asserting evidence the canonical files no
    longer hold, which is the one thing a rebuildable cache may not do.
    """
    indexer = document_indexer(fixture_project)
    build_index(fixture_project, index_documents=indexer)
    repo = SqliteRepository.open(fixture_project, search=search_retrieval)
    before, before_total = _all_pages(repo, "evidence")
    assert before_total is not None and before_total > 0

    shutil.rmtree(fixture_project / "output" / "fail-run")
    refresh_index(fixture_project, index_documents=indexer)

    repo = SqliteRepository.open(fixture_project, search=search_retrieval)
    after, after_total = _all_pages(repo, "evidence")
    assert after_total is not None
    assert after_total < before_total
    assert not any(hit.get("video_id") == "fixture-fail" for hit in after)
    assert not any(hit.get("source_id") == "youtube:fixture-fail" for hit in after)


def test_one_unreadable_run_costs_only_itself(fixture_project: Path) -> None:
    """It used to take the whole search down with it."""
    (fixture_project / "output" / "fail-run" / "transcript.json").write_text(
        "{not json", encoding="utf-8"
    )
    indexer = document_indexer(fixture_project)
    build_index(fixture_project, index_documents=indexer)
    connection = connect(database_path(fixture_project), create=False)
    assert "youtube:fixture-fail" in unreadable_sources(connection)
    found = search_candidates(connection, "evidence")
    assert found.documents
    assert found.complete is False
    assert found.unreadable == ("youtube:fixture-fail",)


def test_a_source_that_becomes_readable_again_stops_being_unknown(
    fixture_project: Path
) -> None:
    """The marker describes the last attempt, not an old one.

    A scan carries an unchanged run's stored problems forward verbatim, so a
    marker left behind by an earlier pass would outlive the damage and report a
    healthy source as unknown for ever.
    """
    damaged = fixture_project / "output" / "fail-run" / "transcript.json"
    original = damaged.read_text(encoding="utf-8")
    damaged.write_text("{not json", encoding="utf-8")
    indexer = document_indexer(fixture_project)
    build_index(fixture_project, index_documents=indexer)
    connection = connect(database_path(fixture_project), create=False)
    assert unreadable_sources(connection)

    damaged.write_text(original, encoding="utf-8")
    refresh_index(fixture_project, index_documents=indexer)
    connection = connect(database_path(fixture_project), create=False)
    assert unreadable_sources(connection) == frozenset()
    assert search_candidates(connection, "evidence").complete is True


def test_a_source_pointing_outside_the_project_is_unsearchable_not_empty(
    tmp_path: Path
) -> None:
    """Containment is re-checked on use: a resolver that does not is not a boundary."""
    connection = _fresh_index(tmp_path)
    connection.execute(
        "INSERT INTO runs (canonical_dir, source_id, digest, scanned_at, problems) "
        "VALUES ('../elsewhere', 'youtube:escape', 'd', 'now', '[]')"
    )
    _source_row(connection, "youtube:escape")

    class _Records:
        sources = [{"id": "youtube:escape", "canonical_dir": "../elsewhere"}]

    report = document_indexer(tmp_path)(connection, _Records())
    connection.commit()
    assert report.sources == 0
    assert "youtube:escape" in report.unsearchable
    assert unreadable_sources(connection) == frozenset({"youtube:escape"})


# --------------------------------------------------------------------------
# 10. D-028's two additive fields
# --------------------------------------------------------------------------


def test_a_unit_hit_gets_a_global_id_and_a_caption_hit_does_not() -> None:
    """v1 emits no caption entities (D-023), so there is no entity to address."""
    unit = as_api_hit({"type": "knowledge_unit", "id": "KU-000001"}, "youtube:vid")
    assert unit["source_id"] == "youtube:vid"
    assert unit["global_id"] == "youtube:vid:KU-000001"

    caption = as_api_hit({"type": TRANSCRIPT_CAPTION_HIT, "caption_id": "c"}, "youtube:vid")
    assert caption["source_id"] == "youtube:vid"
    assert "global_id" not in caption


def test_an_id_that_cannot_form_a_global_id_is_null_not_a_plausible_string() -> None:
    """An address that resolves to nothing is worse than no address."""
    hit = as_api_hit({"type": "knowledge_unit", "id": "has:a:colon"}, "youtube:vid")
    assert hit["global_id"] is None
    assert as_api_hit({"type": "knowledge_unit", "id": "KU-1"}, None)["global_id"] is None


def test_nothing_but_those_two_fields_is_added() -> None:
    """``video_id`` stays ``video_id`` (ADR 0001 invariant 6)."""
    original = {"type": "knowledge_unit", "id": "KU-1", "video_id": "vid", "kind": "claim"}
    hit = as_api_hit(original, "youtube:vid")
    assert set(hit) - set(original) == {"source_id", "global_id"}
    assert all(hit[key] == value for key, value in original.items())


# --------------------------------------------------------------------------
# 11. The oracle: the SQLite page is the MemoryRepository page
# --------------------------------------------------------------------------


def _both(root: Path) -> tuple[Any, MemoryRepository]:
    build_index(root, index_documents=document_indexer(root))
    return (
        SqliteRepository.open(root, search=search_retrieval),
        MemoryRepository.from_project(root),
    )


@pytest.mark.parametrize(
    "q", ["evidence", "the", "a", "coverage", "knowledge unit", "100%", "NEAR(x y)", "*"]
)
def test_the_sqlite_page_is_the_memory_repository_page(
    fixture_project: Path, q: str
) -> None:
    """The full contract seam, walked page by page, against the cache-free oracle.

    ``MemoryRepository`` reads the canonical files with no index at all, so where
    the two disagree the canonical files are right and the index is stale
    (ADR 0001 invariant 3). Walked rather than sampled, because a paging bug
    shows up at a boundary and not on the first page.
    """
    repo, memory = _both(fixture_project)
    assert _all_pages(repo, q) == _all_pages(memory, q)


@pytest.mark.parametrize("include_transcript", [True, False])
def test_the_transcript_filter_agrees_with_the_oracle(
    fixture_project: Path, include_transcript: bool
) -> None:
    repo, memory = _both(fixture_project)
    assert _all_pages(repo, "the", include_transcript=include_transcript) == _all_pages(
        memory, "the", include_transcript=include_transcript
    )


def test_scoping_to_one_source_agrees_with_the_oracle(fixture_project: Path) -> None:
    repo, memory = _both(fixture_project)
    assert _all_pages(repo, "the", source_id="youtube:fixture-pass") == _all_pages(
        memory, "the", source_id="youtube:fixture-pass"
    )


def test_an_unindexed_source_id_is_an_empty_page_with_a_total_of_zero(
    fixture_project: Path
) -> None:
    repo, memory = _both(fixture_project)
    query = SearchQuery(q="the", source_id="youtube:absent")
    assert repo.search(query).page_info() == memory.search(query).page_info()
    assert repo.search(query).total == 0
    assert repo.search(query).items == []


# --------------------------------------------------------------------------
# 12. The real sample, when the machine has one
# --------------------------------------------------------------------------


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """A copy of the real sample. ``output/`` itself is never written to."""
    output = tmp_path / "output"
    output.mkdir()
    shutil.copytree(SAMPLE_DIR, output / SAMPLE_ID)
    library = PROJECT_ROOT / "output" / "library"
    if library.exists():
        shutil.copytree(library, output / "library")
    return tmp_path


@requires_sample
@pytest.mark.parametrize("q,total", sorted(SAMPLE_TOTALS.items()))
def test_the_measured_totals_of_the_real_sample(
    sample_project: Path, q: str, total: int
) -> None:
    """The numbers a token-only index would have got wrong: 3, 10 and 162.

    Pinned because they are the measurement the whole two-disjunct design rests
    on. They are not read off one developer's machine and asserted blind — the
    test below proves the same figures are what the cache-free oracle reports.
    """
    repo, _ = _both(sample_project)
    assert repo.search(SearchQuery(q=q, limit=3)).total == total


@requires_sample
@pytest.mark.parametrize("q", sorted(SAMPLE_TOTALS))
def test_the_real_sample_pages_identically_to_the_oracle(
    sample_project: Path, q: str
) -> None:
    repo, memory = _both(sample_project)
    assert _all_pages(repo, q) == _all_pages(memory, q)


def _fixture_documents(root: Path) -> Iterable[Any]:
    for name in sorted(FIXTURE_NAMES):
        yield from run_documents(root / "output" / name)


@requires_sample
def test_retrieval_narrows_the_real_sample_rather_than_scanning_it(
    sample_project: Path
) -> None:
    """The point of the index: candidates, not the corpus.

    ``learning`` scores 4 of 578 documents. Retrieving all 578 and rescoring them
    would give the same answer and none of the reason this module exists, so the
    candidate count is asserted to be the answer's size and not the library's.
    """
    build_index(sample_project, index_documents=document_indexer(sample_project))
    connection = connect(database_path(sample_project), create=False)
    corpus = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    found = search_candidates(connection, "learning")
    assert len(found.documents) == SAMPLE_TOTALS["learning"]
    assert len(found.documents) < corpus
