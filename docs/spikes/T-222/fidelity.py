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

    def fx_text(self, ref: str) -> str | None:
        request = urllib.request.Request(
            f"{FX_ORIGIN}/i/status/{ref}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return ((json.load(response) or {}).get("tweet") or {}).get("text")
        except Exception:  # noqa: BLE001 - an outage is a result, not a crash
            return None


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
        fx = fetch.fx_text(ref)
        verdict, reason = classify(tier0, guest, fx)
        entry = {
            "case": case["id"],
            "ref": ref,
            "why": case["why"],
            "verdict": verdict,
            "reason": reason,
            "lengths": {"tier0": len(tier0 or ""), "guest": len(guest or ""), "fxtwitter": len(fx or "")},
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
        "tier0_truncated": [e["case"] for e in report["comparisons"] if e["tier0_truncated"]],
    }
    (args.out / "fidelity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.out / 'fidelity.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
