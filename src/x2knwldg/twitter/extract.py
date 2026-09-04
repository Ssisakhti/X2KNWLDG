"""The capture becomes a run: item-based segmentation, provenance and coverage.

``T-227``. What acquisition wrote is a ``schemas/capture/v1/`` capture beside
immutable raw evidence; nothing about it is discoverable, auditable or citable
yet. This module turns it into a canonical run the existing source-grounded /
derived pipeline can work on, and it reads the **capture** — never a provider
response (ADR 0007 decision 7).

Four things it deliberately does not do, each because the alternative would be a
second implementation of something that already has one:

**A post is the segment.** :func:`x2knwldg.segmenter.create_segments` is
time-aware over captions and has no meaning here, and no ``segments.json`` is
written: the capture's ``items`` array *is* the segmentation, in root-first
order, and it is already sealed. Writing a second file holding the same
boundaries would be two answers to "where does this post start" the moment one
of them was edited.

**Coverage is item-based.** :func:`x2knwldg.coverage.create_pending_coverage`
mints time windows over a duration. There is no duration here, and a window with
no bounds would be a window in name only, so the entries are ``items`` keyed by
``post_id``. The rules that are genuinely *shared* — the three-attempt cap, the
recomputed summary, ``PASS`` being impossible while anything is unresolved — are
shared, in ``validators``, rather than reimplemented.

**Normalization stays where it is.** Items are re-derived from preserved bytes
through :func:`x2knwldg.twitter.normalize.post_from`, the same function
acquisition used (D-219). That is what makes the re-derivation check below worth
running: a second copy of the rule would agree with itself.

**Nothing is fetched.** A quoted post and a `t.co` link are *named*, never
followed. Quoted posts are recorded as external references — separate cited
sources per ADR 0007 decision 8, not embedded content — and linked pages are not
retrieved at all.

Metrics are not carried. The contract can represent them, but only as an
observation with an ``observed_at``, and a bare count in a canonical run invites
comparison across time as though it were a property of the post. Acquisition
declined to copy them for the same reason (D-219); extraction declines to invent
an ``observed_at`` they never had.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from ..ids import is_id_part
from ..io import (
    JsonReadError,
    dumps_json,
    read_json,
    sha256_text,
    write_group,
    write_json,
)
from ..pipeline import PipelineError
from ..validators import (
    bundle_shape_error,
    validate_item_coverage,
    validate_item_coverage_links,
    validate_knowledge_units,
    validate_post_provenance,
    validate_relationships,
)
from .normalize import post_from

#: What ``metadata.json`` declares, and what every validator dispatches on. The
#: field already existed with ``ids.DEFAULT_SOURCE_TYPE`` as the value assumed
#: for a run that predates it, so this needs no new mechanism — a Twitter run is
#: one that says so.
SOURCE_TYPE = "twitter"

CAPTURE_FILENAME = "capture.json"


def post_url(post_id: str) -> str:
    """The canonical URL of one post.

    The ``/i/status/`` form on purpose: it needs no author handle, so it is
    the one spelling that works for every item a capture holds — including a
    post whose author is not recorded because it is unavailable. One
    implementation because ``T-228`` addresses each item as an artifact of its
    own and needs the same URL this module already writes into
    ``metadata.source_url``.
    """
    return f"https://x.com/i/status/{post_id}"

#: The capture is the one canonical document extraction reads, so it is the one
#: a digest is recorded over (D-163's rule, applied to this medium). Unlike
#: ``segments.json`` it is not re-derivable from anything the pipeline holds —
#: it is a provider read — which is why :func:`evidence_integrity` recomputes the
#: *item set* from the preserved bytes instead.
SEALED_CANONICAL_FILES = (CAPTURE_FILENAME,)


class ExtractionError(PipelineError):
    """The capture cannot be turned into a run, and the reason is stated.

    A ``PipelineError`` since `T-229`, and for a concrete reason rather than
    tidiness: making the Twitter apply gate reachable from the CLI made this
    class reachable from ``cli.main``, which catches ``USER_FACING_ERRORS`` and
    prints the documented ``{"status": "ERROR"}`` envelope. As a bare
    ``RuntimeError`` it was outside that tuple, so a refused bundle left the
    command on a raw traceback — exactly the class of escape D-074 and the
    ``TranscriptError``/``IdError`` entries in that tuple were added to close,
    reproduced by a new medium. It refuses for the same reason
    ``artifacts.apply_extraction_bundle`` raises ``PipelineError``, so it is the
    same kind of event and now says so (D-243).
    """


class RunAlreadyInitialized(ExtractionError):
    """This capture already has canonical outputs.

    Its own type for the reason ``pipeline.RunAlreadyExists`` has one: the
    caller's answer differs. Re-initializing would rewrite a coverage document
    an audit may already have filled in, and losing an audit is not a thing to
    do on the way to doing something else.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_capture(run_dir: Path) -> dict[str, Any]:
    """The run's capture, or an :class:`ExtractionError` naming what is wrong."""
    path = run_dir / CAPTURE_FILENAME
    try:
        capture = read_json(path)
    except JsonReadError as exc:
        raise ExtractionError(f"Capture: {exc}") from exc
    if not isinstance(capture, dict):
        raise ExtractionError(f"A capture must be a JSON object: {path}")
    for required in ("items", "anchor", "coverage", "completeness", "order", "raw_evidence"):
        if required not in capture:
            raise ExtractionError(f"{path} is not a v1 capture: no {required!r}")
    return capture


