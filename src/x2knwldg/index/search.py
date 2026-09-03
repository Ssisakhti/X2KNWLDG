"""FTS5 candidate retrieval behind ``query.rank_documents`` (``T-103``).

``MemoryRepository`` answers a search by reading every canonical file it holds,
folding and tokenising every unit and caption, and scoring all of them — per
page. This module removes that walk and *nothing else*: it retrieves the
documents that can possibly score, rebuilds them as real
:class:`~x2knwldg.query.SearchDocument` objects, and hands them to
:func:`~x2knwldg.query.rank_documents` unchanged.

**FTS5 is retrieval. ``query.py`` is ranking.** That split is the whole design,
and it is the same move ADR 0002 invariant 5 makes for filters: the indexes
narrow candidates, and the Python function is the specification. So ``bm25()``
appears nowhere here. It is a different ranking function; adopting it would
reorder every result the CLI and the MCP tools ship today and forfeit
``T-104``'s equivalence proof, in exchange for a relevance model nobody asked
for.

Retrieving the right candidates is subtler than "run the query through an FTS
index", because :meth:`~x2knwldg.query.SearchDocument.score` is two disjuncts::

    overlap      = len(query_tokens & self.tokens)
    phrase_bonus = 5 if folded_query in self.folded else 0
    return self.weight * (phrase_bonus + overlap / max(1, len(query_tokens)))

``weight`` is always positive, so ``score > 0`` **iff** the query's tokens
intersect the document's tokens **or** the folded query is a substring of the
folded text. Each disjunct needs its own index, and each one has a trap.

**The substring disjunct: GLOB, never LIKE, never MATCH.** ``LIKE '%' || q ||
'%'`` is wrong outright, because ``%`` and ``_`` in a *user's* query are LIKE
wildcards: a search for ``100%`` matches a document reading "growth was 100
percent", and ``a_b`` matches ``axb``. Both are hits the user never asked for.
``LIKE … ESCAPE`` fixes the semantics and disables the trigram optimisation
entirely — the plan drops from ``INDEX 0:G0`` to ``INDEX 0:``. ``GLOB`` is
byte-exact, which is exactly what is wanted here because both sides are already
NFKC-casefolded by ``query._fold``, and it keeps the index once ``*``, ``?`` and
``[`` are escaped. Trigram ``MATCH`` is refused for a different reason: it
silently returns **zero rows** for a needle under three characters (``ai``,
``機``), and absence presented as a fact is the one thing this codebase refuses.

**The overlap disjunct is a plain table, not an FTS5 tokenizer.** FTS5's
tokenizers are not ``query._tokens``. ``unicode61`` splits on ``_`` where
Python's ``\\w+`` does not, and it does not split scriptless CJK at all, while
``_tokens`` expands a CJK run into single characters and adjacent bigrams.
Measured: for the query ``機習`` against ``機械学習のモデル`` the scorer returns
0.667 — both characters are tokens of the document — while ``unicode61 MATCH``
returns nothing *and* a trigram substring scan returns nothing, because the two
characters are not adjacent so no substring exists. Every such disagreement is a
silently missing hit. So ``schema.document_tokens`` stores ``_tokens``'s own
output verbatim, one row per token, and the overlap disjunct is exact by
construction rather than approximately right.

What that buys, measured on the real sample (578 documents, 5083 token rows):

===========  ================  ==============  ==========  =========
query        token candidates  substring only  this union  oracle
===========  ================  ==============  ==========  =========
``learning``                3               1           4          4
``model``                  10               9          19         19
``the``                   162              91         253        253
===========  ================  ==============  ==========  =========

The right two columns agree for every query tried, which is the point: a
token-only index would have returned 3, 10 and 162 and said nothing about the
rest. Retrieval costs 0.2 ms for ``learning`` and 1.2 ms for ``the``; on a
synthetic 57,800-document library, 1.0 ms and 22 ms.

Where this module sits
----------------------

It fills the two hooks the neighbouring modules leave open, and each is one
line to wire::

    build_index(root, index_documents=document_indexer(root))
    SqliteRepository.open(root, search=search_retrieval)

* :func:`document_indexer` builds ``scanner.DocumentIndexer`` — the closure a
  scan calls with the record set it committed, inside its own transaction.
* :func:`search_retrieval` is ``repository.SearchRetrieval`` — one
  ``SearchQuery`` in, the whole ranked hit list out, with whether the count is
  complete.

Underneath, and usable on their own: :func:`index_documents` indexes one
source's documents, and :func:`search_candidates` retrieves without ranking.

What is searchable, and what is deliberately not
-----------------------------------------------

The field set is ``query.run_documents``', and this module builds its corpus from
that function rather than re-deriving the list, so the two readers cannot drift
and a widening is one edit rather than two (D-046).

``derivation_note`` **is** indexed (D-047), on the ground that a phrase a reader
can see in the Reader should be a phrase they can search for — not on recall.
Measured on the real sample it contributes 25 tokens no other field holds out of
1095. The accepted cost is precision: it is *derived* commentary about
provenance, so a domain term found only there ranks a unit for what the reasoning
says rather than for what the unit claims.

Two things are left out, and each is **measured** to cost no reachable word
rather than assumed to:

* **``context``.** Every token it holds already appears in the unit's own
  ``content`` or ``normalized_statement`` — on the real sample, where 9 units
  carry one, the set difference is empty. Indexing it would answer no query it
  does not already answer.
* **Transcript segment text.** A segment's ``text`` is byte-identically the
  concatenation of the captions it spans, and those are indexed, so segments hold
  zero words of their own. What a segment hit would change is the granularity of
  a result, not what can be found — a Reader question, answerable by grouping
  captions through the ``caption_ids`` a segment already carries. It would also
  need a third hit shape: D-028 freezes two, so minting one is an
  ``openapi.json`` change first (ADR 0002 invariant 3, D-048).

Both measurements are tests in ``tests/test_sqlite_equivalence.py``, so if either
stops being true the suite says so rather than this docstring going stale.

Stdlib only, Python 3.10 floor, parameterised SQL throughout. Read-only with
respect to every canonical file. Every connection is expected to come from
:func:`~x2knwldg.index.schema.connect`, which sets ``row_factory`` — the rows
here are read by column name.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import ids
from ..query import SearchDocument, rank_documents, run_documents
from ..repository import SearchQuery
from .errors import StoreError
from .repository import SearchCandidates
from .schema import SEARCH_PROBLEM_PREFIX

__all__ = [
    "HIT_TYPES",
    "KNOWLEDGE_UNIT_HIT",
    "TRANSCRIPT_CAPTION_HIT",
    "Candidates",
    "IndexReport",
    "as_api_hit",
    "clear_source_documents",
    "document_indexer",
    "index_documents",
    "search_candidates",
    "search_retrieval",
    "unreadable_sources",
]


# --------------------------------------------------------------------------
# 1. The two hit shapes, and the escaping each disjunct needs
# --------------------------------------------------------------------------

#: D-028 freezes exactly these two, discriminated by ``type``. Named here rather
#: than spelled as literals at four call sites, and enforced by
#: :func:`index_documents`: a third shape is an ``openapi.json`` change
#: first (ADR 0002 invariant 3).
KNOWLEDGE_UNIT_HIT = "knowledge_unit"
TRANSCRIPT_CAPTION_HIT = "transcript_caption"
HIT_TYPES = (KNOWLEDGE_UNIT_HIT, TRANSCRIPT_CAPTION_HIT)

#: GLOB's three metacharacters, and the character class that makes each literal.
#: ``]`` needs no escape outside a class, and ``[[]`` is how a literal ``[`` is
#: written — ``\\[`` is not an escape GLOB understands.
_GLOB_ESCAPES = {"*": "[*]", "?": "[?]", "[": "[[]"}

#: A marker row in ``document_tokens`` for a document whose folded text holds a
#: NUL, which makes the substring disjunct unanswerable in SQL.
#:
#: SQLite's GLOB compares NUL-terminated C strings, so for a document whose
#: folded text is ``"before\\x00after the end"`` the pattern ``*after*`` matches
#: nothing while Python's ``"after" in folded`` is ``True``. Measured, and
#: reachable: a canonical file may legally contain ``\\u0000`` in a unit's
#: ``content``, and ``run_documents`` carries it straight through to ``folded``.
#:
#: Rather than lose those hits, such a document gets this extra token row and
#: every search asks for it, so the document is always a candidate and the
#: Python rescore — which is the definition of a match — decides. The value can
#: never collide with a real token: ``_tokens`` yields only ``\\w+`` matches and
#: slices of them, and ``·`` is a word character in no script.
#:
#: :func:`search_candidates` strips it back out, so a rebuilt document's
#: ``tokens`` is the set ``run_documents`` produced and not a superset of it.
_GLOB_UNSAFE_TOKEN = "·x2knwldg:glob-unsafe"

#: Prefix of the ``runs.problems`` entry that records a source this module could
#: not read the documents of. ``problems`` is the tier D-043 defines for "a run
#: indexed with named gaps", and a run whose records indexed but whose
#: searchable text could not be read is precisely that: its hits are unknown,
#: not zero, and :func:`unreadable_sources` reads them back so ``total`` can say
#: so (ADR 0004 invariant 6). Set and cleared on every index pass, so it always
#: describes the most recent attempt rather than an old one.
#:
#: Imported from :mod:`x2knwldg.index.schema`, which declares the table whose
#: column holds it, so the scanner can fold the same marker into the report of
#: the pass that wrote it.
_UNSEARCHABLE_PREFIX = SEARCH_PROBLEM_PREFIX

#: Scratch tables the query binds its token and scope sets through. A long
#: ``IN (?, ?, ?, …)`` list would do the same job until it did not:
#: ``SQLITE_LIMIT_VARIABLE_NUMBER`` is 999 on builds still in support, and a
#: 512-character CJK query expands to over a thousand tokens. TEMP tables are
#: per-connection, dropped when it closes, and permitted even on a ``mode=ro``
#: connection.
_SCOPE_TABLE = "x2knwldg_search_scope"
_TOKEN_TABLE = "x2knwldg_search_tokens"
_CANDIDATE_TABLE = "x2knwldg_search_candidates"

#: Executed one statement at a time and never through ``executescript``: that
#: method commits a pending transaction before it runs, which on the build
#: connection would commit half a build.
_SCRATCH_DDL = (
    f"CREATE TEMP TABLE IF NOT EXISTS {_SCOPE_TABLE} "
    "(source_id TEXT NOT NULL PRIMARY KEY) WITHOUT ROWID",
    f"CREATE TEMP TABLE IF NOT EXISTS {_TOKEN_TABLE} "
    "(token TEXT NOT NULL PRIMARY KEY) WITHOUT ROWID",
    f"CREATE TEMP TABLE IF NOT EXISTS {_CANDIDATE_TABLE} "
    "(document_id INTEGER NOT NULL PRIMARY KEY) WITHOUT ROWID",
)


def _glob_pattern(needle: str) -> str:
    """*needle* as a GLOB pattern matching it anywhere in a value.

    Every metacharacter in the needle is neutralised, so a user searching for
    ``*`` finds a literal asterisk rather than every document in the library.
    """
    return "*" + "".join(_GLOB_ESCAPES.get(char, char) for char in needle) + "*"


# --------------------------------------------------------------------------
# 2. D-028's two additive fields
# --------------------------------------------------------------------------


def as_api_hit(hit: Mapping[str, Any], source_id: str | None) -> dict[str, Any]:
    """*hit* with ``source_id`` and, for a unit, ``global_id``. Nothing else.

    The same two fields ``MemoryRepository.as_api_hit`` adds, added at **index**
    time rather than at read time so the stored ``hit`` is the shape served and
    no field is rebuilt on the way out. Every other key passes through
    untouched: ``video_id`` stays ``video_id`` (ADR 0001 invariant 6).

    A ``transcript_caption`` hit gets no ``global_id`` at all — v1 emits no
    caption entities (D-023), so there is no entity to address — and a unit
    whose id cannot form a global id gets ``None`` rather than a plausible
    string that resolves to nothing.

    This construction exists in two places, and the second one is not a comment
    asking the reader to keep them in step: ``tests/test_sqlite_search.py``
    asserts hit-for-hit equality with ``MemoryRepository.search`` over the
    fixture corpus, so a divergence fails a test rather than reaching a client.
    """
    enriched = dict(hit)
    enriched["source_id"] = source_id
    if hit.get("type") == KNOWLEDGE_UNIT_HIT:
        enriched["global_id"] = _unit_global_id(source_id, hit.get("id"))
    return enriched


def _unit_global_id(source_id: str | None, local_id: Any) -> str | None:
    if source_id is None:
        return None
    try:
        parsed = ids.parse_source_id(source_id)
        return ids.make_global_id(parsed.source_type, parsed.external_id, local_id).value
    except ids.IdError:
        return None


# --------------------------------------------------------------------------
# 3. Writing the corpus
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexReport:
    """What one indexing pass did, with nothing omitted in silence."""

    #: Sources whose documents were read and indexed.
    sources: int = 0
    #: Documents written across them.
    documents: int = 0
    #: Sources whose corpus was dropped because the records no longer hold them.
    removed: int = 0
    #: ``source_id -> reason`` for every source whose documents could not be
    #: read. Recorded in ``runs.problems`` too, so a later search reports
    #: ``total=None`` for them rather than counting their hits as none.
    unsearchable: Mapping[str, str] = field(default_factory=dict)


def clear_source_documents(connection: sqlite3.Connection, source_id: str) -> int:
    """Forget every indexed document belonging to *source_id*. Returns the count.

    ``documents_trigrams`` is an **external-content** FTS5 index, which means it
    does not see a ``DELETE`` on ``documents`` at all: its rows have to be
    retired explicitly, with the *old* text, before the content row goes away.
    Skipping that leaves the index describing text the table no longer holds,
    and the symptom is not a stale hit: measured, the next substring query
    **raises** ``fts5: missing row N from content table``, an
    ``sqlite3.DatabaseError`` reaching the API as a 500 on a well-formed
    request. So the old ``folded`` value is read back and handed to the
    ``'delete'`` command rather than assumed.
    """
    rows = connection.execute(
        "SELECT rowid, folded FROM documents WHERE source_id = ?", (source_id,)
    ).fetchall()
    for row in rows:
        connection.execute(
            "INSERT INTO documents_trigrams (documents_trigrams, rowid, folded) "
            "VALUES ('delete', ?, ?)",
            (row["rowid"], row["folded"]),
        )
        connection.execute(
            "DELETE FROM document_tokens WHERE document_id = ?", (row["rowid"],)
        )
    connection.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
    return len(rows)


def index_documents(
    connection: sqlite3.Connection,
    source_id: str,
    documents: Iterable[SearchDocument],
) -> int:
    """Index *documents* as the whole searchable corpus of *source_id*.

    Re-runnable by construction: the source's existing rows are cleared first,
    so re-indexing an unchanged run leaves the same corpus rather than a second
    copy of it. That matters beyond tidiness — a doubled corpus doubles
    ``total`` and returns every hit twice — and the incremental build path
    re-indexes on every scan.

    ``ordinal`` records the position ``run_documents`` produced each document
    at, and it is the tiebreak the whole ranking rests on:
    :func:`~x2knwldg.query.rank_documents` sorts **stably**, so equal scores
    come out in the order they were fed in. Retrieval feeds them back in
    ``(source_id, ordinal)`` order — see :data:`_ROWS_SQL`.

    The ``hit`` mapping is stored whole, as JSON, in its own key order. Nothing
    rebuilds a field from a column: D-028's two shapes are frozen and
    deliberately sparse — a unit that states no numeric ``start_sec`` carries
    neither a timing nor a ``source_url`` — and a column per field would have to
    invent a representation for each of those absences. A hit whose ``type`` is
    not one of :data:`HIT_TYPES` is refused rather than stored.

    The caller owns the transaction. Indexing many sources in one is what makes
    a build atomic, so this neither begins nor commits.
    """
    clear_source_documents(connection, source_id)
    indexed = 0
    for ordinal, document in enumerate(documents):
        hit = document.hit
        hit_type = hit.get("type")
        if hit_type not in HIT_TYPES:
            raise StoreError(
                f"{source_id}: a search hit of type {hit_type!r} is not one of the two "
                f"shapes the contract freezes ({', '.join(HIT_TYPES)}). Minting a third "
                "is a change to schemas/api/v1/openapi.json first and to the index second"
            )
        cursor = connection.execute(
            "INSERT INTO documents (source_id, hit_type, hit, folded, weight, ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                source_id,
                hit_type,
                json.dumps(dict(hit), ensure_ascii=False, separators=(",", ":")),
                document.folded,
                float(document.weight),
                ordinal,
            ),
        )
        document_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO documents_trigrams (rowid, folded) VALUES (?, ?)",
            (document_id, document.folded),
        )
        tokens = set(document.tokens)
        if "\x00" in document.folded:
            # GLOB cannot see past the NUL, so this document is marked as one
            # the substring disjunct must not be trusted for.
            tokens.add(_GLOB_UNSAFE_TOKEN)
        connection.executemany(
            "INSERT INTO document_tokens (token, document_id) VALUES (?, ?)",
            [(token, document_id) for token in tokens],
        )
        indexed += 1
    return indexed


def document_indexer(
    project_root: Path, *, output_dir: str = "output"
) -> Callable[[sqlite3.Connection, Any], IndexReport]:
    """Build the ``scanner.DocumentIndexer`` hook for *project_root*.

    A scan calls the returned closure with the record set it committed, inside
    its own write transaction, so a crash leaves the previous corpus rather than
    a half-built one that reports itself ready. The root is bound here because
    the hook's signature carries only the connection and the records — and
    because the root is the caller's fact, not something to re-derive from the
    database file and hope the two agree.

    *output_dir* names the directory the caller's runs live under, and is used
    only to *say* so in the reason a source is reported unsearchable.
    Deliberately not resolved against: every ``Source`` record carries its own
    project-relative ``canonical_dir``, which already includes that directory,
    and containment is checked against *project_root* — the identical rule
    ``MemoryRepository._run_dir`` applies. Making the containment tighter here
    would give the index and the oracle two different answers to "is this source
    searchable", which is the one thing ADR 0004 invariant 1 forbids.

    What the closure does, per pass:

    * for every source in the records, resolve its run directory from its own
      ``canonical_dir`` — **no id is ever joined onto a path** (D-042, ADR 0003)
      — read its documents with ``query.run_documents``, and index them;
    * record a source whose canonical files cannot be read as *unsearchable*
      rather than indexing it empty, so the damage costs only that source. One
      unreadable run used to take a whole search down with it;
    * **drop the corpus of every source the records no longer hold.** The
      scanner never touches ``documents``, ``document_tokens`` or
      ``documents_trigrams`` — not even on a full rebuild — so after a build
      those tables still hold the previous pass's rows. Without this a deleted
      run's hits would go on being returned for ever, with ``total`` counting
      them.

    Every source is re-indexed on every pass, including the ones a scan found
    unchanged. That is deliberate: the hook is handed records, not per-run
    verdicts, so re-reading is the only way an incremental index provably equals
    a rebuilt one — the equivalence ``T-104`` exists to check. It costs about
    6 ms per 578 documents.

    The closure returns an :class:`IndexReport`. ``DocumentIndexer`` is typed as
    returning ``None`` and the scanner ignores the value; it is there because a
    caller that wants to know what one pass did should not have to re-query for
    it.
    """
    root = Path(project_root).expanduser().resolve()
    expected = f"{root / output_dir}"

    def index(connection: sqlite3.Connection, records: Any) -> IndexReport:
        sources = 0
        documents = 0
        unsearchable: dict[str, str] = {}
        held: set[str] = set()
        for source in getattr(records, "sources", ()):
            source_id = source.get("id")
            if not isinstance(source_id, str) or not source_id:
                # A record with no id is not addressable and cannot own a hit.
                continue
            held.add(source_id)
            run_dir = _run_dir(source, root)
            if run_dir is None:
                reason = (
                    "the source record states no canonical directory inside the "
                    f"project (runs are expected under {expected})"
                )
                unsearchable[source_id] = reason
                clear_source_documents(connection, source_id)
                _record_searchability(connection, source_id, reason)
                continue
            try:
                found = run_documents(run_dir)
            except (OSError, ValueError) as exc:
                # A canonical file that is present and unparseable is not an
                # empty run — `UnsearchableRun` is a ValueError for exactly this
                # seam. Nothing is invented and nothing is counted.
                unsearchable[source_id] = str(exc)
                clear_source_documents(connection, source_id)
                _record_searchability(connection, source_id, str(exc))
                continue
            documents += index_documents(
                connection,
                source_id,
                [
                    SearchDocument(
                        hit=as_api_hit(document.hit, source_id),
                        folded=document.folded,
                        tokens=document.tokens,
                        weight=document.weight,
                    )
                    for document in found
                ],
            )
            sources += 1
            _record_searchability(connection, source_id, None)

        removed = 0
        stale = connection.execute(
            "SELECT DISTINCT source_id FROM documents"
        ).fetchall()
        for row in stale:
            if row["source_id"] not in held:
                clear_source_documents(connection, row["source_id"])
                removed += 1
        return IndexReport(
            sources=sources,
            documents=documents,
            removed=removed,
            unsearchable=unsearchable,
        )

    return index


def _run_dir(source: Mapping[str, Any], project_root: Path) -> Path | None:
    """The run directory a ``Source`` record points at, or ``None``.

    The record carries the path; nothing is rebuilt from an id. ``None`` means
    the record states no directory, or states one that does not resolve inside
    the project root — in either case the source cannot be searched, and saying
    so is the whole answer. The same rule as ``MemoryRepository._run_dir``, and
    the parity test over the fixture corpus is what keeps them the same rule.
    """
    canonical_dir = source.get("canonical_dir")
    if not isinstance(canonical_dir, str) or not canonical_dir:
        return None
    run_dir = (project_root / canonical_dir).resolve()
    if run_dir != project_root and project_root not in run_dir.parents:
        return None
    return run_dir


def _record_searchability(
    connection: sqlite3.Connection, source_id: str, reason: str | None
) -> None:
    """Note in ``runs.problems`` whether this source's documents could be read.

    Written on **every** pass, set or cleared, so the entry always describes the
    most recent attempt. A scan carries an unchanged run's stored problems
    forward verbatim, so a marker left behind by an earlier pass would outlive
    the damage and report a healthy source as unknown for ever.

    A source with no ``runs`` row cannot be recorded against — the scanner
    always writes one before calling the hook, and a caller that indexes without
    one gets the fact back in :class:`IndexReport` instead.
    """
    rows = connection.execute(
        "SELECT canonical_dir, problems FROM runs WHERE source_id = ?", (source_id,)
    ).fetchall()
    for row in rows:
        try:
            stored = json.loads(row["problems"])
        except ValueError:
            stored = []
        kept = [
            problem
            for problem in (stored if isinstance(stored, list) else [])
            if not (isinstance(problem, str) and problem.startswith(_UNSEARCHABLE_PREFIX))
        ]
        if reason is not None:
            kept.append(f"{_UNSEARCHABLE_PREFIX}{reason}")
        connection.execute(
            "UPDATE runs SET problems = ? WHERE canonical_dir = ?",
            (json.dumps(kept), row["canonical_dir"]),
        )


# --------------------------------------------------------------------------
# 4. What a search can and cannot know
# --------------------------------------------------------------------------


def unreadable_sources(connection: sqlite3.Connection) -> frozenset[str]:
    """The indexed sources whose searchable text could not be read.

    A source in here has **unknown** search hits, not zero of them, and that
    distinction is the whole of ADR 0004 invariant 6: ``PageInfo.total`` is null
    for unknown and never zero for it. The way in is a
    :data:`_UNSEARCHABLE_PREFIX` problem: the run was indexed, and its canonical
    files would not yield documents.

    D-043's **other** tier — a run that could not be indexed at all — is
    deliberately not here, and this used to claim it was. Every skipped run is
    constructed with ``source_id=None`` (``scanner._Run``'s default, on all four
    of its skip paths), because a run with no records has no ``Source`` and so
    no id to attribute anything to; its records are evicted, so it is not in
    ``_resolve_scope``'s scope either. The branch that read
    ``skipped_reason IS NOT NULL`` was therefore unreachable twice over, and
    the test that covered it inserted a row shape production never writes —
    proving the branch worked rather than that it happened.

    Nothing is lost by dropping it: a skipped run is reported to a reader by
    ``/api/status``, which names every one of them in ``runs.skipped`` with its
    reason. ``tests/test_sqlite_search.py`` asserts the ``source_id IS NULL``
    shape, so if a skipped run ever gains an id this decision gets revisited
    instead of silently coming back to life.
    """
    unreadable: set[str] = set()
    rows = connection.execute(
        "SELECT source_id, problems FROM runs "
        "WHERE source_id IS NOT NULL AND skipped_reason IS NULL"
    ).fetchall()
    for row in rows:
        try:
            problems = json.loads(row["problems"])
        except ValueError:
            continue
        if not isinstance(problems, list):
            continue
        if any(
            isinstance(problem, str) and problem.startswith(_UNSEARCHABLE_PREFIX)
            for problem in problems
        ):
            unreadable.add(row["source_id"])
    return frozenset(unreadable)


@dataclass(frozen=True)
class Candidates:
    """The documents a query could match, and what a count over them cannot cover.

    ``documents`` is in the order :func:`~x2knwldg.query.rank_documents` must be
    fed: sources by id ascending, canonical file order within a source. Pass it
    straight through — ranking is ``query.py``'s and is not reimplemented here.
    """

    #: Every document whose score can be non-zero, in feed order.
    documents: tuple[SearchDocument, ...] = ()
    #: In-scope sources that are indexed but whose text could not be read.
    unreadable: tuple[str, ...] = ()
    #: Requested source ids that name no indexed source at all.
    unknown: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether a count over these documents is a count of everything.

        ``False`` only for an unreadable source. A requested id that names
        nothing does **not** make the count unknown: "this index holds no such
        source" is a fact, and zero is the honest answer to it.
        """
        return not self.unreadable


