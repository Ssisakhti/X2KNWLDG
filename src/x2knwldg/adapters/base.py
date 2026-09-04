"""The source-neutral adapter contract (canvas plan §11, ADR 0001 item 7, T-004).

An adapter maps one canonical run directory onto the v1 index model in
``schemas/v1/``. It is a **reader**. It opens canonical files, copies values,
and returns records; it never writes, never recomputes a status, and never
supplies a value the canonical files do not contain. ``output/<id>/raw/`` is
immutable evidence and is only ever stat-ed and hashed.

Five rules shape every adapter, and each of them is enforced here rather than
left to the individual implementation:

**Identifiers are built, never spelled.** Every id goes through
:mod:`x2knwldg.ids`, so the three cross-field invariants that JSON Schema cannot
express hold by construction and are re-checked in :func:`check_records`
(risk R12).

**Paths are project-relative.** :func:`project_relative` refuses a path outside
the project root, so an absolute host path cannot reach a record even by
accident (risk R15). ``output/library/status.json`` and ``videos.json`` carry
absolute paths today; nothing here reads them.

**Status is copied.** :func:`read_status` maps a missing, unreadable, or
unrecognised validator file to ``UNKNOWN`` — never to ``PASS``, and it has no
path that raises ``PARTIAL`` or ``FAIL`` upward (ADR 0001 invariant 2).

**A media type is stated only when it is registered.** Anything else is
``None`` rather than a plausible guess.

**A value is copied only when the frozen model can carry it.** Reading a value
out of a canonical file is not the same as being able to state it: ``kind``,
``confidence``, ``provenance_class``, ``label``, ``duration_sec`` and the rest
are all constrained by ``schemas/v1/``, and a canonical file is free to hold
something outside those bounds. :func:`copied_text`, :func:`copied_number`,
:func:`copied_choice` and :func:`copied_timestamp` are the only way a value
reaches a record. An **absent** value is reported as absent, exactly as before;
a value that is **present and out of contract** is refused, because the two
alternatives are both dishonest — emitting a record the project's own schemas
reject, or quietly repairing canonical data the adapter is only allowed to read.
Refusal names the file, the record and the field, so the canonical data can be
fixed where it lives.

Adding a source type means adding a subclass and registering it. It must not
require a change to this module, to the schemas, or to the frontend.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, NoReturn

from .. import constants, ids
from ..io import read_json_or_reason, scrub_host_paths, sha256_file

#: Index model version these records conform to. The version is the schema
#: *directory*: a breaking change becomes ``schemas/v2/`` and a new constant.
SCHEMA_VERSION = "1.0"

#: The three statuses a canonical validator file may state. Anything outside
#: this set is reported as ``UNKNOWN``.
RUN_STATUSES = frozenset({"PASS", "PARTIAL", "FAIL"})

#: What an absent, unreadable, or unrecognised status becomes. It exists so
#: that nothing ever has to be guessed.
UNKNOWN_STATUS = "UNKNOWN"

#: Registered IANA media types for the file extensions the pipeline writes.
#: ``.srt`` is deliberately absent: SubRip has no registered type, and the
#: ``Artifact.media_type`` contract asks for null rather than a guess.
MEDIA_TYPES: Mapping[str, str] = {
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".vtt": "text/vtt",
}

# --------------------------------------------------------------------------
# The v1 value contract, mirrored from schemas/v1/ — drift-tested
# --------------------------------------------------------------------------
#
# The adapters are stdlib-only and cannot import ``jsonschema`` (ADR 0001
# invariant 5), so the bounds the schemas state are mirrored here in the same
# way ``ids.py`` mirrors the identifier patterns (D-015).
# ``tests/test_adapters_hardening.py`` reads ``schemas/v1/*.json`` and fails the
# moment one of these disagrees with the schema it mirrors, so the schema stays
# the authority and this stays a copy.

#: ``common.schema.json#/$defs/knowledgeKind`` — the 30 kinds of
#: ``constants.py`` plus the one ``library.py`` mints for a concept node.
KNOWLEDGE_KINDS = frozenset(constants.KNOWLEDGE_KINDS | {"canonical_concept"})

#: ``common.schema.json#/$defs/canonicalRelationType``.
CANONICAL_RELATION_TYPES = frozenset(constants.RELATION_TYPES)

#: ``common.schema.json#/$defs/librarySyntheticRelationType``.
LIBRARY_SYNTHETIC_RELATION_TYPES = frozenset({"derived_from", "expresses_concept"})

#: ``common.schema.json#/$defs/provenanceClass``. ``user`` is workspace content
#: and never appears in a canonical file, so an adapter accepts only the two
#: classes the pipeline writes.
PROVENANCE_CLASSES = frozenset({"source", "derived", "user"})
CANONICAL_PROVENANCE_CLASSES = frozenset({"source", "derived"})

#: ``common.schema.json#/$defs/confidence`` — copied verbatim, never defaulted,
#: and never outside the range the model states.
MIN_CONFIDENCE = 0
MAX_CONFIDENCE = 1

#: ``common.schema.json#/$defs/isoTimestamp``. An offset is required: a naive
#: local time is not a point in time, and ``datetime.fromisoformat`` would
#: happily accept one the schema rejects.
ISO_TIMESTAMP_PATTERN = (
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})"
)

#: Length bounds, by the field they belong to.
MAX_URL_LENGTH = 2048  # source.url, artifact.url
MAX_TITLE_LENGTH = 1024  # source.title
MAX_AUTHOR_LENGTH = 512  # source.author
MAX_LANGUAGE_LENGTH = 32  # source.language
MAX_LABEL_LENGTH = 4096  # entity_ref.label
MAX_MEDIA_TYPE_LENGTH = 128  # artifact.media_type
MAX_RELATION_LENGTH = 128  # indexed_relation.relation
MAX_SEGMENT_ID_LENGTH = 128  # locator.segment_id
MAX_PATH_LENGTH = 4096  # common.projectRelativePath
MAX_EDGE_ID_LENGTH = 1300  # indexed_relation.id


# Anchored with ``\Z`` rather than ``$``, for the reason ``ids.py`` gives: the
# pattern is read as ECMA-262 in the schema, where ``$`` does not match before a
# trailing newline, and Python's does.
_ISO_TIMESTAMP_RE = re.compile(f"^{ISO_TIMESTAMP_PATTERN}\\Z")

#: The fractional-second digits, for :func:`_parseable`. Not part of the
#: accepted shape — the pattern above already decides that — only of rewriting a
#: valid timestamp into the spelling the floor interpreter can parse.
_FRACTION_RE = re.compile(r"\.(\d+)")


class AdapterError(RuntimeError):
    """A run cannot be mapped onto the index model without guessing.

    Raised in preference to emitting a record that states something the
    canonical files do not support.
    """


# --------------------------------------------------------------------------
# The record set an adapter returns
# --------------------------------------------------------------------------


@dataclass
class IndexRecords:
    """The four v1 record families produced from one or more sources.

    Purely a carrier: it holds plain dicts so the index (``T-101``–``T-104``)
    and the API (``T-105``–``T-107``) can persist and serialise them without a
    translation layer, and so the contract tests can validate them directly
    against the JSON Schemas.
    """

    sources: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)

    def __add__(self, other: IndexRecords) -> IndexRecords:
        return IndexRecords(
            sources=[*self.sources, *other.sources],
            artifacts=[*self.artifacts, *other.artifacts],
            entities=[*self.entities, *other.entities],
            relations=[*self.relations, *other.relations],
        )

    def by_model(self) -> dict[str, list[dict[str, Any]]]:
        """Keyed by schema file stem, so a record set validates in a loop."""
        return {
            "source": self.sources,
            "artifact": self.artifacts,
            "entity_ref": self.entities,
            "indexed_relation": self.relations,
        }

    def addressable(self) -> Iterator[tuple[str, str, str]]:
        """Every id this set claims, as ``(namespace, id, claimant)``.

        The namespaces are the repository seam's, and deliberately not a second
        opinion about them: ``repository/base.ORDER_KEYS`` names the field each
        family is addressed by, and ``check_index_integrity`` gives sources and
        relations a namespace each while artifacts and entities share one,
        because a global id addresses either and the API resolves both out of
        the same space. :func:`check_records` claims each of these, so the rule
        that no two records share an id is written once and read from here.
        """
        for source in self.sources:
            yield "source id", source["id"], f"source in {source.get('canonical_dir')}"
        for artifact in self.artifacts:
            yield "global id", artifact["id"], f"artifact {artifact.get('kind')}"
        for entity in self.entities:
            yield "global id", entity["global_id"], f"{entity.get('entity_type')}"
        for relation in self.relations:
            yield "edge id", relation["id"], f"{relation.get('relation')} edge"


# --------------------------------------------------------------------------
# Shared helpers — the four rules
# --------------------------------------------------------------------------


def project_relative(path: Path, project_root: Path) -> str:
    """Return *path* relative to *project_root*, or refuse.

    Refusing is the point. A path outside the project root has no
    project-relative form, and the alternative — storing the absolute host
    path — is exactly what risk R15 describes: it breaks the moment the
    project moves.
    """
    resolved = path.expanduser().resolve()
    root = project_root.expanduser().resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        # "lies outside {root}", not "lies outside the project root {root}":
        # `scanner._project_relative_reason` substitutes the root for the words
        # "the project root", so the longer phrasing scrubbed to "…lies outside
        # the project root the project root". The sentence has to read correctly
        # both before and after that substitution.
        raise AdapterError(
            f"{resolved} lies outside {root}; index records carry "
            "project-relative paths only (risk R15)"
        ) from exc
    text = relative.as_posix()
    # ``projectRelativePath`` excludes the backslash, so a file whose *name*
    # contains one has no project-relative form the model can carry.
    if "\\" in text:
        raise AdapterError(
            f"{resolved} contains a backslash, which a project-relative path may not "
            "(schemas/v1/common.schema.json projectRelativePath)"
        )
    # And no control character, for the same reason and from the same rule. A
    # newline in a path used to defeat the schema's own anti-traversal
    # lookahead — `.` matches no newline in either Python `re` or ECMA-262 —
    # so the pattern now excludes the whole control range and this refuses
    # what the pattern refuses, rather than handing the schemas a value they
    # will reject.
    control = next((char for char in text if char < " " or char == "\x7f"), None)
    if control is not None:
        raise AdapterError(
            f"{resolved} contains the control character {control!r}, which a "
            "project-relative path may not "
            "(schemas/v1/common.schema.json projectRelativePath)"
        )
    if len(text) > MAX_PATH_LENGTH:
        raise AdapterError(
            f"the project-relative path of {resolved} is {len(text)} characters, over "
            f"the {MAX_PATH_LENGTH} the v1 index model allows"
        )
    return text


def refuse(owner: str, field: str, value: Any, requirement: str) -> NoReturn:
    """Refuse a canonical value the v1 model cannot carry.

    One phrasing for every such refusal, so the failure always names the record,
    the field, what was read, and what the model asks for instead. The adapter
    reads canonical data; it does not repair it, and it does not pass it on
    knowing the schemas will reject it.
    """
    shown = repr(value)
    if len(shown) > 120:
        shown = f"{shown[:117]}…"
    raise AdapterError(
        f"{owner}: {field} is {shown}, but the v1 index model {requirement}. "
        "A canonical value is copied or refused, never adjusted"
    )


def copied_text(
    value: Any,
    *,
    owner: str,
    field: str,
    max_length: int | None,
    allow_empty: bool = True,
    required: bool = False,
) -> str | None:
    """Text a record may carry, or ``None`` when the canonical file has none.

    ``max_length`` is ``None`` for the fields the schemas leave unbounded — an
    excerpt and a derivation note are copied verbatim however long they are, and
    inventing a bound here would truncate evidence.
    """
    if value is None:
        if required:
            refuse(owner, field, value, "requires text there")
        return None
    if not isinstance(value, str):
        refuse(owner, field, value, f"carries text there, not {type(value).__name__}")
    if not value and not allow_empty:
        refuse(owner, field, value, "carries no empty string there")
    if max_length is not None and len(value) > max_length:
        raise AdapterError(
            f"{owner}: {field} is {len(value)} characters, over the {max_length} the "
            "v1 index model allows"
        )
    return value


def copied_number(
    value: Any,
    *,
    owner: str,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
    required: bool = False,
) -> Any:
    """A number a record may carry, or ``None`` when there is none."""
    if value is None:
        if required:
            refuse(owner, field, value, "requires a number there")
        return None
    # ``bool`` is an ``int`` in Python and is not a number to JSON Schema.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        refuse(owner, field, value, "carries a number there")
    if integer and not isinstance(value, int):
        refuse(owner, field, value, "carries a whole number there")
    if not math.isfinite(value):
        refuse(owner, field, value, "carries a finite number there")
    if minimum is not None and value < minimum:
        refuse(owner, field, value, f"carries no value below {minimum} there")
    if maximum is not None and value > maximum:
        refuse(owner, field, value, f"carries no value above {maximum} there")
    return value


def copied_confidence(
    value: Any, *, owner: str, field: str = "confidence", required: bool = False
) -> Any:
    """A confidence, copied verbatim inside the range the model states.

    Never invented and never defaulted: an absent confidence stays absent
    wherever the model allows one, and is refused where it does not.
    """
    return copied_number(
        value,
        owner=owner,
        field=field,
        minimum=MIN_CONFIDENCE,
        maximum=MAX_CONFIDENCE,
        required=required,
    )


def copied_choice(
    value: Any,
    *,
    owner: str,
    field: str,
    allowed: frozenset[str],
    required: bool = False,
) -> str | None:
    """A value from a closed vocabulary, or ``None`` when there is none.

    The vocabularies are the schemas', not the adapter's. A canonical file that
    states something outside one is reported, not translated into the nearest
    member and not passed through for a downstream validator to trip over.
    """
    if value is None:
        if required:
            refuse(owner, field, value, f"requires one of {_vocabulary(allowed)}")
        return None
    if value not in allowed:
        refuse(owner, field, value, f"knows only {_vocabulary(allowed)}")
    return value


def _parseable(text: str) -> str:
    """*text* in the narrower spelling ``datetime.fromisoformat`` accepts on 3.10.

    ``requires-python`` declares 3.10 as the floor, and on 3.10 that constructor
    parses only what ``isoformat()`` emits: no ``Z`` designator — it landed in
    3.11 — and fractional seconds of exactly three or six digits. Both are
    perfectly good RFC 3339, both are accepted by
    ``common.schema.json#/$defs/isoTimestamp``, and every Twitter capture uses
    the first one: `acquisition.requested_at` is written as `...:00Z`, so
    projecting an acquired post raised `ValueError: Invalid isoformat string` on
    the floor interpreter and nowhere else.

    Rewritten for the **parse only**. What the caller returns is the model's own
    text, verbatim, because a copied field that quietly changed spelling would
    be a record stating something the canonical file does not.
    """
    if text[-1] in "Zz":
        text = f"{text[:-1]}+00:00"
    fraction = _FRACTION_RE.search(text)
    if fraction and len(fraction.group(1)) not in (3, 6):
        digits = fraction.group(1)[:6].ljust(6, "0")
        text = f"{text[: fraction.start(1)]}{digits}{text[fraction.end(1) :]}"
    return text


def copied_timestamp(value: Any, *, owner: str, field: str) -> str | None:
    """An RFC 3339 timestamp, verbatim, or ``None`` when there is none.

    Both halves matter: the shape has to be the one the model states, and it has
    to name a real instant. ``2026-02-30T00:00:00+00:00`` passes the pattern and
    is not a date.
    """
    text = copied_text(value, owner=owner, field=field, max_length=64, allow_empty=False)
    if text is None:
        return None
    if not _ISO_TIMESTAMP_RE.match(text):
        refuse(owner, field, value, "carries an RFC 3339 timestamp with an offset there")
    try:
        datetime.fromisoformat(_parseable(text))
    except ValueError:
        refuse(owner, field, value, "carries a real date and time there")
    return text


def _vocabulary(allowed: frozenset[str]) -> str:
    names = sorted(allowed)
    if len(names) > 8:
        return f"the {len(names)} values of schemas/v1/ ({', '.join(names[:4])}, …)"
    return ", ".join(names)


def media_type_for(path: Path) -> str | None:
    """The registered media type of *path*, or ``None`` when there is none."""
    return MEDIA_TYPES.get(path.suffix.lower())


def read_optional_json(path: Path) -> Any | None:
    """Read a canonical JSON file, or return ``None`` if it cannot be read.

    A half-finished or damaged run must still be indexable and still be
    displayed honestly, so an unreadable file is an absence rather than a
    crash. What is absent is reported as absent — never filled in.

    The reading itself is :func:`x2knwldg.io.read_json_or_reason`, the one
    tolerant reader in the package: this used to be a fifth ``json.loads``, and
    five readers of one file format is five answers to 'what is a damaged file'.
    Delegating also inherits ``io``'s refusal of ``NaN`` and ``Infinity``, which
    ``json`` accepts by default and no other language's parser will read back.

    Use :func:`read_optional_json_or_reason` where the caller can report the
    damage; this shorthand is for the reads whose absence is the whole answer.
    """
    return read_json_or_reason(path)[0]


def read_optional_json_or_reason(path: Path) -> tuple[Any | None, str | None]:
    """``(document, reason)`` — the reason set only when the file is *damaged*.

    An absent file is an absence: ``(None, None)``. A file that is there and
    cannot be read is damage, and the reason is handed back so the caller can
    put it where a reader will find it. The distinction is made by asking
    whether the path exists rather than by reading ``io``'s message, because a
    check that parses an error string breaks the next time the string is
    reworded.

    Silently reading a damaged file as an empty one is the failure this exists
    to prevent: a corrupted ``knowledge_units.json`` takes every unit in the run
    out of the index, and without the reason the index says only that the run
    has no knowledge — which is a different claim, and a false one.
    """
    document, reason = read_json_or_reason(path)
    if document is None and reason is not None and not path.exists():
        return None, None
    return document, reason


#: Re-exported from :mod:`x2knwldg.ids`, which is where it moved under `T-230`.
#: The finalize path needs the same answer and cannot import this package
#: without a low-level writer depending on the index layer, so the rule moved
#: down to the module that owns the vocabulary. Every importer here keeps
#: working, and there is one implementation of it (D-240).
declared_source_type = ids.declared_source_type


def read_status(document: Any | None) -> str:
    """The ``status`` a validator document states, verbatim, or ``UNKNOWN``.

    There is deliberately no branch in this function that can turn a stated
    ``PARTIAL`` or ``FAIL`` into anything else (ADR 0001 invariant 2).
    """
    if not isinstance(document, Mapping):
        return UNKNOWN_STATUS
    status = document.get("status")
    # D-161: `in` against a frozenset hashes its left operand, so a validator
    # file carrying `{"status": ["PASS"]}` or `{"status": {}}` raised
    # `TypeError: unhashable type` from inside a function whose whole contract
    # is that it never raises. `scanner` catches only `AdapterError` and
    # `TypeError` is not in `cli.USER_FACING_ERRORS`, so `x2knwldg ui` died on
    # a raw traceback with no `{"status": "ERROR"}` envelope — and every other
    # run in the project became unreachable because of one malformed file in
    # one of them. A status that is not a string is not a recognised status,
    # which is what the docstring above already promises `UNKNOWN` covers.
    if not isinstance(status, str):
        return UNKNOWN_STATUS
    return status if status in RUN_STATUSES else UNKNOWN_STATUS


def check_records(records: IndexRecords, *, self_contained: bool = True) -> IndexRecords:
    """Assert everything about a record set that JSON Schema cannot.

    The three invariants of ``schemas/v1/README.md`` — a global id equals its
    parts, a source id equals its parts, a time range does not end before it
    starts — plus three that follow from them: an artifact belongs to the source
    it names, no two records claim one id, and no edge names an endpoint the set
    has no entity for.

    The last two are exactly ``repository.check_index_integrity``, deliberately
    to the letter. That function refuses the same two conditions when a
    repository is constructed, which is the right failure at the wrong end of
    the seam: the records are produced *here*, so a set that cannot be paged or
    drawn is refused here, and the far side stays as the guard that no other
    implementation can hand the API something worse. Two checks of one rule that
    disagreed would be worse than either alone.

    A **duplicate id** makes the repository's order non-total, and a tie across
    a page boundary drops a record from the paged output while ``total`` goes on
    counting it — a silent deletion. A **dangling edge** cannot be drawn, so the
    graph omits it while ``/api/sources/{id}/relations`` still lists it, and the
    two views then disagree about one fact. ``validators.py:208`` already calls
    an edge naming an unknown unit a canonical error, so refusing it here agrees
    with the validator rather than inventing a rule.

    Called by every adapter before it returns, and again by
    :func:`x2knwldg.adapters.adapt_project` over the **combined** set: an id is
    unique per run by construction, but two runs are free to declare the same
    ``video_id``, and an index keyed by id would then keep whichever record it
    wrote last and silently lose the other.

    *self_contained* is false for a record set that is a **fragment** of the
    index rather than the whole of it. Only :func:`adapt_library` produces one:
    its ``expresses_concept`` edges run from knowledge units the *runs* own to
    concepts the library owns, so their endpoints are outside the set by
    construction (D-025), and membership can only be judged over the union —
    where ``adapt_project`` judges it. Uniqueness is checked either way.
    """
    for source in records.sources:
        _wrap(ids.check_source_ids, source, f"source {source.get('id')}")

    for artifact in records.artifacts:
        owner = f"artifact {artifact.get('id')}"
        global_id = _wrap(ids.parse_global_id, artifact["id"], owner)
        if artifact.get("source_id") != global_id.source_id.value:
            raise AdapterError(
                f"{owner} claims source_id {artifact.get('source_id')!r}, but its own id "
                f"belongs to {global_id.source_id.value!r}"
            )

    for entity in records.entities:
        owner = f"{entity.get('entity_type')} {entity.get('global_id')}"
        _wrap(ids.check_entity_ref_ids, entity, owner)
        locator = entity.get("locator")
        if locator is not None:
            _wrap(ids.check_locator, locator, f"locator of {owner}")

    for relation in records.relations:
        owner = f"relation {relation.get('id')}"
        _wrap(ids.parse_global_id, relation["from_id"], owner)
        _wrap(ids.parse_global_id, relation["to_id"], owner)

    claimed: dict[tuple[str, str], str] = {}
    for namespace, value, owner in records.addressable():
        _claim(claimed, namespace, value, owner)

    if self_contained:
        _check_endpoints(records)
    return records


def _claim(claimed: dict[tuple[str, str], str], namespace: str, value: str, owner: str) -> None:
    previous = claimed.get((namespace, value))
    if previous is not None:
        raise AdapterError(
            f"{owner} and {previous} both claim the {namespace} {value!r}; "
            "one record, one id"
        )
    claimed[(namespace, value)] = owner


def _check_endpoints(records: IndexRecords) -> None:
    """No edge may name an endpoint no entity record has."""
    entities = {entity["global_id"] for entity in records.entities}
    for relation in records.relations:
        for side in ("from_id", "to_id"):
            endpoint = relation.get(side)
            if endpoint not in entities:
                raise AdapterError(
                    f"relation {relation.get('id')!r} names {side} {endpoint!r}, which no "
                    "entity record has; an edge to an entity the index does not carry "
                    "cannot be drawn, and would be listed by the API anyway"
                )


def _wrap(check, value, owner: str):
    """Run an ``ids`` check, naming the record that failed it."""
    try:
        return check(value)
    except ids.IdError as exc:
        raise AdapterError(f"{owner}: {exc}") from exc
    except KeyError as exc:
        raise AdapterError(f"{owner} is missing the required field {exc.args[0]!r}") from exc


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Reading a canonical record, and naming what was wrong with it
# --------------------------------------------------------------------------
#
# These moved here with the projection they serve (``T-228``). They were
# ``youtube.py``'s while it was the only adapter minting entities and
# relations; the rules they carry — a missing field is named, an id is built
# through ``ids`` so the failure says which record broke, an edge id is
# deterministic and its parts escaped — are not YouTube's, and a second copy of
# any of them in a second adapter is exactly the drift D-219 removed from the
# capture normalizer.


def required_field(record: Mapping[str, Any], key: str, owner: str) -> Any:
    if key not in record:
        raise AdapterError(f"{owner} is missing the required field {key!r}")
    return record[key]


def build_id(factory, value: Any, owner: str):
    """Build an id through ``ids``, naming what failed. Never an f-string."""
    try:
        return factory(value)
    except ids.IdError as exc:
        raise AdapterError(f"{owner}: {exc}") from exc


def edge_id(from_id: str, relation: Any, to_id: str) -> str:
    """A deterministic edge id, so a rebuild yields the identical set (T-104).

    The parts are escaped before they are joined. A global id can never contain
    ``|`` and a relation name from either vocabulary never does either, so no
    id this project produces today changes shape — but a separator that only
    works while nothing collides with it is an id collision waiting for the
    first relation vocabulary that admits one, and two distinct edges sharing an
    id is one of them silently disappearing from the index.
    """
    edge_id = "|".join(_escape_id_part(part) for part in (from_id, relation, to_id))
    if len(edge_id) > MAX_EDGE_ID_LENGTH:
        raise AdapterError(
            f"edge id {edge_id[:80]}… is {len(edge_id)} characters, over the "
            f"{MAX_EDGE_ID_LENGTH} the IndexedRelation contract allows"
        )
    return edge_id


def _escape_id_part(part: str) -> str:
    """Make *part* unable to spell the separator, reversibly."""
    return part.replace("\\", "\\\\").replace("|", "\\|")


@dataclass(frozen=True)
class ArtifactSpec:
    """One well-known file of a run, and the local id that addresses it."""

    key: str
    kind: str
    role: str
    relative: str


def list_items(document: Any, key: str, owner: str) -> list[Mapping[str, Any]]:
    """The list under *key*, or an empty list — never a partial read.

    An unreadable document and an absent key are both absences and read as
    empty. A key that is present but holds something other than a list of
    objects is neither: reading past it would report a count and a record set
    that quietly omit whatever was in there.
    """
    if not isinstance(document, Mapping) or key not in document:
        return []
    value = document.get(key)
    if not isinstance(value, list):
        refuse(owner, key, value, "reads a list of objects there")
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            refuse(owner, f"{key}[{index}]", item, "reads an object there")
    return list(value)


class SourceAdapter(ABC):
    """Maps canonical run directories of one source type onto the v1 model.

    Subclasses declare ``source_type`` and ``version``, which together become
    the ``adapter`` field of every ``Source`` record, so a stale record can
    always be traced back to the code that wrote it.
    """

    #: Adapter namespace, and the first part of every id it produces.
    source_type: ClassVar[str]

    #: Bumped when this adapter's output changes shape, so a re-index can be
    #: forced without a schema version bump.
    version: ClassVar[str]

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()

    @property
    def ref(self) -> dict[str, str]:
        """The ``adapterRef`` recorded on every ``Source`` this adapter emits."""
        return {"name": self.source_type, "version": self.version}

    def relative(self, path: Path) -> str:
        return project_relative(path, self.project_root)

    def read_canonical(self, path: Path, damaged: list[dict[str, str]]) -> Any | None:
        """A canonical file, or ``None``. Override to report *why* it was None.

        The base behaviour is the plain tolerant read: an absent or unreadable
        file is an absence. ``YouTubeAdapter`` overrides it to append to
        *damaged*, because a file that is present and unreadable is damage and
        only one of "missing count" and "broken file" is actionable.
        """
        return read_optional_json(path)

    def _status(self, run_dir: Path, damaged: list[dict[str, str]]) -> dict[str, Any]:
        """Copy the run status out of the two validator files.

        ``overall`` is ``validation.json``'s top-level status, which already
        aggregates all five sections including coverage. Recomputing it here
        would be a second opinion, and the UI is forbidden one (ADR 0001
        invariant 2).

        On the **base class** since ``T-227``, because a second source type
        arrived and this is not a YouTube rule: what a ``status`` record *is* —
        the three verbatim copies, the two paths, the bounded `audit_attempts` —
        is the same question whatever medium a run came from, and the schema
        holds every adapter to one answer. It lived on ``YouTubeAdapter``, and
        the Twitter adapter's first version wrote ``read_status(validation)``
        straight into the field: a bare string where the model requires an
        object, schema-invalid, and caught by nothing until a test validated the
        projection. The same schema's own ``audit_attempts`` comment records the
        previous instance of that exact gap.

        Subclasses supply :meth:`read_canonical`, because *how* a damaged file
        is reported is the adapter's business; what the status says is not.
        """
        validation_path = run_dir / "validation.json"
        coverage_path = run_dir / "coverage.json"
        validation = self.read_canonical(validation_path, damaged)
        coverage = self.read_canonical(coverage_path, damaged)

        status: dict[str, Any] = {
            "validation": read_status(validation),
            "coverage": read_status(coverage),
            "overall": read_status(validation),
            "validation_path": self.relative(validation_path) if validation is not None else None,
            "coverage_path": self.relative(coverage_path) if coverage is not None else None,
        }
        # Copied verbatim inside the bounds the record can carry. A count above
        # the WORKFLOW.md cap of three means the run broke the repair rule, and
        # a count that is not a whole number means the file is damaged: both are
        # refused here, loudly and by name. Clamping would hide the first and
        # nulling would restate the second as 'no file', which is a different
        # claim. ``0`` is the honest never-audited state ``coverage.py`` writes
        # and is carried through as stated.
        if isinstance(coverage, Mapping) and "audit_attempts" in coverage:
            status["audit_attempts"] = copied_number(
                coverage.get("audit_attempts"),
                owner=self.relative(coverage_path),
                field="audit_attempts",
                minimum=0,
                maximum=constants.MAX_AUDIT_ATTEMPTS,
                integer=True,
            )
        else:
            status["audit_attempts"] = None
        return status

    def _file_artifact(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        spec: ArtifactSpec,
        hash_artifacts: bool,
        unmappable: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """One canonical artifact, or ``None`` when its path cannot be mapped.

        Defect D-100: ``self.relative`` resolves symlinks, so a canonical file
        that *is* a symlink to somewhere outside the project resolved outside
        it and raised — taking the **whole run** down over one file. Measured:
        a symlinked ``report.md``, ``raw/source.srt`` or vault note each made
        ``adapt_run`` refuse the run entirely, and since D-078 that is a
        skipped-and-named run rather than a dead index, which is better and
        still wrong.

        ``adapter_metadata.unmappable_artifacts`` is the channel that already
        exists for exactly this — "a generated ``vault/`` note whose filename
        cannot spell an id, skipped and named" (D-045) — so an artifact the
        index model cannot address is reported there and the rest of the run is
        indexed. Not mapped to its *lexical* path instead: the bytes really do
        live outside the project, ``media.py``'s containment check would refuse
        to serve them, and an artifact in the index whose bytes cannot be
        fetched is a promise the API does not keep.
        """
        path = run_dir / spec.relative
        try:
            relative = self.relative(path)
        except AdapterError as exc:
            unmappable.append(
                {
                    "path": f"{spec.relative} (in {run_dir.name})",
                    "reason": scrub_host_paths(str(exc)),
                }
            )
            return None
        available = path.is_file()
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.entity(spec.key).value,
            "source_id": source_id.value,
            "kind": spec.kind,
            "role": spec.role,
            "media_type": media_type_for(path),
            "path": relative,
            "url": None,
            "bytes": path.stat().st_size if available else None,
            "sha256": sha256_file(path) if available and hash_artifacts else None,
            # Everything under raw/ is evidence and is never written again.
            "immutable": spec.role == "raw",
            "available": available,
        }

    # ----------------------------------------------------------------
    # The projection every medium shares
    # ----------------------------------------------------------------
    #
    # ``T-228``. What a knowledge unit *is* — a global id, a provenance class,
    # a kind, a label chosen the way ``library.py`` chooses it, a confidence,
    # and either a locator or the work a derived unit shows — is not a
    # statement about video, and neither is what a canonical edge is. The one
    # thing that differs between media is **where the evidence sits**, so that
    # is the one thing subclasses override.
    #
    # This is D-228's argument applied a second time: ``_status`` moved here
    # because what a status record is is not a YouTube rule, and the Twitter
    # adapter had already written a schema-invalid one by re-deriving it. The
    # same failure was available here at four times the size — and a second
    # implementation of ``_derived_refs`` in particular would be free to
    # disagree with its own ``derived_from`` edges, which is the exact bug that
    # method's docstring exists to prevent.

    def _locator(
        self,
        unit: Mapping[str, Any],
        source_id: ids.SourceId,
        owner: str,
    ) -> dict[str, Any]:
        """Where *unit*'s evidence sits, in this medium's coordinates.

        The only medium-specific step of the shared projection, and the reason
        it is a method rather than a branch: a time-based medium answers with a
        ``time_range`` into its segments, and a text-based one with a
        ``text_span`` into the item the claim was taken from (D-233). An
        adapter that mints source-class entities must answer; one that does not
        never reaches this.
        """
        raise AdapterError(
            f"{type(self).__name__} projects a source-class knowledge unit "
            f"({owner}) but states no locator for this medium"
        )

    def _knowledge_entities(
        self, run_dir: Path, source_id: ids.SourceId, units: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        canonical_path = self.relative(run_dir / "knowledge_units.json")
        entities = []
        for unit in units:
            local_id = required_field(unit, "id", f"a knowledge unit in {canonical_path}")
            owner = f"knowledge unit {local_id!r} in {canonical_path}"
            global_id = build_id(source_id.entity, local_id, owner)
            # 'user' is workspace content and never appears in a canonical file;
            # a unit that claims it would also claim a canonical path, which the
            # three-tier storage boundary forbids (D-006).
            provenance = copied_choice(
                required_field(unit, "source_class", owner),
                owner=owner,
                field="source_class",
                allowed=CANONICAL_PROVENANCE_CLASSES,
                required=True,
            )
            entity: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "global_id": global_id.value,
                "source_type": global_id.source_type,
                "external_id": global_id.external_id,
                "local_id": global_id.local_id,
                "library_id": global_id.library_id,
                "source_id": source_id.value,
                "entity_type": "knowledge_unit",
                "provenance_class": provenance,
                "kind": copied_choice(
                    unit.get("kind"),
                    owner=owner,
                    field="kind",
                    allowed=KNOWLEDGE_KINDS,
                    # A knowledge unit whose kind is unstated has no honest
                    # projection: the model requires one for this entity type.
                    required=True,
                ),
                # library.py:52 already makes this choice; making a different
                # one here would put two labels on one entity.
                "label": copied_text(
                    unit.get("normalized_statement") or unit.get("content"),
                    owner=owner,
                    field="normalized_statement/content",
                    max_length=MAX_LABEL_LENGTH,
                ),
                "confidence": copied_confidence(unit.get("confidence"), owner=owner),
                "canonical_path": canonical_path,
            }
            if provenance == "source":
                entity["locator"] = self._locator(unit, source_id, owner)
            else:
                entity["derived_from"] = self._derived_refs(unit, source_id, owner)
                # 'Derived from nothing, for no stated reason' is not derived
                # synthesis, and the note is what makes the claim auditable.
                entity["derivation_note"] = copied_text(
                    unit.get("derivation_note"),
                    owner=owner,
                    field="derivation_note",
                    max_length=None,
                    allow_empty=False,
                    required=True,
                )
            entities.append(entity)
        return entities

    def _derived_refs(
        self, unit: Mapping[str, Any], source_id: ids.SourceId, owner: str
    ) -> list[str]:
        """The units a derived unit was synthesised from, as global ids.

        The one place the list is read, so the ``EntityRef`` and the
        ``derived_from`` edges cannot disagree about it. A derived unit that
        shows no work is refused rather than given an empty list: the empty list
        asserts derived provenance while naming nothing, the schemas reject it,
        and the edge that should have recorded the provenance silently vanishes
        along with it.
        """
        refs = unit.get("derived_from")
        if refs is None:
            raise AdapterError(
                f"{owner} is derived but names nothing it was derived from; a derived "
                "unit shows its work or it is not indexed as derived"
            )
        if not isinstance(refs, list):
            refuse(owner, "derived_from", refs, "carries a list of unit ids there")
        if not refs:
            raise AdapterError(
                f"{owner} is derived from an empty list; an empty list asserts derived "
                "provenance while showing no work"
            )
        values = [build_id(source_id.entity, ref, f"derived_from of {owner}").value for ref in refs]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise AdapterError(
                f"{owner} names {', '.join(duplicates)} in derived_from more than once; "
                "one provenance edge, one entry"
            )
        return values

    def _canonical_relations(
        self, run_dir: Path, source_id: ids.SourceId, edges: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        canonical_path = self.relative(run_dir / "relationships.json")
        relations = []
        for index, edge in enumerate(edges):
            owner = f"relationship {index} in {canonical_path}"
            from_id = build_id(source_id.entity, required_field(edge, "from", owner), owner)
            to_id = build_id(source_id.entity, required_field(edge, "to", owner), owner)
            # The canonical vocabulary is exactly constants.RELATION_TYPES. An
            # edge outside it is not a canonical edge, and calling it one — or
            # quietly relabelling it as synthetic — would blur the vocabulary
            # separation the whole relation model rests on.
            name = copied_choice(
                required_field(edge, "relation", owner),
                owner=owner,
                field="relation",
                allowed=CANONICAL_RELATION_TYPES,
                required=True,
            )
            relation: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "id": edge_id(from_id.value, name, to_id.value),
                "from_id": from_id.value,
                "to_id": to_id.value,
                "relation": name,
                "relation_vocabulary": "canonical",
                "provenance_class": copied_choice(
                    edge.get("source_class"),
                    owner=owner,
                    field="source_class",
                    allowed=CANONICAL_PROVENANCE_CLASSES,
                    required=True,
                ),
                # A canonical edge states a confidence; unlike derived_from,
                # this one is about the edge itself, so an absent value cannot
                # be read as 'no confidence exists' and is refused instead.
                "confidence": copied_confidence(
                    edge.get("confidence"), owner=owner, required=True
                ),
                "source_id": source_id.value,
                "canonical_path": canonical_path,
            }
            # Without the flag a self-loop is an error, not a design
            # (validators.py:124), so it is carried through as stated.
            if "intentional_self_loop" in edge:
                relation["intentional_self_loop"] = bool(edge["intentional_self_loop"])
            relations.append(relation)
        return relations

    def _derived_from_relations(
        self, run_dir: Path, source_id: ids.SourceId, units: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """``derived_from`` edges, the library-synthetic vocabulary.

        ``confidence`` is ``null`` on purpose. The unit carries a confidence
        about *itself*; no confidence about the edge exists anywhere in the
        canonical data, and copying the unit's onto the edge would put a number
        on a claim nothing made. ``library.py:70`` writes the unit's value into
        its own graph for its own reasons; the index does not carry that
        forward as though it were an edge confidence.
        """
        canonical_path = self.relative(run_dir / "knowledge_units.json")
        relations = []
        for unit in units:
            local_id = unit.get("id")
            if unit.get("source_class") != "derived":
                continue
            owner = f"knowledge unit {local_id!r} in {canonical_path}"
            from_id = build_id(source_id.entity, local_id, owner)
            # The same list the EntityRef carries, read once: a unit that shows
            # no work is refused there and here alike, so an edge can no longer
            # go missing while the unit it belongs to is still indexed.
            for to_id_value in self._derived_refs(unit, source_id, owner):
                relations.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "id": edge_id(from_id.value, "derived_from", to_id_value),
                        "from_id": from_id.value,
                        "to_id": to_id_value,
                        "relation": "derived_from",
                        "relation_vocabulary": "library_synthetic",
                        "provenance_class": "derived",
                        "confidence": None,
                        "source_id": source_id.value,
                        "canonical_path": canonical_path,
                    }
                )
        return relations

    @abstractmethod
    def detect(self, run_dir: Path) -> bool:
        """Whether *run_dir* is a run this adapter can map."""

    @abstractmethod
    def adapt_run(self, run_dir: Path, *, hash_artifacts: bool = False) -> IndexRecords:
        """Map one canonical run directory onto the v1 model.

        *hash_artifacts* is off by default: hashing every file of every run is
        the incremental indexer's concern (``T-102``), not something a caller
        that only wants to read a status should pay for.
        """