def post_order(capture: dict[str, Any]) -> list[str]:
    """Post ids in the order the capture states, which is root-first.

    Taken from ``items`` rather than re-sorted. ``order.basis`` is
    ``parent_links``, and the capture's own contract test already holds the
    chain contiguous and consistent with ``completeness.upward``; re-deriving
    the order here would be a second opinion about a question the capture has
    already answered, and a second opinion is what D-217 had to reconcile.
    """
    return [item["post_id"] for item in capture["items"]]


def posts_by_id(capture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["post_id"]: item for item in capture["items"]}


def canonical_text(item: dict[str, Any]) -> str | None:
    """The authored text a claim's span indexes, or ``None`` if none was observed.

    ``None`` and ``""`` are different answers and the caller must be able to
    tell them apart: an unavailable post observed no text at all, while a post
    whose text is empty is a post that was read and said nothing.
    """
    text = item.get("text")
    if not isinstance(text, dict):
        return None
    canonical = text.get("canonical")
    return canonical if isinstance(canonical, str) else None


def is_available(item: dict[str, Any]) -> bool:
    return (item.get("availability") or {}).get("state") == "available"


def external_references(capture: dict[str, Any]) -> list[dict[str, Any]]:
    """Posts this run cites but does not contain: the quotes.

    ADR 0007 decision 8 — a quoted post is a separate cited source, not embedded
    content. The capture carries its id and author and nothing else, so that is
    all this can state, and extraction may not fetch it to learn more. Recorded
    at the run level rather than as a relation between knowledge units because
    the quoted post *is not a unit of this run*: there is nothing of it here to
    relate to.
    """
    references: list[dict[str, Any]] = []
    for item in capture["items"]:
        quote = item.get("quote")
        if not isinstance(quote, dict):
            continue
        references.append(
            {
                "relation": "quotes",
                "from_post_id": item["post_id"],
                "post_id": quote["quoted_post_id"],
                "author_username": quote["quoted_author_username"],
                "fetched": False,
                "note": (
                    "a separate cited source (ADR 0007 decision 8); its content is not "
                    "in this run and was not retrieved"
                ),
            }
        )
    return references


