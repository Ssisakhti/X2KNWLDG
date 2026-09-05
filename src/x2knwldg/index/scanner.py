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
import os.path
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .. import synthesis
from ..adapters import (
    LIBRARY_DIR_NAME,
    AdapterError,
    IndexRecords,
    adapt_library,
    adapt_run,
    project_relative,
    read_optional_json_or_reason,
)
from ..io import discover_run_dirs, scrub_host_paths, sha256_file
from ..io import run_dirs as io_run_dirs
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

#: The source layer's per-source tables (`T-254`). Separate from
#: :data:`_MEMBER_TABLES` because that tuple is also what the library fragment
#: is evicted from, and the library owns no source node and no brief: both of
#: these declare ``source_id NOT NULL``, so a ``source_id IS NULL`` delete over
#: them would be a statement about rows that cannot exist.
_SOURCE_MEMBER_TABLES: tuple[str, ...] = ("source_entities", "source_briefs")

#: Every table a whole build discards, in addition to the four record families.
#: ``source_relations`` is here and not in :data:`_SOURCE_MEMBER_TABLES`: it
#: belongs to the corpus rather than to any one source, exactly as the canonical
#: file it is read from sits beside the runs rather than inside one (D-247).
_SOURCE_TABLES: tuple[str, ...] = (*_SOURCE_MEMBER_TABLES, "source_relations")

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
#: The hook `T-103` wires in. Its return value is deliberately unconstrained
#: and unread here: `search.document_indexer` returns an `IndexReport` because
#: a caller that wants to know what one pass did should not have to re-query,
#: and this module ignores it. `None` in the alias made every real
#: implementation the wrong type (D-114).
DocumentIndexer = Callable[[sqlite3.Connection, IndexRecords], object]


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

    D-158: the rules were mirrored here rather than shared, on the argument
    that "a second opinion about which directories are runs would be a second
    index" — which was right, and is why they are now *called* rather than
    restated. :func:`io.discover_run_dirs` is the one implementation, and it
    added the clause all three copies were missing: a directory resolving to
    one already discovered is an alias, not a second run.
    """
    return io_run_dirs(output_root)


def _canonical_key(path: Path, project_root: Path) -> tuple[str, str | None]:
    """``(canonical_dir, reason)`` for a discovered run or the library fragment.

    Defect D-078: ``project_relative`` calls ``.resolve()``, so a run directory
    that is a *symlink* to somewhere outside the project resolves outside it and
    the call raises ``AdapterError``. That call was the first statement of
    ``_examine`` — **outside** the ``try:`` that implements the D-043
    skip-and-name contract — and it appeared a second time inside ``_apply``'s
    prior-row lookup. So one symlinked directory under ``output/`` took the
    entire index down even with ``strict=False``: the scan left
    ``state='error'`` with the old counts still in the row, and every endpoint
    answered ``503`` for every run. ``run_dirs`` globs ``*/metadata.json`` and
    ``glob`` follows directory symlinks, so an ordinary "runs live on an
    external drive" setup reaches it.

    The directory still has a place *in the project*: where the scan found it,
    before resolution. That is the row's key — computed lexically, so a
    symlink's target cannot change it — and the reason says why nothing can be
    read through it. The reason names the project-relative key only: the
    resolved target is a host path, and ``skipped_runs[].reason`` is served by
    ``/api/status`` (D-030, ADR-0003).
    """
    try:
        return project_relative(path, project_root), None
    except AdapterError:
        key = _lexical_key(path, project_root)
        return key, (
            f"{key} resolves outside the project root; index records carry "
            "project-relative paths only (risk R15)"
        )


def _lexical_key(path: Path, project_root: Path) -> str:
    """*path*'s place in the project, computed without resolving it.

    Where the scan *found* the directory, which is a symlink's own identity
    rather than its target's. D-078 needs it because resolution raises for a
    link pointing outside the root; D-158 needs it because resolution
    *succeeds* for a link pointing at another run, and hands back the target's
    key — which is the collision that refused the whole index.
    """
    root = Path(os.path.abspath(project_root.expanduser()))
    lexical = Path(os.path.abspath(path.expanduser()))
    try:
        return lexical.relative_to(root).as_posix()
    except ValueError:
        # Not under the project root even before resolution. `run_dirs` globs
        # under `output_root`, so this needs an `output_root` from outside the
        # project; the bare name still keys a row and still names the run.
        return path.name


def _project_relative_reason(
    reason: str, run_dir: Path, canonical_dir: str, project_root: Path
) -> str:
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
    # D-085: this was that `replace` alone, which redacts only paths *under*
    # the run directory — while `project_relative`'s own message also names the
    # absolute project root, and a symlink names a path outside the run
    # entirely. Both spellings of the run directory are offered because
    # `AdapterError` names the *resolved* one, and `scrub_host_paths` reduces
    # whatever is still absolute afterwards rather than trusting this list to
    # be complete.
    return scrub_host_paths(
        reason,
        [
            (run_dir.expanduser().resolve(), canonical_dir),
            (run_dir, canonical_dir),
            (project_root.expanduser().resolve(), "the project root"),
            (project_root, "the project root"),
        ],
    )


def _run_files(run_dir: Path) -> list[Path]:
    """Every regular file **of the run**, sorted by path. Symlinks excluded.

    Defect D-100: ``path.is_file()`` follows symlinks, so a symlinked file
    inside a run put its *target* into the digest — and ``io.sha256_file`` then
    read that target in full on every scan, for a file the run does not own.
    Worse, the digest changed when something outside the run changed and did
    not change when the link was repointed at identical bytes, so "unchanged"
    stopped meaning what the incremental scan needs it to mean.

    A run's digest is the bytes the run holds. What a link points at is
    reported by the adapter as an unmappable artifact instead (see
    ``youtube._file_artifact``), which is where a thing the index cannot
    address belongs.
    """
    return sorted(
        path
        for path in run_dir.rglob("*")
        if path.name not in IGNORED_FILENAMES and path.is_file() and not path.is_symlink()
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
    if model in ("artifact", "source_entity"):
        return (record.get("source_id"),)
    if model == "source_relation":
        return (record.get("from_source_id"), record.get("to_source_id"))
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
    "source_entity": (
        "INSERT INTO source_entities (identity, digest, doc, source_id) "
        "VALUES (?, ?, ?, ?)"
    ),
    "source_relation": (
        "INSERT INTO source_relations (identity, digest, doc, from_source_id, "
        "to_source_id) VALUES (?, ?, ?, ?, ?)"
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
    families = [(model, by_model[model]) for model, _table in MODELS]
    # `T-254`. The fifth family, stored into its own table rather than appended
    # to `entities` — D-251 in the schema, not only in the adapter.
    families.append(("source_entity", records.source_entities))
    for model, rows in families:
        statement = _INSERTS[model]
        for record in rows:
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
    for table in (*_MEMBER_TABLES, *_SOURCE_MEMBER_TABLES):
        connection.execute(f"DELETE FROM {table} WHERE source_id = ?", (source_id,))


def _write_brief(connection: sqlite3.Connection, run: _Run) -> None:
    """Store what ``synthesis.brief_state`` said about one run's brief (`T-254`).

    A row is written for **every** indexed run, including one with no brief at
    all. ``unavailable`` with a reason is an answer about the source; a missing
    row would make "this run has no brief" and "this run is not in the index"
    the same silence, and the Source Map has to tell them apart.

    ``doc`` is the document when there is one to show and ``NULL`` when there is
    not — which is ``available`` and ``stale``, and not ``unavailable``. A stale
    brief is carried rather than withheld: the record exists, it describes
    inputs whose digests have moved, and the state says so out loud, which is
    the whole reason ``stale`` is a state rather than an error.
    """
    if run.source_id is None or run.brief is None:
        return
    connection.execute(
        "INSERT INTO source_briefs (source_id, state, reason, doc) VALUES (?, ?, ?, ?)",
        (
            run.source_id,
            run.brief["state"],
            run.brief["reason"],
            None if run.brief["brief"] is None else json.dumps(run.brief["brief"]),
        ),
    )


def _write_source_relations(connection: sqlite3.Connection, output_root: Path) -> None:
    """Replace the stored cross-source synthesis with what the file holds (`T-254`).

    Rewritten on **every** scan, whole or incremental, and deliberately without
    a ``runs`` row of its own. ``output/synthesis/source_relations.json`` is one
    small file that belongs to no run — ``io.NOT_A_RUN`` names its directory
    beside ``library/`` — so there is no per-run digest that could decide it was
    unchanged, and giving it a row in a table keyed by *run directory* would
    make it look like a run to every count that reads that table. Re-reading one
    file is cheaper than the bookkeeping that would avoid it.

    The read is ``artifacts.source_relations_document``, the same function the
    cache-free oracle uses, so a damaged file yields no relations on both paths
    rather than an exception on one and an empty answer on the other. Imported
    here rather than at module scope: the scanner is reachable from the CLI's
    index branch, and ``artifacts`` pulls in the whole pipeline layer.
    """
    from ..artifacts import source_relations_document

    connection.execute("DELETE FROM source_relations")
    for relation in source_relations_document(output_root):
        connection.execute(
            _INSERTS["source_relation"],
            (
                identity(relation, "source_relation"),
                content_digest(relation),
                json.dumps(relation),
                *_column_values(relation, "source_relation"),
            ),
        )


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
    #: ``synthesis.brief_state`` for this run, or ``None`` when the run was not
    #: re-read on this pass. Read here rather than in ``_apply`` because this is
    #: the one place that has the run directory *and* has decided the run is
    #: worth re-reading; an unchanged run keeps the row the last pass wrote,
    #: which is the same bargain every other record family makes.
    brief: dict[str, object] | None = None
    #: Whether this run had records in the index *before* this scan. It decides
    #: whether the library's cross-source projection can still be trusted.
    had_records: bool = False


def _examine(
    run_dir: Path,
    *,
    project_root: Path,
    canonical_dir: str,
    unindexable: str | None,
    prior: sqlite3.Row | None,
    strict: bool,
) -> _Run:
    """Decide one run: unchanged, re-adapted, or skipped and named.

    D-078: ``canonical_dir`` arrives as a parameter rather than being computed
    here, so the string that keys the prior-row lookup in ``_apply`` and the
    string that keys the row written below are the same one, and neither can
    raise from outside the skip-and-name path.
    """
    stored = prior["digest"] if prior is not None else None
    digest = _digest_of(run_dir, stored)
    had_records = prior is not None and prior["skipped_reason"] is None
    if unindexable is not None:
        # D-078. `strict` refuses the whole project so that `T-104`'s oracle,
        # which raises here too, still agrees record for record.
        if strict:
            raise AdapterError(unindexable)
        return _Run(canonical_dir, _SKIPPED, digest, reason=unindexable, had_records=had_records)
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
            reason=_project_relative_reason(
                str(exc), run_dir, canonical_dir, project_root
            ),
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
        # `T-254`. Never raises, so a damaged brief cannot cost the run its
        # index entry — which is the same promise `brief_state` makes one layer
        # down, kept here rather than restated.
        brief=synthesis.brief_state(run_dir),
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
    return _stored_state_row(connection)[0]


def _stored_state_row(connection: sqlite3.Connection) -> tuple[str, str | None]:
    """``(state, built_at)`` as stored, or ``("absent", None)``."""
    row = connection.execute(
        "SELECT state, built_at FROM index_state WHERE id = 1"
    ).fetchone()
    if row is None:
        return "absent", None
    return row["state"], row["built_at"]


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
        previous_state, previous_built_at = _stored_state_row(connection)
        whole = not incremental or previous_state != "ready"
        # Committed on its own, before any work: a crash from here on reopens as
        # `building`, never as a `ready` half-full index.
        #
        # D-162: `built_at` is carried forward rather than cleared. Every write
        # `_apply` makes is inside one transaction, so a reader during a build —
        # or after a build that was killed — sees the *previous* generation,
        # whole. Clearing `built_at` threw that away: SIGKILL a refresh and the
        # tables still held the full previous index, but `state='building'` with
        # `built_at=None` made `_require_ready` refuse every endpoint, so an
        # intact library cost a full rebuild to get back. This is D-086's own
        # reasoning — "the stored records are exactly what they were and
        # refusing every endpoint would cost the reader a library they can still
        # be shown" — applied to the crash path, which is the likelier one.
        # `building` with no `built_at` still means what it always meant: no
        # build has ever finished here, so there is nothing to serve.
        with connection:
            _write_state(connection, "building", built_at=previous_built_at)
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
            # Reported, not swallowed — and D-085: the message is served
            # verbatim in a 503 body, so no host path may survive into it.
            message = scrub_host_paths(
                f"{type(exc).__name__}: {exc}",
                [
                    (project_root.expanduser().resolve(), "the project root"),
                    (project_root, "the project root"),
                ],
            )
            with connection:
                if previous_state == "ready":
                    # D-086: `_apply` does every write inside one `with
                    # connection:`, so a failure rolls all of them back and the
                    # stored records are exactly what they were. Committing
                    # `error` here anyway made `_require_ready` refuse every
                    # endpoint for every run — so adding one run that
                    # duplicates an existing `video_id` cost the reader the
                    # whole library until the cause was removed. The index is
                    # still readable and still as fresh as its `built_at` says;
                    # what failed is *this scan*, and that is what the message
                    # now says.
                    _write_state(
                        connection,
                        "ready",
                        built_at=previous_built_at,
                        message=f"the last scan failed and was rolled back: {message}",
                    )
                else:
                    _write_state(connection, "error", message=message)
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
    discovered, aliases = discover_run_dirs(output_root)

    runs = []
    for alias, target in aliases:
        # D-158. Named rather than dropped: a run that vanishes from the
        # library with nothing said is the failure D-043 exists to prevent, and
        # before this the symptom was the *whole index* refused for a duplicate
        # `video_id` that no directory in the project actually declared twice.
        # The key is lexical — `_canonical_key` resolves, and resolving is
        # precisely what makes the alias collide with its target's row. `strict`
        # does not raise here: `adapt_project` skips the alias too, so the
        # oracle and the index still agree record for record.
        alias_key = _lexical_key(alias, project_root)
        target_key, _ = _canonical_key(target, project_root)
        runs.append(
            _Run(
                alias_key,
                _SKIPPED,
                _digest_of(alias, None),
                reason=(
                    f"{alias_key} resolves to {target_key}, which this scan already "
                    "indexed; it is an alias of that run, not a second one"
                ),
                had_records=False,
            )
        )
    for run_dir in discovered:
        # D-078: one computation of the key, used for the lookup and the row.
        canonical_dir, unindexable = _canonical_key(run_dir, project_root)
        runs.append(
            _examine(
                run_dir,
                project_root=project_root,
                canonical_dir=canonical_dir,
                unindexable=unindexable,
                prior=previous.get(canonical_dir),
                strict=strict,
            )
        )
    library_dir = output_root / LIBRARY_DIR_NAME
    library_key, library_unindexable = _canonical_key(library_dir, project_root)
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
        # `rebuild_library_fragment` is false only when `prior_library` exists —
        # it is one of the disjuncts that sets it — but the checker cannot see
        # that, and neither can a reader in a hurry.
        library_reason = prior_library["skipped_reason"] if prior_library is not None else None
    elif library_unindexable is not None:
        # D-078: the same class as a symlinked run. A `library/` that resolves
        # outside the project has no project-relative form, and this used to
        # raise out of the middle of the scan rather than be named. Not raised
        # under `strict` because `_library_damage` below is not either: the
        # fragment is a projection, and a project whose runs are all readable
        # is still a readable project.
        library = IndexRecords()
        library_reason = library_unindexable
    else:
        library_reason = _library_damage(output_root)
        if library_reason is not None:
            library = IndexRecords()
        else:
            library, library_reason = _checked_library(
                adapt_library(library_dir, project_root), combined
            )
    if library_reason is not None:
        # D-085/D-087: `_library_damage` builds its reason out of
        # `io.JsonReadError`, which names the file absolutely — and D-087 put
        # that reason on `/api/status`, so surfacing it without this would have
        # traded a silent zero for a host-path leak. The fragment's own
        # directory is offered as a replacement so the sentence still says
        # which file, and the catch-all takes care of the rest.
        library_reason = _project_relative_reason(
            library_reason, library_dir, library_key, project_root
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
            # `T-254`. The source layer's tables are discarded with the rest:
            # `build_index` promises to discard "whatever was stored", and a
            # family left behind by that loop is exactly the defect D-088
            # records for the search corpus.
            for table in _SOURCE_TABLES:
                connection.execute(f"DELETE FROM {table}")
            # D-088: `build_index`'s docstring promises it discards "whatever
            # was stored", and this loop discarded everything *except* the
            # search corpus — `documents` and the two FTS5 tables were left to
            # `index_documents`, which defaults to `None`. So
            # `build_index(root)`, the default signature, rebuilt every record
            # family and left the corpus from the previous pass: measured, a
            # unit's edited content was unfindable while its deleted text was
            # still being returned, with `total` counting it.
            #
            # This is not the "half-populating" the note below rules out. It is
            # the same discard as the lines above, and it needs none of
            # `search`'s per-source logic: `delete-all` is FTS5's own bulk
            # command for retiring an external-content index, so no old text
            # has to be read back and this module gains no dependency on the
            # one that fills the tables. A hook, when there is one, then
            # repopulates from the records this scan committed.
            connection.execute(
                "INSERT INTO documents_trigrams (documents_trigrams) VALUES ('delete-all')"
            )
            connection.execute("DELETE FROM document_tokens")
            connection.execute("DELETE FROM documents")
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
            _write_brief(connection, run)
            _write_run(connection, run)
        # `T-254`. After the runs, because a relation names two of them, and on
        # every pass, because the file it is read from has no per-run digest.
        _write_source_relations(connection, output_root)
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

        # `source_id -> reason` for every source whose canonical files would
        # not yield documents on this pass. Filled by the hook below.
        unsearchable: dict[str, str] = {}
        # `documents` and the two external-content FTS5 tables belong to
        # `T-103`: keeping an external-content index in step with its content
        # table is that module's contract, and half-populating them here would
        # leave a searchable corpus nobody owns. The hook is called with the
        # records this scan committed, inside the same transaction, so wiring it
        # up is `index_documents=search.index_documents` and nothing else.
        if index_documents is not None:
            # The hook's own report, **read** rather than discarded. It records
            # `source_id -> reason` for every source whose canonical files
            # would not yield documents, and writes the same marker into
            # `runs.problems`. `incomplete_runs` below was built from the run
            # objects, which were frozen before this line — so a source that
            # became unsearchable *on this scan* was reported by nothing until
            # the next one, and this scan said `discovered=3 indexed=3
            # skipped=0` about an index that had just lost a source's search
            # text. The module's own thesis is that the cheap path may skip
            # work, never reporting.
            report = index_documents(connection, combined)
            unsearchable.update(getattr(report, "unsearchable", None) or {})

        _write_state(connection, "ready", built_at=built_at)

    skipped_runs = [
        {"relative_path": run.canonical_dir, "reason": run.reason}
        for run in runs
        if run.state == _SKIPPED
    ]
    # A run's stored problems, plus the searchability marker this pass just
    # wrote. `run.problems` was frozen before `index_documents` ran, so a
    # source that lost its search text on *this* scan appeared in no report
    # until the next one.
    incomplete_runs = []
    for run in runs:
        problems = list(run.problems)
        reason = unsearchable.get(run.source_id) if run.source_id else None
        if reason is not None:
            problems.append(f"{schema.SEARCH_PROBLEM_PREFIX}{reason}")
        if problems:
            incomplete_runs.append(
                {
                    "relative_path": run.canonical_dir,
                    "source_id": run.source_id,
                    "problems": problems,
                }
            )
    if library_reason is not None:
        skipped_runs.append({"relative_path": library_key, "reason": library_reason})
    return ScanReport(
        # D-158: aliases are discovered directories too, and each is accounted
        # for as skipped. Leaving them out of the total would satisfy the
        # invariant by not counting the thing being reported.
        runs_discovered=len(discovered) + len(aliases),
        runs_indexed=sum(1 for run in runs if run.state != _SKIPPED),
        runs_skipped=sum(1 for run in runs if run.state == _SKIPPED),
        runs_unchanged=sum(1 for run in runs if run.state == _UNCHANGED),
        runs_evicted=len(evicted),
        skipped_runs=tuple(skipped_runs),
        incomplete_runs=tuple(incomplete_runs),
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