# --------------------------------------------------------------------------
# 5. Retrieval
# --------------------------------------------------------------------------


def search_candidates(
    connection: sqlite3.Connection,
    q: str,
    *,
    source_ids: Sequence[str] | None = None,
    include_transcript: bool = True,
    unreadable: Iterable[str] | None = None,
) -> Candidates:
    """Every indexed document that can score for *q*, rebuilt for ranking.

    *source_ids* restricts the search to those sources; ``None`` searches every
    source the index holds. *include_transcript* ``False`` drops
    ``transcript_caption`` hits, which is what ``/api/search`` does with
    ``include_transcript=false``. *unreadable* overrides
    :func:`unreadable_sources` for a caller that already knows.

    A well-formed source id naming no indexed source is reported in
    :attr:`Candidates.unknown` and contributes nothing — not an error, and not
    an unknown count.

    The query string reaches SQLite only as bound parameters, and only ever as a
    GLOB pattern or as rows of a token table. No part of it is interpolated into
    SQL and no part of it is an FTS5 ``MATCH`` expression, so the operators a
    user may legally type — ``"``, ``*``, ``-``, ``NEAR``, ``AND``, ``:`` — are
    text to be searched for. They cannot raise, cannot mean something
    unintended, and cannot reach a client as a 500.

    The folding and tokenising are ``query.py``'s own, obtained by building a
    throwaway :meth:`~x2knwldg.query.SearchDocument.of` over the query text.
    That is deliberate rather than lazy: it is the identical code path
    ``rank_documents`` takes, so the two cannot drift, and it needs no private
    name from another module. ``_fold`` is not idempotent for every string, so
    re-deriving a document's tokens from its stored ``folded`` column would not
    give the same set — which is why they are stored and read back instead.
    """
    probe = SearchDocument.of({}, q)
    needle = probe.folded.strip()
    if not needle:
        # `score` returns 0 for an empty folded query whatever the document, so
        # there is nothing to retrieve. `SearchQuery` refuses a blank query
        # earlier; reaching here it is simply an empty result.
        return Candidates()

    scope, unknown = _resolve_scope(connection, source_ids)
    unreadable_ids = (
        unreadable_sources(connection) if unreadable is None else frozenset(unreadable)
    )
    blocked = tuple(sorted(source for source in scope if source in unreadable_ids))
    searchable = [source for source in scope if source not in unreadable_ids]
    if not searchable:
        return Candidates(unreadable=blocked, unknown=unknown)

    tokens = set(probe.tokens)
    tokens.add(_GLOB_UNSAFE_TOKEN)

    # A read path that leaves a transaction open holds a lock the build then
    # waits on. Filling the scratch tables is a write, which makes sqlite3 begin
    # one, so whether one was already in flight is recorded and only a
    # transaction *this* call started is undone. Nothing but TEMP rows is ever
    # written here, so that rollback loses nothing.
    began_outside = not connection.in_transaction
    try:
        for statement in _SCRATCH_DDL:
            connection.execute(statement)
        _fill(connection, _SCOPE_TABLE, "source_id", searchable)
        _fill(connection, _TOKEN_TABLE, "token", tokens)
        connection.execute(f"DELETE FROM {_CANDIDATE_TABLE}")
        connection.execute(
            _CANDIDATE_SQL,
            {
                "include_transcript": 1 if include_transcript else 0,
                "caption": TRANSCRIPT_CAPTION_HIT,
                "pattern": _glob_pattern(needle),
            },
        )
        documents = _rebuild(connection)
    finally:
        if began_outside and connection.in_transaction:
            connection.rollback()
    return Candidates(documents=documents, unreadable=blocked, unknown=unknown)