def create_pending_coverage(capture: dict[str, Any]) -> dict[str, Any]:
    """The unaudited coverage document: one entry per included post.

    Three states an included post can be in, and they are different claims:

    * **auditable** — it was observed and has text, so an audit owes it either
      knowledge units or an accounted omission. Minted ``pending``.
    * **unavailable** — nothing was observed, so there is nothing to audit and
      never will be at this tier. Minted ``omitted`` with ``source_unavailable``
      (D-225), which is a reason the pipeline states rather than an auditor's
      judgement call.
    * **observed but incomplete** — the post is there and its text is known to
      be cut short. Minted ``pending`` *and* carrying an unresolved item, so it
      can still be audited over what was observed while the gap keeps the run
      off ``PASS``. It is ``unresolved`` rather than ``omitted`` because it is
      exactly the kind of gap that a second route can close (``T-225``);
      omitting it would file a resolvable gap as a decision.

    Only ``known_truncated`` counts as incomplete. ``unverified`` is the normal
    state of every single-route read — text completeness has no in-band signal
    on any measured route — so treating it as a gap would put every Twitter run
    at ``PARTIAL`` forever and make the verdict mean nothing. That limitation is
    real and is recorded where it belongs: in the capture, and in
    ``metadata.capture_coverage_status``.

    **The capture's own omissions are partitioned, not copied.** An entry in
    ``capture.coverage.omitted_items`` may name a post that *is* an included
    item — the truncated post is both included and omitted, and so is an
    unavailable one — so a straight copy would file a post as excluded from an
    audit it is the subject of. Membership decides: an omission naming an
    included post is that post's business and is already covered by the two
    rules above, and everything else — a third-party parent, descendants no
    credential-free route can enumerate — was never a candidate and is carried
    through with the capture's own reason, verbatim.

    ``expected_item_count`` is not recomputed here. The capture is the document
    that knows what it expected to find, and disagreeing with it would be a
    second answer to that question.
    """
    included_ids = {item["post_id"] for item in capture["items"]}
    items: list[dict[str, Any]] = []
    for index, item in enumerate(capture["items"]):
        post_id = item["post_id"]
        entry: dict[str, Any] = {
            "item_id": f"CI-{index + 1:04d}",
            "post_id": post_id,
            "status": "pending",
            "knowledge_units": [],
            "omitted_items": [],
            "unresolved_items": [],
        }
        if not is_available(item):
            entry["status"] = "omitted"
            entry["omitted_items"] = [
                {
                    "type": "source_unavailable",
                    "note": (
                        "The post was not observed at this tier, so it carries no text "
                        "to audit. Deleted, suspended and protected are not "
                        "distinguishable below Tier 2."
                    ),
                }
            ]
        else:
            entry["unresolved_items"] = [
                {
                    "type": "coverage_not_audited",
                    "note": "Knowledge extraction and coverage audit have not run yet.",
                }
            ]
            completeness = ((item.get("text") or {}).get("completeness") or {}).get("status")
            if completeness == "known_truncated":
                entry["unresolved_items"].append(
                    {
                        "type": "capture_text_truncated",
                        "note": (
                            "The acquiring surface returned only part of this post's text, "
                            "so an audit of it cannot be complete. A corroborating route "
                            "can close this gap."
                        ),
                    }
                )
        items.append(entry)

    excluded = [
        dict(entry)
        for entry in capture["coverage"]["omitted_items"]
        if entry.get("post_id") not in included_ids
    ]
    pending = sum(1 for entry in items if entry["status"] == "pending")
    unresolved = sum(len(entry["unresolved_items"]) for entry in items)
    return {
        "schema_version": "1.0",
        "source_type": SOURCE_TYPE,
        "source_id": capture["anchor"]["post_id"],
        # Named so nothing mistakes these entries for the time windows the
        # YouTube coverage document carries. A validator dispatches on it.
        "basis": "items",
        "status": "PARTIAL",
        "audit_attempts": 0,
        "items": items,
        "excluded_items": excluded,
        "summary": {
            "total_items": len(items),
            "covered_items": 0,
            "pending_items": pending,
            "unresolved_important_items": unresolved,
            "excluded_items": len(excluded),
        },
    }


