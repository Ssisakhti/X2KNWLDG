"""Acquisition: a user's reference becomes one capture on disk (T-224).

The seam's job, and its whole job, is to turn a reference the user supplied into
``schemas/capture/v1/`` bytes plus the raw evidence those bytes cite. It reads
one route — the pinned local provider at Tier 1 — and it never guesses at
anything the route did not return. Corroboration and fallbacks are ``T-225``'s;
extraction is ``T-227``'s; the index and the UI are ``T-228``'s. Nothing here
writes ``metadata.json``, so an acquired post is invisible to
:func:`x2knwldg.io.discover_run_dirs` and to the library until a later task
gives it one — a run half-made by acquisition must not appear in ``status`` as a
broken YouTube run.

**A reference is parsed offline.** :func:`parse_reference` accepts a bare post id
or an X status URL and refuses everything else before a process is spawned, so
``123; rm -rf /`` fails as a bad reference rather than reaching the provider —
which would not run it either, since ``argv`` is a list and no shell is
involved, but a reference is data and the check belongs where the data arrives.

**A thread is walked upward, from its last post.** D-206, and it is the measured
half of the MVP: following ``reply_to`` terminates at a parent-less root and
*is* a completeness proof, credential-free. Descendants cannot be enumerated at
any credential-free tier — ``x thread`` and ``x replies`` return the anchor
alone, and a 250-post author archive held 3 of the 10 members of a real thread —
so ``completeness.downward`` is ``unprovable`` and the contract has no field in
which to claim otherwise. An anchor that turns out to *be* a root is therefore
``PARTIAL`` with its descendants named as omitted, and the caller is told to
re-ingest from the thread's last post.

**A transport failure is not a finding.** D-209: this path runs over an
always-on tunnel, and exit 8 covers both "the tunnel is down" and "the request
timed out". Either one aborts the acquisition with nothing written — no capture,
no evidence, no coverage verdict. A dropped tunnel that produced a ``PARTIAL``
would look exactly like a thread that ends there, and that is the misreading
D-209 exists to prevent. A provider that answers with something unusable is a
different failure with a different name: :class:`ProviderDrift`. A rate limit
(:class:`RateLimited`) joins the transient class rather than the drift one — the
tool did exactly what it should, and a budget is a property of X.

**Nothing is overwritten.** Evidence is immutable, so a second acquisition into
a run that already holds a capture is refused. The capture and every evidence
file are handed to :func:`x2knwldg.io.write_group` together, so a failure part
way through leaves the directory exactly as it was (D-090).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..io import write_group
from ..pipeline import resolve_run_dir
from . import evidence as evidence_module
from .normalize import post_from
from .provider import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIER,
    DEFAULT_TIMEOUT_SEC,
    Read,
    Tier,
    VerifiedProvider,
)
from .provider import read_tweet as provider_read_tweet

CAPTURE_SCHEMA_VERSION = "1.0"

#: The acquisition output, at the run root beside where the canonical YouTube
#: files live for a video run. ``T-227`` consumes it; nothing else writes it.
CAPTURE_FILENAME = "capture.json"

RAW_DIR_NAME = "raw"

#: A bound on the upward walk. The longest self-thread T-222 measured was ten
#: posts; 400 is far past any plausible authored thread and still a bound, so a
#: provider that answered every read with a parent pointing at a new id could
#: not walk forever.
MAX_THREAD_HOPS = 400

#: The honest default for text completeness on a single-route read. Text
#: completeness has **no in-band signal** on any measured route: Tier 0 returned
#: 280 characters of a real 2967-character post, and 273 of 418 of an ordinary
#: Persian one, with no field announcing either loss. ``corroborated`` needs a
#: second route, which is ``T-225``'s work, so this seam never claims it.
_UNVERIFIED_NOTE = (
    "one route only; text completeness has no in-band signal on any measured route"
)
_TIER0_NOTE = (
    "one route only, and Tier 0 is the surface T-222 measured truncating long posts "
    "silently; a second route is required before this text can be called whole"
)

_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
    }
)


class AcquisitionError(Exception):
    """A refusal, with nothing written. The message is for the user."""


class TransientFailure(AcquisitionError):
    """The read could not be completed, and nothing was learned from that.

    The class D-209 is about. Its members say nothing about the post, the thread
    or the provider — the honest response is to retry later — so they must never
    reach a capture as a completeness finding, and must never be confused with
    :class:`ProviderDrift`. Nothing is written when one is raised, which is what
    stops a dropped tunnel from producing a ``PARTIAL`` that looks exactly like
    a thread ending there.
    """


class TransportFailure(TransientFailure):
    """The network failed: the tunnel is down, or the request timed out.

    Measured on 2026-09-04: x-cli returns exit ``8`` for a dropped tunnel *and*
    for a timeout, so the distinction that matters is not in the exit status but
    in what a caller may conclude from it, which is nothing.
    """


class RateLimited(TransientFailure):
    """X refused the read for now, and said when the window resets.

    Deliberately **not** :class:`ProviderDrift`: the tool did exactly what it
    should, and a rate limit is a property of the budget rather than of the
    provider's output. T-222 measured the guest tier as metering *per
    operation*, so a thread walk and an archive read draw on different budgets.
    """


class ProviderDrift(AcquisitionError):
    """The provider answered, and the answer cannot be used.

    Its own type, and deliberately not the same as a transport failure: this one
    says something about the provider — unparseable output, a record of the
    wrong kind, a missing field the contract requires — and is the failure a
    pinned, digest-verified tool is *supposed* to make loud rather than silent.
    Told apart from a dropped tunnel because D-209 requires exactly that
    distinction.
    """


@dataclass
class Acquisition:
    """What one acquisition produced, before and after it reached the disk."""

    capture: dict[str, Any]
    run_dir: Path
    capture_path: Path
    evidence_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def coverage_status(self) -> str:
        status = self.capture["coverage"]["status"]
        assert isinstance(status, str)
        return status


def parse_reference(reference: str) -> str:
    """A bare post id, or an X status URL, into a post id. Offline, and strict.

    Refused rather than repaired, on D-020's rule: a reference that is not one
    must fail, not be turned into something that happens to parse. Query strings
    and the trailing ``/photo/1`` an X share link carries are ignored, because
    they are not part of the identity of the post.
    """
    candidate = (reference or "").strip()
    if not candidate:
        raise AcquisitionError("No post reference given.")
    if candidate.isdigit():
        if len(candidate) > 25:
            raise AcquisitionError(f"Not a post id: {reference!r} is longer than 25 digits.")
        return candidate

    url = candidate if "//" in candidate else f"https://{candidate}"
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise AcquisitionError(f"Not an X post reference: {reference!r}")
    if parts.hostname is None or parts.hostname.lower() not in _HOSTS:
        raise AcquisitionError(
            f"Not an X post URL: {reference!r}. Give a post id, or a URL on "
            f"{', '.join(sorted(_HOSTS))}."
        )
    segments = [segment for segment in parts.path.split("/") if segment]
    for marker in ("status", "statuses"):
        if marker in segments:
            index = segments.index(marker)
            if index + 1 < len(segments) and segments[index + 1].isdigit():
                return segments[index + 1]
            break
    raise AcquisitionError(
        f"No post id in {reference!r}. An X status URL looks like "
        "https://x.com/<user>/status/<id>."
    )


def parse_record(read: Read) -> dict[str, Any]:
    """One successful read's stdout as an x-cli ``tweet`` record.

    Every failure here is :class:`ProviderDrift`, because the read already
    succeeded: the tool exited ``0`` and then handed back something this seam
    cannot normalize. That is the case the pin exists for — a provider whose
    output shape moved — and it is reported as such rather than as a fact about
    the post or about the network.
    """
    try:
        parsed = json.loads(read.stdout.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ProviderDrift(
            f"The provider's output was not UTF-8 ({exc}); nothing was preserved."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderDrift(
            f"The provider exited 0 but its output is not JSON ({exc}); "
            f"the request was: {read.request_shape}"
        ) from exc

    if isinstance(parsed, list):
        record = parsed[0] if parsed else None
    elif isinstance(parsed, dict):
        record = parsed
    else:
        record = None
    if not isinstance(record, dict):
        raise ProviderDrift(
            "The provider exited 0 and returned no record; the request was: "
            f"{read.request_shape}"
        )
    if record.get("kind") != "tweet":
        raise ProviderDrift(
            f"The provider returned a {record.get('kind')!r} record where a 'tweet' was "
            "expected; the capture contract models posts only."
        )

    post_id = record.get("id")
    if not isinstance(post_id, str) or not post_id.isdigit():
        raise ProviderDrift(f"The record carries no usable post id: {post_id!r}")
    author = record.get("author") or {}
    missing = [
        name
        for name, value in (
            ("author.username", author.get("username")),
            ("author.rest_id", author.get("rest_id")),
        )
        if not isinstance(value, str) or not value
    ]
    if missing:
        raise ProviderDrift(
            f"The record for post {post_id} is missing {', '.join(missing)}, which the "
            "capture contract requires of every available post."
        )
    return record


def _text_completeness(tier: Tier) -> dict[str, Any]:
    return {
        "status": "unverified",
        "note": _TIER0_NOTE if tier.number == 0 else _UNVERIFIED_NOTE,
    }


def _unavailable_item(post_id: str) -> dict[str, Any]:
    """A post that resolved to nothing, carrying nothing it did not observe.

    No author, no text, no timestamp: none was observed. And the reason is
    always ``not_determinable_at_this_tier`` — deleted, suspended and protected
    collapse into one message below Tier 2, so naming one of them would be a
    guess dressed as a finding.
    """
    return {
        "post_id": post_id,
        "availability": {"state": "unavailable", "reason": "not_determinable_at_this_tier"},
    }


def _refuse(read: Read, post_id: str, *, walking: bool = False) -> None:
    """Turn a read that produced no record into the right kind of refusal.

    Three kinds, and the difference is the whole of D-209: a rate limit and a
    transport failure are transient and say nothing, while anything else means
    the provider answered in a way this seam cannot use. Reporting the first two
    as drift would put the blame on a pinned tool for the network's behaviour —
    and would discard a good capture on the wrong reason.
    """
    _refuse_on_transport(read, post_id)
    where = f"Walking to parent {post_id}" if walking else f"Reading post {post_id}"
    if read.outcome == "rate_limited":
        raise RateLimited(
            f"{where} was rate limited by X: {read.error_text or 'no message'}. Nothing was "
            "written. The tool names the surface and the reset time; retry after it."
        )
    raise ProviderDrift(
        f"{where} ended as {read.outcome} (exit {read.exit_code}): "
        f"{read.error_text or 'no message'}"
    )


def _refuse_on_transport(read: Read, post_id: str) -> None:
    if read.is_transport_failure:
        raise TransportFailure(
            f"The network, not the provider: reading post {post_id} ended as "
            f"{read.outcome} ({read.error_text or 'no message'}). Nothing was written. "
            "This says nothing about the post or about the provider — the tunnel this "
            "path depends on (D-209) may be down. Retry when it is up."
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def acquire(
    reference: str,
    *,
    provider: VerifiedProvider,
    output_root: Path,
    via_tunnel: bool,
    tier: Tier = DEFAULT_TIER,
    thread: bool = False,
    tunnel_note: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    max_bytes: int = DEFAULT_MAX_BYTES,
    requested_at: str | None = None,
) -> Acquisition:
    """Acquire one post, or one same-author self-thread from its last post.

    *via_tunnel* is **stated, never inferred**. The schema requires it and the
    seam cannot measure it: an interface that exists does not prove traffic
    routes through it, and D-209 is on record precisely because an environment
    premise was taken rather than established. So the caller says, and the
    capture records what the caller said.
    """
    anchor_id = parse_reference(reference)
    stamp = requested_at or _now()
    run_dir = resolve_run_dir(output_root, anchor_id)
    capture_path = run_dir / CAPTURE_FILENAME
    if capture_path.exists():
        raise AcquisitionError(
            f"A capture already exists at {capture_path}. Raw evidence and captures are "
            "immutable: move or version that run before acquiring it again."
        )

    reads: list[Read] = []
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    anchor_read = provider_read_tweet(
        provider, anchor_id, tier=tier, timeout=timeout, max_bytes=max_bytes
    )
    reads.append(anchor_read)
    _refuse_on_transport(anchor_read, anchor_id)

    if anchor_read.outcome == "ok":
        records.append(parse_record(anchor_read))
    elif anchor_read.outcome != "not_found":
        _refuse(anchor_read, anchor_id)

    unresolved_at: str | None = None
    crossed_author: str | None = None
    if records and thread:
        records, unresolved_at, crossed_author = _walk_upward(
            records[0],
            provider=provider,
            tier=tier,
            timeout=timeout,
            max_bytes=max_bytes,
            reads=reads,
        )

    preserved = _preserve_reads(
        reads=reads,
        records=records,
        run_dir=run_dir,
        output_root=output_root,
        tier=tier,
    )

    capture = _assemble(
        anchor_id=anchor_id,
        records=records,
        reads=reads,
        preserved=[item.record for item in preserved],
        provider=provider,
        tier=tier,
        thread=thread,
        via_tunnel=via_tunnel,
        tunnel_note=tunnel_note,
        requested_at=stamp,
        unresolved_at=unresolved_at,
        crossed_author=crossed_author,
        warnings=warnings,
    )

    entries = [(item.path, item.text) for item in preserved]
    entries.append((capture_path, json.dumps(capture, indent=2, ensure_ascii=False) + "\n"))
    (run_dir / RAW_DIR_NAME).mkdir(parents=True, exist_ok=True)
    write_group(entries)

    return Acquisition(
        capture=capture,
        run_dir=run_dir,
        capture_path=capture_path,
        evidence_paths=[item.path for item in preserved],
        warnings=warnings,
    )


def _walk_upward(
    anchor: dict[str, Any],
    *,
    provider: VerifiedProvider,
    tier: Tier,
    timeout: float,
    max_bytes: int,
    reads: list[Read],
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Follow ``reply_to`` from the anchor to a root. Returns root-first records.

    Three ways the walk ends, and they are different claims:

    * a post with no parent — the one real completeness proof available;
    * a parent that resolves to nothing — the chain is broken at a named id, and
      the capture says so rather than presenting what it has as whole;
    * a parent by **another author** — the self-thread is whole, and the
      conversation above it is outside the MVP (ADR 0007 excludes third-party
      replies). The boundary is named as an omission, not silently trimmed.
    """
    author_rest_id = (anchor.get("author") or {}).get("rest_id")
    chain = [anchor]
    seen = {anchor["id"]}
    unresolved_at: str | None = None
    crossed_author: str | None = None

    current = anchor
    hops = 0
    while True:
        parent_id = current.get("reply_to")
        if parent_id is None or parent_id == "":
            break
        if not isinstance(parent_id, str) or not parent_id.isdigit():
            # The provider's own pointer, and it is not an id. Drift, not a bad
            # reference: nothing the user typed reached this value.
            raise ProviderDrift(
                f"Post {current['id']} names {parent_id!r} as its parent, which is not a "
                "post id."
            )
        if parent_id in seen:
            # A chain that returns to a post it already walked is not a thread.
            # X cannot produce one; a provider whose output moved could, and
            # following it would loop until the hop bound with a duplicate item
            # set to show for it.
            raise ProviderDrift(
                f"The parent chain returns to post {parent_id}, which it has already "
                "walked. A thread cannot contain a cycle."
            )
        hops += 1
        if hops > MAX_THREAD_HOPS:
            raise AcquisitionError(
                f"The upward walk passed {MAX_THREAD_HOPS} hops without reaching a root; "
                "refused rather than followed further."
            )
        read = provider_read_tweet(
            provider, parent_id, tier=tier, timeout=timeout, max_bytes=max_bytes
        )
        reads.append(read)
        _refuse_on_transport(read, parent_id)
        if read.outcome == "not_found":
            unresolved_at = parent_id
            break
        if read.outcome != "ok":
            _refuse(read, parent_id, walking=True)
        parent = parse_record(read)
        if (parent.get("author") or {}).get("rest_id") != author_rest_id:
            crossed_author = parent["id"]
            break
        chain.append(parent)
        seen.add(parent["id"])
        current = parent

    chain.reverse()
    return chain, unresolved_at, crossed_author


