#!/usr/bin/env python3
"""T-222 acquisition qualification harness.

Measures what each credential-free acquisition route actually returns from the
machine it is run on, and writes sanitized fixtures plus a verdict per matrix
cell. This is a spike instrument, not part of the product: it imports nothing
from `x2knwldg`, writes nothing into `output/`, and integrates no provider.

Three things are measured separately, because one does not imply the next:

  1. request success   — did the route answer at all
  2. field observation — did the answer carry the fields the case needs
  3. completeness      — for threads, is the post set provably whole

Usage:
    python3 qualify.py --xcli /path/to/x [--out .] [--rate 1.0] [--only ID,ID]

Exit status is 0 when every cell was measured, 1 when a cell could not be
measured, and 2 when the credential scan rejected a fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Anything matching these must never reach a committed fixture. The guest token
# is not an account credential, but it is still minted material and is redacted
# so a fixture can never be mistaken for one that carries it.
CREDENTIAL_PATTERNS = [
    (re.compile(r'"guest_token"\s*:\s*"[^"]+"'), '"guest_token":"<REDACTED>"'),
    (re.compile(r"(auth_token|ct0|kdt|twid)=[^&\s\"';]+"), r"\1=<REDACTED>"),
    (re.compile(r"[Bb]earer\s+[A-Za-z0-9%_\-.]{20,}"), "Bearer <REDACTED>"),
]
# The syndication surface takes a `token` derived from the post id. It is not a
# credential and x-cli recomputes it, but it is stripped so no fixture carries a
# request token of any kind. The separator has to allow `&` as well as a
# literal `&`: x-cli's JSON escapes the ampersand, which a `[?&]`-only pattern
# walks straight past, and it did until this was measured.
TOKEN_IN_URL = re.compile(r"((?:[?&]|\\u0026)token=)[^&\"'\s\\]+")

USER_AGENT = "x2knwldg-T222-spike/1.0 (acquisition qualification)"
FX_ORIGIN = "https://api.fxtwitter.com"
OEMBED_ORIGIN = "https://publish.x.com"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize(text: str) -> tuple[str, list[str]]:
    """Redact credential-shaped material. Returns the text and what was hit."""
    removed: list[str] = []
    for pattern, replacement in CREDENTIAL_PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            removed.append(f"{pattern.pattern} x{n}")
    text, n = TOKEN_IN_URL.subn(r"\1<STRIPPED>", text)
    if n:
        removed.append(f"syndication request token in url x{n}")
    return text, removed


def scan_for_credentials(text: str) -> list[str]:
    """Second pass, after sanitization: anything left is a hard stop."""
    hits = []
    for pattern, _ in CREDENTIAL_PATTERNS:
        for match in pattern.finditer(text):
            if "<REDACTED>" not in match.group(0):
                hits.append(match.group(0)[:40])
    for match in TOKEN_IN_URL.finditer(text):
        if "<STRIPPED>" not in match.group(0):
            hits.append(match.group(0)[:40])
    return hits


class Runner:
    def __init__(self, xcli: Path, rate: float) -> None:
        self.xcli = xcli
        self.rate = rate
        self._last = 0.0

    def _pace(self) -> None:
        wait = self.rate - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def xcli_run(self, args: list[str]) -> dict[str, Any]:
        self._pace()
        cmd = [str(self.xcli), *args]
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "harness timeout after 120s", -1
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "transport": "subprocess",
            # The binary path is the harness's, not evidence; the argv shape is.
            "command": ["x", *args],
            "exit": code,
            "latency_ms": elapsed,
            "stdout": out,
            "stderr": err.strip(),
        }

    def http_get(self, url: str) -> dict[str, Any]:
        self._pace()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        started = time.monotonic()
        status, body, error = 0, b"", ""
        final_url = url
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                body = response.read()
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read()
        except Exception as exc:  # noqa: BLE001 - an outage is a result here
            error = f"{type(exc).__name__}: {exc}"
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "transport": "https",
            "command": url,
            "http_status": status,
            "final_url": final_url,
            "cross_origin_redirect": not final_url.startswith(url.split("/status/")[0]),
            "latency_ms": elapsed,
            "stdout": body.decode("utf-8", "replace"),
            "stderr": error,
            "exit": 0 if status == 200 else 1,
        }


def parse_xcli(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed[0] if parsed else None
    return parsed if isinstance(parsed, dict) else None


def observe_xcli(post: dict[str, Any] | None) -> set[str]:
    """Turn one x-cli record into the set of expectation names it satisfies."""
    if not post:
        return set()
    seen: set[str] = set()
    text = post.get("text") or ""
    if text:
        seen.add("text")
    if post.get("created_at"):
        seen.add("created_at")
    if (post.get("author") or {}).get("username"):
        seen.add("author")
    if post.get("lang"):
        seen.add("lang")
    if post.get("lang") == "fa":
        seen.add("lang_is_fa")
    if any("؀" <= ch <= "ۿ" for ch in text):
        seen.add("rtl_text")
    if post.get("reply_to"):
        seen.add("parent_ref")
    else:
        seen.add("is_root")
    quoted = post.get("quoted") or {}
    if quoted.get("id"):
        seen.add("quoted_ref")
    if (quoted.get("author") or {}).get("username"):
        seen.add("quoted_author")
    if len(text) >= 521:
        seen.add("full_text_521")
    for medium in post.get("media") or []:
        kind = medium.get("type")
        if kind == "photo":
            seen.add("media_photo")
        if kind == "video":
            seen.add("media_video")
        if kind == "animated_gif":
            seen.add("media_gif")
        if medium.get("alt_text"):
            seen.add("media_alt_text")
        if medium.get("variants"):
            seen.add("media_variants")
    return seen


def observe_fx(raw: str) -> set[str]:
    try:
        post = (json.loads(raw) or {}).get("tweet") or {}
    except json.JSONDecodeError:
        return set()
    if not post:
        return set()
    seen: set[str] = set()
    text = post.get("text") or ""
    if text:
        seen.add("text")
    if post.get("created_at"):
        seen.add("created_at")
    if (post.get("author") or {}).get("screen_name"):
        seen.add("author")
    if post.get("lang"):
        seen.add("lang")
    if post.get("lang") == "fa":
        seen.add("lang_is_fa")
    if any("؀" <= ch <= "ۿ" for ch in text):
        seen.add("rtl_text")
    if post.get("replying_to"):
        seen.add("parent_ref")
    else:
        seen.add("is_root")
    quoted = post.get("quote") or {}
    if quoted.get("id"):
        seen.add("quoted_ref")
    if (quoted.get("author") or {}).get("screen_name"):
        seen.add("quoted_author")
    if len(text) >= 521:
        seen.add("full_text_521")
    media = post.get("media") or {}
    for medium in media.get("all") or []:
        kind = medium.get("type")
        if kind == "photo":
            seen.add("media_photo")
        if kind in {"video", "gif"}:
            seen.add("media_video" if kind == "video" else "media_gif")
        if medium.get("altText"):
            seen.add("media_alt_text")
        if medium.get("variants"):
            seen.add("media_variants")
    return seen


def observe_oembed(raw: str) -> set[str]:
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    seen: set[str] = set()
    html = doc.get("html") or ""
    if html:
        seen.add("text")
    if doc.get("author_name"):
        seen.add("author")
    if 'dir="rtl"' in html:
        seen.add("rtl_text")
    if 'lang="fa"' in html:
        seen.add("lang_is_fa")
    if 'lang="' in html:
        seen.add("lang")
    return seen


ROUTES = {
    "xcli_t0": {
        "label": "x-cli Tier 0 (X public surfaces, no token at all)",
        "third_party": False,
    },
    "xcli_guest": {
        "label": "x-cli Tier 1 (anonymous guest token, no account)",
        "third_party": False,
    },
    "fxtwitter": {
        "label": "FxTwitter (third party; discloses the post id)",
        "third_party": True,
    },
    "oembed": {
        "label": "Official X oEmbed (corroboration only)",
        "third_party": False,
    },
}


def probe(runner: Runner, route: str, ref: str) -> dict[str, Any]:
    if route == "xcli_t0":
        result = runner.xcli_run(["tweet", ref, "--tier", "0", "--no-cache", "-o", "json"])
        result["observed"] = sorted(observe_xcli(parse_xcli(result["stdout"])))
    elif route == "xcli_guest":
        result = runner.xcli_run(["tweet", ref, "--tier", "guest", "--no-cache", "-o", "json"])
        result["observed"] = sorted(observe_xcli(parse_xcli(result["stdout"])))
    elif route == "fxtwitter":
        result = runner.http_get(f"{FX_ORIGIN}/i/status/{ref}")
        result["observed"] = sorted(observe_fx(result["stdout"]))
    else:
        url = f"{OEMBED_ORIGIN}/oembed?url=https://x.com/i/status/{ref}"
        result = runner.http_get(url)
        result["observed"] = sorted(observe_oembed(result["stdout"]))
    return result


def verdict_for(case: dict[str, Any], result: dict[str, Any], route: str) -> tuple[str, str]:
    expected = set(case.get("expect", []))
    observed = set(result.get("observed", []))
    answered = result["exit"] == 0 and bool(observed)
    if not answered:
        detail = result["stderr"] or f"exit={result['exit']}"
        if route == "oembed":
            return "NOT_SUPPORTED", f"oEmbed returns embed HTML only; {detail[:70]}"
        return "FAIL", f"route did not answer: {detail[:90]}"
    missing = sorted(expected - observed)
    if not missing:
        return "PASS", f"answered and carried all {len(expected)} expected fields"
    if route == "oembed":
        return "PARTIAL", f"corroborates author/text; cannot carry {', '.join(missing)}"
    return "PARTIAL", f"answered but missing {', '.join(missing)}"


def verdict_for_failure(result: dict[str, Any], route: str) -> tuple[str, str]:
    """A failure case passes when the route refuses honestly."""
    fabricated = bool(result.get("observed"))
    if fabricated:
        return "FAIL", "route returned a record for material that does not resolve"
    if route.startswith("xcli"):
        if result["exit"] in (1, 6):
            return "PASS", f"refused with exit {result['exit']}: {result['stderr'][:70]}"
        return "PARTIAL", f"refused, but with exit {result['exit']} (expected 1 or 6)"
    status = result.get("http_status")
    if status in (404, 400) or result["stderr"]:
        return "PASS", f"refused with http {status}, no record fabricated"
    body = result.get("body_head", "")
    if status == 200 and body.lstrip().startswith("<"):
        return "PARTIAL", (
            f"http {status} with an HTML body, not JSON: a consumer that trusts "
            "the status code sees success where there is no record"
        )
    return "PARTIAL", f"http {status} without a record; outcome is not explicit"


def walk_up(runner: Runner, anchor: str, tier: str) -> dict[str, Any]:
    """Follow reply_to upward. Completeness is proven only by reaching a root."""
    chain: list[dict[str, Any]] = []
    current: str | None = anchor
    hops = 0
    unresolved: str | None = None
    while current and hops < 30:
        result = runner.xcli_run(["tweet", current, "--tier", tier, "--no-cache", "-o", "json"])
        post = parse_xcli(result["stdout"]) if result["exit"] == 0 else None
        if not post:
            unresolved = current
            break
        chain.append(
            {
                "id": post["id"],
                "author": (post.get("author") or {}).get("username"),
                "parent": post.get("reply_to"),
                "chars": len(post.get("text") or ""),
            }
        )
        current = post.get("reply_to")
        hops += 1
    authors = {link["author"] for link in chain}
    reached_root = bool(chain) and chain[-1]["parent"] is None
    return {
        "anchor": anchor,
        "tier": tier,
        "chain_root_last": [link["id"] for link in chain],
        "length": len(chain),
        "reached_root": reached_root,
        "unresolved_at": unresolved,
        "single_author": len(authors) == 1,
        "authors": sorted(a for a in authors if a),
        "ordering": "derived from parent links, not from arrival order",
    }


RATE_LIMITED_EXIT = 5
_ARCHIVE_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


def fetch_archive(runner: Runner, author: str, depth: int) -> dict[str, Any]:
    """One archive read per author per run.

    Every anchor of a thread interrogates the same author archive, so asking
    once is both cheaper and the only way to keep three anchors from spending
    the UserTweets budget and turning a rate limit into a capability verdict.
    """
    key = (author, depth)
    if key in _ARCHIVE_CACHE:
        return _ARCHIVE_CACHE[key]
    result = runner.xcli_run(
        ["timeline", author, "--tier", "guest", "--no-cache", "-n", str(depth), "-o", "json"]
    )
    try:
        posts = json.loads(result["stdout"])
    except json.JSONDecodeError:
        posts = []
    entry = {
        "ids": {post["id"] for post in posts} if isinstance(posts, list) else set(),
        "exit": result["exit"],
        "stderr": result["stderr"],
    }
    _ARCHIVE_CACHE[key] = entry
    return entry


def archive_downward(runner: Runner, author: str, chain: list[str], depth: int) -> dict[str, Any]:
    """Try to discover the same thread from the author's own archive."""
    archive = fetch_archive(runner, author, depth)
    found = [ref for ref in chain if ref in archive["ids"]]
    rate_limited = archive["exit"] == RATE_LIMITED_EXIT
    return {
        "author": author,
        "archive_requested": depth,
        "archive_returned": len(archive["ids"]),
        "chain_members_found": len(found),
        "chain_members_total": len(chain),
        "found": found,
        "exit": archive["exit"],
        # A transport failure is not evidence about what the archive contains.
        "measured": not rate_limited and archive["exit"] == 0,
        "transport_note": archive["stderr"][:160] if archive["exit"] else "",
    }


