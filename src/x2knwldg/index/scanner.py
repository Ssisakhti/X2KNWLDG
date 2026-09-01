"""Discovery, change detection and the build lifecycle (``T-102``).

This is the only module in the package that writes rows, and it writes them
under one thesis: **the index is a rebuildable cache, so a scan may be cheap,
but it may never be quiet.** Every run the scanner meets ends in exactly one of
four reported outcomes — indexed, unchanged, skipped, evicted — and the count of
each is carried on :class:`ScanReport` beside the reason for every departure
from the happy path. A count that omits a run without saying so is the defect
``rebuild_library`` was reworked to close (D-043), and the same rule holds here:
the cheap path may skip *work*, never *reporting*.

Five decisions worth stating, because each one closes a hole that would
otherwise only ever surface as a wrong count.

**A run's digest covers its whole subtree, not its ``metadata.json``.** The
records a run produces depend on far more than one file:
``YouTubeAdapter._file_artifact`` reads ``path.is_file()`` into ``available``
and ``path.stat().st_size`` into ``bytes``; ``_raw_source_spec`` globs
``raw/source.*`` and *refuses* a run holding two of them; ``_vault_artifacts``
walks ``vault/**/*.md`` and turns each filename into either an artifact id or an
``adapter_metadata.unmappable_artifacts`` finding. And a re-run rewrites
``knowledge_units.json`` while leaving ``metadata.json`` untouched. So the digest
is taken over *every regular file* in the run directory — run-relative path,
size and content hash, sorted by path — because anything narrower would call a
deleted vault note, a truncated transcript or a flipped ``available``
"unchanged". Only ``.DS_Store`` is ignored, by name: it churns on every Finder
visit and no adapter reads it. Dotfiles in general are **not** ignored — a note
named ``.notes.md`` is picked up by the adapter's ``*.md`` walk and does produce
a finding, so ignoring it here would let that finding go stale.

**The prefilter and the confirmation live in one column.** Canvas §13.1 permits
"hash/mtime" and the schema gives a run a single ``digest``, so the stored value
is ``<fingerprint>:<content>``: a hash over every file's
``(path, mtime_ns, size)``, and a hash over every file's ``(path, size,
sha256)``. A refresh computes the cheap half first and stops there when it
matches. When only the cheap half differs the strong half is computed, and a
match there still means *unchanged* — a touched file whose bytes are identical
is not a re-run — while the row is updated so the next scan is cheap again.
Every :func:`x2knwldg.io.sha256_file` call is wrapped, because it lets
``OSError`` escape; a file that cannot be hashed becomes a *named problem* on
the run rather than either a crash or a silently missing input.

**Damage has two tiers, exactly as D-043 established them.** A run
``adapt_run`` refuses is *skipped*: it cannot be indexed at all, and
``{relative_path, reason}`` says so. A run that indexes with named gaps is
*incomplete*: ``{relative_path, source_id, problems}``, the problems copied out
of ``Source.adapter_metadata``'s ``unreadable_files`` and
``unmappable_artifacts``, which is where the adapter already records what it
could not map. Both tiers are stored on the ``runs`` row, so a later refresh
that skips the work still re-reports the finding.

**The library fragment can be skipped too, and it has two ways to fail.**
:func:`adapt_library` returns an empty record set both when a project has no
library — a real absence — and when ``library/graph.json`` or
``library/concepts.json`` is *damaged*, which reaches a reader as "0 concepts"
with nothing to say otherwise. That is the silent zero D-043 forbids, and it
cannot be fixed inside ``adapters/`` from here, so this module reads both paths
itself first. The second failure is staleness: ``library/graph.json`` is a
projection over the runs, rebuilt by ``rebuild_library`` and not by this
scanner, so deleting a run leaves its ``expresses_concept`` edges naming
knowledge units nothing carries. Either way the fragment is dropped **whole**
and named — never filtered down to the edges that still resolve, which would
reshape the graph with no report and leave concepts expressed by nothing.

``library/`` is therefore re-derived whenever any run's records changed, and it
keeps a ``runs`` row of its own keyed by ``output/library``: without one, a
``rebuild_library`` that changed no run would leave the fragment as the previous
scan saw it — a stale answer arrived at cheaply. It is not a run, and
:func:`run_dirs` never yields it.

**A crash reopens as ``building``.** ``index_state`` is set to ``building`` and
committed before any work; every row of a scan is then written in one
transaction that ends by writing ``ready`` and ``built_at``, so an interrupted
build leaves the previous rows intact and the state honest. A failure writes
``error`` with the message. No path writes ``ready`` over a half-full index, and
:func:`refresh_index` refuses to be incremental against a state that never
reached ``ready``.

One deliberate divergence, for whoever writes ``T-104``: ``adapt_project``
propagates ``AdapterError`` and refuses the **whole project** when one run is
unmappable, while this scanner skips that run and names it. Skip-and-name is
right per D-043 — one broken run must not cost a reader every other run — but it
means that on a damaged project this index is a named superset of what the
``MemoryRepository`` oracle can produce, and the two disagree about the project.
So ``strict=True`` reproduces ``adapt_project``'s refusal exactly, which is the
mode a page-for-page equivalence proof wants.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..adapters import (
    LIBRARY_DIR_NAME,
    AdapterError,
    IndexRecords,
    adapt_library,
    adapt_run,
    project_relative,
    read_optional_json_or_reason,
)
from ..io import sha256_file
from ..repository import (
    RepositoryError,
    check_index_integrity,
    content_digest,
    identity,
)
from . import schema
from .errors import IndexCorrupt

__all__ = [
    "IGNORED_FILENAMES",
    "MODELS",
    "DocumentIndexer",
    "ScanReport",
    "build_index",
    "refresh_index",
    "run_dirs",
]

#: Files inside a run directory that no adapter reads and that change on their
#: own. Ignoring anything else here would let a real finding go stale — see the
#: module docstring on ``.notes.md``.
IGNORED_FILENAMES = frozenset({".DS_Store"})

#: ``(model, table)`` for the four record families, in the order
#: ``IndexRecords.by_model`` names them. The model string is the key
#: ``repository.ORDER_KEYS`` is indexed by, so ``identity`` can never be asked
#: for a family the seam does not know.
MODELS: tuple[tuple[str, str], ...] = (
    ("source", "sources"),
    ("artifact", "artifacts"),
    ("entity_ref", "entities"),
    ("indexed_relation", "relations"),
)

#: The tables that carry a ``source_id``, and are therefore evictable per
#: source. ``sources`` is addressed by its own ``identity`` instead.
_MEMBER_TABLES: tuple[str, ...] = tuple(
    table for _model, table in MODELS if table != "sources"
)

#: Separates the cheap fingerprint from the content hash inside one ``digest``.
#: Both halves are hex, so the separator cannot occur inside either.
_DIGEST_SEPARATOR = ":"

#: What a file that cannot be hashed contributes to the content half. A stable
#: token, so the digest still *changes* when the file becomes readable again.
_UNHASHABLE = "unhashable"

#: The two library files ``adapt_library`` reads. Checked for damage here
#: because it reports their damage and their absence identically.
_LIBRARY_FILES = ("graph.json", "concepts.json")

#: Signature of the hook that fills ``documents`` and the two FTS5 tables.
#: ``T-103``'s ``x2knwldg.index.search.index_documents`` is the intended
#: argument; this module never imports it (see :func:`build_index`).
DocumentIndexer = Callable[[sqlite3.Connection, IndexRecords], None]


# --------------------------------------------------------------------------
# 1. What a scan reports
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanReport:
    """The outcome of one scan, with nothing omitted in silence.

    The counts are related by one identity, and it is asserted rather than
    hoped for::

        runs_discovered == runs_indexed + runs_skipped

    ``runs_indexed`` is every run whose records are in the index when the scan
    finishes — those re-adapted now *and* those carried over untouched.
    ``runs_unchanged`` is the subset that was carried over, which is the only
    number that says how much work the incremental path saved.
    ``runs_skipped`` is the D-043 damage tier: a run with no records at all,
    every one of them named in :attr:`skipped_runs`. ``runs_evicted`` counts run
    directories that have *gone*, whose records were removed from every table.

    :attr:`skipped_runs` names every *thing* this scan could not index, so it
    carries one entry per skipped run **plus**, when it applies, one for the
    ``library/`` fragment — which is not an ingested run and is therefore not
    counted in ``runs_skipped``. :attr:`library_skipped_reason` is the same
    reason in a field a caller can test without matching on a path, and the
    relationship between the two is asserted below rather than left to be
    noticed: a list that disagreed with its own count would be the D-043 defect
    in miniature.

    The collections are tuples and the mapping is a read-only view: a frozen
    dataclass holding a mutable list is only half frozen, and a report a caller
    can edit is a report that can be made to disagree with the index it
    describes. :meth:`payload` hands back plain JSON-able copies.
    """

    runs_discovered: int = 0
    runs_indexed: int = 0
    runs_skipped: int = 0
    runs_unchanged: int = 0
    runs_evicted: int = 0
    skipped_runs: tuple[Mapping[str, Any], ...] = ()
    incomplete_runs: tuple[Mapping[str, Any], ...] = ()
    counts: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    index_version: int | None = None
    built_at: str | None = None
    library_reindexed: bool = False
    library_skipped_reason: str | None = None

    def __post_init__(self) -> None:
        if self.runs_indexed + self.runs_skipped != self.runs_discovered:
            raise RepositoryError(
                f"a scan discovered {self.runs_discovered} runs but accounts for "
                f"{self.runs_indexed} indexed and {self.runs_skipped} skipped; every "
                "run is reported in exactly one of the two (D-043)"
            )
        if self.runs_unchanged > self.runs_indexed:
            raise RepositoryError(
                f"a scan reports {self.runs_unchanged} runs unchanged out of "
                f"{self.runs_indexed} indexed; an unchanged run is an indexed one"
            )
        expected = self.runs_skipped + (1 if self.library_skipped_reason else 0)
        if len(self.skipped_runs) != expected:
            raise RepositoryError(
                f"a scan names {len(self.skipped_runs)} skipped paths but counts "
                f"{self.runs_skipped} skipped runs"
                + (" and a skipped library fragment" if self.library_skipped_reason else "")
                + "; a list that disagrees with its own count is the defect D-043 closed"
            )

    @property
    def runs_reindexed(self) -> int:
        """The runs whose records this scan actually re-adapted."""
        return self.runs_indexed - self.runs_unchanged

    def payload(self) -> dict[str, Any]:
        """Plain JSON-able dicts, in the shape ``rebuild_library`` reports."""
        return {
            "runs_discovered": self.runs_discovered,
            "runs_indexed": self.runs_indexed,
            "runs_reindexed": self.runs_reindexed,
            "runs_unchanged": self.runs_unchanged,
            "runs_skipped": self.runs_skipped,
            "runs_evicted": self.runs_evicted,
            "skipped_runs": [dict(entry) for entry in self.skipped_runs],
            "incomplete_runs": [dict(entry) for entry in self.incomplete_runs],
            "counts": {key: int(value) for key, value in self.counts.items()},
            "index_version": self.index_version,
            "built_at": self.built_at,
            "library_reindexed": self.library_reindexed,
            "library_skipped_reason": self.library_skipped_reason,
        }


# --------------------------------------------------------------------------
# 2. Discovery — the same walk, made incremental
# --------------------------------------------------------------------------


def run_dirs(output_root: Path) -> list[Path]:
    """Every ingested run under *output_root*, in ``adapt_project``'s order.

    Deliberately the same three rules: ``sorted(glob("*/metadata.json"))``, no
    dotted directory, and never ``library/`` — which is not an ingested source
    but the cross-source projection over all of them. ``adapt_project``'s
    docstring names this scan as the one ``T-102`` makes incremental, so it is
    mirrored rather than re-derived: a second opinion about which directories
    are runs would be a second index.
    """
    return [
        path.parent
        for path in sorted(Path(output_root).glob("*/metadata.json"))
        if not path.parent.name.startswith(".") and path.parent.name != LIBRARY_DIR_NAME
    ]


def _project_relative_reason(reason: str, run_dir: Path, canonical_dir: str) -> str:
    """*reason* with the host path replaced by the project-relative one.

    ``AdapterError`` names the directory it refused, and it names it
    absolutely: "/Users/me/proj/output/broken has no readable metadata.json".
    That string is stored, and since D-050 it is also served by
    ``/api/status`` — at which point an absolute path is a leak of the
    user's filesystem layout to any HTTP client, which D-030 and ADR 0003
    both forbid ("no host path reaches an error body").

    Sanitised here, at the point the reason is *recorded*, rather than on
    the way out: one rule, and the CLI report gains the same property it
    already has for every path it prints beside it. The relative form is
    the same string the row is keyed by, so the two cannot disagree about
    which directory failed.
    """
    return reason.replace(str(run_dir), canonical_dir)


def _run_files(run_dir: Path) -> list[Path]:
    """Every regular file the adapter could observe, sorted by path."""
    return sorted(
        path
        for path in run_dir.rglob("*")
        if path.name not in IGNORED_FILENAMES and path.is_file()
    )


def _relative(run_dir: Path, path: Path) -> str:
    """*path* relative to its run, as posix — never an absolute host path (R15)."""
    return path.relative_to(run_dir).as_posix()


# --------------------------------------------------------------------------
# 3. Change detection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Digest:
    """A run's stored ``digest``, in its two halves.

    ``fingerprint`` is the cheap prefilter and ``content`` is the confirmation.
    Only ``content`` decides whether a run is unchanged; ``fingerprint`` only
    ever decides whether that question is worth reading the files to answer.
    """

    fingerprint: str
    content: str
    problems: tuple[str, ...] = ()

    @property
    def stored(self) -> str:
        return f"{self.fingerprint}{_DIGEST_SEPARATOR}{self.content}"


def _fingerprint(run_dir: Path, files: Sequence[Path]) -> str:
    """The cheap half: ``(path, mtime_ns, size)`` for every file.

    A prefilter and nothing more. It answers "nothing here has been touched"
    without reading a byte, and its *disagreement* is never taken as evidence
    that any content changed — that is what the strong half is for.
    """
    lines = []
    for path in files:
        relative = _relative(run_dir, path)
        try:
            stat = path.stat()
        except OSError as exc:
            # A file that vanished between the walk and the stat is a change by
            # definition, and naming the error keeps the token stable for as
            # long as the condition lasts.
            lines.append(f"{relative}\0{type(exc).__name__}")
            continue
        lines.append(f"{relative}\0{stat.st_mtime_ns}\0{stat.st_size}")
    return content_digest({"fingerprint": lines})


def _content_hash(run_dir: Path, files: Sequence[Path]) -> tuple[str, list[str]]:
    """The strong half: ``(path, size, sha256)`` for every file, plus problems.

    ``io.sha256_file`` opens the file and lets ``OSError`` escape, so every call
    is wrapped. An unreadable file contributes a stable token *and* a named
    problem: crashing would cost the reader every other run in the project, and
    dropping the file from the digest would make "unchanged" mean "unchanged
    except for the part I could not read".
    """
    problems: list[str] = []
    lines = []
    for path in files:
        relative = _relative(run_dir, path)
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
        except OSError as exc:
            problems.append(f"{relative}: cannot be read to hash it ({exc})")
            lines.append(f"{relative}\0{_UNHASHABLE}")
            continue
        lines.append(f"{relative}\0{size}\0{digest}")
    return content_digest({"content": lines}), problems


def _split(stored: str | None) -> tuple[str | None, str | None]:
    """A stored digest as ``(fingerprint, content)``, tolerating anything else.

    A value this code did not write — an older shape, a truncated row — yields
    ``(None, None)``, which compares equal to nothing and therefore means "not
    unchanged". Re-adapting a run is cheap; guessing is not.
    """
    if not isinstance(stored, str) or stored.count(_DIGEST_SEPARATOR) != 1:
        return None, None
    fingerprint, content = stored.split(_DIGEST_SEPARATOR)
    return fingerprint or None, content or None


def _digest_of(run_dir: Path, stored: str | None) -> _Digest:
    """Digest *run_dir*, hashing its files only when the prefilter disagrees."""
    return _digest_of_files(run_dir, _run_files(run_dir), stored)


def _digest_of_files(base: Path, files: Sequence[Path], stored: str | None) -> _Digest:
    """Digest *files*, relative to *base*, hashing only when it has to.

    Takes the file list rather than finding it, because the two things digested
    are found differently: a run is its whole subtree, and the library fragment
    is exactly the two files ``adapt_library`` reads. An absent file is dropped
    from the list rather than recorded as absent, so the digest of a directory
    that is not there is the digest of nothing — which is stable, and compares
    equal to the next scan of the same absence.
    """
    files = [path for path in files if path.is_file()]
    fingerprint = _fingerprint(base, files)
    stored_fingerprint, stored_content = _split(stored)
    if stored_fingerprint is not None and fingerprint == stored_fingerprint:
        # Nothing was touched, so the stored content hash still describes the
        # bytes on disk. Recomputing it would read every file in the run to
        # learn what the row already says.
        return _Digest(fingerprint, stored_content or "")
    content, problems = _content_hash(base, files)
    return _Digest(fingerprint, content, tuple(problems))


# --------------------------------------------------------------------------
# 4. Rows — the record verbatim, plus the columns that narrow it
# --------------------------------------------------------------------------


def _column_values(record: Mapping[str, Any], model: str) -> tuple[Any, ...]:
    """The extracted filter columns the DDL declares for *model*.

    Extracted, never interpreted. ``schema.py`` is explicit that these columns
    are indexes and the ``repository`` predicates are the specification, so a
    value is copied out of the record with ``.get`` and stored as it is: a
    missing confidence is ``NULL`` here and is *failed* by ``matches_entity``
    there, and those are not the same test.
    """
    if model == "source":
        status = record.get("status")
        overall = status.get("overall") if isinstance(status, Mapping) else None
        return (record.get("source_type"), overall)
    if model == "artifact":
        return (record.get("source_id"),)
    if model == "entity_ref":
        confidence = record.get("confidence")
        numeric = isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        return (
            record.get("source_id"),
            record.get("provenance_class"),
            record.get("kind"),
            confidence if numeric else None,
        )
    return (
        record.get("source_id"),
        record.get("relation_vocabulary"),
        record.get("from_id"),
        record.get("to_id"),
    )


_INSERTS: Mapping[str, str] = {
    "source": (
        "INSERT INTO sources (identity, digest, doc, source_type, status_overall) "
        "VALUES (?, ?, ?, ?, ?)"
    ),
    "artifact": "INSERT INTO artifacts (identity, digest, doc, source_id) VALUES (?, ?, ?, ?)",
    "entity_ref": (
        "INSERT INTO entities (identity, digest, doc, source_id, provenance_class, kind, "
        "confidence) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ),
    "indexed_relation": (
        "INSERT INTO relations (identity, digest, doc, source_id, relation_vocabulary, "
        "from_id, to_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ),
}


def _insert_records(connection: sqlite3.Connection, records: IndexRecords) -> None:
    """Store every record verbatim, with its identity and its content digest.

    A plain ``INSERT``. The ``PRIMARY KEY`` on ``identity`` is what makes the
    paging order total, so a collision must *fail* rather than be resolved by
    ``OR REPLACE``, which is last-write-wins — the silent loss
    ``adapt_project`` warns about for two runs declaring one ``video_id``.
    :func:`check_index_integrity` has already refused that case by name; this is
    the belt that catches whatever the braces missed.
    """
    by_model = records.by_model()
    for model, _table in MODELS:
        statement = _INSERTS[model]
        for record in by_model[model]:
            try:
                connection.execute(
                    statement,
                    (
                        identity(record, model),
                        content_digest(record),
                        json.dumps(record),
                        *_column_values(record, model),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise IndexCorrupt(
                    f"the index cannot store {model} {identity(record, model)!r}: {exc}. "
                    "One record, one id — an index that kept the last writer would "
                    "silently lose the other record"
                ) from exc


def _records_of(
    connection: sqlite3.Connection, source_ids: Iterable[str | None]
) -> IndexRecords:
    """Read back the stored records belonging to *source_ids*, verbatim.

    Needed because the integrity check is project-wide: two run directories may
    declare the same ``video_id``, and a refresh that looked only at the run it
    re-adapted could not see the collision — neither run is wrong on its own.
    ``None`` selects the library fragment, whose records belong to no source
    (D-016).
    """
    records = IndexRecords()
    families: Mapping[str, list[dict[str, Any]]] = {
        "source": records.sources,
        "artifact": records.artifacts,
        "entity_ref": records.entities,
        "indexed_relation": records.relations,
    }
    for source_id in source_ids:
        for model, table in MODELS:
            if source_id is None:
                if model == "source":
                    # The library emits no Source record: it is not an ingested
                    # source, and inventing one would give every concept an
                    # owner it does not have.
                    continue
                rows = connection.execute(
                    f"SELECT doc FROM {table} WHERE source_id IS NULL"
                ).fetchall()
            else:
                column = "identity" if model == "source" else "source_id"
                rows = connection.execute(
                    f"SELECT doc FROM {table} WHERE {column} = ?", (source_id,)
                ).fetchall()
            families[model].extend(json.loads(row["doc"]) for row in rows)
    return records


def _evict(connection: sqlite3.Connection, source_id: str | None) -> None:
    """Remove every record belonging to one source, or to the library.

    ``source_id is None`` is the library fragment: its concepts and its
    ``expresses_concept`` edges carry ``source_id: null`` by construction, so
    that is what addresses them.
    """
    if source_id is None:
        for table in _MEMBER_TABLES:
            connection.execute(f"DELETE FROM {table} WHERE source_id IS NULL")
        return
    connection.execute("DELETE FROM sources WHERE identity = ?", (source_id,))
    for table in _MEMBER_TABLES:
        connection.execute(f"DELETE FROM {table} WHERE source_id = ?", (source_id,))


# --------------------------------------------------------------------------
# 5. One run's outcome
# --------------------------------------------------------------------------

#: The three outcomes a discovered run can have. Every one is reported.
_REINDEXED = "reindexed"
_UNCHANGED = "unchanged"
_SKIPPED = "skipped"


@dataclass(frozen=True)
class _Run:
    """What the scan decided about one discovered run directory."""

    canonical_dir: str
    state: str
    digest: _Digest
    records: IndexRecords | None = None
    source_id: str | None = None
    problems: tuple[str, ...] = ()
    reason: str | None = None
    #: Whether this run had records in the index *before* this scan. It decides
    #: whether the library's cross-source projection can still be trusted.
    had_records: bool = False


def _examine(
    run_dir: Path,
    *,
    project_root: Path,
    prior: sqlite3.Row | None,
    strict: bool,
) -> _Run:
    """Decide one run: unchanged, re-adapted, or skipped and named."""
    canonical_dir = project_relative(run_dir, project_root)
    stored = prior["digest"] if prior is not None else None
    digest = _digest_of(run_dir, stored)
    had_records = prior is not None and prior["skipped_reason"] is None
    _stored_fingerprint, stored_content = _split(stored)

    # Only the content half decides. A file whose mtime moved but whose bytes
    # are identical is not a re-run, and the row is rewritten below either way,
    # so the next scan gets the cheap answer again.
    if prior is not None and stored_content is not None and digest.content == stored_content:
        if prior["skipped_reason"]:
            # Still broken, still named. Re-reporting the stored reason is what
            # keeps a cheap refresh from quietly dropping a run an earlier scan
            # could not index.
            return _Run(
                canonical_dir,
                _SKIPPED,
                digest,
                reason=prior["skipped_reason"],
                had_records=False,
            )
        return _Run(
            canonical_dir,
            _UNCHANGED,
            digest,
            source_id=prior["source_id"],
            problems=tuple(_stored_problems(prior)),
            had_records=True,
        )

    try:
        records = adapt_run(run_dir, project_root)
    except AdapterError as exc:
        if strict:
            # `adapt_project` refuses the whole project here, and `T-104` needs
            # a mode that agrees with its oracle record for record.
            raise
        return _Run(
            canonical_dir,
            _SKIPPED,
            digest,
            reason=_project_relative_reason(str(exc), run_dir, canonical_dir),
            had_records=had_records,
        )

    problems = list(digest.problems)
    for source in records.sources:
        problems.extend(_adapter_problems(source))
    return _Run(
        canonical_dir,
        _REINDEXED,
        digest,
        records=records,
        source_id=records.sources[0]["id"] if records.sources else None,
        problems=tuple(problems),
        had_records=had_records,
    )


def _adapter_problems(source: Mapping[str, Any]) -> list[str]:
    """What the adapter says it could not map, as plain sentences.

    ``adapter_metadata`` is the one place in the frozen ``Source`` record where
    an adapter may report an omission, and it is *absent* rather than empty when
    there is nothing to report. Both keys it may carry are read; neither is
    invented, and an empty list stays an empty list.
    """
    metadata = source.get("adapter_metadata")
    if not isinstance(metadata, Mapping):
        return []
    problems: list[str] = []
    for key in ("unreadable_files", "unmappable_artifacts"):
        entries = metadata.get(key)
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
            continue
        for entry in entries:
            if isinstance(entry, Mapping):
                problems.append(f"{key}: {entry.get('path')}: {entry.get('reason')}")
            else:
                problems.append(f"{key}: {entry}")
    return problems


def _checked_library(
    library: IndexRecords, runs: IndexRecords
) -> tuple[IndexRecords, str | None]:
    """The library fragment, or nothing and the reason it cannot be indexed.

    ``library/graph.json`` is a **projection over the runs**, and it is rebuilt
    by ``rebuild_library`` rather than by this scanner, so it goes stale the
    moment a run directory is deleted: its ``expresses_concept`` edges still name
    knowledge units that no longer exist anywhere. ``adapt_project`` refuses the
    whole project in that state, and it is right to — an edge to an entity the
    index does not carry cannot be drawn, so the graph omits it while
    ``/api/sources/{id}/relations`` still lists it, which is the two-views-
    disagree defect ADR 0004 exists to prevent.

    Refusing the whole build is too much, though: every surviving run is
    perfectly indexable, and the stale part is one cross-source projection. So
    the fragment is dropped as a whole and named — D-043 tier 1, applied to the
    library.

    The dangling edges are deliberately **not** filtered out one by one. That
    would reshape the library graph with no report at all, and leave concepts
    asserting they are expressed by nothing. Dropping the fragment loudly is a
    fact a reader can act on; a quietly thinner graph is not.
    """
    entities = {entity["global_id"] for entity in (*runs.entities, *library.entities)}
    dangling = [
        f"{relation.get('id')!r} names {side} {relation.get(side)!r}"
        for relation in library.relations
        for side in ("from_id", "to_id")
        if relation.get(side) not in entities
    ]
    if not dangling:
        return library, None
    shown = dangling[:5]
    if len(dangling) > len(shown):
        shown.append(f"… and {len(dangling) - len(shown)} more")
    return IndexRecords(), (
        "the library graph is stale: " + "; ".join(shown) + ", which no entity record "
        "has. The whole library fragment is dropped rather than committed with an edge "
        "no page can draw, and rather than filtered down to a thinner graph nobody "
        "reported. Run rebuild_library to bring output/library/ back in step with the "
        "runs that are actually present"
    )


def _library_damage(output_root: Path) -> str | None:
    """The reason ``library/`` cannot be indexed, or ``None``.

    ``adapt_library`` returns an empty record set for *both* an absent library
    and a damaged one, and the second reaches a reader as "0 concepts" with
    nothing to say otherwise — the silent zero D-043 exists to forbid. The
    distinction is drawn here with the reader that already draws it: an absent
    file is ``(None, None)``, while a present unreadable one carries its reason.
    """
    library_dir = output_root / LIBRARY_DIR_NAME
    reasons = []
    for name in _LIBRARY_FILES:
        _document, reason = read_optional_json_or_reason(library_dir / name)
        if reason is not None:
            reasons.append(f"{name}: {reason}")
    if not reasons:
        return None
    return (
        "; ".join(reasons)
        + " — the library fragment is not indexed, because indexing zero concepts "
        "would state that the project has none"
    )


# --------------------------------------------------------------------------
# 6. The build lifecycle
# --------------------------------------------------------------------------


def _write_state(
    connection: sqlite3.Connection,
    state: str,
    *,
    built_at: str | None = None,
    message: str | None = None,
) -> None:
    """Set the single ``index_state`` row. Its ``CHECK`` enforces the singleton."""
    connection.execute(
        "INSERT OR REPLACE INTO index_state (id, state, built_at, message) "
        "VALUES (1, ?, ?, ?)",
        (state, built_at, message),
    )


def _stored_state(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT state FROM index_state WHERE id = 1").fetchone()
    return row["state"] if row is not None else "absent"


def _stored_runs(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        row["canonical_dir"]: row
        for row in connection.execute(
            "SELECT canonical_dir, source_id, digest, problems, skipped_reason FROM runs"
        ).fetchall()
    }


def _stored_problems(row: sqlite3.Row) -> list[str]:
    """The problems an earlier scan recorded, so a refresh re-reports them."""
    try:
        stored = json.loads(row["problems"])
    except (TypeError, ValueError):
        return []
    return [str(problem) for problem in stored] if isinstance(stored, list) else []


def _write_run(connection: sqlite3.Connection, run: _Run) -> None:
    """Record what this scan decided, for the scan after it.

    Written for every discovered run, including the unchanged ones: the digest's
    cheap half moves when a file is touched, and storing it again is what keeps
    the *next* scan cheap.
    """
    connection.execute(
        "INSERT OR REPLACE INTO runs (canonical_dir, source_id, digest, scanned_at, "
        "problems, skipped_reason) VALUES (?, ?, ?, ?, ?, ?)",
        (
            run.canonical_dir,
            run.source_id,
            run.digest.stored,
            datetime.now(timezone.utc).isoformat(),
            json.dumps(list(run.problems)),
            run.reason,
        ),
    )


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def _scan(
    project_root: Path,
    *,
    output_dir: str,
    incremental: bool,
    strict: bool,
    index_documents: DocumentIndexer | None,
) -> ScanReport:
    """One scan, whole or incremental. Both entry points land here."""
    project_root = Path(project_root).expanduser().resolve()
    output_root = project_root / output_dir
    connection = schema.connect(schema.database_path(project_root))
    try:
        version = schema.migrate(connection)
        # An index that never reached `ready` has no completed build to be
        # incremental against, so a refresh over one degrades to a full build
        # rather than carrying rows forward on the strength of a state that
        # already says they cannot be trusted.
        whole = not incremental or _stored_state(connection) != "ready"
        # Committed on its own, before any work: a crash from here on reopens as
        # `building`, never as a `ready` half-full index.
        with connection:
            _write_state(connection, "building")
        try:
            return _apply(
                connection,
                project_root=project_root,
                output_root=output_root,
                whole=whole,
                strict=strict,
                index_documents=index_documents,
                version=version,
            )
        except Exception as exc:
            # Reported, not swallowed. The state becomes `error` with the
            # message, so a reader can say *why* rather than saying `absent`.
            with connection:
                _write_state(connection, "error", message=f"{type(exc).__name__}: {exc}")
            raise
    finally:
        connection.close()


def _apply(
    connection: sqlite3.Connection,
    *,
    project_root: Path,
    output_root: Path,
    whole: bool,
    strict: bool,
    index_documents: DocumentIndexer | None,
    version: int,
) -> ScanReport:
    previous = {} if whole else _stored_runs(connection)
    discovered = run_dirs(output_root)

    runs = [
        _examine(
            run_dir,
            project_root=project_root,
            prior=previous.get(project_relative(run_dir, project_root)),
            strict=strict,
        )
        for run_dir in discovered
    ]
    library_dir = output_root / LIBRARY_DIR_NAME
    library_key = project_relative(library_dir, project_root)
    # The library keeps a `runs` row of its own, keyed by its own
    # project-relative directory. It is not a run — `run_dirs` never yields it —
    # but the row is exactly what the table is for: what the scanner remembers so
    # it can decide "unchanged" without re-deriving. Without it, a
    # `rebuild_library` that changed no run at all would leave the fragment as
    # this scan last saw it, which is a stale answer arrived at cheaply.
    seen = {run.canonical_dir for run in runs} | {library_key}
    evicted = sorted(set(previous) - seen)

    # `library/` is a cross-source projection over every run, so any change to
    # the records of any run can change it: one re-adapted, one gone, or one
    # that *had* records and can no longer be indexed at all.
    records_changed = (
        whole
        or bool(evicted)
        or any(run.state == _REINDEXED for run in runs)
        or any(run.state == _SKIPPED and run.had_records for run in runs)
    )
    # The runs' own records first: carried over from the index for the unchanged
    # ones, freshly adapted for the rest. Reading the carried ones back matters
    # because the checks below are project-wide — a duplicate `video_id` across
    # two directories only shows up in the union, and the endpoint of a library
    # edge may live in a run this scan never touched.
    combined = _records_of(
        connection,
        [run.source_id for run in runs if run.state == _UNCHANGED and run.source_id],
    )
    for run in runs:
        if run.records is not None:
            combined = combined + run.records

    prior_library = previous.get(library_key)
    library_digest = _digest_of_files(
        library_dir,
        [library_dir / name for name in _LIBRARY_FILES],
        prior_library["digest"] if prior_library is not None else None,
    )
    rebuild_library_fragment = (
        records_changed
        or prior_library is None
        or library_digest.content != _split(prior_library["digest"])[1]
    )
    if not rebuild_library_fragment:
        # Nothing the fragment is derived from moved, so the stored records — or
        # the stored refusal — are still the answer.
        library = _records_of(connection, [None])
        library_reason = prior_library["skipped_reason"]
    else:
        library_reason = _library_damage(output_root)
        if library_reason is not None:
            library = IndexRecords()
        else:
            library, library_reason = _checked_library(
                adapt_library(library_dir, project_root), combined
            )
    combined = combined + library

    try:
        check_index_integrity(combined.by_model())
    except RepositoryError as exc:
        raise IndexCorrupt(
            f"{exc} — the scan is refused rather than committed: no honest page can be "
            "drawn from these records"
        ) from exc

    built_at = datetime.now(timezone.utc).isoformat()
    with connection:
        if whole:
            connection.execute("DELETE FROM runs")
            for _model, table in MODELS:
                connection.execute(f"DELETE FROM {table}")
        else:
            # Both loops evict by the id the *previous* scan recorded, so a run
            # that changed its `video_id` does not leave its old records behind
            # under an id nothing points at any more. A stored `NULL` means the
            # run had no records to evict — and must never be passed to
            # `_evict`, where `None` addresses the *library* fragment instead.
            for key in evicted:
                if previous[key]["source_id"] is not None:
                    _evict(connection, previous[key]["source_id"])
                connection.execute("DELETE FROM runs WHERE canonical_dir = ?", (key,))
            for run in runs:
                prior = previous.get(run.canonical_dir)
                if run.state != _UNCHANGED and prior is not None:
                    if prior["source_id"] is not None:
                        _evict(connection, prior["source_id"])
            if rebuild_library_fragment:
                _evict(connection, None)

        for run in runs:
            if run.records is not None:
                _insert_records(connection, run.records)
            _write_run(connection, run)
        if rebuild_library_fragment:
            _insert_records(connection, library)
        _write_run(
            connection,
            _Run(
                library_key,
                _REINDEXED if rebuild_library_fragment else _UNCHANGED,
                library_digest,
                reason=library_reason,
            ),
        )

        # `documents` and the two external-content FTS5 tables belong to
        # `T-103`: keeping an external-content index in step with its content
        # table is that module's contract, and half-populating them here would
        # leave a searchable corpus nobody owns. The hook is called with the
        # records this scan committed, inside the same transaction, so wiring it
        # up is `index_documents=search.index_documents` and nothing else.
        if index_documents is not None:
            index_documents(connection, combined)

        _write_state(connection, "ready", built_at=built_at)

    skipped_runs = [
        {"relative_path": run.canonical_dir, "reason": run.reason}
        for run in runs
        if run.state == _SKIPPED
    ]
    if library_reason is not None:
        skipped_runs.append({"relative_path": library_key, "reason": library_reason})
    return ScanReport(
        runs_discovered=len(discovered),
        runs_indexed=sum(1 for run in runs if run.state != _SKIPPED),
        runs_skipped=sum(1 for run in runs if run.state == _SKIPPED),
        runs_unchanged=sum(1 for run in runs if run.state == _UNCHANGED),
        runs_evicted=len(evicted),
        skipped_runs=tuple(skipped_runs),
        incomplete_runs=tuple(
            {
                "relative_path": run.canonical_dir,
                "source_id": run.source_id,
                "problems": list(run.problems),
            }
            for run in runs
            if run.problems
        ),
        counts=MappingProxyType(
            {
                "sources": _count(connection, "sources"),
                "artifacts": _count(connection, "artifacts"),
                "entities": _count(connection, "entities"),
                "relations": _count(connection, "relations"),
            }
        ),
        index_version=version,
        built_at=built_at,
        library_reindexed=rebuild_library_fragment,
        library_skipped_reason=library_reason,
    )


# --------------------------------------------------------------------------
# 7. The two entry points
# --------------------------------------------------------------------------


def build_index(
    project_root: Path,
    *,
    output_dir: str = "output",
    strict: bool = False,
    index_documents: DocumentIndexer | None = None,
) -> ScanReport:
    """Build the index from scratch, discarding whatever was stored.

    Every run is re-adapted, so the result depends on nothing the cache
    remembers. That is what makes the cache disposable: ADR 0001 invariant 3
    says deleting it must lose nothing, and this is the function that keeps that
    promise true.

    *strict* reproduces ``adapt_project``'s refusal: an ``AdapterError`` from
    any run propagates instead of being recorded as a skipped run. The default
    is the D-043 behaviour — skip that run, name it, index the rest.

    *index_documents* is the hook that fills ``documents`` and the two FTS5
    tables. It is called inside the write transaction with the connection and
    the full record set; ``T-103``'s ``search.index_documents`` is the intended
    argument, and this module never imports it, so the two stay independently
    testable.
    """
    return _scan(
        project_root,
        output_dir=output_dir,
        incremental=False,
        strict=strict,
        index_documents=index_documents,
    )


def refresh_index(
    project_root: Path,
    *,
    output_dir: str = "output",
    strict: bool = False,
    index_documents: DocumentIndexer | None = None,
) -> ScanReport:
    """Bring the index up to date, re-adapting only what changed.

    Three outcomes per run, and every one of them is reported: **unchanged**,
    where the stored digest still describes the directory and no work is done;
    **changed or new**, where the run is re-adapted and its old records are
    replaced; and **removed**, where the directory has gone and its records are
    evicted from every table. ``library/`` is re-derived whenever any run's
    records changed, because it is a projection over all of them.

    A refresh against an index that never reached ``ready`` — absent, mid-build,
    crashed, failed — is a full build.
    """
    return _scan(
        project_root,
        output_dir=output_dir,
        incremental=True,
        strict=strict,
        index_documents=index_documents,
    )
