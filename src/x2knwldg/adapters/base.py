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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Iterator, Mapping, NoReturn

from .. import constants, ids
from ..io import read_json_or_reason

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

    def __add__(self, other: "IndexRecords") -> "IndexRecords":
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
        raise AdapterError(
            f"{resolved} lies outside the project root {root}; index records carry "
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
        datetime.fromisoformat(text)
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


def declared_source_type(metadata: Mapping[str, Any]) -> str:
    """The source type a run declares, defaulting as ``library.py:39`` does.

    Every run written before the field existed is a YouTube run. This lives here
    rather than in an adapter because dispatch has to read it *before* an
    adapter has been chosen.
    """
    declared = metadata.get("source_type")
    return declared if isinstance(declared, str) and declared else ids.DEFAULT_SOURCE_TYPE


def read_status(document: Any | None) -> str:
    """The ``status`` a validator document states, verbatim, or ``UNKNOWN``.

    There is deliberately no branch in this function that can turn a stated
    ``PARTIAL`` or ``FAIL`` into anything else (ADR 0001 invariant 2).
    """
    if not isinstance(document, Mapping):
        return UNKNOWN_STATUS
    status = document.get("status")
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