def _metadata(capture: dict[str, Any], canonical_hashes: dict[str, str]) -> dict[str, Any]:
    anchor = capture["anchor"]
    source_id = anchor["post_id"]
    items = capture["items"]
    first_available = next((item for item in items if is_available(item)), None)
    author = (first_available or {}).get("author") or {}
    languages = sorted({item["lang"] for item in items if item.get("lang")})
    document: dict[str, Any] = {
        "schema_version": "1.0",
        "pipeline_version": __version__,
        # The run-id key every existing reader uses, holding this run's external
        # id. `source_type` beside it is what says which kind of id it is; the
        # 3-part global id scheme is source-neutral by construction (D-011) and
        # renaming this field is not T-227's to do.
        "video_id": source_id,
        "source_type": SOURCE_TYPE,
        "source_url": post_url(source_id),
        "author_username": author.get("username"),
        "title": _title(capture),
        "channel": author.get("username") or "Unknown author",
        # Plural and listed: a self-thread can legitimately change language
        # mid-chain, and collapsing that to one value would be a claim the
        # capture does not make.
        "languages": languages,
        "language": languages[0] if len(languages) == 1 else "mixed" if languages else "unknown",
        "anchor": dict(anchor),
        "item_count": len(items),
        "available_item_count": sum(1 for item in items if is_available(item)),
        "order_basis": capture["order"]["basis"],
        "completeness": {
            "upward": dict(capture["completeness"]["upward"]),
            "downward": dict(capture["completeness"]["downward"]),
        },
        "capture_coverage_status": capture["coverage"]["status"],
        "external_references": external_references(capture),
        "acquired_at": capture["acquisition"]["requested_at"],
        "imported_at": _now(),
        "canonical_hashes": dict(canonical_hashes),
    }
    return document


def _title(capture: dict[str, Any]) -> str:
    """A run title taken from the root post's first line, or an honest fallback.

    Truncated on a word boundary and marked with an ellipsis when it is cut, so
    a title is never a sentence fragment presented as a whole one. A capture
    whose first item observed no text has no title to take: it says so.
    """
    for item in capture["items"]:
        text = canonical_text(item)
        if not text:
            continue
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line:
            continue
        if len(first_line) <= 90:
            return first_line
        cut = first_line[:90].rsplit(" ", 1)[0].rstrip()
        return f"{cut or first_line[:90]}…"
    return "Post with no observed text"


def initialize_run(run_dir: Path) -> dict[str, Any]:
    """Write ``metadata.json`` and ``coverage.json`` for an acquired capture.

    The analogue of ``pipeline.import_transcript``, and shorter for a reason:
    there is no transcript to parse, no segmentation to compute and no integrity
    check to run over captions, because the capture already carries its item
    boundaries and its own digests. What is left is to declare what the run is
    and to scaffold the audit that has not happened.

    Refuses a run that already has canonical outputs rather than rewriting them.
    """
    run_dir = run_dir.expanduser().resolve()
    capture = read_capture(run_dir)
    source_id = capture["anchor"]["post_id"]
    if not is_id_part(source_id):
        raise ExtractionError(f"The capture's anchor is not a usable run id: {source_id!r}")
    if (run_dir / "metadata.json").exists() or (run_dir / "coverage.json").exists():
        raise RunAlreadyInitialized(
            f"{run_dir} already has canonical outputs. Re-initializing would discard a "
            "coverage audit; move or version the run instead."
        )

    capture_text = (run_dir / CAPTURE_FILENAME).read_text(encoding="utf-8")
    canonical_hashes = {CAPTURE_FILENAME: sha256_text(capture_text)}
    coverage = create_pending_coverage(capture)
    metadata = _metadata(capture, canonical_hashes)
    write_group(
        [
            (run_dir / "metadata.json", dumps_json(metadata)),
            (run_dir / "coverage.json", dumps_json(coverage)),
        ]
    )
    return metadata


