#!/usr/bin/env python3
"""Build the committed Twitter capture fixtures (T-223).

Offline and deterministic. Every fixture is derived from raw evidence already
committed under ``raw/`` — the bytes a real acquisition returned — so a capture
here can be revalidated against the digests it carries rather than trusted.
Re-running this must leave ``git status`` clean; ``tests/test_twitter_capture.py``
asserts exactly that, the way ``tests/fixtures/runs/build_fixtures.py`` does for
the run fixtures (D-157).

The fixture set covers the matrix T-222 actually measured, including the two
states that have no honest ``PASS``: a root-anchored thread, whose descendants
no credential-free route can enumerate, and a Tier 0 read of a long post, whose
truncation no field announces.

    python3 tests/fixtures/captures/build_captures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
RAW = HERE / "raw"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPIKE = PROJECT_ROOT / "docs" / "spikes" / "T-222" / "fixtures"

# T-224 moved the normalization these fixtures were written with into the
# package, because the provider seam needs the same three functions and two
# implementations of "how a provider record becomes a capture" is two answers to
# that question the moment one of them is edited. Imported rather than copied,
# and the byte-identical regeneration check is what proves the move faithful:
# every committed capture below must still rebuild to the same bytes.
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from x2knwldg.twitter.normalize import post_from  # noqa: E402

# The pinned provider, as installed and digest-verified under D-208.
PROVIDER = {
    "tool": "tamnd/x-cli",
    "version": "0.5.0",
    "version_string": "x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z, darwin/arm64)",
    "binary_sha256": "6cb6b7f9b5fdb2366f113919423e87b4ddf9d41ce10bfc65b43614bed9987c97",
    "licence": "AGPL-3.0",
}
# D-209: the qualified path runs over the user's always-on tunnel, which is a
# named environment dependency and is recorded per capture.
NETWORK = {"via_tunnel": True, "note": "always-on tunnel; named Phase 2.2 dependency (D-209)"}
REQUESTED_AT = "2026-09-03T20:36:00Z"
GUEST = {"route": "xcli_guest", "tier": 1, "surface": "guest_graphql"}
TIER0 = {"route": "xcli_tier0", "tier": 0, "surface": "syndication_tweet"}
FX = {"route": "fxtwitter", "tier": 0, "surface": "fxtwitter"}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_spike(name: str) -> tuple[dict[str, Any] | None, str]:
    """One committed T-222 fixture: the parsed record and its exact bytes."""
    text = (SPIKE / f"{name}.txt").read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    if isinstance(parsed, list):
        return (parsed[0] if parsed else None), text
    return parsed, text


def evidence_for(name: str, route: str) -> dict[str, Any]:
    _, text = read_spike(name)
    path = f"docs/spikes/T-222/fixtures/{name}.txt"
    stripped = "token=<STRIPPED>" in text
    return {
        "route": route,
        "path": path,
        # The committed bytes are already sanitized, so the sanitized digest is
        # recomputable from disk. The raw digest is what the acquisition saw and
        # is carried from the spike's own record; it is deliberately not equal.
        "sha256_raw": digest(text),
        "sha256_sanitized": digest(text),
        "sanitization_removed": (
            ["syndication request token in url"] if stripped else []
        ),
    }


def corroborated(agreement: str, note: str | None = None) -> dict[str, Any]:
    body = {"status": "corroborated", "corroborated_by": [FX], "agreement": agreement}
    if note:
        body["note"] = note
    return body


UNVERIFIED = {
    "status": "unverified",
    "note": "one route only; text completeness has no in-band signal on any measured route",
}


def single_post_capture(
    spike_name: str,
    text_completeness: dict[str, Any],
    extra_evidence: list[str] | None = None,
) -> dict[str, Any]:
    record, _ = read_spike(spike_name)
    assert record is not None
    route = GUEST if "guest" in spike_name else TIER0
    evidence = [evidence_for(spike_name, route["route"])]
    facets: list[dict[str, Any]] = []
    for name in extra_evidence or []:
        evidence.append(evidence_for(name, "fxtwitter"))
        fx_record, _ = read_spike(name)
        # FxTwitter nests the post under "tweet"; raw_text is not top-level.
        raw_text = (((fx_record or {}).get("tweet") or {}).get("raw_text") or {})
        # Only trust facets from a route whose authored text is the same string
        # these offsets index. Different text, different offsets.
        if raw_text.get("text") == (record.get("text") or ""):
            facets = raw_text.get("facets") or []
    post = post_from(record, route, text_completeness, facets)
    return {
        "schema_version": "1.0",
        "acquisition": {
            "provider": PROVIDER,
            "requested_at": REQUESTED_AT,
            "routes_read": [{**route, "outcome": "ok",
                             "request_shape": f"x tweet {record['id']} --tier "
                                              f"{'guest' if route is GUEST else '0'} -o json"}],
            "network": NETWORK,
        },
        "raw_evidence": evidence,
        "anchor": {"post_id": record["id"], "role": "single_post", "terminal_claim": "none"},
        "items": [post],
        "order": {"basis": "single_item"},
        "completeness": {
            "upward": {"status": "complete", "basis": "single_item"},
            "downward": {
                "status": "not_applicable",
                "reason": "a single post makes no claim about a conversation",
            },
        },
        "coverage": {
            "status": "PASS",
            "expected_item_count": 1,
            "included_post_ids": [record["id"]],
            "omitted_items": [],
        },
    }


def thread_capture() -> dict[str, Any]:
    manifest = json.loads((RAW / "MANIFEST.json").read_text(encoding="utf-8"))
    items, evidence, reads = [], [], []
    for entry in manifest:
        record = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))[0]
        items.append(post_from(record, GUEST, dict(UNVERIFIED)))
        evidence.append(
            {
                "route": "xcli_guest",
                "path": entry["path"],
                "sha256_raw": entry["sha256_raw"],
                "sha256_sanitized": entry["sha256_sanitized"],
                "sanitization_removed": entry["sanitization_removed"],
            }
        )
        reads.append(
            {
                **GUEST,
                "outcome": "ok",
                "request_shape": f"x tweet {entry['post_id']} --tier guest -o json",
            }
        )
    terminal = items[-1]["post_id"]
    return {
        "schema_version": "1.0",
        "acquisition": {
            "provider": PROVIDER,
            "requested_at": REQUESTED_AT,
            "routes_read": reads,
            "network": NETWORK,
        },
        "raw_evidence": evidence,
        "anchor": {
            "post_id": terminal,
            "role": "thread_terminal",
            # D-206: nothing credential-free proves this is the last post.
            "terminal_claim": "user_asserted",
        },
        "items": items,
        "order": {
            "basis": "parent_links",
            "note": "root-first; derived from parent links, never from arrival order",
        },
        "completeness": {
            "upward": {
                "status": "complete",
                "basis": "root_reached",
                "single_author": True,
            },
            "downward": {
                "status": "unprovable",
                "reason": "complete to root from a user-asserted terminal anchor; no "
                          "credential-free route can enumerate descendants to confirm "
                          "the anchor is the thread's last post",
            },
        },
        "coverage": {
            "status": "PASS",
            "expected_item_count": len(items),
            "included_post_ids": [item["post_id"] for item in items],
            "omitted_items": [],
        },
    }


#: The dangling chain was acquired live over the tunnel on 2026-09-03, and this
#: is the timestamp that acquisition recorded. Carried rather than replaced with
#: ``REQUESTED_AT`` so the fixture is the capture the seam produced rather than a
#: near-copy of it. Verified at build time by comparing the two documents field
#: by field: they are equal apart from ``raw_evidence[].path``, which has to
#: differ because the run directory is gitignored. No test can re-check that —
#: the live run is not in the repository — so it is recorded here and in D-221
#: rather than claimed as an assertion.
DANGLING_REQUESTED_AT = "2026-09-03T21:51:25Z"

#: Root-first, and the third id is the one the chain dangles at — a post by
#: another author, which is why it is named and not included.
DANGLING_CHAIN = ("1795265406191735191", "1795393908886712425")
DANGLING_PARENT = "1795231379619274846"

#: Latencies as measured on the live acquisition, in read order.
DANGLING_LATENCY_MS = (1915, 3074, 2169)


def local_evidence_for(post_id: str) -> dict[str, Any]:
    """One preserved response committed under ``raw/``, digested from disk.

    Nothing in these two files was sanitized — the acquisition recorded
    ``sanitization_removed: []`` for both — so the raw and sanitized digests are
    genuinely equal here, and both recompute from the committed bytes.
    """
    path = RAW / f"ylecun_convnets_{post_id}.json"
    text = path.read_text(encoding="utf-8")
    return {
        "route": "xcli_guest",
        "path": f"tests/fixtures/captures/raw/{path.name}",
        "sha256_raw": digest(text),
        "sha256_sanitized": digest(text),
        "sanitization_removed": [],
    }


def dangling_chain_capture() -> dict[str, Any]:
    """The PARTIAL that D-217's own test had no fixture for: a chain that dangles.

    Measured live over the tunnel rather than constructed, because the shape is
    a *claim about a provider* and constructing it would have meant recording a
    post as unavailable that measurement says is fine (D-221). Two `ylecun`
    posts walked from the last one; the walk stops because the parent above them
    is by another author, which ADR 0007 puts outside the MVP. So the first item
    keeps the ``parent_post_id`` that ``upward.unresolved_at`` names, and the
    root-first invariant's conditional branch finally has something to run on.

    The crossed parent's **bytes are never preserved** — ``_walk_upward`` stops
    before appending it, so it is not among the records ``_preserve_reads``
    walks. Only its id appears, in ``unresolved_at`` and in the omission's
    reason. The other author's content is not in this repository.
    """
    items = []
    evidence = []
    for post_id in DANGLING_CHAIN:
        record = json.loads(
            (RAW / f"ylecun_convnets_{post_id}.json").read_text(encoding="utf-8")
        )[0]
        items.append(post_from(record, GUEST, dict(UNVERIFIED)))
        evidence.append(local_evidence_for(post_id))
    # Read order is anchor first, then upward: the reverse of item order.
    read_order = (*reversed(DANGLING_CHAIN), DANGLING_PARENT)
    reads = [
        {
            **GUEST,
            "outcome": "ok",
            "request_shape": f"x tweet {post_id} --tier guest --no-cache -o json",
            "latency_ms": latency,
            "exit_code": 0,
        }
        for post_id, latency in zip(read_order, DANGLING_LATENCY_MS, strict=True)
    ]
    return {
        "schema_version": "1.0",
        "acquisition": {
            "provider": PROVIDER,
            "requested_at": DANGLING_REQUESTED_AT,
            "routes_read": reads,
            "network": NETWORK,
        },
        "raw_evidence": evidence,
        "anchor": {
            "post_id": DANGLING_CHAIN[-1],
            "role": "thread_terminal",
            "terminal_claim": "user_asserted",
        },
        "items": items,
        "order": {
            "basis": "parent_links",
            "note": "ordered by parent links, never by arrival order; the first item's "
                    "parent is unresolved, so this chain does not begin at a root",
        },
        "completeness": {
            "upward": {
                "status": "incomplete",
                "basis": "unresolved_hop",
                "single_author": True,
                "unresolved_at": DANGLING_PARENT,
            },
            # Neither direction is established, and the reason may not say
            # otherwise: keyed on the anchor's role alone this read "complete to
            # root" beside an `incomplete` status, which is what the live
            # measurement caught.
            "downward": {
                "status": "unprovable",
                "reason": "the chain above this anchor is not proven complete to a root, "
                          "and no credential-free route can enumerate descendants to "
                          "confirm the anchor is the thread's last post; neither direction "
                          "is established",
            },
        },
        "coverage": {
            "status": "PARTIAL",
            "expected_item_count": len(items) + 1,
            "included_post_ids": list(DANGLING_CHAIN),
            "omitted_items": [
                {
                    "post_id": DANGLING_PARENT,
                    "reason": "the parent is by another author; third-party replies are "
                              "outside the MVP scope (ADR 0007), so the walk stopped at "
                              "the self-thread's first post",
                }
            ],
        },
    }


def root_anchored_capture() -> dict[str, Any]:
    """The honest PARTIAL: anchored at a root, descendants unenumerable."""
    manifest = json.loads((RAW / "MANIFEST.json").read_text(encoding="utf-8"))
    root = manifest[0]
    record = json.loads(Path(root["path"]).read_text(encoding="utf-8"))[0]
    capture = {
        "schema_version": "1.0",
        "acquisition": {
            "provider": PROVIDER,
            "requested_at": REQUESTED_AT,
            "routes_read": [
                {**GUEST, "outcome": "ok",
                 "request_shape": f"x tweet {root['post_id']} --tier guest -o json"},
                {"route": "xcli_guest", "tier": 1, "surface": "guest_graphql",
                 "outcome": "ok", "request_shape": "x timeline NASA --tier guest -n 250 -o json"},
            ],
            "network": NETWORK,
        },
        "raw_evidence": [
            {
                "route": "xcli_guest",
                "path": root["path"],
                "sha256_raw": root["sha256_raw"],
                "sha256_sanitized": root["sha256_sanitized"],
                "sanitization_removed": root["sanitization_removed"],
            }
        ],
        "anchor": {
            "post_id": root["post_id"],
            "role": "thread_root",
            "terminal_claim": "none",
        },
        "items": [post_from(record, GUEST, dict(UNVERIFIED))],
        "order": {"basis": "parent_links", "note": "one item; the thread's root"},
        "completeness": {
            "upward": {"status": "complete", "basis": "root_reached", "single_author": True},
            "downward": {
                "status": "unprovable",
                "reason": "anchored at the root: x thread and x replies return the anchor "
                          "alone at every credential-free tier, and a 250-post author "
                          "archive held 3 of the 10 known members",
            },
        },
        "coverage": {
            "status": "PARTIAL",
            "expected_item_count": 1,
            "included_post_ids": [root["post_id"]],
            "omitted_items": [
                {
                    "descriptor": "descendants of the anchor",
                    "reason": "not enumerable at any credential-free tier; re-ingest from "
                              "the thread's last post to obtain them",
                }
            ],
        },
    }
    return capture


def truncated_capture() -> dict[str, Any]:
    """Tier 0 read of a long post: the truncation no field announces."""
    record, _ = read_spike("long_note_post_xl__xcli_t0")
    assert record is not None
    full, _ = read_spike("long_note_post_xl__xcli_guest")
    assert full is not None
    short = len(record["text"])
    complete = len(full["text"])
    capture = single_post_capture(
        "long_note_post_xl__xcli_t0",
        {
            "status": "known_truncated",
            "corroborated_by": [GUEST],
            "agreement": "disagree",
            "note": f"Tier 0 returned {short} of {complete} characters and carried no "
                    "is_note_tweet, truncated or note_tweet field; the loss is not "
                    "detectable from this response alone",
        },
    )
    capture["coverage"] = {
        "status": "PARTIAL",
        "expected_item_count": 1,
        "included_post_ids": [record["id"]],
        "omitted_items": [
            {
                "post_id": record["id"],
                "reason": f"text truncated by the acquiring surface: {short} of "
                          f"{complete} characters",
            }
        ],
    }
    return capture


def unavailable_capture() -> dict[str, Any]:
    """The FAIL: a well-formed reference that resolves to nothing."""
    ref = "999999999999999999"
    return {
        "schema_version": "1.0",
        "acquisition": {
            "provider": PROVIDER,
            "requested_at": REQUESTED_AT,
            "routes_read": [
                {**TIER0, "outcome": "not_found", "exit_code": 6,
                 "request_shape": f"x tweet {ref} --tier 0 -o json",
                 "error_text": "Tweet not found: 999999999999999999 (deleted, suspended, "
                               "or protected)."},
                {**GUEST, "outcome": "not_found", "exit_code": 6,
                 "request_shape": f"x tweet {ref} --tier guest -o json"},
                {**FX, "outcome": "not_found", "http_status": 404,
                 "request_shape": f"https://api.fxtwitter.com/i/status/{ref}"},
            ],
            "network": NETWORK,
        },
        "raw_evidence": [evidence_for("unavailable_post__fxtwitter", "fxtwitter")],
        "anchor": {"post_id": ref, "role": "single_post", "terminal_claim": "none"},
        "items": [
            {
                "post_id": ref,
                # No author, text, or timestamp: none was observed, and the schema
                # would rather carry an unavailable post than an invented one.
                "availability": {
                    "state": "unavailable",
                    "reason": "not_determinable_at_this_tier",
                },
            }
        ],
        "order": {"basis": "single_item"},
        "completeness": {
            "upward": {"status": "incomplete", "basis": "unresolved_hop", "unresolved_at": ref},
            "downward": {"status": "not_applicable", "reason": "nothing resolved to walk from"},
        },
        "coverage": {
            "status": "FAIL",
            "expected_item_count": 1,
            "included_post_ids": [],
            "omitted_items": [
                {
                    "post_id": ref,
                    "reason": "unavailable on all three routes; deleted, suspended and "
                              "protected are not distinguishable below Tier 2",
                }
            ],
        },
    }


FIXTURES = {
    "pass-single-post-en": lambda: single_post_capture(
        "single_post_en__xcli_guest",
        corroborated("identical"),
        ["single_post_en__fxtwitter"],
    ),
    "pass-single-post-fa": lambda: single_post_capture(
        "single_post_fa__xcli_guest",
        corroborated("identical", "Persian prose; ZWNJ and Persian digits identical on both routes"),
        ["single_post_fa__fxtwitter"],
    ),
    # T-227 asked for one more Persian case, and this is the one that carries a
    # span. `pass-single-post-fa` is 418 characters of unbroken RTL prose with
    # no entity at all, so nothing in it exercises an offset. This post ends in
    # an LTR run — a bare `t.co` link at [262, 285] — inside RTL text, which is
    # where a bidi-naive reading of an offset goes wrong and nowhere else. It is
    # also the only committed case whose media carries no `alt_text`: extraction
    # may not describe what the video shows.
    "pass-single-post-fa-video": lambda: single_post_capture(
        "video_post_fa__xcli_guest",
        corroborated(
            "identical",
            "Persian prose ending in an LTR t.co link; identical on both routes, "
            "and the URL span comes from the corroborating route (D-218)",
        ),
        ["video_post_fa__fxtwitter"],
    ),
    "pass-quote-post": lambda: single_post_capture(
        "quote_post__xcli_guest",
        corroborated("identical_url_normalized"),
        ["quote_post__fxtwitter"],
    ),
    "pass-media-alt-text": lambda: single_post_capture(
        "photo_with_alt__xcli_guest",
        corroborated("identical_url_normalized"),
        ["photo_with_alt__fxtwitter"],
    ),
    "pass-thread-terminal-anchor": thread_capture,
    "partial-thread-dangling-chain": dangling_chain_capture,
    "partial-thread-root-anchor": root_anchored_capture,
    "partial-tier0-truncated-text": truncated_capture,
    "fail-unavailable-post": unavailable_capture,
}


def main() -> int:
    for name, build in FIXTURES.items():
        path = HERE / f"{name}.json"
        path.write_text(
            json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  wrote {path.relative_to(HERE.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