def search_retrieval(
    connection: sqlite3.Connection, query: SearchQuery
) -> SearchCandidates:
    """``repository.SearchRetrieval`` — one ``SearchQuery`` in, ranked hits out.

    The seam ``SqliteRepository`` pages over. It owns the offset, the window and
    the cursor — search pages by offset because "a relevance rank is not a
    stable key" (D-032) — so this returns the **whole** ranked list and no page
    of it.

    ``complete`` is ``False`` only for a source that is indexed and unreadable,
    which is what makes the contract report ``total: null``. A well-formed
    source id naming no indexed source leaves it ``True``: "this index holds no
    such source" is a fact, and zero is the honest answer to it, not unknown.

    Ranking is :func:`~x2knwldg.query.rank_documents`, called and not
    transcribed — the same function ``MemoryRepository`` ranks with, over
    documents rebuilt to be the ones ``run_documents`` produced. That is the
    whole of ``T-104``'s equivalence: two implementations, one ranking rule.
    """
    candidates = search_candidates(
        connection,
        query.q,
        source_ids=None if query.source_id is None else [query.source_id],
        include_transcript=query.include_transcript,
    )
    return SearchCandidates(
        hits=tuple(dict(hit) for hit in rank_documents(candidates.documents, query.q)),
        complete=candidates.complete,
    )