def _carry_item_scaffold_forward(coverage: dict[str, Any], capture: dict[str, Any]) -> None:
    """Restore the facts the scaffold knows and an audit does not get to restate.

    The item-based counterpart of ``artifacts._carry_coverage_scaffold_forward``
    and the same lesson (D-164): a bundle's coverage document *replaces* the
    scaffolded one, so whatever the scaffold knew and the bundle omits is
    silently dropped — and worse, whatever the bundle *states* about itself is
    then what the validator measures it against.

    Three groups of field, and the difference between them is who is entitled to
    the answer:

    * **What the capture says.** ``basis``, ``source_id``, ``source_type`` and
      ``excluded_items`` are read off the capture, so they are imposed rather
      than accepted. An audit that renamed its own ``basis`` would be read by
      the time-window validator and report every post missing; an audit that
      shortened ``excluded_items`` would quietly promote a third-party parent
      into something nobody has to account for.
    * **What the pipeline minted.** The ``source_unavailable`` omission (D-225)
      and the ``capture_text_truncated`` unresolved item are facts about what
      was observed, not judgements — ``prompts/twitter/05_item_coverage_audit.md``
      tells the model in as many words not to overwrite them, and this is where
      that promise is kept. Re-imposed if missing, and re-imposing the
      truncation gap is what stops a model reaching ``PASS`` by deleting it.
    * **What the audit says.** Every entry's ``status``, its
      ``knowledge_units``, its own omissions and any unresolved item it added.
      Those are the audit's to write, and none of them is touched here.

    ``coverage_not_audited`` is deliberately *not* re-imposed: it is the
    scaffold saying no audit has run, and resolving it is exactly what an audit
    does. ``summary`` is recomputed rather than carried, for the reason its
    YouTube sibling is: it is derived from the entries the bundle just supplied.
    """
    scaffold = create_pending_coverage(capture)
    minted = {entry["post_id"]: entry for entry in scaffold["items"]}
    for field in ("schema_version", "source_type", "source_id", "basis"):
        coverage[field] = scaffold[field]
    coverage["excluded_items"] = [dict(entry) for entry in scaffold["excluded_items"]]

    entries = coverage.get("items")
    if not isinstance(entries, list):
        # `validate_item_coverage` reports the shape failure, and the gate
        # refuses on it. Nothing to carry forward into a document that is not
        # one.
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        mint = minted.get(entry.get("post_id"))
        if mint is None:
            # A post that is not in this capture. Again the validator's to
            # refuse — inventing an `item_id` for it would only make the
            # refusal harder to read.
            continue
        entry["item_id"] = mint["item_id"]
        for field, kept in (
            ("omitted_items", {"source_unavailable"}),
            ("unresolved_items", {"capture_text_truncated"}),
        ):
            stated = entry.get(field, [])
            if not isinstance(stated, list):
                # Present and the wrong type. Left exactly as it is:
                # `validate_item_coverage` reports `coverage_item_field_not_array`
                # and the gate refuses, which is a better answer than quietly
                # replacing a malformed field with a well-formed one. A *missing*
                # field is different — it is an audit that said nothing, and
                # what the pipeline minted still holds.
                continue
            present = {
                item.get("type") for item in stated if isinstance(item, dict)
            }
            restored = [
                dict(item)
                for item in mint[field]
                if item["type"] in kept and item["type"] not in present
            ]
            if restored:
                entry[field] = [*restored, *stated]

    statuses = [entry.get("status") if isinstance(entry, dict) else None for entry in entries]
    coverage["summary"] = {
        "total_items": len(entries),
        "covered_items": sum(1 for status in statuses if status == "covered"),
        "pending_items": sum(1 for status in statuses if status == "pending"),
        "unresolved_important_items": sum(
            len(entry.get("unresolved_items") or [])
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("unresolved_items"), list)
        ),
        "excluded_items": len(coverage["excluded_items"]),
    }


