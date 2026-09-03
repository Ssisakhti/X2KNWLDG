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
from ..validators import (
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

#: The capture is the one canonical document extraction reads, so it is the one
#: a digest is recorded over (D-163's rule, applied to this medium). Unlike
#: ``segments.json`` it is not re-derivable from anything the pipeline holds —
#: it is a provider read — which is why :func:`evidence_integrity` recomputes the
#: *item set* from the preserved bytes instead.
SEALED_CANONICAL_FILES = (CAPTURE_FILENAME,)


class ExtractionError(RuntimeError):
    """The capture cannot be turned into a run, and the reason is stated."""


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
        "source_url": f"https://x.com/i/status/{source_id}",
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
    for relative, raw in preserved.items():
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
