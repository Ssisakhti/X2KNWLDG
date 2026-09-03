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