def apply_extraction_bundle(run_dir: Path, bundle_path: Path) -> dict[str, Any]:
    """Apply a model's extraction to an initialized Twitter run, or refuse it whole.

    The gate ``artifacts.apply_extraction_bundle`` is for a YouTube run, and it
    is a gate in the same sense: a bundle that fails validation is not written,
    so a run cannot reach the disk in a state its own validators refuse. What
    differs is only what the bundle is checked *against* — a capture rather than
    a transcript and segments, a post id and a codepoint span rather than a time
    range, item coverage rather than a timeline. The bundle's top-level contract
    is shared outright (``validators.bundle_shape_error``), because that one is
    about the bundle and not about the medium.

    The four canonical files are written in **one** ``write_group``: they
    describe a single extraction, and ``validate_run`` immediately below reads
    all four, so a half-applied bundle would be validated as though it were a
    whole one.
    """
    run_dir = run_dir.expanduser().resolve()
    capture = read_capture(run_dir)
    metadata = _read(run_dir / "metadata.json")
    try:
        bundle = read_json(bundle_path.expanduser().resolve())
    except JsonReadError as exc:
        raise ExtractionError(f"Extraction bundle: {exc}") from exc
    shape_error = bundle_shape_error(bundle)
    if shape_error:
        raise ExtractionError(shape_error)

    source_id = capture["anchor"]["post_id"]
    if metadata.get("video_id") != source_id:
        # The run's two documents disagree about which post this run is. A
        # bundle applied here would be applied to whichever of them the reader
        # happened to trust.
        raise ExtractionError(
            f"{run_dir} has metadata for {metadata.get('video_id')!r} beside a capture "
            f"anchored at {source_id!r}; the run was not initialized from this capture."
        )

    units_document = {
        "schema_version": "1.0",
        "video_id": source_id,
        # What `validate_knowledge_units` dispatches on (D-226). Declared in the
        # canonical file rather than inferred later, so a reader of
        # `knowledge_units.json` alone knows which provenance shape its units
        # carry.
        "source_type": SOURCE_TYPE,
        "units": bundle["knowledge_units"],
    }
    relationships_document = {
        "schema_version": "1.0",
        "video_id": source_id,
        "relationships": bundle["relationships"],
    }
    coverage_document = bundle["coverage"]
    _carry_item_scaffold_forward(coverage_document, capture)

    unit_validation = validate_knowledge_units(units_document)
    unit_ids = {
        unit["id"]
        for unit in units_document["units"]
        if isinstance(unit, dict) and isinstance(unit.get("id"), str) and unit["id"]
    }
    errors = {
        "knowledge_units": unit_validation["errors"],
        "provenance": validate_post_provenance(units_document, capture)["errors"],
        "relationships": validate_relationships(relationships_document, unit_ids)["errors"],
        "coverage": validate_item_coverage(coverage_document, capture)["errors"],
    }
    if any(errors.values()):
        raise ExtractionError(
            f"Extraction bundle failed validation: {json.dumps(errors, ensure_ascii=False)}"
        )
    # Kept separate for the reason the YouTube gate keeps it separate: this is
    # the cross-document rule, and it is the one an apply gate exists to catch —
    # a unit cited under a post it does not cite leaves that post looking
    # covered with no evidence of its own.
    link_errors = validate_item_coverage_links(coverage_document, units_document["units"])
    if link_errors:
        raise ExtractionError(
            f"Coverage does not match the knowledge units: "
            f"{json.dumps(link_errors, ensure_ascii=False)}"
        )

    extraction_metadata = bundle.get("extraction_metadata")
    if extraction_metadata is not None:
        metadata["extraction"] = extraction_metadata
    metadata["extracted_at"] = _now()
    write_group(
        [
            (run_dir / "knowledge_units.json", dumps_json(units_document)),
            (run_dir / "relationships.json", dumps_json(relationships_document)),
            (run_dir / "coverage.json", dumps_json(coverage_document)),
            (run_dir / "metadata.json", dumps_json(metadata)),
        ]
    )
    return validate_run(run_dir)

