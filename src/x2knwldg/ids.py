"""Identifier helpers for the source-neutral index model (D-011, T-003).

Two identifier forms are real, and neither replaces the other:

``<source-type>:<external-id>:<local-id>``
    The **global id**. Identity for the index, the API, and board files.

``<video-id>:<knowledge-unit-id>``, or ``concept:<hash>``
    The **library id**, exactly as ``output/library/graph.json`` spells it.
    ``.claude/commands/kg_navigator.md`` mandates this form, so ``library.py``
    must keep emitting it. This module *adds* the global form alongside it and
    converts between the two; it never replaces one with the other.

``SR-<16 hex digits>``
    A **source relation** id (`T-251`, D-247), and the one identifier here that
    is a digest rather than a spelling of its parts. It cannot be a spelling:
    the record joins two source ids, and concatenating them would exceed every
    length bound the other forms live inside. It is deterministic for the same
    reason ``adapters.base.edge_id`` is — a rebuild must reach the identical set
    — and :func:`source_relation_id` states exactly which four parts are
    identity and which fields are content.

The patterns here mirror ``schemas/v1/common.schema.json`` (D-015). The
duplication is deliberate — the core package stays zero-dependency and cannot
import ``jsonschema`` — and it is guarded: ``tests/test_ids.py`` fails the
moment a pattern or a length bound disagrees with the schema.

This module also enforces the three invariants that JSON Schema cannot express,
listed in ``schemas/v1/README.md``:

1. ``global_id`` equals ``source_type:external_id:local_id``.
2. ``Source.id`` equals ``source_type:external_id``.
3. A ``time_range`` locator has ``end_sec >= start_sec``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .constants import SOURCE_RELATION_SCOPES, SOURCE_RELATION_TYPES
from .io import require_seconds

# --------------------------------------------------------------------------
# Vocabulary mirrored from schemas/v1/common.schema.json — drift-tested
# --------------------------------------------------------------------------

SOURCE_TYPE_PATTERN = "[a-z][a-z0-9_]*"
ID_PART_PATTERN = "[A-Za-z0-9_-][A-Za-z0-9._-]*"

SOURCE_TYPE_MAX_LENGTH = 32
ID_PART_MAX_LENGTH = 256
SOURCE_ID_MAX_LENGTH = 300
GLOBAL_ID_MAX_LENGTH = 600
LIBRARY_ID_MAX_LENGTH = 600

# Anchored with ``\Z``, not ``$``. The pattern *strings* above are mirrored
# verbatim into ``schemas/v1/common.schema.json``, where they are read as
# ECMA-262 and ``$`` does not match before a trailing newline. Python's
# ``$`` does, so ``^...$`` here would accept ``"KU-1\n"`` — an id the schema
# rejects, and one that reaches a TypeScript consumer as unaddressable.
_SOURCE_TYPE_RE = re.compile(f"^{SOURCE_TYPE_PATTERN}\\Z")
_ID_PART_RE = re.compile(f"^{ID_PART_PATTERN}\\Z")

#: Reserved namespace for cross-source library entities (D-016). A canonical
#: concept belongs to no single source, so ``concept:<hash>`` becomes
#: ``library:concepts:<hash>``.
LIBRARY_SOURCE_TYPE = "library"
LIBRARY_CONCEPTS_EXTERNAL_ID = "concepts"

#: Prefix ``library.py`` uses for canonical concept ids in the library form.
CONCEPT_LIBRARY_PREFIX = "concept"

#: Source type assumed for a canonical run whose ``metadata.json`` predates the
#: field. Every existing run is a YouTube run.
DEFAULT_SOURCE_TYPE = "youtube"

#: The local id of the one entity that stands for a whole acquired source
#: (D-244, `T-251`). ``EntityRef.entity_type`` has reserved ``source`` since
#: `T-002`; this is the ``local_id`` half of the identity that reservation
#: implies, so a source node is addressed as ``<source-type>:<external-id>:source``.
#:
#: The segment was free and is now claimed rather than assumed:
#: ``YouTubeAdapter``'s raw artifact key is ``raw_source``, not ``source``, and
#: ``IndexRecords.addressable`` claims this id in the same namespace as every
#: artifact and entity, so a future adapter that spells an artifact key
#: ``source`` is refused instead of silently overwriting the source node.
SOURCE_ENTITY_LOCAL_ID = "source"

#: Prefix and digest width of a ``SourceRelation`` id (D-247, `T-251`).
SOURCE_RELATION_ID_PREFIX = "SR-"
SOURCE_RELATION_DIGEST_LENGTH = 16

#: The separator joining the parts of a source-relation digest. A unit
#: separator cannot occur in a source id, a relation type or a scope — every
#: part is validated against a closed vocabulary or ``ID_PART_PATTERN`` before
#: it is joined — so the encoding is unambiguous by construction rather than by
#: hope. ``adapters.base.edge_id`` escapes its separator for the same reason;
#: here the parts cannot spell it at all.
_DIGEST_SEPARATOR = "\x1f"


def declared_source_type(metadata: Mapping[str, Any]) -> str:
    """The source type a run declares, or :data:`DEFAULT_SOURCE_TYPE`.

    Every run written before the field existed is a YouTube run, so an absent
    ``source_type`` is an answer rather than a gap.

    This lives here, in the module that owns the vocabulary, because **dispatch
    has to read it before an adapter has been chosen** — and by `T-230` three
    modules were reading it three ways: ``adapters.base``, which is where this
    function was and which the finalize path cannot import without inverting the
    layering, ``library.rebuild_library``, and ``validators.validate_provenance``.
    The first two were the same rule spelled twice, and are now this one call.

    The third is deliberately **not** a caller. ``validate_provenance`` reads
    ``document.get("source_type", DEFAULT_SOURCE_TYPE)``, which returns ``None``
    for a document that states ``"source_type": null`` — and that is how it
    reports ``unknown_source_type`` rather than silently validating a null as a
    YouTube run. Folding it in here would turn one of its errors into a default,
    so it keeps its own read and a comment saying so.
    """
    declared = metadata.get("source_type")
    return declared if isinstance(declared, str) and declared else DEFAULT_SOURCE_TYPE


class IdError(ValueError):
    """An identifier is malformed, or its parts contradict the whole."""


# --------------------------------------------------------------------------
# Part validation
# --------------------------------------------------------------------------


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise IdError(f"{label} must be a string, got {type(value).__name__}")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IdError(f"{label} must be a mapping, got {type(value).__name__}")
    return value


def _require_offset(value: Any, label: str) -> int:
    """Return *value* as a codepoint offset, or raise ``IdError``.

    A half-open character range is indexed with integers, so unlike
    ``_require_seconds`` this refuses a float outright rather than widening to
    one: ``text[0:2.0]`` is a ``TypeError``, and an offset that cannot slice
    the text it addresses is not an offset. ``bool`` is excluded for the reason
    it is excluded there — it is an ``int`` in Python and ``True`` is not a
    position.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise IdError(f"{label} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise IdError(f"{label} must not be negative, got {value}")
    return value


def _require_seconds(value: Any, label: str) -> float:
    """Return *value* as a timestamp in seconds, or raise ``IdError``.

    Mirrors ``timestampSec`` in ``schemas/v1/common.schema.json``: a number,
    and not a negative one. ``bool`` is excluded because it is an ``int`` in
    Python and ``True`` is not a time. ``NaN`` is excluded because every
    comparison against it is ``False``, so a ``NaN`` end time would slip past
    an ``end < start`` test and land in an index as an unorderable locator.

    D-185: the rule is ``io.require_seconds`` and this is the ``IdError``
    spelling of it. It used to be a near-verbatim copy that never imported
    ``io`` at all, differing from ``segmenter``'s copy only in the exception
    type — which is now the one thing this function supplies.
    """
    return require_seconds(value, label, error=IdError)


def validate_source_type(value: Any) -> str:
    """Return *value* if it is a well-formed source type, else raise."""
    text = _require_text(value, "source_type")
    if not _SOURCE_TYPE_RE.match(text):
        raise IdError(f"source_type {text!r} must match {SOURCE_TYPE_PATTERN!r}")
    if len(text) > SOURCE_TYPE_MAX_LENGTH:
        raise IdError(f"source_type {text!r} exceeds {SOURCE_TYPE_MAX_LENGTH} characters")
    return text


def validate_id_part(value: Any, label: str = "id part") -> str:
    """Return *value* if it is a well-formed identifier segment, else raise.

    Colons are excluded so an identifier always splits unambiguously, and a
    leading dot is excluded so no segment can ever be ``.`` or ``..``.
    """
    text = _require_text(value, label)
    if not _ID_PART_RE.match(text):
        raise IdError(f"{label} {text!r} must match {ID_PART_PATTERN!r}")
    if len(text) > ID_PART_MAX_LENGTH:
        raise IdError(f"{label} {text!r} exceeds {ID_PART_MAX_LENGTH} characters")
    return text


def is_id_part(value: Any) -> bool:
    """Whether *value* can stand as one segment of an identifier."""
    try:
        validate_id_part(value)
    except IdError:
        return False
    return True


# --------------------------------------------------------------------------
# The two-part source id
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceId:
    """``<source-type>:<external-id>`` — identifies a source, not an entity."""

    source_type: str
    external_id: str

    @property
    def value(self) -> str:
        return f"{self.source_type}:{self.external_id}"

    def __str__(self) -> str:
        return self.value

    def entity(self, local_id: str) -> GlobalId:
        """Return the global id of *local_id* inside this source."""
        return make_global_id(self.source_type, self.external_id, local_id)


def make_source_id(source_type: Any, external_id: Any) -> SourceId:
    """D-114: ``Any``, not ``str``, because refusing junk is the contract.

    ``validate_id_part`` has always taken ``Any`` and raised ``IdError`` for
    anything that is not a usable segment, and every caller reads its argument
    out of an untrusted JSON document and wraps the call in ``except IdError``
    for exactly that reason. A ``str`` annotation described a precondition no
    caller could satisfy, so it made the checker complain about the one thing
    the function exists to handle."""
    validate_source_type(source_type)
    validate_id_part(external_id, "external_id")
    source_id = SourceId(source_type, external_id)
    if len(source_id.value) > SOURCE_ID_MAX_LENGTH:
        raise IdError(f"source id {source_id.value!r} exceeds {SOURCE_ID_MAX_LENGTH} characters")
    return source_id


def parse_source_id(value: str) -> SourceId:
    text = _require_text(value, "source id")
    parts = text.split(":")
    if len(parts) != 2:
        raise IdError(f"source id {text!r} must have exactly two colon-separated parts")
    return make_source_id(parts[0], parts[1])


# --------------------------------------------------------------------------
# The three-part global id (D-011)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GlobalId:
    """``<source-type>:<external-id>:<local-id>`` — index, API, and board identity."""

    source_type: str
    external_id: str
    local_id: str

    @property
    def value(self) -> str:
        return f"{self.source_type}:{self.external_id}:{self.local_id}"

    def __str__(self) -> str:
        return self.value

    @property
    def source_id(self) -> SourceId:
        """The two-part id of the source this entity belongs to.

        Canonical concepts live in the reserved ``library`` namespace and belong
        to no ingested source, so their ``source_id`` is ``None`` in a record.
        """
        return SourceId(self.source_type, self.external_id)

    @property
    def is_library_concept(self) -> bool:
        return (
            self.source_type == LIBRARY_SOURCE_TYPE
            and self.external_id == LIBRARY_CONCEPTS_EXTERNAL_ID
        )

    @property
    def library_id(self) -> str:
        """The same entity as ``output/library/graph.json`` spells it."""
        return library_id_from_global_id(self)


def make_global_id(source_type: Any, external_id: Any, local_id: Any) -> GlobalId:
    validate_source_type(source_type)
    validate_id_part(external_id, "external_id")
    validate_id_part(local_id, "local_id")
    global_id = GlobalId(source_type, external_id, local_id)
    if len(global_id.value) > GLOBAL_ID_MAX_LENGTH:
        raise IdError(f"global id {global_id.value!r} exceeds {GLOBAL_ID_MAX_LENGTH} characters")
    return global_id


def parse_global_id(value: str) -> GlobalId:
    """Parse a three-part global id with a two-limit split on ``':'``."""
    text = _require_text(value, "global id")
    parts = text.split(":", 2)
    if len(parts) != 3:
        raise IdError(f"global id {text!r} must have three colon-separated parts")
    return make_global_id(parts[0], parts[1], parts[2])


def is_global_id(value: Any) -> bool:
    try:
        parse_global_id(value)
    except IdError:
        return False
    return True


def concept_global_id(concept_hash: str) -> GlobalId:
    """Global id of a cross-source canonical concept (D-016)."""
    return make_global_id(LIBRARY_SOURCE_TYPE, LIBRARY_CONCEPTS_EXTERNAL_ID, concept_hash)


def source_entity_global_id(source_id: SourceId | str) -> GlobalId:
    """Global id of the entity that stands for a whole acquired source (D-244).

    One per run, whatever the run's status: a ``FAIL`` run is a source that
    exists, and a Source Map that quietly omitted it would be reporting a
    smaller library than the one on disk.

    Built rather than spelled, like every other id here, so the first invariant
    of ``schemas/v1/README.md`` holds by construction: the parts and the whole
    cannot disagree, and a malformed ``external_id`` is refused at the point the
    adapter reads it rather than at the point the index tries to store it.
    """
    parsed = source_id if isinstance(source_id, SourceId) else parse_source_id(source_id)
    return parsed.entity(SOURCE_ENTITY_LOCAL_ID)


def source_relation_id(
    from_source_id: Any, to_source_id: Any, relation_type: Any, scope: Any
) -> str:
    """The deterministic id of one ``SourceRelation`` (D-247, `T-251`).

    ``SR-`` followed by the first 16 hex digits of the SHA-256 of the four parts
    that *are* the relation's identity: the two endpoints in their recorded
    order, the relation type, and the scope.

    **What is identity, and what is content.** ``basis``, ``rationale`` and
    ``generated_from`` are deliberately not in the digest. A later synthesis run
    that finds a fourth ground for the same critique has learned more about one
    relation, not discovered a second one, so it updates a record instead of
    minting a new id and leaving the old one to be deleted by a path that could
    forget to. What the digest *does* separate is what
    ``SOURCE_MAP_SPEC.md`` §3.3 allows to coexist: two records between the same
    pair of sources whose supported semantics differ.

    **Direction is part of the identity.** ``critiques`` is not its own inverse,
    so the two orderings of one pair are two ids and the arguments are never
    sorted.

    Every part is validated before it is hashed — the endpoints as source ids,
    the type and scope against the closed vocabularies of
    :mod:`x2knwldg.constants`. A digest over unvalidated input is a stable id
    for a record that should never have existed.
    """
    endpoints = [
        parse_source_id(_require_text(value, label)).value
        for value, label in (
            (from_source_id, "from_source_id"),
            (to_source_id, "to_source_id"),
        )
    ]
    if endpoints[0] == endpoints[1]:
        raise IdError(
            f"a source relation joins two different sources; both endpoints are "
            f"{endpoints[0]!r}"
        )
    relation = _require_text(relation_type, "relation_type")
    if relation not in SOURCE_RELATION_TYPES:
        raise IdError(
            f"relation_type {relation!r} is not one of the {len(SOURCE_RELATION_TYPES)} "
            "source relation types"
        )
    qualifier = _require_text(scope, "scope")
    if qualifier not in SOURCE_RELATION_SCOPES:
        raise IdError(f"scope {qualifier!r} must be one of {sorted(SOURCE_RELATION_SCOPES)}")

    payload = _DIGEST_SEPARATOR.join([*endpoints, relation, qualifier])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{SOURCE_RELATION_ID_PREFIX}{digest[:SOURCE_RELATION_DIGEST_LENGTH]}"


def is_source_relation_id(value: Any) -> bool:
    """Whether *value* has the shape a ``SourceRelation`` id is written in.

    A shape check, not a proof: it says the string could have come from
    :func:`source_relation_id`, never that it did. Only recomputing the digest
    from the record's own endpoints, type and scope shows that, which is the
    apply gate's job in `T-253`.
    """
    if not isinstance(value, str) or not value.startswith(SOURCE_RELATION_ID_PREFIX):
        return False
    digest = value[len(SOURCE_RELATION_ID_PREFIX) :]
    return len(digest) == SOURCE_RELATION_DIGEST_LENGTH and all(
        char in "0123456789abcdef" for char in digest
    )


# --------------------------------------------------------------------------
# The two-part library id — mandated by kg_navigator, never replaced
# --------------------------------------------------------------------------


def make_library_id(external_id: Any, local_id: Any) -> str:
    """``<video-id>:<knowledge-unit-id>``, the form ``library.py`` emits.

    ``Any`` for the reason :func:`make_source_id` gives.
    """
    validate_id_part(external_id, "external_id")
    validate_id_part(local_id, "local_id")
    library_id = f"{external_id}:{local_id}"
    if len(library_id) > LIBRARY_ID_MAX_LENGTH:
        raise IdError(f"library id {library_id!r} exceeds {LIBRARY_ID_MAX_LENGTH} characters")
    return library_id


def make_concept_library_id(concept_hash: str) -> str:
    """``concept:<hash>``, the form ``library.py`` emits for a concept node."""
    return make_library_id(CONCEPT_LIBRARY_PREFIX, concept_hash)


def parse_library_id(value: str) -> tuple[str, str]:
    """Split a library id into its two parts without interpreting them."""
    text = _require_text(value, "library id")
    parts = text.split(":")
    if len(parts) != 2:
        raise IdError(f"library id {text!r} must have exactly two colon-separated parts")
    validate_id_part(parts[0], "library id prefix")
    validate_id_part(parts[1], "library id suffix")
    return parts[0], parts[1]


def global_id_from_library_id(
    value: str, *, source_type: str | None = None
) -> GlobalId:
    """Convert a library id to its global form.

    The library form states two parts and the global form needs three, so the
    missing part — the source type — is supplied by the caller. Pass the
    ``source_type`` the record carries (``library.py`` writes it beside every
    node, D-011) and the conversion is exact for **every** source type. Omit it
    and the id is read as a legacy YouTube one, which is what every library id
    written before D-011 is.

    ``concept:<hash>`` is the one prefix with a reserved meaning: a canonical
    concept in the ``library:concepts`` namespace (D-016). That reading applies
    only when the caller states no source type, or states ``library``. An
    ingested source whose external id is literally ``concept`` therefore keeps
    its own namespace — passing ``source_type="youtube"`` yields
    ``youtube:concept:<hash>``, not the library concept it used to be silently
    captured into. A stated source type is always taken literally; only the
    unstated case falls back to the reserved reading.
    """
    prefix, suffix = parse_library_id(value)
    if prefix == CONCEPT_LIBRARY_PREFIX:
        if source_type is None or source_type == LIBRARY_SOURCE_TYPE:
            return concept_global_id(suffix)
        return make_global_id(source_type, prefix, suffix)
    return make_global_id(
        DEFAULT_SOURCE_TYPE if source_type is None else source_type, prefix, suffix
    )


def library_id_from_global_id(value: GlobalId | str) -> str:
    """Convert a global id back to the library form.

    Left inverse of :func:`global_id_from_library_id` for every source type,
    given the source type back::

        library = library_id_from_global_id(g)
        global_id_from_library_id(library, source_type=g.source_type) == g

    That round trip is total — it holds for ``library:concepts:<hash>``, for a
    source whose external id happens to be ``concept``, and for every source
    type, not only ``youtube``. The source type is not recoverable from the
    library string alone; it never was, and pretending otherwise is what made
    the conversion lossy.

    Exactly one global id has no library form: ``library:concept:<local>``,
    whose two-part spelling ``concept:<local>`` is the reserved concept
    encoding of D-016 inside the very namespace that reserves it. It is
    refused rather than written down as an id that reads back as a different
    record.
    """
    global_id = value if isinstance(value, GlobalId) else parse_global_id(value)
    if global_id.is_library_concept:
        return make_concept_library_id(global_id.local_id)
    if (
        global_id.source_type == LIBRARY_SOURCE_TYPE
        and global_id.external_id == CONCEPT_LIBRARY_PREFIX
    ):
        raise IdError(
            f"{global_id.value!r} has no library form: "
            f"{CONCEPT_LIBRARY_PREFIX}:{global_id.local_id} is the reserved spelling of "
            f"{LIBRARY_SOURCE_TYPE}:{LIBRARY_CONCEPTS_EXTERNAL_ID}:{global_id.local_id} "
            "(D-016), so the two would be indistinguishable"
        )
    return make_library_id(global_id.external_id, global_id.local_id)


# --------------------------------------------------------------------------
# The three invariants JSON Schema cannot express
# --------------------------------------------------------------------------


def check_entity_ref_ids(record: Mapping[str, Any]) -> None:
    """Invariant 1 — an ``EntityRef``'s ``global_id`` equals its three parts.

    Also checks the two derived fields when they are present and non-null:
    ``source_id`` must be the entity's own source, and ``library_id`` must be
    the same entity in the library vocabulary (risk R12 — the two forms must
    never drift).
    """
    global_id = make_global_id(
        record["source_type"], record["external_id"], record["local_id"]
    )
    stated = record["global_id"]
    if stated != global_id.value:
        raise IdError(
            f"global_id {stated!r} contradicts its parts, which spell {global_id.value!r}"
        )

    stated_source = record.get("source_id")
    if stated_source is not None:
        expected_source = (
            None if global_id.is_library_concept else global_id.source_id.value
        )
        if expected_source is None:
            raise IdError(
                f"{global_id.value} is a cross-source library entity and has no source_id, "
                f"but the record states {stated_source!r}"
            )
        if stated_source != expected_source:
            raise IdError(
                f"source_id {stated_source!r} does not own entity {global_id.value!r}"
            )

    stated_library = record.get("library_id")
    if stated_library is not None and stated_library != global_id.library_id:
        raise IdError(
            f"library_id {stated_library!r} contradicts global_id {global_id.value!r}, "
            f"which spells {global_id.library_id!r}"
        )


def check_source_ids(record: Mapping[str, Any]) -> None:
    """Invariant 2 — a ``Source``'s ``id`` equals its two parts."""
    source_id = make_source_id(record["source_type"], record["external_id"])
    stated = record["id"]
    if stated != source_id.value:
        raise IdError(
            f"Source id {stated!r} contradicts its parts, which spell {source_id.value!r}"
        )


def check_locator(locator: Mapping[str, Any]) -> None:
    """Invariant 3 — a locator's range does not end before it starts.

    Any ``artifact_id`` present must also be a well-formed global id.

    A ``time_range`` must actually state two timings, and each must be a
    finite, non-negative number of seconds — the ``timestampSec`` contract.
    Before this checked, a locator carrying ``None``, a string, or a negative
    second passed the ordering test or crashed out of it with a bare
    ``TypeError``/``KeyError``, neither of which a caller catching ``IdError``
    could see. Every failure here is an ``IdError``.

    A ``text_span`` is the same invariant over a different coordinate, and it
    is checked for the same reason rather than by analogy: ``T-228`` projects
    every source claim in a non-time-based medium through this branch (D-233),
    so from here on it carries real traffic. The schema requires the branch's
    four fields and bounds each at zero, but JSON Schema compares no two
    fields, so a span ending before it starts is schema-valid — and a locator
    the index cannot order is exactly what invariant 3 exists to refuse. The
    excerpt is deliberately **not** measured against ``end_char - start_char``:
    the two agree only under the medium's own definition of a character, and
    ``twitter.extract`` already compares an excerpt with its own slice
    verbatim, where the capture's text is in hand. Re-deriving that here from
    a length would be a second, weaker answer to a question already settled.
    """
    _require_mapping(locator, "locator")
    artifact_id = locator.get("artifact_id")
    if artifact_id is not None:
        parse_global_id(artifact_id)
    kind = locator.get("type")
    if kind == "time_range":
        for field in ("start_sec", "end_sec"):
            if field not in locator:
                raise IdError(f"time_range locator is missing {field}")
        start_sec = _require_seconds(locator["start_sec"], "start_sec")
        end_sec = _require_seconds(locator["end_sec"], "end_sec")
        if end_sec < start_sec:
            raise IdError(
                f"time_range locator ends at {end_sec} before it starts at {start_sec}"
            )
        return
    if kind == "text_span":
        # The schema makes artifact_id required on this branch alone, because a
        # character offset into an unnamed artifact addresses nothing. The
        # check above only runs when one is *present*, so its absence is caught
        # here rather than passing as "no artifact_id to validate".
        if artifact_id is None:
            raise IdError("text_span locator is missing artifact_id")
        for field in ("start_char", "end_char"):
            if field not in locator:
                raise IdError(f"text_span locator is missing {field}")
        start_char = _require_offset(locator["start_char"], "start_char")
        end_char = _require_offset(locator["end_char"], "end_char")
        if end_char < start_char:
            raise IdError(
                f"text_span locator ends at {end_char} before it starts at {start_char}"
            )
