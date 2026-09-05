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

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import ids
from ..io import LIBRARY_DIR_NAME as LIBRARY_DIR_NAME
from ..io import scrub_host_paths
from .base import (
    MAX_AUTHOR_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_LANGUAGE_LENGTH,
    MAX_SEGMENT_ID_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_URL_LENGTH,
    SCHEMA_VERSION,
    AdapterError,
    ArtifactSpec,
    IndexRecords,
    SourceAdapter,
    build_id,
    check_records,
    copied_choice,
    copied_confidence,
    copied_number,
    copied_text,
    copied_timestamp,
    declared_source_type,
    edge_id,
    list_items,
    project_relative,
    read_optional_json,
    read_optional_json_or_reason,
    required_field,
)

#: Directory name of the cross-source library inside ``output/``.
#: Re-exported from :mod:`x2knwldg.io` (D-158), where run discovery is stated
#: now that one rule serves the scanner, the adapters and the library rebuild.
#: Every existing ``from .adapters import LIBRARY_DIR_NAME`` keeps working.


#: The files ``pipeline.py`` and ``artifacts.py`` write, in the order a reader
#: meets them. ``key`` becomes the local part of the artifact's global id, so
#: ``youtube:<video-id>:transcript`` stays stable and readable across rebuilds.
#: ``raw/source.*`` is absent from this table because its extension follows the
#: imported file (``pipeline.py:203``) and is therefore discovered, not assumed.
CANONICAL_ARTIFACTS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec("metadata", "metadata", "canonical", "metadata.json"),
    ArtifactSpec("transcript", "transcript", "canonical", "transcript.json"),
    ArtifactSpec("segments", "segments", "canonical", "segments.json"),
    ArtifactSpec("knowledge_units", "knowledge_units", "canonical", "knowledge_units.json"),
    ArtifactSpec("relationships", "relationships", "canonical", "relationships.json"),
    ArtifactSpec("graph", "graph", "canonical", "graph.json"),
    ArtifactSpec("coverage", "coverage", "canonical", "coverage.json"),
    ArtifactSpec("validation", "validation", "canonical", "validation.json"),
    ArtifactSpec("report", "report", "canonical", "report.md"),
    ArtifactSpec("raw_transcript", "raw_transcript", "raw", "raw/transcript.json"),
    ArtifactSpec("raw_transcript_md", "raw_transcript", "raw", "raw/transcript.md"),
    ArtifactSpec("extraction_bundle", "extraction_bundle", "work", "work/extraction_bundle.json"),
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

        # What the run holds but the index cannot carry is collected rather than
        # dropped, and reported on the Source record below: an artifact whose
        # name cannot spell an id, and a canonical file that is there and cannot
        # be read. Neither is allowed to leave the index quietly short.
        unmappable: list[dict[str, str]] = []
        damaged: list[dict[str, str]] = []
        artifacts = self._artifacts(run_dir, source_id, metadata, hash_artifacts, unmappable)
        knowledge = self.read_canonical(run_dir / "knowledge_units.json", damaged)
        relationships = self.read_canonical(run_dir / "relationships.json", damaged)
        units = list_items(knowledge, "units", self.relative(run_dir / "knowledge_units.json"))
        edges = list_items(
            relationships, "relationships", self.relative(run_dir / "relationships.json")
        )

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
            unmappable=unmappable,
            damaged=damaged,
        )

        return check_records(
            IndexRecords(
                sources=[source],
                artifacts=artifacts,
                entities=entities,
                relations=relations,
                source_entities=[self._source_entity(run_dir, source_id, metadata)],
            )
        )

    def read_canonical(self, path: Path, damaged: list[dict[str, str]]) -> Any | None:
        """A canonical file, or ``None`` — recording *why* when there is a why.

        An absent file is an absence and says nothing. A file that is present
        and unreadable is damage, and the damage is reported on the Source
        record: the counts derived from it are already omitted rather than
        zeroed, but 'this count is missing' does not say that the file is
        broken, and only one of those two is actionable.
        """
        document, reason = read_optional_json_or_reason(path)
        if reason is not None:
            # D-100's wrap, which `_file_artifact` got and this did not.
            # `self.relative` **resolves**, so a canonical file that is a
            # symlink to somewhere outside the project raised `AdapterError`
            # here and took the whole run down — downgrading it from "indexed,
            # with this file named as damaged" to "absent". A run whose
            # `validation.json` is both symlinked outside the root *and*
            # unparseable is damaged in a way this record can state, and
            # stating it is the whole point of this channel.
            #
            # The lexical path is used when the resolved one cannot be
            # expressed, for the reason `_file_artifact` gives: the bytes
            # really do live outside the project, and the entry is a
            # *report*, not an addressable artifact.
            try:
                relative = self.relative(path)
            except AdapterError:
                damaged.append(
                    {
                        "path": path.name,
                        "reason": scrub_host_paths(
                            f"{reason}; it also resolves outside the project root, "
                            "so it has no project-relative path (risk R15)"
                        ),
                    }
                )
                return document
            # D-051's rule, on D-045's other channel. Every ``JsonReadError``
            # names the file it could not read and names it *absolutely*, and
            # this record is served verbatim inside a 200 body by
            # ``/api/sources`` — at which point the reason leaks the user's
            # filesystem layout to any HTTP client, which D-030 and ADR 0003
            # both forbid. Sanitised here, at the point the reason is
            # recorded, rather than on the way out: one rule, the CLI gains
            # the same property, and it becomes the same relative string the
            # entry's ``path`` is keyed by, so the two cannot disagree about
            # which file failed. The substring is exact rather than hopeful --
            # ``io.read_json`` formats this very ``path`` into the message.
            relative = self.relative(path)
            damaged.append({"path": relative, "reason": reason.replace(str(path), relative)})
        return document

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
        unmappable: list[dict[str, str]],
        damaged: list[dict[str, str]],
    ) -> dict[str, Any]:
        owner = self.relative(run_dir / "metadata.json")
        # Before the report is assembled: both of these read canonical files,
        # and a file found damaged in there belongs in the report below.
        status = self._status(run_dir, damaged)
        counts = self._counts(run_dir, units, edges, damaged)
        adapter_metadata: dict[str, Any] = {
            key: metadata[key] for key in ADAPTER_METADATA_FIELDS if key in metadata
        }
        # Free-form by design, and the only place in the frozen Source record
        # where an adapter may say what it could not map. Reporting it here
        # keeps the omission in the index and in the API instead of leaving the
        # file to disappear between the run and the Reader. Absent when there is
        # nothing to report: an empty list reads like an unread finding.
        if unmappable:
            adapter_metadata["unmappable_artifacts"] = unmappable
        if damaged:
            adapter_metadata["unreadable_files"] = damaged
        # `T-252`: whether the run's brief still describes the run as it is now.
        # Absent when there is none, so no existing record moves (D-257).
        brief = self._source_knowledge_metadata(run_dir)
        if brief is not None:
            adapter_metadata["source_knowledge"] = brief
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.value,
            "source_type": source_id.source_type,
            "external_id": source_id.external_id,
            "url": copied_text(
                metadata.get("video_url"),
                owner=owner,
                field="video_url",
                max_length=MAX_URL_LENGTH,
                allow_empty=False,
            ),
            "title": copied_text(
                metadata.get("title"), owner=owner, field="title", max_length=MAX_TITLE_LENGTH
            ),
            # A YouTube channel is the publisher; the generic model calls that
            # field 'author' so a Medium byline and an X handle land in it too.
            "author": copied_text(
                metadata.get("channel"),
                owner=owner,
                field="channel",
                max_length=MAX_AUTHOR_LENGTH,
            ),
            "language": copied_text(
                metadata.get("language"),
                owner=owner,
                field="language",
                max_length=MAX_LANGUAGE_LENGTH,
            ),
            "duration_sec": copied_number(
                metadata.get("duration_sec"), owner=owner, field="duration_sec", minimum=0
            ),
            "imported_at": copied_timestamp(
                metadata.get("imported_at"), owner=owner, field="imported_at"
            ),
            "extracted_at": copied_timestamp(
                metadata.get("extracted_at"), owner=owner, field="extracted_at"
            ),
            "canonical_dir": self.relative(run_dir),
            "status": status,
            "counts": counts,
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "adapter": self.ref,
            "adapter_metadata": adapter_metadata,
        }

    def _counts(
        self,
        run_dir: Path,
        units: list[Mapping[str, Any]] | None,
        edges: list[Mapping[str, Any]] | None,
        damaged: list[dict[str, str]],
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
        transcript = self.read_canonical(run_dir / "transcript.json", damaged)
        if transcript is not None:
            counts["captions"] = len(
                list_items(transcript, "captions", self.relative(run_dir / "transcript.json"))
            )
        segments = self.read_canonical(run_dir / "segments.json", damaged)
        if segments is not None:
            counts["segments"] = len(
                list_items(segments, "segments", self.relative(run_dir / "segments.json"))
            )
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
        unmappable: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        artifacts = [
            mapped
            for spec in CANONICAL_ARTIFACTS
            if (mapped := self._file_artifact(
                run_dir, source_id, spec, hash_artifacts, unmappable
            )) is not None
        ]

        raw_source = self._raw_source_spec(run_dir)
        if raw_source is not None:
            mapped = self._file_artifact(
                run_dir, source_id, raw_source, hash_artifacts, unmappable
            )
            if mapped is not None:
                artifacts.append(mapped)

        artifacts.extend(
            self._vault_artifacts(run_dir, source_id, hash_artifacts, unmappable)
        )

        video = self._video_artifact(run_dir, source_id, metadata)
        if video is not None:
            artifacts.append(video)

        # `T-252`: emitted only when the run has a brief (D-257).
        brief = self._source_knowledge_artifact(
            run_dir, source_id, hash_artifacts, unmappable
        )
        if brief is not None:
            artifacts.append(brief)
        return artifacts

    def _raw_source_spec(self, run_dir: Path) -> ArtifactSpec | None:
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
        return ArtifactSpec("raw_source", "raw_source", "raw", f"raw/{matches[0].name}")

    def _vault_artifacts(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        hash_artifacts: bool,
        unmappable: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """The Obsidian export under ``vault/``.

        Generated views, so ``role`` is ``export``. The local id is the
        run-relative path with separators folded to dots — unique by
        construction, and readable enough to recognise in a URL.

        A note whose filename cannot spell an id — a space in it, say — is
        reported on the Source record and left out of the index, rather than
        taken as a reason to refuse the run. The vault is a generated export
        beside the canonical files; one unaddressable note must not make a whole
        project unindexable, and the canonical evidence is unaffected either
        way. The omission is stated, never silent: nothing here drops a file the
        run holds without saying so.
        """
        vault = run_dir / "vault"
        artifacts = []
        for path in sorted(p for p in vault.rglob("*.md") if p.is_file()):
            relative = path.relative_to(run_dir)
            key = ".".join(relative.with_suffix("").parts)
            if not ids.is_id_part(key):
                unmappable.append(
                    {
                        "path": relative.as_posix(),
                        "reason": (
                            f"the local id {key!r} this filename spells is not addressable "
                            f"(it must match {ids.ID_PART_PATTERN!r} and stay under "
                            f"{ids.ID_PART_MAX_LENGTH} characters); the note is not indexed"
                        ),
                    }
                )
                continue
            spec = ArtifactSpec(key, "vault_note", "export", relative.as_posix())
            mapped = self._file_artifact(
                run_dir, source_id, spec, hash_artifacts, unmappable
            )
            if mapped is not None:
                artifacts.append(mapped)
        return artifacts

    def _video_artifact(
        self, run_dir: Path, source_id: ids.SourceId, metadata: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """The video itself: a URL and no local file.

        ``T-114`` depends on this being explicit. ``available`` states that the
        source recorded a URL, not that the remote video was fetched — the
        adapter performs no network access, and the UI must never assume a
        local media file exists.
        """
        url = copied_text(
            metadata.get("video_url"),
            owner=self.relative(run_dir / "metadata.json"),
            field="video_url",
            max_length=MAX_URL_LENGTH,
            allow_empty=False,
        )
        if url is None:
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

    def _locator(
        self,
        unit: Mapping[str, Any],
        source_id: ids.SourceId,
        owner: str,
    ) -> dict[str, Any]:
        """A ``time_range`` into the **segments** artifact.

        ``validators.py:166`` resolves a unit's ``segment_id`` against
        ``segments.json`` and requires the excerpt to appear in that segment's
        text, so the segments file — not the transcript — is the artifact the
        evidence sits in.

        The artifact it addresses is computed here rather than passed in: the
        base class calls this without one because *which* artifact holds the
        evidence is precisely the medium-specific part (``T-228``).
        """
        segments_artifact = source_id.entity("segments").value
        provenance = unit.get("source")
        if not isinstance(provenance, Mapping):
            raise AdapterError(
                f"source-class {owner} has no source block, so it has "
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
                raise AdapterError(f"source-class {owner} has no {field_name}")
            locator[field_name] = copied_number(
                provenance[field_name],
                owner=owner,
                field=field_name,
                minimum=0,
                required=True,
            )
        segment_id = provenance.get("segment_id")
        if segment_id is not None:
            locator["segment_id"] = copied_text(
                segment_id,
                owner=owner,
                field="segment_id",
                max_length=MAX_SEGMENT_ID_LENGTH,
                allow_empty=False,
            )
        excerpt = provenance.get("evidence_excerpt")
        if excerpt is not None:
            # Verbatim, and never empty: the model has no length limit on an
            # excerpt, so nothing here truncates evidence, and an empty one is
            # refused rather than quietly read as an absent one.
            locator["excerpt"] = copied_text(
                excerpt,
                owner=owner,
                field="evidence_excerpt",
                max_length=None,
                allow_empty=False,
            )
        return locator

    # ----------------------------------------------------------------
    # Relations
    # ----------------------------------------------------------------



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
    for node in list_items(graph, "nodes", graph_path):
        library_id = node.get("id")
        global_id = node.get("global_id")
        if isinstance(library_id, str) and isinstance(global_id, str):
            global_by_library_id[library_id] = global_id

    entities = []
    for concept in list_items(concepts_document, "concepts", concepts_path):
        library_id = required_field(concept, "id", f"a concept in {concepts_path}")
        owner = f"concept {library_id!r} in {concepts_path}"
        global_id = build_id(ids.global_id_from_library_id, library_id, owner)
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
                "label": copied_text(
                    concept.get("canonical_label"),
                    owner=owner,
                    field="canonical_label",
                    max_length=MAX_LABEL_LENGTH,
                ),
                "confidence": None,
                "canonical_path": concepts_path,
            }
        )

    relations = []
    for index, edge in enumerate(list_items(graph, "edges", graph_path)):
        if edge.get("relation") != "expresses_concept":
            continue
        owner = f"library edge {index} in {graph_path}"
        from_id = _resolve(global_by_library_id, edge.get("from"), owner)
        to_id = _resolve(global_by_library_id, edge.get("to"), owner)
        relations.append(
            {
                "schema_version": SCHEMA_VERSION,
                "id": edge_id(from_id, "expresses_concept", to_id),
                "from_id": from_id,
                "to_id": to_id,
                "relation": "expresses_concept",
                "relation_vocabulary": "library_synthetic",
                # A synthetic edge is recorded synthesis by definition, so a
                # library that called one 'source' evidence is refused rather
                # than believed (D-025).
                "provenance_class": copied_choice(
                    edge.get("source_class", "derived"),
                    owner=owner,
                    field="source_class",
                    allowed=frozenset({"derived"}),
                    required=True,
                ),
                "confidence": copied_confidence(edge.get("confidence"), owner=owner),
                # Cross-source: the edge belongs to the library, not to a run.
                "source_id": None,
                "canonical_path": graph_path,
            }
        )

    # A fragment, not the whole index: every ``expresses_concept`` edge runs
    # from a knowledge unit the *run* owns to a concept the library owns, so its
    # ``from_id`` is outside this set by construction (D-025). Endpoint
    # membership is judged over the union, in ``adapt_project``.
    return check_records(
        IndexRecords(entities=entities, relations=relations), self_contained=False
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _resolve(table: Mapping[str, str], library_id: Any, owner: str) -> str:
    global_id = table.get(library_id) if isinstance(library_id, str) else None
    if global_id is None:
        raise AdapterError(
            f"{owner} names {library_id!r}, which output/library/graph.json does not "
            "carry a global id for; rebuild the library so both id forms are present"
        )
    return global_id