# --------------------------------------------------------------------------
# 6. The retrieval statements, and the trap in them
# --------------------------------------------------------------------------

#: The two disjuncts of ``SearchDocument.score``, as one statement.
#:
#: **Do not "tidy" the token half into a join.** ``token IN (SELECT token FROM
#: …)`` plans as ``SEARCH document_tokens USING PRIMARY KEY (token=?)``; the
#: equivalent ``FROM document_tokens JOIN <tokens> USING (token)`` plans as a
#: full ``SCAN document_tokens USING COVERING INDEX document_tokens_by_document``
#: — every token row in the library, per search, for identical semantics. It is
#: about a thousand times slower and no test would fail.
_CANDIDATE_SQL = f"""
INSERT INTO {_CANDIDATE_TABLE} (document_id)
SELECT d.rowid
  FROM documents AS d
 WHERE d.source_id IN (SELECT source_id FROM {_SCOPE_TABLE})
   AND (:include_transcript OR d.hit_type <> :caption)
   AND (
        d.rowid IN (
            SELECT document_id FROM document_tokens
             WHERE token IN (SELECT token FROM {_TOKEN_TABLE})
        )
     OR d.rowid IN (
            SELECT rowid FROM documents_trigrams WHERE folded GLOB :pattern
        )
   )
"""

