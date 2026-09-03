#!/usr/bin/env python3
"""T-222 addendum — Persian/RTL text fidelity across the acquisition routes.

The capability matrix in `qualify.py` scores each route against each case
independently. It cannot see a class of problem that only appears when two
routes are compared: whether they return the *same characters* for the same
post. That matters twice over for this project.

  1. A source claim cites a post id plus an exact text span. If two routes
     disagree about the text, a span recorded from one does not resolve
     against the other, and the locator silently points at the wrong words.
  2. Persian carries codepoints that normalization loves to damage — ZWNJ,
     the Persian/Arabic ye and kaf pairs, three digit systems, bidi controls.
     A route that quietly folds any of them corrupts the corpus.
  3. A provider's own entity spans may index codepoints or UTF-16 units. The
     two agree across all of Persian and diverge after the first emoji, so the
     basis has to be measured against astral text, not assumed.

Stdlib only; imports nothing from `x2knwldg`; integrates no provider.

Usage:
    python3 fidelity.py --xcli /path/to/x [--out .]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "x2knwldg-T222-spike/1.0 (text fidelity)"
FX_ORIGIN = "https://api.fxtwitter.com"
URL_TOKEN = re.compile(r"https?://\S+")

# Codepoints whose survival is the whole question. Named so a report can say
# which one moved rather than "the text differs".
MARKERS = {
    "ZWNJ U+200C": "‌",
    "persian_ye U+06CC": "ی",
    "arabic_ye U+064A": "ي",
    "persian_keheh U+06A9": "ک",
    "arabic_kaf U+0643": "ك",
    "RLM U+200F": "‏",
    "LRM U+200E": "‎",
    "RLE U+202B": "‫",
    "PDF U+202C": "‬",
    "RLI U+2067": "⁧",
}


def inventory(text: str) -> list[str]:
    found = {name for name, ch in MARKERS.items() if ch in text}
    if any("۰" <= c <= "۹" for c in text):
        found.add("persian_digits U+06F0-9")
    if any("٠" <= c <= "٩" for c in text):
        found.add("arabic_indic_digits U+0660-9")
    if any(c.isascii() and c.isdigit() for c in text):
        found.add("ascii_digits")
    return sorted(found)


def first_difference(left: str, right: str) -> dict[str, Any] | None:
    # strict=False on purpose: unequal lengths are a result here, handled below.
    for index, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return {
                "index": index,
                "left": a,
                "left_codepoint": f"U+{ord(a):04X}",
                "right": b,
                "right_codepoint": f"U+{ord(b):04X}",
            }
    if len(left) != len(right):
        return {
            "index": min(len(left), len(right)),
            "note": "one is a prefix of the other",
            "length_delta": len(left) - len(right),
        }
    return None


def strip_urls(text: str) -> str:
    """Normalize away the one thing the routes legitimately disagree about."""
    return URL_TOKEN.sub("", text).strip()


class Fetch:
    def __init__(self, xcli: Path) -> None:
        self.xcli = xcli

    def xcli_text(self, ref: str, tier: str) -> str | None:
        proc = subprocess.run(
            [str(self.xcli), "tweet", ref, "--tier", tier, "--no-cache", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return None
        try:
            return json.loads(proc.stdout)[0].get("text")
        except (json.JSONDecodeError, IndexError, KeyError):
            return None

    def fx_post(self, ref: str) -> dict[str, Any] | None:
        request = urllib.request.Request(
            f"{FX_ORIGIN}/i/status/{ref}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return (json.load(response) or {}).get("tweet") or {}
        except Exception:  # noqa: BLE001 - an outage is a result, not a crash
            return None


def facet_alignment(post: dict[str, Any]) -> dict[str, Any]:
    """Do the provider's entity spans index codepoints or UTF-16 units?

    The difference is invisible in Persian, which is all BMP, and corrupts every
    span after the first emoji. Measured rather than assumed: an astral
    character makes the two readings disagree, and only one of them slices the
    authored link back out.
    """
    raw = post.get("raw_text") or {}
    text = raw.get("text") or ""
    checks = []
    encoded = text.encode("utf-16-le")
    for facet in raw.get("facets") or []:
        start, end = facet.get("indices", [0, 0])
        original = facet.get("original")
        by_codepoint = text[start:end] == original
        by_utf16 = encoded[start * 2 : end * 2].decode("utf-16-le", "replace") == original
        checks.append(
            {
                "type": facet.get("type"),
                "indices": [start, end],
                "codepoint_aligned": by_codepoint,
                "utf16_aligned": by_utf16,
            }
        )
    return {
        "astral_characters": sorted({c for c in text if ord(c) > 0xFFFF}),
        "facets": checks,
        "basis": (
            "not_exercised"
            if not checks
            else "codepoints"
            if all(c["codepoint_aligned"] for c in checks)
            else "utf-16"
            if all(c["utf16_aligned"] for c in checks)
            else "inconsistent"
        ),
    }


def classify(tier0: str | None, guest: str | None, fx: str | None) -> tuple[str, str]:
    if guest is None:
        return "FAIL", "the default route returned no text"
    truncated = tier0 is not None and len(tier0) < len(guest)
    if fx is None:
        return "PARTIAL", "no third-party reading available to corroborate against"
    if guest == fx:
        base = "PASS"
        reason = "the two independent routes returned identical characters"
    elif strip_urls(guest) == strip_urls(fx):
        base = "PASS"
        reason = (
            "identical once URLs are normalized away; the routes disagree only "
            "about link representation, not about the authored text"
        )
    else:
        base = "PARTIAL"
        reason = "the routes disagree on the authored text, not merely on links"
    if truncated:
        reason += f"; Tier 0 returned {len(tier0)} of {len(guest)} characters"
    return base, reason


def main() -> int:
    parser = argparse.ArgumentParser(description="T-222 Persian/RTL text fidelity")
    parser.add_argument("--xcli", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    spec = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    cases = spec["text_fidelity_cases"]
    fetch = Fetch(args.xcli)

    report: dict[str, Any] = {
        "task": "T-222",
        "addendum": "Persian/RTL text fidelity across routes",
        "generated_by": "docs/spikes/T-222/fidelity.py",
        "why": (
            "A locator cites an exact text span. If two routes disagree about the "
            "characters, a span recorded from one silently misresolves against the "
            "other. Measured rather than assumed."
        ),
        "comparisons": [],
    }

    for case in cases:
        ref = case["ref"]
        tier0 = fetch.xcli_text(ref, "0")
        guest = fetch.xcli_text(ref, "guest")
        post = fetch.fx_post(ref) or {}
        # `tweet.text` is a RENDERED form: links expanded, a trailing media link
        # dropped. `raw_text.text` is the authored form, which is what a locator
        # span must index. Comparing the rendered field is what made the routes
        # look like they disagreed about Persian text; they do not.
        fx = ((post.get("raw_text") or {}).get("text")) or None
        fx_rendered = post.get("text") or None
        verdict, reason = classify(tier0, guest, fx)
        entry = {
            "case": case["id"],
            "ref": ref,
            "why": case["why"],
            "verdict": verdict,
            "reason": reason,
            "lengths": {
                "tier0": len(tier0 or ""),
                "guest": len(guest or ""),
                "fxtwitter_authored": len(fx or ""),
                "fxtwitter_rendered": len(fx_rendered or ""),
            },
            "authored_vs_rendered_differ": (fx or "") != (fx_rendered or ""),
            "entity_span_basis": facet_alignment(post),
            "identical_raw": {"guest_vs_fx": guest == fx, "tier0_vs_guest": tier0 == guest},
            "identical_url_normalized": {
                "guest_vs_fx": strip_urls(guest or "") == strip_urls(fx or "")
            },
            "codepoints_present": inventory(guest or ""),
            "codepoints_agree_guest_vs_fx": inventory(guest or "") == inventory(fx or ""),
            # The comparison that answers the actual question. Comparing raw
            # inventories reports a false disagreement whenever one route strips
            # a URL, because the ASCII digits inside a t.co slug vanish with it.
            "codepoints_agree_url_normalized": (
                inventory(strip_urls(guest or "")) == inventory(strip_urls(fx or ""))
            ),
            "first_difference_guest_vs_fx": first_difference(guest or "", fx or ""),
            "tier0_truncated": bool(tier0 is not None and guest and len(tier0) < len(guest)),
        }
        report["comparisons"].append(entry)
        print(f"  {case['id']:26s} {verdict:8s} {reason[:78]}")

    marks: set[str] = set()
    damaged = []
    url_artifact = []
    for entry in report["comparisons"]:
        marks.update(entry["codepoints_present"])
        if not entry["codepoints_agree_url_normalized"]:
            damaged.append(entry["case"])
        elif not entry["codepoints_agree_guest_vs_fx"]:
            url_artifact.append(entry["case"])
    report["summary"] = {
        "codepoint_classes_exercised": sorted(marks),
        "cases_with_real_codepoint_damage": damaged,
        "cases_whose_inventory_gap_is_only_a_stripped_url": url_artifact,
        "url_representation_differs": [
            e["case"]
            for e in report["comparisons"]
            if not e["identical_raw"]["guest_vs_fx"]
            and e["identical_url_normalized"]["guest_vs_fx"]
        ],
        "authored_text_identical_across_routes": [
            e["case"] for e in report["comparisons"] if e["identical_raw"]["guest_vs_fx"]
        ],
        "entity_span_basis": sorted(
            {e["entity_span_basis"]["basis"] for e in report["comparisons"]}
        ),
        "cases_with_astral_characters": [
            e["case"] for e in report["comparisons"] if e["entity_span_basis"]["astral_characters"]
        ],
        "tier0_truncated": [e["case"] for e in report["comparisons"] if e["tier0_truncated"]],
    }
    (args.out / "fidelity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.out / 'fidelity.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
