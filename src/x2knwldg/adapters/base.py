"""The source-neutral adapter contract (canvas plan §11, ADR 0001 item 7, T-004).

An adapter maps one canonical run directory onto the v1 index model in
``schemas/v1/``. It is a **reader**. It opens canonical files, copies values,
and returns records; it never writes, never recomputes a status, and never
supplies a value the canonical files do not contain. ``output/<id>/raw/`` is
immutable evidence and is only ever stat-ed and hashed.

Four rules shape every adapter, and each of them is enforced here rather than
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

Adding a source type means adding a subclass and registering it. It must not
require a change to this module, to the schemas, or to the frontend.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Iterator, Mapping

from .. import ids

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

    def addressable(self) -> Iterator[tuple[str, str]]:
        """Every id this set claims, paired with a description of the claimant.

        Artifacts and entities share one global-id namespace per source, so
        uniqueness has to be checked across both.
        """
        for artifact in self.artifacts:
            yield artifact["id"], f"artifact {artifact.get('kind')}"
        for entity in self.entities:
            yield entity["global_id"], f"{entity.get('entity_type')}"


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
    return relative.as_posix()


def media_type_for(path: Path) -> str | None:
    """The registered media type of *path*, or ``None`` when there is none."""
    return MEDIA_TYPES.get(path.suffix.lower())


def read_optional_json(path: Path) -> Any | None:
    """Read a canonical JSON file, or return ``None`` if it cannot be read.

    A half-finished or damaged run must still be indexable and still be
    displayed honestly, so an unreadable file is an absence rather than a
    crash. What is absent is reported as absent — never filled in.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


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


def check_records(records: IndexRecords) -> IndexRecords:
    """Assert everything about a record set that JSON Schema cannot.

    The three invariants of ``schemas/v1/README.md`` — a global id equals its
    parts, a source id equals its parts, a time range does not end before it
    starts — plus two that follow from them: an artifact belongs to the source
    it names, and no two records claim the same global id.

    Called by every adapter before it returns, so the invariants are enforced
    where the records are produced and not only where they are tested.
    """
    for source in records.sources:
        _wrap(ids.check_source_ids, source, f"source {source.get('id')}")

    claimed: dict[str, str] = {}
    for artifact in records.artifacts:
        owner = f"artifact {artifact.get('id')}"
        global_id = _wrap(ids.parse_global_id, artifact["id"], owner)
        if artifact.get("source_id") != global_id.source_id.value:
            raise AdapterError(
                f"{owner} claims source_id {artifact.get('source_id')!r}, but its own id "
                f"belongs to {global_id.source_id.value!r}"
            )
        _claim(claimed, artifact["id"], owner)

    for entity in records.entities:
        owner = f"{entity.get('entity_type')} {entity.get('global_id')}"
        _wrap(ids.check_entity_ref_ids, entity, owner)
        locator = entity.get("locator")
        if locator is not None:
            _wrap(ids.check_locator, locator, f"locator of {owner}")
        _claim(claimed, entity["global_id"], owner)

    for relation in records.relations:
        owner = f"relation {relation.get('id')}"
        _wrap(ids.parse_global_id, relation["from_id"], owner)
        _wrap(ids.parse_global_id, relation["to_id"], owner)

    return records


def _claim(claimed: dict[str, str], global_id: str, owner: str) -> None:
    previous = claimed.get(global_id)
    if previous is not None:
        raise AdapterError(
            f"{owner} and {previous} both claim the global id {global_id!r}; "
            "one entity, one address"
        )
    claimed[global_id] = owner


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
