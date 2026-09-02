from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeGuard


class JsonReadError(ValueError):
    """A JSON file that could not be read as a JSON document.

    One error type for every way a read can fail — absent, unreadable, malformed,
    or carrying a constant no other language's JSON parser accepts — so that
    every caller has one thing to catch and one decision to make. There used to
    be three readers for this one job (``io.read_json``, ``artifacts._read`` and
    an inline ``json.loads`` in ``library.py``) and three different failures for
    the same damaged file: a ``PipelineError``, a bare ``FileNotFoundError``, and
    an uncaught traceback out of the middle of a library rebuild.

    A ``ValueError`` subclass because that is what ``json`` itself raises, so
    existing ``except ValueError`` callers keep working.
    """


class CanonicalValueError(ValueError):
    """A canonical document holds a value that cannot be rendered or addressed.

    Defect D-074: ``format_timestamp`` was ``max(0, int(seconds))``, and
    ``int("0.0")`` raises a bare ``ValueError`` — so a canonical file timed
    ``"0.0"`` took ``finalize`` down with a raw traceback. ``ValueError`` is not
    in ``cli.USER_FACING_ERRORS``, so that also broke the documented
    ``{"status": "ERROR"}`` stderr contract; this type is in that tuple.

    A ``ValueError`` subclass for the same reason :class:`JsonReadError` is one:
    it is a bad *value*, and existing ``except ValueError`` callers keep working.
    """


#: An absolute POSIX path with at least two segments. Deliberately narrow: a
#: single segment (``/tmp``) is not distinctive enough to be worth mangling
#: ordinary prose over, and requiring two slashes keeps ``and/or`` out of it.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w>])(?:/[A-Za-z0-9._\- ]+){2,}")


#: A string that is *nothing but* an absolute path. Used where a whole field
#: value is a path (``report``, ``graph``, ``path``) and prose is not.
_ABSOLUTE_PATH_ONLY = re.compile(r"/(?:[A-Za-z0-9._\- ]+/)*[A-Za-z0-9._\- ]+")


def scrub_host_paths_roots_only(
    text: str, replacements: Sequence[tuple[str | Path, str]] = ()
) -> str:
    """*text* with the named roots substituted and nothing else touched.

    The half of :func:`scrub_host_paths` that is safe to apply to content: a
    root is the operator's filesystem and can never be a meaningful part of an
    extracted quotation, while the catch-all regex would mangle a unit that
    happens to mention a path.
    """
    for needle, label in sorted(
        ((str(needle), label) for needle, label in replacements if len(str(needle)) > 1),
        key=lambda pair: len(pair[0]),
        reverse=True,
    ):
        text = text.replace(needle, label)
    return text


def scrub_host_paths(
    text: str, replacements: Sequence[tuple[str | Path, str]] = ()
) -> str:
    """*text* with host filesystem paths removed and the sentence left standing.

    Defect D-085: ``scanner._project_relative_reason`` was a single
    ``reason.replace(str(run_dir), canonical_dir)``, so it redacted only paths
    *under* the run directory — while an ``AdapterError`` from
    ``project_relative`` also names the absolute project root, and a symlink
    names a path outside the run entirely. Both reach ``/api/status`` in
    ``skipped_runs[].reason``, and the scan's failure message reaches a ``503``
    body verbatim. D-030 and ADR-0003 both forbid a host path in an error body,
    and the enumeration was never going to be complete.

    Two stages, because they answer different needs. The *replacements* are
    meaningful substitutions the caller knows — a run directory for its
    project-relative form, a root for the words "the project root" — applied
    longest first so a nested path is not half-replaced. Whatever still looks
    absolute afterwards is a path nobody anticipated and is reduced to its last
    segment.

    D-063 is why this scrubs rather than truncates: **the reason still has to
    state the damage.** Deleting the sentence would satisfy a bare no-host-path
    assertion and silently close D-045's diagnostic channel, which is the
    failure this whole family of findings is about.
    """
    text = scrub_host_paths_roots_only(text, replacements)
    return _ABSOLUTE_PATH_RE.sub(
        lambda match: f"<path>/{match.group(0).rsplit('/', 1)[-1]}", text
    )