def _preserve_reads(
    *,
    reads: list[Read],
    records: list[dict[str, Any]],
    run_dir: Path,
    output_root: Path,
    tier: Tier,
) -> list[evidence_module.PreservedEvidence]:
    """Preserve the bytes of every read that produced an item, in item order.

    A read that returned no record has no bytes to preserve — its existence is
    recorded in ``routes_read`` instead, which is why a failed read is never
    dropped from the capture. Pairing is by :attr:`Read.post_id`, so bytes and
    post can never be matched to each other by inference.
    """
    stdout_by_id = {read.post_id: read.stdout for read in reads if read.ok and read.stdout}
    raw_dir = run_dir / RAW_DIR_NAME
    relative_to = output_root.expanduser().resolve().parent
    preserved: list[evidence_module.PreservedEvidence] = []
    for record in records:
        post_id = record["id"]
        raw = stdout_by_id.get(post_id)
        if raw is None:
            continue
        preserved.append(
            evidence_module.prepare(
                raw=raw,
                destination=raw_dir / f"{tier.route}_{post_id}.json",
                relative_to=relative_to,
                route=tier.route,
            )
        )

    # An unavailable post produced no record, and "we looked and it is not
    # there" still has to cite something: the contract requires at least one
    # piece of raw evidence per capture, and rightly — a finding with no
    # preserved bytes is an assertion. The tool's own message is what was
    # observed, so that is what is kept, sanitized like any other evidence.
    for read in reads:
        if read.outcome != "not_found":
            continue
        if not read.error_text:
            raise ProviderDrift(
                f"Post {read.post_id} was reported unavailable with no message, so there is "
                "nothing to preserve as evidence of it."
            )
        preserved.append(
            evidence_module.prepare(
                raw=read.error_text.encode("utf-8"),
                destination=raw_dir / f"{tier.route}_{read.post_id}.unavailable.txt",
                relative_to=relative_to,
                route=tier.route,
            )
        )
    return preserved


