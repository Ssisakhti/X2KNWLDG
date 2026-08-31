"""Identifier helpers for the source-neutral index model (D-011, T-003).

Two identifier forms are real, and neither replaces the other:

``<source-type>:<external-id>:<local-id>``
    The **global id**. Identity for the index, the API, and board files.

``<video-id>:<knowledge-unit-id>``, or ``concept:<hash>``
    The **library id**, exactly as ``output/library/graph.json`` spells it.
    ``.claude/commands/kg_navigator.md`` mandates this form, so ``library.py``
    must keep emitting it. This module *adds* the global form alongside it and
    converts between the two; it never replaces one with the other.

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

import re
from dataclasses import dataclass
from typing import Any, Mapping


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

_SOURCE_TYPE_RE = re.compile(f"^{SOURCE_TYPE_PATTERN}$")
_ID_PART_RE = re.compile(f"^{ID_PART_PATTERN}$")

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


class IdError(ValueError):
    """An identifier is malformed, or its parts contradict the whole."""


# --------------------------------------------------------------------------
# Part validation
# --------------------------------------------------------------------------


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise IdError(f"{label} must be a string, got {type(value).__name__}")
    return value


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


def make_source_id(source_type: str, external_id: str) -> SourceId:
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


def is_source_id(value: Any) -> bool:
    try:
        parse_source_id(value)
    except IdError:
        return False
    return True


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


def make_global_id(source_type: str, external_id: str, local_id: str) -> GlobalId:
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


# --------------------------------------------------------------------------
# The two-part library id — mandated by kg_navigator, never replaced
# --------------------------------------------------------------------------


def make_library_id(external_id: str, local_id: str) -> str:
    """``<video-id>:<knowledge-unit-id>``, the form ``library.py`` emits."""
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
    value: str, *, source_type: str = DEFAULT_SOURCE_TYPE
) -> GlobalId:
    """Convert a library id to its global form.

    ``concept:<hash>`` maps into the reserved ``library:concepts`` namespace
    (D-016); every other library id is ``<external-id>:<local-id>`` inside
    *source_type*.
    """
    prefix, suffix = parse_library_id(value)
    if prefix == CONCEPT_LIBRARY_PREFIX:
        return concept_global_id(suffix)
    return make_global_id(source_type, prefix, suffix)


def library_id_from_global_id(value: GlobalId | str) -> str:
    """Convert a global id back to the library form. Inverse of the above."""
    global_id = value if isinstance(value, GlobalId) else parse_global_id(value)
    if global_id.is_library_concept:
        return make_concept_library_id(global_id.local_id)
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
    """Invariant 3 — a ``time_range`` locator has ``end_sec >= start_sec``.

    Any ``artifact_id`` present must also be a well-formed global id.
    """
    artifact_id = locator.get("artifact_id")
    if artifact_id is not None:
        parse_global_id(artifact_id)
    if locator.get("type") != "time_range":
        return
    start_sec = locator["start_sec"]
    end_sec = locator["end_sec"]
    if end_sec < start_sec:
        raise IdError(
            f"time_range locator ends at {end_sec} before it starts at {start_sec}"
        )
