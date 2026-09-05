"""The Twitter adapter — ``output/<post-id>/`` seen through the v1 index model.

``T-227`` registered the source type with a source-only projection so that one
acquired post could not refuse the whole project's (D-227). ``T-228`` completes
it: artifacts, entities, locators and relations, so a Twitter run reaches the
index, the API, search, the Reader and the Map on the same eleven frozen
operations a YouTube run does.

What is mapped
--------------

============================  ==================================================
``metadata.json``             the ``Source`` record, and its ``adapter_metadata``
the files in the run          ``Artifact`` records — the canonical files, and
                              every preserved read under ``raw/``
each item of the capture      an ``Artifact`` of kind ``post``: no local file,
                              the post's own URL, and ``available`` stating
                              what the capture stated
``validation.json``,          the ``Source.status`` block, copied verbatim
``coverage.json``
``knowledge_units.json``      ``EntityRef`` records, and their ``text_span``
                              locators into the post each claim was taken from
``relationships.json``        ``IndexedRelation`` records, ``canonical``
                              vocabulary
a unit's ``derived_from``     ``IndexedRelation`` records, ``library_synthetic``
============================  ==================================================

Almost none of that list is implemented here. Everything but the first three
rows is :class:`~x2knwldg.adapters.base.SourceAdapter`'s, because what a
knowledge unit is and what a canonical edge is do not change with the medium
(``T-228``, extending D-228's argument from ``_status`` to the projection it
belongs to). This module supplies the three things that *are* medium-specific:
which files a run has, what an item is, and where a claim's evidence sits.

The locator is the whole of the third (D-233). A claim carries a ``post_id``
and a codepoint span into that post's ``text.canonical``, and it is projected
as a ``text_span`` into an artifact minted for that post — not as a widened
``post_id`` branch. One locator type then serves this medium and the article,
book and web-page adapters that follow it, and the artifact id carries the
identity that a ``video_id`` comparison carries for YouTube.

What is deliberately not mapped
-------------------------------

**No provider name reaches a record.** The capture states which tool read which
tier, and ``T-228``'s brief is that provider names are not part of the UI
contract: a Reader that renders "acquired via x-cli" makes the fallback
providers of ``T-225``/``T-226`` a visible change of behaviour rather than an
implementation detail. The provenance stays in ``capture.json``, which is an
artifact anyone can open.

**No ``graph.json``, ``report.md`` or vault note.** They are not omitted here —
they do not exist. ``artifacts.finalize_run`` is YouTube-shaped and ``T-230``
generalizes it (D-234), so this adapter maps the run as it actually is: an
artifact whose file is absent is reported ``available: false`` rather than left
out, and the two that a Twitter run will never have are simply not in its table.

**No quoted post is fetched, and no ``Entity`` is minted for one.** ADR 0007
decision 8 makes a quote a separate cited source; the capture carries the
quoted id and author and nothing else, and ``metadata.external_references``
already records it. An entity here would be a node the run has no content for.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import ids
from ..ids import is_id_part, make_source_id
from ..twitter.extract import CAPTURE_FILENAME, is_available, post_url
from .base import (
    MAX_TITLE_LENGTH,
    MAX_URL_LENGTH,
    SCHEMA_VERSION,
    AdapterError,
    ArtifactSpec,
    IndexRecords,
    SourceAdapter,
    build_id,
    check_records,
    copied_number,
    copied_text,
    copied_timestamp,
    declared_source_type,
    list_items,
    read_optional_json,
    refuse,
    required_field,
)

#: The files a Twitter run holds, in the order a reader meets them. ``key``
#: becomes the local part of the artifact's global id, so
#: ``twitter:<anchor>:capture`` stays stable and readable across rebuilds.
#:
#: Four of YouTube's twelve are absent and each absence is a fact about the
#: medium rather than an omission: there is no ``transcript.json`` or
#: ``segments.json`` because a post *is* the segment (``T-227``), and no
#: ``graph.json`` or ``report.md`` because nothing writes them yet — ``T-230``
#: generalizes ``finalize_run`` (D-234). Listing either of the last two would
#: put a permanently ``available: false`` artifact in every Twitter run's
#: record set, which reads as damage rather than as a stage not yet reached.
CANONICAL_ARTIFACTS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec("metadata", "metadata", "canonical", "metadata.json"),
    ArtifactSpec("capture", "capture", "canonical", CAPTURE_FILENAME),
    ArtifactSpec("knowledge_units", "knowledge_units", "canonical", "knowledge_units.json"),
    ArtifactSpec("relationships", "relationships", "canonical", "relationships.json"),
    ArtifactSpec("coverage", "coverage", "canonical", "coverage.json"),
    ArtifactSpec("validation", "validation", "canonical", "validation.json"),
    ArtifactSpec("extraction_bundle", "extraction_bundle", "work", "work/extraction_bundle.json"),
)

#: Local-id prefix for the artifact minted per capture item (D-233). Separate
#: from the raw-evidence prefix below so that no filename can ever spell a post
#: id: both are ``idPart``s in one namespace, and a collision there is one
#: artifact silently replacing another.
POST_ID_PREFIX = "post-"

#: Local-id prefix for a preserved provider read under ``raw/``.
RAW_ID_PREFIX = "raw-"


def _counts(run_dir: Path, metadata: Mapping[str, Any]) -> dict[str, int]:
    """Cached counts, every one reproducible from the canonical files.

    The schema is explicit that a stale count "is a bug, never a data
    achievement", so these are read from the files rather than carried from
    anywhere: a run whose extraction has not happened counts zero units, and
    says so.
    """
    knowledge = read_optional_json(run_dir / "knowledge_units.json")
    relationships = read_optional_json(run_dir / "relationships.json")
    units = knowledge.get("units") if isinstance(knowledge, dict) else None
    units = [unit for unit in units if isinstance(unit, dict)] if isinstance(units, list) else []
    edges = relationships.get("relationships") if isinstance(relationships, dict) else None
    edges = [edge for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []
    item_count = metadata.get("item_count")
    counts = {
        "knowledge_units": len(units),
        "source_units": sum(1 for unit in units if unit.get("source_class") == "source"),
        "derived_units": sum(1 for unit in units if unit.get("source_class") == "derived"),
        "relationships": len(edges),
    }
    if isinstance(item_count, int) and not isinstance(item_count, bool) and item_count >= 0:
        counts["segments"] = item_count
    return counts


class TwitterAdapter(SourceAdapter):
    """Maps a Twitter run onto one ``Source`` record and nothing else."""

    source_type = "twitter"
    #: ``1.0``: ``T-228`` completed the projection D-227 deliberately left
    #: partial at ``0.1``, and the bump is what forces the re-index that
    #: decision asked for. A cache built against the source-only shape must not
    #: go on serving a run that now has artifacts, entities and relations.
    version = "1.0"

    def detect(self, run_dir: Path) -> bool:
        metadata = read_optional_json(run_dir / "metadata.json")
        if not isinstance(metadata, dict):
            return False
        return metadata.get("source_type") == self.source_type

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
            source_id = make_source_id(self.source_type, external_id)
        except ids.IdError as exc:
            raise AdapterError(f"{run_dir / 'metadata.json'}: {exc}") from exc

        unmappable: list[dict[str, str]] = []
        damaged: list[dict[str, str]] = []
        capture = self.read_canonical(run_dir / CAPTURE_FILENAME, damaged)
        items = list_items(capture, "items", self.relative(run_dir / CAPTURE_FILENAME))
        artifacts = self._artifacts(
            run_dir, source_id, items, hash_artifacts, unmappable
        )

        knowledge = self.read_canonical(run_dir / "knowledge_units.json", damaged)
        relationships = self.read_canonical(run_dir / "relationships.json", damaged)
        units = list_items(knowledge, "units", self.relative(run_dir / "knowledge_units.json"))
        edges = list_items(
            relationships, "relationships", self.relative(run_dir / "relationships.json")
        )

        # Every one of these three is the base class's. The locator is the hook
        # this module overrides, and it is the only place the medium shows.
        entities = self._knowledge_entities(run_dir, source_id, units)
        relations = self._canonical_relations(run_dir, source_id, edges)
        relations += self._derived_from_relations(run_dir, source_id, units)

        source = self._source(
            run_dir, metadata, source_id, source_id.value, artifacts, unmappable, damaged
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

    # ----------------------------------------------------------------
    # Where a claim's evidence sits
    # ----------------------------------------------------------------

    def _locator(
        self,
        unit: Mapping[str, Any],
        source_id: ids.SourceId,
        owner: str,
    ) -> dict[str, Any]:
        """A ``text_span`` into the artifact minted for the post it quotes.

        The unit's ``source`` block already carries exactly the four fields
        this branch needs — ``post_id``, ``start_char``, ``end_char`` and
        ``evidence_excerpt`` — because ``twitter.extract`` writes them and
        ``validators.validate_post_provenance`` has already compared the
        excerpt with its own slice of ``text.canonical``, verbatim. So this is
        a mapping and not a re-derivation: nothing here re-reads the capture,
        re-slices the text, or normalizes anything. Normalizing would discard
        the ZWNJ, NBSP and Persian digits a Persian post is made of, which is
        exactly what the provenance rule refuses.

        No ``video_id`` guard, because there is nothing to compare: a post
        claim names no run. ``YouTubeAdapter._locator`` leaves the locator
        unaddressed when a unit's provenance names a *different* video, so that
        a canonically broken unit is never pointed at the wrong artifact. Here
        the artifact id is built **from the claim's own** ``post_id``, so the
        locator cannot address a post other than the one the claim names — the
        guard's job is done by construction rather than by a comparison.
        """
        provenance = unit.get("source")
        if not isinstance(provenance, Mapping):
            raise AdapterError(
                f"source-class {owner} has no source block, so it has "
                "no locator; a locator is never constructed without canonical data"
            )
        post_id = required_field(provenance, "post_id", owner)
        artifact = build_id(source_id.entity, f"{POST_ID_PREFIX}{post_id}", owner)
        locator: dict[str, Any] = {
            "type": "text_span",
            "artifact_id": artifact.value,
        }
        for field_name in ("start_char", "end_char"):
            if field_name not in provenance:
                raise AdapterError(f"source-class {owner} has no {field_name}")
            offset = copied_number(
                provenance[field_name],
                owner=owner,
                field=field_name,
                minimum=0,
                required=True,
            )
            # A half-open character range indexes a string, and text[0:2.0] is
            # a TypeError. `copied_number` accepts either, so the integer rule
            # is stated here rather than assumed of it.
            if isinstance(offset, float) and not offset.is_integer():
                refuse(owner, field_name, provenance[field_name], "states a whole character offset")
            locator[field_name] = int(offset)
        excerpt = provenance.get("evidence_excerpt")
        if excerpt is not None:
            locator["excerpt"] = copied_text(
                excerpt,
                owner=owner,
                field="evidence_excerpt",
                max_length=None,
                allow_empty=False,
            )
        return locator

    # ----------------------------------------------------------------
    # Artifacts
    # ----------------------------------------------------------------

    def _artifacts(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        items: list[Mapping[str, Any]],
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
        artifacts.extend(self._raw_artifacts(run_dir, source_id, hash_artifacts, unmappable))
        artifacts.extend(self._post_artifacts(run_dir, source_id, items, unmappable))
        # `T-252`: emitted only when the run has a brief (D-257). The base
        # class's, because what a brief is does not change with the medium.
        brief = self._source_knowledge_artifact(
            run_dir, source_id, hash_artifacts, unmappable
        )
        if brief is not None:
            artifacts.append(brief)
        return artifacts

    def _raw_artifacts(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        hash_artifacts: bool,
        unmappable: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Every preserved provider read, discovered rather than assumed.

        YouTube's single ``raw/source.<ext>`` is one file whose extension
        follows the import; a capture preserves one file **per route read**, so
        the table cannot name them and the directory is listed instead. Sorted,
        because a record set that changes order between rebuilds is not the
        rebuild-equivalence ``T-104`` proves.

        A filename that cannot spell an ``idPart`` is reported through
        ``adapter_metadata.unmappable_artifacts`` and the run is still indexed
        (D-045, D-100). It is not renamed to fit: the path is evidence, and an
        artifact whose id was invented does not address the bytes it claims to.
        """
        raw_dir = run_dir / "raw"
        if not raw_dir.is_dir():
            return []
        artifacts = []
        for path in sorted(raw_dir.iterdir()):
            if not path.is_file():
                continue
            local_id = f"{RAW_ID_PREFIX}{path.name}"
            if not is_id_part(local_id):
                unmappable.append(
                    {
                        "path": f"raw/{path.name} (in {run_dir.name})",
                        "reason": (
                            f"the name cannot spell an identifier segment, so "
                            f"{local_id!r} is not addressable"
                        ),
                    }
                )
                continue
            mapped = self._file_artifact(
                run_dir,
                source_id,
                ArtifactSpec(local_id, "raw_source", "raw", f"raw/{path.name}"),
                hash_artifacts,
                unmappable,
            )
            if mapped is not None:
                artifacts.append(mapped)
        return artifacts

    def _post_artifacts(
        self,
        run_dir: Path,
        source_id: ids.SourceId,
        items: list[Mapping[str, Any]],
        unmappable: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """One artifact per capture item — the unit a claim addresses (D-233).

        It has no local file and it is not a copy of one: the post's text lives
        inside ``capture.json``, which is its own artifact above. What this
        record carries is the *identity* — a global id a ``text_span`` can name
        and the Reader and the Map can address — plus the post's own URL, in
        the shape ``YouTubeAdapter._video_artifact`` already established for a
        thing that exists remotely.

        ``available`` is the capture's ``availability.state`` and nothing else.
        A tombstone is a real item with a real id that a run legitimately
        contains; dropping it would make the artifact set disagree with the
        item coverage that counts it, and inventing ``available: true`` for it
        would be the class of claim the whole capture contract forbids.
        """
        seen: set[str] = set()
        artifacts = []
        for index, item in enumerate(items):
            owner = f"item {index} of {self.relative(run_dir / CAPTURE_FILENAME)}"
            post_id = required_field(item, "post_id", owner)
            if not isinstance(post_id, str):
                refuse(owner, "post_id", post_id, "states a post id as a string")
            local_id = f"{POST_ID_PREFIX}{post_id}"
            if not is_id_part(local_id):
                unmappable.append(
                    {
                        "path": f"post {post_id} (in {run_dir.name})",
                        "reason": f"{local_id!r} is not an addressable identifier segment",
                    }
                )
                continue
            # A capture whose items repeat a post id would mint two artifacts
            # with one id. `check_records` refuses that at the end of
            # `adapt_run`, but the message it can give names an id and not the
            # duplication that produced it.
            if post_id in seen:
                raise AdapterError(
                    f"{owner} repeats post_id {post_id!r}, which an earlier item "
                    "already claims; one post, one artifact"
                )
            seen.add(post_id)
            artifacts.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "id": build_id(source_id.entity, local_id, owner).value,
                    "source_id": source_id.value,
                    "kind": "post",
                    "role": "external",
                    "media_type": None,
                    "path": None,
                    "url": copied_text(
                        post_url(post_id),
                        owner=owner,
                        field="post_id",
                        max_length=MAX_URL_LENGTH,
                        allow_empty=False,
                    ),
                    "bytes": None,
                    "sha256": None,
                    # The bytes are not ours and we did not fetch them, so
                    # there is nothing here to call immutable. `raw/` is where
                    # this run's immutable evidence lives.
                    "immutable": False,
                    "available": is_available(dict(item)),
                }
            )
        return artifacts

    def _source(
        self,
        run_dir: Path,
        metadata: Mapping[str, Any],
        source_id: ids.SourceId,
        owner: str,
        artifacts: list[dict[str, Any]],
        unmappable: list[dict[str, str]],
        damaged: list[dict[str, str]],
    ) -> dict[str, Any]:
        adapter_metadata: dict[str, Any] = {
            "item_count": metadata.get("item_count"),
            "available_item_count": metadata.get("available_item_count"),
            "capture_coverage_status": metadata.get("capture_coverage_status"),
            "order_basis": metadata.get("order_basis"),
            "completeness": metadata.get("completeness"),
            "anchor": metadata.get("anchor"),
            "external_references": metadata.get("external_references"),
            "extraction": metadata.get("extraction"),
            "fixture": metadata.get("fixture"),
            "fixture_note": metadata.get("fixture_note"),
            "unmappable_artifacts": unmappable,
            "damaged_files": damaged,
        }
        # `T-252`: whether the run's brief still describes the run as it is now.
        # Added rather than always present, so a run without one keeps exactly
        # the record it had (D-257) — this dict's other keys are unconditional
        # and may hold `None`, which is this adapter's own convention and not
        # one to extend to a key whose absence is meaningful.
        brief = self._source_knowledge_metadata(run_dir)
        if brief is not None:
            adapter_metadata["source_knowledge"] = brief
        return {
            "schema_version": SCHEMA_VERSION,
            "id": source_id.value,
            "source_type": source_id.source_type,
            "external_id": source_id.external_id,
            "url": copied_text(
                metadata.get("source_url"),
                owner=owner,
                field="source_url",
                max_length=MAX_URL_LENGTH,
                allow_empty=False,
            ),
            "title": copied_text(
                metadata.get("title"), owner=owner, field="title", max_length=MAX_TITLE_LENGTH
            ),
            # The generic model's publisher field. A YouTube channel, a Medium
            # byline and an X handle all land here.
            "author": copied_text(
                metadata.get("author_username"),
                owner=owner,
                field="author_username",
                max_length=MAX_TITLE_LENGTH,
            ),
            "language": copied_text(
                metadata.get("language"), owner=owner, field="language", max_length=64
            ),
            # No duration: a post is not a time-based medium, and `0` would be a
            # measurement rather than an absence.
            "duration_sec": None,
            "imported_at": copied_timestamp(
                metadata.get("imported_at"), owner=owner, field="imported_at"
            ),
            "extracted_at": copied_timestamp(
                metadata.get("acquired_at"), owner=owner, field="acquired_at"
            ),
            "canonical_dir": self.relative(run_dir),
            # The base class's builder, not a second one: `status` is a
            # structured record — three verbatim copies, two paths, a bounded
            # `audit_attempts` — and this adapter's first version wrote a bare
            # string into it. There is no branch anywhere in it that can turn a
            # stated PARTIAL or FAIL into anything else (ADR 0001 invariant 2).
            "status": self._status(run_dir, []),
            # The six keys `schemas/v1/source.schema.json` defines, and only
            # those: `counts` is `additionalProperties: false`. `segments` is
            # the item count, which is the one mapping that is *exactly* right
            # here — a post is the segment. `captions` is omitted rather than
            # zeroed: there are none, and `0` would say a count was taken.
            "counts": _counts(run_dir, metadata),
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "adapter": self.ref,
            # Fields of `metadata.json` the generic `Source` record has no home
            # for, carried through untouched. What is **not** carried is the
            # acquisition block: the provider's name, version and binary digest
            # are in `capture.json`, which is an artifact, and putting them here
            # would publish them on `/api/sources` and make a provider name part
            # of the read surface T-228 is told to keep them out of.
            "adapter_metadata": adapter_metadata,
        }