#: Feed order, and it is deliberately not ``ORDER BY rowid``. A full rebuild
#: happens to assign rowids source by source, but an incremental re-index of one
#: source appends its documents at the end of the table — so rowid order would
#: put a re-indexed source last and silently diverge from a rebuild, which is
#: exactly the equivalence ``T-104`` tests. ``MemoryRepository`` feeds sources id
#: ascending and then canonical file order, so this does too.
_ROWS_SQL = f"""
SELECT d.rowid AS document_id, d.hit, d.folded, d.weight
  FROM documents AS d
  JOIN {_CANDIDATE_TABLE} AS c ON c.document_id = d.rowid
 ORDER BY d.source_id, d.ordinal
"""

_TOKENS_SQL = f"""
SELECT token, document_id
  FROM document_tokens
 WHERE document_id IN (SELECT document_id FROM {_CANDIDATE_TABLE})
"""


def _fill(
    connection: sqlite3.Connection, table: str, column: str, values: Iterable[str]
) -> None:
    """Replace *table*'s contents with *values*, ignoring duplicates."""
    connection.execute(f"DELETE FROM {table}")
    connection.executemany(
        f"INSERT OR IGNORE INTO {table} ({column}) VALUES (?)",
        [(value,) for value in values],
    )


def _resolve_scope(
    connection: sqlite3.Connection, source_ids: Sequence[str] | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The sources to search, and the requested ids that name none.

    Scope resolves against ``sources`` and not against ``documents``: a source
    with no units and no captions is searched and found empty, which is a
    different answer from a source the index does not hold.
    """
    if source_ids is None:
        rows = connection.execute("SELECT identity FROM sources ORDER BY identity")
        return tuple(row["identity"] for row in rows), ()
    known: list[str] = []
    unknown: list[str] = []
    for source_id in source_ids:
        row = connection.execute(
            "SELECT 1 FROM sources WHERE identity = ?", (source_id,)
        ).fetchone()
        (known if row is not None else unknown).append(source_id)
    return tuple(known), tuple(unknown)


def _rebuild(connection: sqlite3.Connection) -> tuple[SearchDocument, ...]:
    """The candidate rows as ``SearchDocument``s, ready for ``rank_documents``.

    Every field comes back off a row: the hit from the stored JSON, ``folded``
    and ``weight`` from their columns, ``tokens`` from ``document_tokens``.
    Nothing is recomputed, so a rebuilt document *is* the one ``run_documents``
    produced — which is what makes ranking over the index and ranking over the
    canonical files the same answer rather than a similar one.
    """
    tokens: dict[int, set[str]] = {}
    for row in connection.execute(_TOKENS_SQL):
        token = row["token"]
        if token == _GLOB_UNSAFE_TOKEN:
            # A marker this module wrote, not a token the document holds.
            continue
        tokens.setdefault(row["document_id"], set()).add(token)
    return tuple(
        SearchDocument(
            hit=_hit(row["hit"]),
            folded=row["folded"],
            tokens=frozenset(tokens.get(row["document_id"], ())),
            weight=row["weight"],
        )
        for row in connection.execute(_ROWS_SQL)
    )


def _hit(stored: str) -> Mapping[str, Any]:
    """The stored hit, or a refusal that names the store rather than the request."""
    try:
        hit = json.loads(stored)
    except ValueError as exc:
        raise StoreError(
            "an indexed search hit is not readable JSON, so the index cannot be "
            "searched honestly. The index is a rebuildable cache: delete the cache "
            "directory and rebuild it from the canonical files"
        ) from exc
    if not isinstance(hit, dict):
        raise StoreError(
            f"an indexed search hit is a {type(hit).__name__} rather than an object; "
            "delete the cache directory and rebuild the index"
        )
    return hit
