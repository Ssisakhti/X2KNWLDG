"""The YouTube adapter — ``output/<video-id>/`` seen through the v1 index model.

The first adapter, and the reference implementation of the contract in
:mod:`x2knwldg.adapters.base` (``T-004``, canvas plan §11). It changes no
canonical output: every canonical file keeps its own schema, ``video_id`` keeps
its name (ADR 0001 invariant 6), and ``library.py`` keeps emitting the two-part
node id that ``.claude/commands/kg_navigator.md`` mandates. Source-neutrality
lives here, in the mapping, and nowhere in the pipeline.

What is mapped
--------------

============================  ==================================================
``metadata.json``             the ``Source`` record, and its ``adapter_metadata``
the files in the run          ``Artifact`` records, including the vault export
``validation.json``,          the ``Source.status`` block, copied verbatim
``coverage.json``
``knowledge_units.json``      ``EntityRef`` records, and their ``time_range``
                              locators into the segments artifact
``relationships.json``        ``IndexedRelation`` records, ``canonical``
                              vocabulary
a unit's ``derived_from``     ``IndexedRelation`` records, ``library_synthetic``
``output/library/``           canonical concepts and their ``expresses_concept``
                              edges, via :func:`adapt_library`
============================  ==================================================

What is deliberately not mapped
-------------------------------

``caption``, ``segment``, and ``coverage_window`` are reserved in the
``EntityRef.entity_type`` vocabulary and are **not** emitted in v1. Each already
has a canonical representation that the Reader and the indexer read directly —
captions and segments inside their artifacts, where ``T-103`` indexes their text,
and coverage windows inside ``coverage.json`` — and none of them has a consumer
that needs a global handle yet. Minting 500-odd caption entities per source, or
a segment entity whose only honest ``label`` would be ``null`` because the real
text does not fit the field, buys nothing and has to be undone later. Because the
enum already reserves the names, adding them when a consumer exists needs no
schema version bump.

Coverage window membership is likewise not an ``IndexedRelation``: expressing
"this window is covered by these units" would mean inventing a fourth relation
vocabulary, which is a schema change and not this task's to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .. import ids
from ..io import sha256_file
from .base import (
    SCHEMA_VERSION,
    AdapterError,
    IndexRecords,
    SourceAdapter,
    check_records,
    declared_source_type,
    media_type_for,
    project_relative,
    read_optional_json,
    read_status,
)

#: Directory name of the cross-source library inside ``output/``.
LIBRARY_DIR_NAME = "library"


@dataclass(frozen=True)
class _ArtifactSpec:
    """One well-known file of a run, and the local id that addresses it."""

    key: str
    kind: str
    role: str
    relative: str


#: The files ``pipeline.py`` and ``artifacts.py`` write, in the order a reader
#: meets them. ``key`` becomes the local part of the artifact's global id, so
#: ``youtube:<video-id>:transcript`` stays stable and readable across rebuilds.
#: ``raw/source.*`` is absent from this table because its extension follows the
#: imported file (``pipeline.py:203``) and is therefore discovered, not assumed.
CANONICAL_ARTIFACTS: tuple[_ArtifactSpec, ...] = (
    _ArtifactSpec("metadata", "metadata", "canonical", "metadata.json"),
    _ArtifactSpec("transcript", "transcript", "canonical", "transcript.json"),
    _ArtifactSpec("segments", "segments", "canonical", "segments.json"),
    _ArtifactSpec("knowledge_units", "knowledge_units", "canonical", "knowledge_units.json"),
    _ArtifactSpec("relationships", "relationships", "canonical", "relationships.json"),
    _ArtifactSpec("graph", "graph", "canonical", "graph.json"),
    _ArtifactSpec("coverage", "coverage", "canonical", "coverage.json"),
    _ArtifactSpec("validation", "validation", "canonical", "validation.json"),
    _ArtifactSpec("report", "report", "canonical", "report.md"),
    _ArtifactSpec("raw_transcript", "raw_transcript", "raw", "raw/transcript.json"),
    _ArtifactSpec("raw_transcript_md", "raw_transcript", "raw", "raw/transcript.md"),
    _ArtifactSpec("extraction_bundle", "extraction_bundle", "work", "work/extraction_bundle.json"),
)

#: Fields of ``metadata.json`` the generic ``Source`` record has no home for.
#: They are carried through untouched rather than dropped or forced into a
#: typed field where they do not belong.
ADAPTER_METADATA_FIELDS = (
    "transcript_source",
    "transcript_hash",
    "pipeline_version",
    "schema_version",
    "extraction",
    "fixture",
    "fixture_note",
)


class YouTubeAdapter(SourceAdapter):
    """Maps a ``output/<video-id>/`` run onto the v1 index model."""

    source_type = "youtube"
    version = "1.0"

    # ----------------------------------------------------------------
    # Detection
    # ----------------------------------------------------------------

    def detect(self, run_dir: Path) -> bool:
        metadata = read_optional_json(run_dir / "metadata.json")
        if not isinstance(metadata, Mapping):
            return False
        return declared_source_type(metadata) == self.source_type

    # ----------------------------------------------------------------
    # The run
    # ----------------------------------------------------------------

    def adapt_run(self, run_dir: Path, *, hash_artifacts: bool = False) -> IndexRecords:
        run_dir = run_dir.expanduser().resolve()
        metadata = read_optional_json(run_dir / "metadata.json")
        if not isinstance(metadata, Mapping):
            raise AdapterError(f"{run_dir} has no readable metadata.json; it is not a run")

        declared = declared_source_type(metadata)
        if declared != self.source_type:
            raise AdapterError(
                f"{run_dir} declares source_type {declared!r}, which the "
                f"{self.source_type} adapter does not map"
            )

        external_id = metadata.get("video_id")
        try:
            source_id = ids.make_source_id(self.source_type, external_id)
        except ids.IdError as exc:
            raise AdapterError(f"{run_dir / 'metadata.json'}: {exc}") from exc

        artifacts = self._artifacts(run_dir, source_id, metadata, hash_artifacts)
        knowledge = read_optional_json(run_dir / "knowledge_units.json")
        relationships = read_optional_json(run_dir / "relationships.json")
        units = _items(knowledge, "units")
        edges = _items(relationships, "relationships")

        entities = self._knowledge_entities(run_dir, source_id, units)
        relations = self._canonical_relations(run_dir, source_id, edges)
        relations += self._derived_from_relations(run_dir, source_id, units)

        source = self._source(
            run_dir,
            source_id,
            metadata,
            artifacts,
            # A file that could not be read has no count to report; ``0`` would
            # state that the run has none, which is a different claim.
            units=units if isinstance(knowledge, Mapping) else None,
            edges=edges if isinstance(relationships, Mapping) else None,
        )

        return check_records(
            IndexRecords(
                sources=[source],
                artifacts=artifacts,
                entities=entities,
                relations=relations,
            )
        )

    # ----------------------------------------------------------------
    # Source
    # ----------------------------------------------------------------

    def _source(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        metadata: Mapping[str, Any],
        artifacts: list[dict[str, Any]],
        *,
        units: list[Mapping[str, Any]] | None,
        edges: list[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.value,
            "source_type": source_id.source_type,
            "external_id": source_id.external_id,
            "url": metadata.get("video_url"),
            "title": metadata.get("title"),
            # A YouTube channel is the publisher; the generic model calls that
            # field 'author' so a Medium byline and an X handle land in it too.
            "author": metadata.get("channel"),
            "language": metadata.get("language"),
            "duration_sec": metadata.get("duration_sec"),
            "imported_at": metadata.get("imported_at"),
            "extracted_at": metadata.get("extracted_at"),
            "canonical_dir": self.relative(run_dir),
            "status": self._status(run_dir),
            "counts": self._counts(run_dir, units, edges),
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "adapter": self.ref,
            "adapter_metadata": {
                key: metadata[key] for key in ADAPTER_METADATA_FIELDS if key in metadata
            },
        }

    def _status(self, run_dir: Path) -> dict[str, Any]:
        """Copy the run status out of the two validator files.

        ``overall`` is ``validation.json``'s top-level status, which already
        aggregates all five sections including coverage (``pipeline.py:281``).
        Recomputing it here would be a second opinion, and the UI is forbidden
        one (ADR 0001 invariant 2).
        """
        validation_path = run_dir / "validation.json"
        coverage_path = run_dir / "coverage.json"
        validation = read_optional_json(validation_path)
        coverage = read_optional_json(coverage_path)

        status: dict[str, Any] = {
            "validation": read_status(validation),
            "coverage": read_status(coverage),
            "overall": read_status(validation),
            "validation_path": self.relative(validation_path) if validation is not None else None,
            "coverage_path": self.relative(coverage_path) if coverage is not None else None,
        }
        # Copied verbatim, including a value above the WORKFLOW.md cap of three.
        # Such a run has broken the repair rule; the schema rejecting the record
        # is the intended way to find that out, and quietly clamping it here
        # would hide it.
        if isinstance(coverage, Mapping):
            attempts = coverage.get("audit_attempts")
            status["audit_attempts"] = attempts if isinstance(attempts, int) else None
        else:
            status["audit_attempts"] = None
        return status

    def _counts(
        self,
        run_dir: Path,
        units: list[Mapping[str, Any]] | None,
        edges: list[Mapping[str, Any]] | None,
    ) -> dict[str, int]:
        """Counts for list rendering, omitted rather than zeroed when unknown.

        A count is a cache convenience. Reporting ``0`` for a file that could
        not be read would state that the run has no knowledge units, which is a
        different claim from not knowing.
        """
        counts: dict[str, int] = {}
        if units is not None:
            counts["knowledge_units"] = len(units)
            counts["source_units"] = sum(1 for u in units if u.get("source_class") == "source")
            counts["derived_units"] = sum(1 for u in units if u.get("source_class") == "derived")
        if edges is not None:
            counts["relationships"] = len(edges)
        transcript = read_optional_json(run_dir / "transcript.json")
        if transcript is not None:
            counts["captions"] = len(_items(transcript, "captions"))
        segments = read_optional_json(run_dir / "segments.json")
        if segments is not None:
            counts["segments"] = len(_items(segments, "segments"))
        return counts

    # ----------------------------------------------------------------
    # Artifacts
    # ----------------------------------------------------------------

    def _artifacts(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        metadata: Mapping[str, Any],
        hash_artifacts: bool,
    ) -> list[dict[str, Any]]:
        artifacts = [
            self._file_artifact(run_dir, source_id, spec, hash_artifacts)
            for spec in CANONICAL_ARTIFACTS
        ]

        raw_source = self._raw_source_spec(run_dir)
        if raw_source is not None:
            artifacts.append(
                self._file_artifact(run_dir, source_id, raw_source, hash_artifacts)
            )

        artifacts.extend(self._vault_artifacts(run_dir, source_id, hash_artifacts))

        video = self._video_artifact(source_id, metadata)
        if video is not None:
            artifacts.append(video)
        return artifacts

    def _file_artifact(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        spec: _ArtifactSpec,
        hash_artifacts: bool,
    ) -> dict[str, Any]:
        path = run_dir / spec.relative
        available = path.is_file()
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.entity(spec.key).value,
            "source_id": source_id.value,
            "kind": spec.kind,
            "role": spec.role,
            "media_type": media_type_for(path),
            "path": self.relative(path),
            "url": None,
            "bytes": path.stat().st_size if available else None,
            "sha256": sha256_file(path) if available and hash_artifacts else None,
            # Everything under raw/ is evidence and is never written again.
            "immutable": spec.role == "raw",
            "available": available,
        }

    def _raw_source_spec(self, run_dir: Path) -> _ArtifactSpec | None:
        """Locate ``raw/source.<ext>``, whose extension follows the import.

        When the file is absent the artifact is omitted rather than reported as
        an unavailable path: without the file there is no extension, and an
        artifact whose path had to be guessed is worse than one that is not
        listed.
        """
        matches = sorted((run_dir / "raw").glob("source.*"))
        if not matches:
            return None
        if len(matches) > 1:
            raise AdapterError(
                f"{run_dir / 'raw'} holds {len(matches)} source files "
                f"({', '.join(path.name for path in matches)}); a run has exactly one"
            )
        return _ArtifactSpec("raw_source", "raw_source", "raw", f"raw/{matches[0].name}")

    def _vault_artifacts(
        self, run_dir: Path, source_id: ids.SourceId, hash_artifacts: bool
    ) -> list[dict[str, Any]]:
        """The Obsidian export under ``vault/``.

        Generated views, so ``role`` is ``export``. The local id is the
        run-relative path with separators folded to dots — unique by
        construction, and readable enough to recognise in a URL.
        """
        vault = run_dir / "vault"
        artifacts = []
        for path in sorted(p for p in vault.rglob("*.md") if p.is_file()):
            relative = path.relative_to(run_dir)
            key = ".".join(relative.with_suffix("").parts)
            spec = _ArtifactSpec(key, "vault_note", "export", relative.as_posix())
            artifacts.append(self._file_artifact(run_dir, source_id, spec, hash_artifacts))
        return artifacts

    def _video_artifact(
        self, source_id: ids.SourceId, metadata: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """The video itself: a URL and no local file.

        ``T-114`` depends on this being explicit. ``available`` states that the
        source recorded a URL, not that the remote video was fetched — the
        adapter performs no network access, and the UI must never assume a
        local media file exists.
        """
        url = metadata.get("video_url")
        if not isinstance(url, str) or not url:
            return None
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.entity("video").value,
            "source_id": source_id.value,
            "kind": "video",
            "role": "external",
            "media_type": None,
            "path": None,
            "url": url,
            "bytes": None,
            "sha256": None,
            "immutable": False,
            "available": True,
        }

    # ----------------------------------------------------------------
    # Knowledge units
    # ----------------------------------------------------------------

    def _knowledge_entities(
        self, run_dir: Path, source_id: ids.SourceId, units: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        canonical_path = self.relative(run_dir / "knowledge_units.json")
        segments_artifact = source_id.entity("segments").value
        entities = []
        for unit in units:
            local_id = _required(unit, "id", "knowledge unit")
            global_id = _build(source_id.entity, local_id, f"knowledge unit {local_id!r}")
            provenance = _required(unit, "source_class", f"knowledge unit {local_id!r}")
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
                "kind": unit.get("kind"),
                # library.py:52 already makes this choice; making a different
                # one here would put two labels on one entity.
                "label": unit.get("normalized_statement") or unit.get("content"),
                "confidence": unit.get("confidence"),
                "canonical_path": canonical_path,
            }
            if provenance == "source":
                entity["locator"] = self._locator(unit, source_id, segments_artifact)
            elif provenance == "derived":
                entity["derived_from"] = [
                    _build(source_id.entity, ref, f"derived_from of {local_id!r}").value
                    for ref in unit.get("derived_from", [])
                ]
                entity["derivation_note"] = unit.get("derivation_note")
            entities.append(entity)
        return entities

    def _locator(
        self,
        unit: Mapping[str, Any],
        source_id: ids.SourceId,
        segments_artifact: str,
    ) -> dict[str, Any]:
        """A ``time_range`` into the **segments** artifact.

        ``validators.py:166`` resolves a unit's ``segment_id`` against
        ``segments.json`` and requires the excerpt to appear in that segment's
        text, so the segments file — not the transcript — is the artifact the
        evidence sits in.
        """
        local_id = unit.get("id")
        provenance = unit.get("source")
        if not isinstance(provenance, Mapping):
            raise AdapterError(
                f"source-class knowledge unit {local_id!r} has no source block, so it has "
                "no locator; a locator is never constructed without canonical data"
            )
        locator: dict[str, Any] = {"type": "time_range"}
        # A unit whose provenance names a different video is a canonical error
        # (validators.py:163) and shows up in validation.json. The run is still
        # indexed and still shown honestly — but the evidence is not in this
        # source's segments file, so the locator is left unaddressed rather
        # than pointed at the wrong artifact.
        if provenance.get("video_id") == source_id.external_id:
            locator["artifact_id"] = segments_artifact
        for field_name in ("start_sec", "end_sec"):
            if field_name not in provenance:
                raise AdapterError(
                    f"source-class knowledge unit {local_id!r} has no {field_name}"
                )
            locator[field_name] = provenance[field_name]
        segment_id = provenance.get("segment_id")
        if segment_id:
            locator["segment_id"] = segment_id
        excerpt = provenance.get("evidence_excerpt")
        if excerpt:
            locator["excerpt"] = excerpt
        return locator

    # ----------------------------------------------------------------
    # Relations
    # ----------------------------------------------------------------

    def _canonical_relations(
        self, run_dir: Path, source_id: ids.SourceId, edges: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        canonical_path = self.relative(run_dir / "relationships.json")
        relations = []
        for index, edge in enumerate(edges):
            owner = f"relationship {index}"
            from_id = _build(source_id.entity, _required(edge, "from", owner), owner)
            to_id = _build(source_id.entity, _required(edge, "to", owner), owner)
            name = _required(edge, "relation", owner)
            relation: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "id": _edge_id(from_id.value, name, to_id.value),
                "from_id": from_id.value,
                "to_id": to_id.value,
                "relation": name,
                "relation_vocabulary": "canonical",
                "provenance_class": edge.get("source_class"),
                "confidence": edge.get("confidence"),
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
            from_id = _build(source_id.entity, local_id, f"knowledge unit {local_id!r}")
            for ref in unit.get("derived_from", []):
                to_id = _build(source_id.entity, ref, f"derived_from of {local_id!r}")
                relations.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "id": _edge_id(from_id.value, "derived_from", to_id.value),
                        "from_id": from_id.value,
                        "to_id": to_id.value,
                        "relation": "derived_from",
                        "relation_vocabulary": "library_synthetic",
                        "provenance_class": "derived",
                        "confidence": None,
                        "source_id": source_id.value,
                        "canonical_path": canonical_path,
                    }
                )
        return relations


# --------------------------------------------------------------------------
# The cross-source library
# --------------------------------------------------------------------------


def adapt_library(library_dir: Path, project_root: Path) -> IndexRecords:
    """Map ``output/library/`` — canonical concepts and their edges.

    Concepts are cross-source, so they belong to no ``Source`` and carry no
    ``source_id``. They live in the reserved ``library:concepts`` namespace
    (D-016). No ``Source`` record is emitted for the library: it is not an
    ingested source, and inventing one would give every concept an owner it
    does not have.

    ``derived_from`` edges also appear in ``library/graph.json``, and are
    deliberately **not** taken from here — :meth:`YouTubeAdapter._derived_from_relations`
    already emits them from the run that owns them, and a run must be indexable
    before ``rebuild_library`` has ever been called.

    ``status.json`` and ``videos.json`` are not read at all: they hold absolute
    host paths (risk R15) and nothing here needs them.
    """
    library_dir = library_dir.expanduser().resolve()
    graph = read_optional_json(library_dir / "graph.json")
    concepts_document = read_optional_json(library_dir / "concepts.json")
    if graph is None or concepts_document is None:
        # A project that has never been finalized has no library. That is an
        # absence, not an error.
        return IndexRecords()

    concepts_path = project_relative(library_dir / "concepts.json", project_root)
    graph_path = project_relative(library_dir / "graph.json", project_root)

    # library.py emits both id forms on every node (T-003), which is what lets
    # a library id be resolved without assuming the source type it came from.
    global_by_library_id: dict[str, str] = {}
    for node in _items(graph, "nodes"):
        library_id = node.get("id")
        global_id = node.get("global_id")
        if isinstance(library_id, str) and isinstance(global_id, str):
            global_by_library_id[library_id] = global_id

    entities = []
    for concept in _items(concepts_document, "concepts"):
        library_id = _required(concept, "id", "concept")
        global_id = _build(
            ids.global_id_from_library_id, library_id, f"concept {library_id!r}"
        )
        stated = concept.get("global_id")
        if stated is not None and stated != global_id.value:
            raise AdapterError(
                f"concept {library_id!r} states global_id {stated!r}, but its library id "
                f"spells {global_id.value!r} (risk R12)"
            )
        entities.append(
            {
                "schema_version": SCHEMA_VERSION,
                "global_id": global_id.value,
                "source_type": global_id.source_type,
                "external_id": global_id.external_id,
                "local_id": global_id.local_id,
                "library_id": library_id,
                "source_id": None,
                "entity_type": "concept",
                "provenance_class": "derived",
                "kind": "canonical_concept",
                "label": concept.get("canonical_label"),
                "confidence": None,
                "canonical_path": concepts_path,
            }
        )

    relations = []
    for index, edge in enumerate(_items(graph, "edges")):
        if edge.get("relation") != "expresses_concept":
            continue
        from_id = _resolve(global_by_library_id, edge.get("from"), f"library edge {index}")
        to_id = _resolve(global_by_library_id, edge.get("to"), f"library edge {index}")
        relations.append(
            {
                "schema_version": SCHEMA_VERSION,
                "id": _edge_id(from_id, "expresses_concept", to_id),
                "from_id": from_id,
                "to_id": to_id,
                "relation": "expresses_concept",
                "relation_vocabulary": "library_synthetic",
                "provenance_class": edge.get("source_class", "derived"),
                "confidence": edge.get("confidence"),
                # Cross-source: the edge belongs to the library, not to a run.
                "source_id": None,
                "canonical_path": graph_path,
            }
        )

    return check_records(IndexRecords(entities=entities, relations=relations))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _items(document: Any, key: str) -> list[Mapping[str, Any]]:
    """The list under *key*, or an empty list — never a partial read."""
    if not isinstance(document, Mapping):
        return []
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _required(record: Mapping[str, Any], key: str, owner: str) -> Any:
    if key not in record:
        raise AdapterError(f"{owner} is missing the required field {key!r}")
    return record[key]


def _build(factory, value: Any, owner: str):
    """Build an id through ``ids``, naming what failed. Never an f-string."""
    try:
        return factory(value)
    except ids.IdError as exc:
        raise AdapterError(f"{owner}: {exc}") from exc


def _resolve(table: Mapping[str, str], library_id: Any, owner: str) -> str:
    global_id = table.get(library_id) if isinstance(library_id, str) else None
    if global_id is None:
        raise AdapterError(
            f"{owner} names {library_id!r}, which output/library/graph.json does not "
            "carry a global id for; rebuild the library so both id forms are present"
        )
    return global_id


def _edge_id(from_id: str, relation: str, to_id: str) -> str:
    """A deterministic edge id, so a rebuild yields the identical set (T-104)."""
    edge_id = f"{from_id}|{relation}|{to_id}"
    if len(edge_id) > 1300:
        raise AdapterError(
            f"edge id {edge_id[:80]}… is {len(edge_id)} characters, over the 1300 the "
            "IndexedRelation contract allows"
        )
    return edge_id