def is_finite_seconds(value: Any) -> TypeGuard[float]:
    """Whether ``value`` is a real, finite number of seconds.

    The base of the three tiers below, and the one place the rule is written.
    It lives here because ``io`` imports nothing from the package, so everything
    can reach it.

    D-185: this docstring used to claim that ``transcripts._is_finite_number``,
    ``validators._is_seconds`` and the ``_require_seconds`` coercers in ``ids``
    and ``segmenter`` "all defer to it". Only the first two did. The other two
    were near-verbatim reimplementations that never imported it, and a fifth
    guard the docstring did not name — ``query._seconds`` — had **no finiteness
    check at all**, so a ``NaN`` reached a sort key on which every comparison is
    ``False``: precisely the failure the paragraph below says is excluded. Six
    implementations of one rule, described as one.

    The tiers are :func:`is_finite_seconds` (the predicate),
    :func:`is_non_negative_seconds` (the predicate plus the schema's
    ``timestampSec`` rule), :func:`require_seconds` (the raising coercer, in the
    caller's own exception type) and :func:`seconds_or_none` (the optional one).

    ``bool`` is excluded because ``True`` is an ``int`` in Python and is not a
    time. ``NaN`` and the infinities are excluded because every comparison
    against ``NaN`` is ``False``, so a ``NaN`` bound slips past an
    ``end < start`` test, and neither can be written back as JSON any other
    language will read.

    A ``TypeGuard`` rather than a ``bool`` (D-114): every caller reads its
    argument out of an untrusted JSON document, so the value arrives as
    ``Any | None`` and the comparison that follows this check is what a type
    checker flags. Saying that the check *narrows* is both true and the only
    way the guard is legible to a reader who is not the author.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_non_negative_seconds(value: Any) -> TypeGuard[float]:
    """:func:`is_finite_seconds`, and not negative (D-185).

    The rule ``schemas/v1/common.schema.json`` states as ``timestampSec``, and
    the one extra clause the two coercers below add over the bare predicate.
    """
    return is_finite_seconds(value) and value >= 0


def require_seconds(
    value: Any, label: str, *, error: type[Exception] = ValueError
) -> float:
    """*value* as a non-negative finite number of seconds, or raise (D-185).

    The three messages are the ones ``ids`` and ``segmenter`` each wrote out,
    kept word for word: they differed only in the exception type, which is what
    *error* is for — ``ids`` refuses with ``IdError`` because a bad bound there
    is a bad identifier, and ``segmenter`` with ``ValueError``.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(f"{label} must be a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise error(f"{label} must be a finite number of seconds, got {value!r}")
    if number < 0:
        raise error(f"{label} must not be negative, got {value!r}")
    return number


def seconds_or_none(value: Any) -> float | None:
    """*value* as a timing, or ``None`` when it does not state one (D-185).

    The optional tier: absence is an answer here, so this returns rather than
    raises. It still applies the *whole* rule — ``query._seconds`` did not, and
    let ``inf`` and ``NaN`` through as sort keys on which every comparison is
    ``False``, which is a search result ordered by a value that cannot order.
    """
    return float(value) if is_finite_seconds(value) else None


def _whole_seconds(value: Any, label: str) -> int:
    """``value`` as whole non-negative seconds, or a :class:`CanonicalValueError`.

    Strict rather than forgiving (D-074): ``int()`` accepted the string
    ``"12"``, silently truncated ``True`` to ``1``, and crashed on ``"0.0"``,
    ``None`` and ``NaN``. A timestamp is either a number or it is a defect in
    the document, and rendering a guessed one into ``report.md`` beside a
    working YouTube deep link is exactly the invented position this project
    refuses everywhere else.
    """
    if not is_finite_seconds(value):
        raise CanonicalValueError(
            f"{label} must be a finite number of seconds, "
            f"got {type(value).__name__}: {value!r}"
        )
    return max(0, int(value))


#: The directory under ``output/`` that is not an ingested run but the
#: cross-source projection over all of them. It used to live in
#: ``adapters/youtube.py``, which is re-exported for every existing caller;
#: it moved here because run discovery is stated here now (D-158).
LIBRARY_DIR_NAME = "library"


def discover_run_dirs(output_root: Path) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """``(runs, aliases)`` — every ingested run under *output_root*, once each.

    The one statement of a rule that was written three times and disagreed
    three ways (D-158). ``index.scanner.run_dirs`` skipped dotted directories
    and ``library/``; ``adapters.adapt_project`` did the same; and
    ``library._run_dirs`` did neither, so a rebuild indexed runs the scanner
    refuses. A rule with three implementations is three rules.

    The third clause is new, and it is the one that was missing everywhere.
    ``glob`` **follows directory symlinks**, so an ordinary convenience link —
    ``ln -s output/pqlWNihgdjI output/latest`` — is discovered as a second run.
    Every record it produces is a duplicate of the first's, and
    ``check_index_integrity`` then refuses the *entire* index: every endpoint
    ``503``, both runs lost, and the message blames a duplicate ``video_id``
    rather than the link. ``_run_files`` has excluded symlinks since D-100;
    discovery did not. A directory that resolves to one already yielded is
    reported as an *alias* rather than walked again — named, because a run that
    silently disappears from the library is the failure D-043 exists to
    prevent, and because "this is the same run under another name" is a true
    and useful thing to say.

    Resolution is only used to *recognise* the alias. A symlink resolving
    outside the project keeps its own identity here and reaches D-078's
    skip-and-name path unchanged, which is what refuses to read through it.
    """
    candidates = [
        metadata_path.parent
        for metadata_path in sorted(Path(output_root).glob("*/metadata.json"))
        if not metadata_path.parent.name.startswith(".")
        and metadata_path.parent.name != LIBRARY_DIR_NAME
    ]

    # Which directory *owns* each resolved location. A real directory always
    # wins over a link to it, whatever the sort order says: `output/latest`
    # sorts before `output/pass-run`, and calling the real run an alias of the
    # convenience link would be the same loss under a politer name. Among links
    # alone the first in sorted order owns it, so the choice stays deterministic.
    owner: dict[str, Path] = {}
    for run_dir in candidates:
        resolved = os.path.realpath(run_dir)
        held = owner.get(resolved)
        if held is None or (held.is_symlink() and not run_dir.is_symlink()):
            owner[resolved] = run_dir

    runs: list[Path] = []
    aliases: list[tuple[Path, Path]] = []
    for run_dir in candidates:
        held = owner[os.path.realpath(run_dir)]
        if held == run_dir:
            runs.append(run_dir)
        else:
            aliases.append((run_dir, held))
    return runs, aliases


def run_dirs(output_root: Path) -> list[Path]:
    """Every ingested run under *output_root*, for a caller with no use for
    the aliases :func:`discover_run_dirs` names."""
    return discover_run_dirs(output_root)[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """The digest of *text* as it will be written — UTF-8, no BOM.

    The counterpart of :func:`sha256_file` for a document that has been
    serialised but not yet stored. ``write_text`` encodes UTF-8 and delegates to
    ``write_bytes``, so hashing ``dumps_json(document)`` here and hashing the
    resulting file later give the same value, which is what lets a digest be
    recorded at import and checked against the bytes on disk afterwards (D-163).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reject_non_finite(constant: str) -> Any:
    """Refuse the ``NaN``/``Infinity`` *tokens*: see also :func:`_reject_non_finite_float`."""
    raise ValueError(f"Canonical JSON must not contain {constant}")


def _reject_non_finite_float(text: str) -> float:
    """Refuse a numeric literal that *parses* to an infinity.

    Defect D-075: ``parse_constant`` only ever sees the bare ``NaN`` and
    ``Infinity`` tokens, so ``1e999`` — legal JSON, and ``inf`` once parsed —
    passed the reader and every validator, then died inside ``_write_group``
    with ``Out of range float values are not JSON compliant: inf`` and a full
    traceback. This docstring's promise that "canonical JSON must be readable
    everywhere" belongs on the parsed number, not on the spelling.
    """
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"Canonical JSON must not contain a non-finite number ({text})")
    return number


def dumps_json(value: Any) -> str:
    """Serialise *value* as canonical JSON text, exactly as it is written to disk.

    Separated from :func:`write_json` so a caller writing several files together
    can serialise all of them *before* touching any of them: a value that cannot
    be represented then fails with nothing on disk changed, rather than half way
    through a sequence of writes.
    """
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically and durably, leaving no stray temp file.

    The replace is atomic per file: a reader sees either the old file or the new
    one, never a half-written one. Atomicity *across* files is a separate problem
    and belongs to the caller — see :func:`write_group`.

    D-170: ordering was all this guaranteed, and it said so. ``grep -rn fsync
    src`` returned nothing, under eleven layered atomic replaces. The per-file
    claim holds against a concurrent *reader* and not against power loss: a
    rename can reach the disk while the data it names has not, and what a run
    then holds is a zero-length canonical file that ``write_group``'s rollback
    can no longer undo, because the bytes it would restore are gone too. Two
    syncs close it — the file's own before the rename, so the rename can never
    name unwritten data, and the directory's after, so the rename itself is
    durable. Every write in the package funnels through here, so this is the
    only place either has to happen.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("wb", dir=path.parent, delete=False, suffix=".tmp") as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _sync_directory(directory: Path) -> None:
    """Make a rename in *directory* durable, where the platform allows it.

    Opening a directory for ``fsync`` is POSIX; on Windows it raises, and there
    the file's own ``fsync`` above is as far as this can go. A failure to sync
    the directory is never worth failing a write that has already landed.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_text(path: Path, text: str) -> None:
    """Write *text* to *path* as UTF-8, atomically. See :func:`write_bytes`.

    Encoded here rather than written through a text-mode handle so the bytes on
    disk are the bytes given: a canonical file ends every line with ``\\n`` on
    every platform, not with whatever the host's line separator happens to be.
    """
    write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Write ``value`` as canonical JSON, atomically and without a stray temp file.

    ``allow_nan=False`` keeps NaN/Infinity — which no other language's JSON
    parser accepts — out of the canonical outputs, and a failed write removes its
    own ``.tmp`` instead of leaving it in the output directory.
    """
    write_text(path, dumps_json(value))


def write_group(
    entries: Sequence[tuple[Path, str]],
    *,
    prune: Sequence[Path] = (),
) -> None:
    """Write several files as one step, or leave every one of them as it was.

    :func:`write_text` is atomic for a single file, which is not the property
    these callers need: ``apply_extraction_bundle`` replaces four canonical
    files that are only meaningful together, ``finalize_run`` replaces
    ``graph.json``, ``report.md`` and a whole vault in the same breath, and
    ``import_transcript`` writes the nine files that *are* a run. A failure
    between two of those writes left the run internally inconsistent — a
    ``knowledge_units.json`` from this bundle beside a ``coverage.json`` from
    the last one — and ``validate_run`` would then read the mismatched set and
    report ``PASS`` on it, because each file is individually well formed.

    POSIX offers no multi-file commit, so this is the honest approximation:
    every document is serialised by the caller *before* the first write, each
    write is an atomic replace, and if one fails the previous contents of all of
    them are put back. The remaining window is a crash between two ``rename``
    calls, which no userspace code can close.

    *prune* names directories this group **owns**: every file under them that
    the group did not write is removed, and restored if the group fails. Defect
    D-090: without it a generator only ever added. Apply a bundle with KU-001
    and KU-002, finalize, retract KU-002, finalize again — ``report.md`` drops
    it and ``vault/knowledge_units/source/KU-002.md`` is still there, linked
    from nothing, indistinguishable from a unit that still exists. No validator
    looks at the vault, so nothing else was ever going to notice.

    It lives here rather than in ``artifacts`` (D-090) because
    ``import_transcript`` needs it and ``artifacts`` imports ``pipeline``, not
    the other way round. ``io`` imports nothing from the package, which is what
    lets both reach it.
    """
    # D-171: two entries that name one file. Unit ids `ku-a` and `KU-A` are
    # distinct to every validator — `validate_knowledge_units` dedupes
    # case-sensitively and `ids.is_id_part` permits mixed case — and
    # `artifacts._slug` does not case-fold, so on macOS's default
    # case-insensitive filesystem the two produce one path and the second write
    # wins. `finalize` then reported `PASS` and claimed four files while the
    # disk held three, `report.md` listed both units, and one unit's note was
    # simply gone. `written` is a *set* of unresolved paths, so nothing here
    # noticed. CI is Linux; the stated development platform is macOS (D-115).
    #
    # Refused rather than repaired: which of the two notes should survive is not
    # this function's to decide, and silently keeping one is exactly the
    # behaviour that lost the other.
    # The key is case-folded and NFC-normalised on *every* platform, not only
    # where the filesystem is. `os.path.normcase` is a no-op on macOS, so a
    # platform-accurate rule would make this defect invisible to Linux CI —
    # which is exactly how it survived. Two canonical files differing only in
    # case or in Unicode composition are a hazard wherever they are written, and
    # nothing this package writes needs the distinction.
    collisions: dict[str, list[Path]] = {}
    for path, _ in entries:
        key = unicodedata.normalize("NFC", str(path.resolve())).casefold()
        collisions.setdefault(key, []).append(path)
    duplicated = sorted(
        (paths for paths in collisions.values() if len(paths) > 1),
        key=lambda paths: str(paths[0]),
    )
    if duplicated:
        named = "; ".join(
            " and ".join(sorted(str(path) for path in paths)) for paths in duplicated
        )
        # `CanonicalValueError`, not a bare `ValueError`: it is a bad *value* in
        # a canonical document (two unit ids that address one note), and it is
        # in `cli.USER_FACING_ERRORS`, so the CLI keeps its documented
        # `{"status": "ERROR"}` contract instead of dying on a traceback. Same
        # reasoning as D-074.
        raise CanonicalValueError(
            "write_group was given two entries that name one file once case and "
            f"Unicode composition are accounted for, so one would silently "
            f"overwrite the other: {named}"
        )

    written = {path.resolve() for path, _ in entries}
    stale = [
        path
        for directory in prune
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.resolve() not in written
    ]
    previous: list[tuple[Path, bytes | None]] = []
    for path in [entry[0] for entry in entries] + stale:
        try:
            previous.append((path, path.read_bytes()))
        except OSError:
            previous.append((path, None))
    try:
        for path, text in entries:
            write_text(path, text)
        for path in stale:
            path.unlink(missing_ok=True)
    except BaseException:
        for path, snapshot in previous:
            try:
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    write_bytes(path, snapshot)
            except OSError:
                # The rollback is best effort by definition — the write that
                # brought us here may have failed because the disk is full. The
                # original failure is what the caller must see.
                pass
        raise


def read_json(path: Path) -> Any:
    """The JSON document at *path*, or a :class:`JsonReadError` naming what is wrong.

    The single strict reader. Use it wherever a missing or damaged file means the
    caller must stop; use :func:`read_json_or_reason` wherever it means the caller
    must carry on and report the damage.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                parse_constant=_reject_non_finite,
                parse_float=_reject_non_finite_float,
            )
    except FileNotFoundError as exc:
        raise JsonReadError(f"Missing JSON file: {path}") from exc
    except IsADirectoryError as exc:
        raise JsonReadError(f"Not a JSON file: {path}") from exc
    except OSError as exc:
        raise JsonReadError(f"Unreadable JSON file: {path} ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise JsonReadError(f"JSON file is not valid UTF-8: {path} ({exc})") from exc
    except ValueError as exc:
        raise JsonReadError(f"Malformed JSON in {path} ({exc})") from exc


def read_json_or_reason(path: Path) -> tuple[Any, str | None]:
    """``(document, None)``, or ``(None, reason)`` when *path* cannot be read.

    The tolerant half of :func:`read_json`, for the callers whose job is to keep
    going: a damaged run must still be indexable, and what is wrong with it must
    still be *stated* rather than silently dropped. The reason is returned rather
    than logged so the caller can put it somewhere a reader will find it.
    """
    try:
        return read_json(path), None
    except JsonReadError as exc:
        return None, str(exc)


def format_timestamp(seconds: float) -> str:
    """``seconds`` as ``HH:MM:SS``, or a :class:`CanonicalValueError` (D-074)."""
    whole = _whole_seconds(seconds, "timestamp")
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timestamp_url(video_id: str, seconds: float) -> str:
    """A YouTube deep link, or a :class:`CanonicalValueError` (D-074).

    Refuses for the same reason :func:`format_timestamp` does: the two are
    rendered side by side into ``report.md``, and a link that opens the wrong
    moment is worse than one that is absent.
    """
    return (
        f"https://www.youtube.com/watch?v={video_id}"
        f"&t={_whole_seconds(seconds, 'timestamp')}s"
    )