def evidence_integrity(
    run_dir: Path, metadata: Any, capture: Any
) -> dict[str, Any]:
    """Does the evidence still hash to what the run recorded — and re-derive?

    Three independent checks, the same doctrine as
    ``pipeline._evidence_integrity`` and with one of the three replaced because
    its premise does not hold here:

    1. **The recorded digest.** ``metadata.canonical_hashes`` pins the exact
       bytes of ``capture.json`` as written at initialization. Absent rather
       than empty on a run that recorded none, so "no digest was taken" stays
       distinguishable from "the digest does not match" — the first is an older
       run, the second is tampering.
    2. **The preserved bytes.** Every ``raw_evidence`` entry's
       ``sha256_sanitized`` is recomputed from the file on disk. This is the
       acceptance criterion the capture contract was frozen on, run here over a
       real run rather than over a fixture.
    3. **Re-derivation.** ``segments.json`` is a pure function of the captions,
       so the YouTube path recomputes it. A capture is a provider read and is a
       pure function of nothing — so what is recomputed instead is the **item
       set**: each available item is re-derived from its own preserved response
       through the same :func:`post_from` acquisition used, and compared. That
       catches an edited ``capture.json`` whose digest was also updated, which
       is exactly the case check 1 cannot see.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(metadata, dict) or not isinstance(capture, dict):
        return {"status": "FAIL", "errors": [{"code": "unreadable_run"}], "warnings": warnings}

    recorded = metadata.get("canonical_hashes")
    if not isinstance(recorded, dict) or CAPTURE_FILENAME not in recorded:
        warnings.append({"code": "no_recorded_capture_digest", "file": CAPTURE_FILENAME})
    else:
        path = run_dir / CAPTURE_FILENAME
        actual = sha256_text(path.read_text(encoding="utf-8")) if path.is_file() else None
        if actual is None:
            errors.append({"code": "missing_canonical_file", "file": CAPTURE_FILENAME})
        elif actual != recorded[CAPTURE_FILENAME]:
            errors.append(
                {
                    "code": "canonical_file_digest_mismatch",
                    "file": CAPTURE_FILENAME,
                    "recorded": recorded[CAPTURE_FILENAME],
                    "actual": actual,
                }
            )

    project_root = run_dir.parent.parent
    preserved: dict[str, bytes] = {}
    for entry in capture.get("raw_evidence") or []:
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            errors.append({"code": "raw_evidence_without_path"})
            continue
        evidence_path = (project_root / relative).resolve()
        if project_root.resolve() not in evidence_path.parents:
            errors.append({"code": "raw_evidence_outside_project", "path": relative})
            continue
        if not evidence_path.is_file():
            errors.append({"code": "raw_evidence_missing", "path": relative})
            continue
        raw = evidence_path.read_bytes()
        actual = sha256_text(raw.decode("utf-8", "surrogateescape"))
        if actual != entry.get("sha256_sanitized"):
            errors.append(
                {
                    "code": "raw_evidence_digest_mismatch",
                    "path": relative,
                    "recorded": entry.get("sha256_sanitized"),
                    "actual": actual,
                }
            )
            continue
        preserved[relative] = raw

    errors.extend(_rederivation_errors(capture, preserved))
    status = "FAIL" if errors else "PASS"
    return {"status": status, "errors": errors, "warnings": warnings}


def _rederivation_errors(
    capture: dict[str, Any], preserved: dict[str, bytes]
) -> list[dict[str, Any]]:
    """Each available item, rebuilt from its own preserved response.

    Pairing is by post id read out of the response, never by position: an
    ordering assumption is how bytes and post get matched to each other by
    inference, which is the thing ``_preserve_reads`` avoids on the way in.

    Only the fields ``post_from`` produces are compared. ``text.completeness``
    and ``text.supplied_by`` are decided by the *route*, not by the record, so
    they are not re-derivable from a response and are excluded rather than
    compared against a guess.
    """
    import json

    errors: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    for raw in preserved.values():
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not every preserved response is JSON: an unavailability is
            # preserved as the tool's own message (D-216), and there is no item
            # to re-derive from it.
            continue
        record = parsed[0] if isinstance(parsed, list) and parsed else parsed
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            records[record["id"]] = record

    for item in capture["items"]:
        if not is_available(item):
            continue
        post_id = item["post_id"]
        record = records.get(post_id)
        if record is None:
            errors.append({"code": "item_without_preserved_response", "post_id": post_id})
            continue
        text = item.get("text") or {}
        rebuilt = post_from(
            record,
            text.get("supplied_by") or {},
            text.get("completeness") or {},
        )
        # Entities are excluded from the comparison for the same reason
        # completeness is: at the qualified local route the only spans available
        # are mentions, which `post_from` does reproduce — but a capture that
        # gained URL spans from a corroborating route (D-218) carries spans this
        # record cannot supply. Comparing them would report a fixture built from
        # two routes as tampered with.
        for shape in (item, rebuilt):
            if isinstance(shape.get("text"), dict):
                shape["text"] = {k: v for k, v in shape["text"].items() if k != "entities"}
        if dumps_json(rebuilt) != dumps_json({k: v for k, v in item.items() if k != "edits"}):
            errors.append(
                {
                    "code": "item_disagrees_with_preserved_response",
                    "post_id": post_id,
                }
            )
    return errors


def validate_run(run_dir: Path) -> dict[str, Any]:
    """Validate a Twitter run and write ``validation.json``.

    Section for section the same report ``pipeline.validate_run`` produces, so a
    reader and the API see one shape whichever medium a run came from. What
    differs is what each section is checked *against*: the capture rather than a
    transcript and segments, a post id and a codepoint span rather than a time
    range, and item coverage rather than a timeline.
    """
    run_dir = run_dir.expanduser().resolve()
    capture = read_capture(run_dir)
    metadata = _read(run_dir / "metadata.json")
    knowledge = _read(run_dir / "knowledge_units.json")
    relationships = _read(run_dir / "relationships.json")
    coverage = _read(run_dir / "coverage.json")
    units = knowledge.get("units", []) if isinstance(knowledge, dict) else []
    unit_ids = {
        unit["id"]
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("id"), str) and unit["id"]
    }
    result: dict[str, Any] = {
        "capture": _capture_section(capture),
        "evidence": evidence_integrity(run_dir, metadata, capture),
        "knowledge_units": validate_knowledge_units(knowledge),
        "provenance": validate_post_provenance(knowledge, capture),
        "relationships": validate_relationships(relationships, unit_ids),
        "coverage": validate_item_coverage(coverage, capture),
    }
    link_errors = validate_item_coverage_links(coverage, units)
    if link_errors:
        result["coverage"]["errors"] = list(result["coverage"]["errors"]) + link_errors
        result["coverage"]["status"] = "FAIL"
    result["status"] = _verdict(result, coverage)
    write_json(run_dir / "validation.json", result)
    return result


def _read(path: Path) -> dict[str, Any]:
    try:
        document = read_json(path)
    except JsonReadError as exc:
        raise ExtractionError(f"Canonical output: {exc}") from exc
    if not isinstance(document, dict):
        raise ExtractionError(f"Canonical output must be a JSON object: {path}")
    return document


def _capture_section(capture: dict[str, Any]) -> dict[str, Any]:
    """The capture's own verdict, restated rather than recomputed.

    A run can be no better than the capture under it: a ``FAIL`` capture — a
    reference that resolved to nothing — cannot become a passing run because
    extraction did its part correctly. Carried into the report so the reason a
    run cannot pass is visible in the run, not only in the capture.
    """
    coverage = capture["coverage"]
    status = coverage["status"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    entry = {
        "code": "capture_not_complete",
        "capture_status": status,
        "expected_item_count": coverage["expected_item_count"],
        "included": len(coverage["included_post_ids"]),
        "omitted": len(coverage["omitted_items"]),
    }
    if status == "FAIL":
        errors.append(entry)
    elif status == "PARTIAL":
        warnings.append(entry)
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


#: How a section's status becomes the run's. The same three-way mapping
#: ``pipeline._run_verdict`` uses: any failing section fails the run, and a
#: coverage document that is not `PASS` holds the run at `PARTIAL` rather than
#: letting a green validator list imply a complete audit.
def _verdict(sections: dict[str, Any], coverage: Any) -> str:
    statuses = {
        name: section.get("status")
        for name, section in sections.items()
        if isinstance(section, dict)
    }
    if any(status == "FAIL" for status in statuses.values()):
        return "FAIL"
    coverage_status = coverage.get("status") if isinstance(coverage, dict) else None
    if coverage_status != "PASS":
        return "PARTIAL"
    if any(status == "PARTIAL" for status in statuses.values()):
        return "PARTIAL"
    return "PASS"