def write_fixture(out_dir: Path, name: str, result: dict[str, Any]) -> dict[str, Any]:
    raw = result.pop("stdout")
    # Kept so a verdict can still say what shape the body had once the bytes
    # have moved to the fixture.
    result["body_head"] = raw[:200]
    raw_digest = sha256(raw.encode("utf-8"))
    clean, removed = sanitize(raw)
    leaks = scan_for_credentials(clean)
    path = out_dir / f"{name}.txt"
    path.write_text(clean, encoding="utf-8")
    return {
        "fixture": path.name,
        "bytes": len(clean.encode("utf-8")),
        "sha256_sanitized": sha256(clean.encode("utf-8")),
        "sha256_raw_before_sanitization": raw_digest,
        "sanitization_removed": removed or ["nothing matched"],
        "credential_scan": "clean" if not leaks else leaks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="T-222 acquisition qualification")
    parser.add_argument("--xcli", required=True, type=Path, help="path to the pinned x binary")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    parser.add_argument("--rate", type=float, default=1.0, help="min seconds between requests")
    parser.add_argument("--only", default="", help="comma-separated case ids")
    args = parser.parse_args()

    spec = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    fixtures = args.out / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    runner = Runner(args.xcli, args.rate)

    wanted = {c.strip() for c in args.only.split(",") if c.strip()}
    version = runner.xcli_run(["version"])["stdout"].strip()
    binary_digest = sha256(args.xcli.read_bytes())

    report: dict[str, Any] = {
        "task": "T-222",
        "generated_by": "docs/spikes/T-222/qualify.py",
        "provider": {
            "tool": "tamnd/x-cli",
            "pinned_release": "v0.5.0",
            "version_string": version,
            "binary_sha256": binary_digest,
            "licence": "AGPL-3.0",
        },
        "routes": ROUTES,
        "cells": [],
        "threads": [],
        "credential_scan": "clean",
    }

    problems = 0
    leaked = 0
    all_cases = [(c, False) for c in spec["mvp_cases"]] + [
        (c, True) for c in spec["failure_cases"]
    ]

    for case, is_failure in all_cases:
        if wanted and case["id"] not in wanted:
            continue
        for route in ROUTES:
            result = probe(runner, route, case["ref"])
            evidence = write_fixture(fixtures, f"{case['id']}__{route}", result)
            if evidence["credential_scan"] != "clean":
                leaked += 1
            if is_failure:
                status, reason = verdict_for_failure(result, route)
            else:
                status, reason = verdict_for(case, result, route)
            if status == "FAIL":
                problems += 1
            report["cells"].append(
                {
                    "case": case["id"],
                    "ref": case["ref"],
                    "route": route,
                    "verdict": status,
                    "reason": reason,
                    "request": {
                        k: v
                        for k, v in result.items()
                        if k in {"command", "exit", "http_status", "latency_ms", "stderr",
                                 "final_url", "cross_origin_redirect"}
                    },
                    "observed": result["observed"],
                    "expected": case.get("expect", []),
                    "evidence": evidence,
                }
            )
            print(f"  {case['id']:22s} {route:12s} {status:14s} {reason[:60]}")

    thread_cases = [
        case
        for case in spec["mvp_cases"]
        if case.get("thread") and not (wanted and case["id"] not in wanted)
    ]
    # The true extent of a thread is established once, from its deepest known
    # anchor. Judging an anchor's downward reach against the chain that same
    # anchor produced would score the root anchor 1-of-1 and call the thread
    # complete, which is the false success this whole task exists to prevent.
    canonical: dict[str, list[str]] = {}
    for case in thread_cases:
        if case["thread"].get("deepest_known_anchor"):
            deepest = walk_up(runner, case["ref"], "0")
            canonical[case["thread"]["key"]] = deepest["chain_root_last"]
            report["canonical_threads"] = report.get("canonical_threads", {})
            report["canonical_threads"][case["thread"]["key"]] = {
                "established_from": case["id"],
                "anchor_ref": case["ref"],
                "members_root_last": list(reversed(deepest["chain_root_last"])),
                "length": deepest["length"],
                "reached_root": deepest["reached_root"],
                "single_author": deepest["single_author"],
            }

    for case in thread_cases:
        thread = case["thread"]
        up = walk_up(runner, case["ref"], "0")
        if not up["reached_root"]:
            status = "FAIL"
            reason = f"never reached a root; unresolved at {up['unresolved_at']}"
        elif not up["single_author"]:
            status = "PARTIAL"
            reason = f"reached a root but crossed authors: {up['authors']}"
        else:
            status = "PASS"
            reason = (
                f"walked {up['length']} post(s) from this anchor to a root with "
                "no parent, all by one author"
            )
        whole = canonical.get(thread["key"]) or up["chain_root_last"]
        down = archive_downward(runner, thread["author"], whole, 250)
        missing = down["chain_members_total"] - down["chain_members_found"]
        if not down["measured"]:
            down_status = "PARTIAL"
            down_reason = (
                "not measured in this run: the archive read did not complete "
                f"({down['transport_note'] or 'exit ' + str(down['exit'])}). "
                "A transport failure says nothing about what the archive holds"
            )
        elif missing == 0:
            down_status = "PASS"
            down_reason = "archive held every member of the whole thread"
        elif down["chain_members_found"] > 0:
            down_status = "PARTIAL"
            down_reason = (
                f"archive held {down['chain_members_found']} of "
                f"{down['chain_members_total']} members of the whole thread, so "
                f"{missing} would be silently absent"
            )
        else:
            down_status = "FAIL"
            down_reason = "archive held no member of the whole thread"
        report["threads"].append(
            {
                "case": case["id"],
                "anchor_role": thread["role"],
                "measured_against_whole_thread": len(whole),
                "upward": {"verdict": status, "reason": reason, **up},
                "downward": {"verdict": down_status, "reason": down_reason, **down},
            }
        )
        print(f"  {case['id']:22s} thread-up    {status:14s} {reason[:60]}")
        print(f"  {case['id']:22s} thread-down  {down_status:14s} {down_reason[:60]}")

    report["not_located"] = spec["not_located"]
    if leaked:
        report["credential_scan"] = f"{leaked} fixture(s) still matched after sanitization"
    (args.out / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.out / 'results.json'} ({len(report['cells'])} cells)")
    if leaked:
        print("CREDENTIAL SCAN FAILED", file=sys.stderr)
        return 2
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