def _assemble(
    *,
    anchor_id: str,
    records: list[dict[str, Any]],
    reads: list[Read],
    preserved: list[dict[str, Any]],
    provider: VerifiedProvider,
    tier: Tier,
    thread: bool,
    via_tunnel: bool,
    tunnel_note: str | None,
    requested_at: str,
    unresolved_at: str | None,
    crossed_author: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    """Build the capture. Every honesty rule the contract cannot express is here."""
    supplied_by = {"route": tier.route, "tier": tier.number, "surface": tier.surface}
    completeness_note = _text_completeness(tier)
    items = [post_from(record, supplied_by, dict(completeness_note)) for record in records]

    network: dict[str, Any] = {"via_tunnel": via_tunnel}
    if tunnel_note:
        network["note"] = tunnel_note

    if not records:
        # The anchor resolved to nothing. The capture still exists, because "we
        # looked and it is not there" is a finding, and it carries an item that
        # invents nothing.
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "acquisition": {
                "provider": provider.as_capture_provider(),
                "requested_at": requested_at,
                "routes_read": [read.as_route_read() for read in reads],
                "network": network,
            },
            "raw_evidence": preserved,
            "anchor": {"post_id": anchor_id, "role": "single_post", "terminal_claim": "none"},
            "items": [_unavailable_item(anchor_id)],
            "order": {"basis": "single_item"},
            "completeness": {
                "upward": {
                    "status": "incomplete",
                    "basis": "unresolved_hop",
                    "unresolved_at": anchor_id,
                },
                "downward": {
                    "status": "not_applicable",
                    "reason": "nothing resolved to walk from",
                },
            },
            "coverage": {
                "status": "FAIL",
                "expected_item_count": 1,
                "included_post_ids": [],
                "omitted_items": [
                    {
                        "post_id": anchor_id,
                        "reason": (
                            "unavailable at this tier; deleted, suspended and protected are "
                            "not distinguishable below Tier 2"
                        ),
                    }
                ],
            },
        }

    anchor_record = next(record for record in records if record["id"] == anchor_id)
    has_parent = bool(anchor_record.get("reply_to"))
    omitted: list[dict[str, Any]] = []

    if not thread:
        role = "thread_middle" if has_parent else "single_post"
        if has_parent:
            warnings.append(
                f"Post {anchor_id} replies to {anchor_record['reply_to']}. This capture is "
                "the single post only; use --thread to walk the self-thread to its root."
            )
        capture_order: dict[str, Any] = {"basis": "single_item"}
        upward: dict[str, Any] = {"status": "complete", "basis": "single_item"}
        downward: dict[str, Any] = {
            "status": "not_applicable",
            "reason": "a single post makes no claim about a conversation",
        }
    else:
        single_author = len({(r.get("author") or {}).get("rest_id") for r in records}) == 1
        if has_parent:
            role = "thread_terminal"
        else:
            role = "thread_root"
            warnings.append(
                f"Post {anchor_id} is the root of its thread, and no credential-free route "
                "can enumerate descendants (D-206). Re-acquire from the thread's LAST post "
                "to capture it whole."
            )
            omitted.append(
                {
                    "descriptor": "descendants of the anchor",
                    "reason": (
                        "not enumerable at any credential-free tier; re-ingest from the "
                        "thread's last post to obtain them"
                    ),
                }
            )
        capture_order = {
            "basis": "parent_links",
            "note": "root-first; derived from parent links, never from arrival order",
        }
        if unresolved_at is not None or crossed_author is not None:
            # The first item is not a root and must not read as one. Its own
            # `parent_post_id` stays — dropping it would hide the very link that
            # proves the chain is incomplete — and the note says what it means.
            capture_order["note"] = (
                "ordered by parent links, never by arrival order; the first item's parent "
                "is unresolved, so this chain does not begin at a root"
            )
        if unresolved_at is not None:
            upward = {
                "status": "incomplete",
                "basis": "unresolved_hop",
                "single_author": single_author,
                "unresolved_at": unresolved_at,
            }
            omitted.append(
                {
                    "post_id": unresolved_at,
                    "reason": (
                        "the parent of the first captured post is unavailable at this tier, "
                        "so the thread is not proven complete to a root"
                    ),
                }
            )
        elif crossed_author is not None:
            upward = {
                "status": "incomplete",
                "basis": "unresolved_hop",
                "single_author": single_author,
                "unresolved_at": crossed_author,
            }
            omitted.append(
                {
                    "post_id": crossed_author,
                    "reason": (
                        "the parent is by another author; third-party replies are outside "
                        "the MVP scope (ADR 0007), so the walk stopped at the self-thread's "
                        "first post"
                    ),
                }
            )
        else:
            upward = {
                "status": "complete",
                "basis": "root_reached",
                "single_author": single_author,
            }
        downward = {
            "status": "unprovable",
            "reason": (
                "complete to root from a user-asserted terminal anchor; no credential-free "
                "route can enumerate descendants to confirm the anchor is the thread's last "
                "post"
            )
            if role == "thread_terminal"
            else (
                "anchored at the root: x thread and x replies return the anchor alone at "
                "every credential-free tier, and a 250-post author archive held 3 of the 10 "
                "known members"
            ),
        }

    included = [item["post_id"] for item in items]
    status = "PASS" if not omitted else "PARTIAL"
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "acquisition": {
            "provider": provider.as_capture_provider(),
            "requested_at": requested_at,
            "routes_read": [read.as_route_read() for read in reads],
            "network": network,
        },
        "raw_evidence": preserved,
        "anchor": {
            "post_id": anchor_id,
            "role": role,
            # D-206: nothing credential-free proves an anchor is a thread's last
            # post, so a terminal anchor is the user's assertion, recorded as one.
            "terminal_claim": "user_asserted" if role == "thread_terminal" else "none",
        },
        "items": items,
        "order": capture_order,
        "completeness": {"upward": upward, "downward": downward},
        "coverage": {
            "status": status,
            "expected_item_count": len(included) + len([o for o in omitted if "post_id" in o]),
            "included_post_ids": included,
            "omitted_items": omitted,
        },
    }
