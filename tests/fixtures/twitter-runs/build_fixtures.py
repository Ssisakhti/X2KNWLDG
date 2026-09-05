"""Regenerate the labelled Twitter run fixtures in this directory (T-227).

    .venv/bin/python tests/fixtures/twitter-runs/build_fixtures.py

The eight cases §11 of ``docs/PROJECT_MANAGEMENT.md`` planned, each a **run
directory** — the input ``capture.json`` and its ``raw/`` evidence beside the
canonical extraction outputs — and each built by driving the real extraction
code: ``initialize_run``, then ``apply_extraction_bundle``, then
``validate_run``. Hand-written expected JSON is what lets a fixture drift from
what the code actually writes (``T-006``, D-157), so nothing here is written by
hand except the bundle a model would have produced.

This directory **is the output root**, and ``tests/fixtures/`` is the project
root the runs are expressed against — so a capture here records its evidence as
``twitter-runs/<case>/raw/<file>``. That is not decoration:
``extract.evidence_integrity`` resolves a capture's recorded paths against
``run_dir.parent.parent``, one rule with no parameter for "where the project
root is", because a second root-resolution rule is what D-039 removed. A run one
level deeper — under an ``output/`` directory of its own, the way a real run
sits — would also have been ignored by git, since ``.gitignore`` excludes
``output/`` at any depth to keep real evidence out of the repository. Both
pressures point the same way, and the layout is the one ``tests/fixtures/runs/``
already uses: the builder, the README and the cases side by side.

**The captures are the committed ones, re-homed and not rewritten.** Each case's
input is a capture from ``tests/fixtures/captures/`` (or, for the edit case, the
shape ``capture_shapes`` constructs, because no measured route produces one —
D-222). The same measured bytes are copied into the run's own ``raw/`` and each
``raw_evidence`` entry gets the new path; every digest is carried from the
committed entry and then **re-verified against the copied file**, so a re-homed
capture that no longer describes its evidence fails the build rather than
shipping. ``sha256_raw`` is carried rather than recomputed: it is a claim about
the bytes the provider returned *before* sanitization, and those bytes were
never committed — one entry (`long_note_post_xl__xcli_t0`) had a syndication
token removed from it.

Every run carries ``"fixture": true`` and a ``fixture_note`` in its
``metadata.json``. The capture cannot carry that marker — the contract's root is
``additionalProperties: false`` — which is stated at greater length in
``tests/capture_shapes.py``.

What the units say is **mechanical and says so**: each available post yields one
`quote` unit whose content is the post's own opening, cited by the span it was
taken from. A fixture's job here is to pin the *shape* the pipeline writes and
the provenance rules it enforces; inventing analytical claims about real posts
would put words in real authors' mouths in a file that is committed forever.

**One case is constructed rather than measured, and says which.** ``facets``
reads its two responses from ``inputs/`` and neither is a recording: they are
written for this fixture, under a synthetic account and a post id no snowflake
has reached, for the reason D-222 already applies to ``edit`` — no measured
route produces the shape, so it is pinned by a fixture instead of by data. What
it pins is :func:`x2knwldg.twitter.normalize.entities_from`, the single place
CLAUDE.md's X-provenance invariant is enforced on a span, and which until this
directory had it had **never executed under test**: no committed x-cli response
carries a facet — the five ``__xcli_guest`` spike files all report ``facets:
0`` — so the loop that re-slices every span and drops the ones that do not
match was uncovered while its own docstring claimed it had been "proven against
a post carrying astral emoji". The response here carries three facets and its
text carries two astral characters, so the two readings of the same link differ
by exactly the two code units D-211 measured: the codepoint span survives, the
UTF-16 span slices to ``tps://t.co/… —`` and is dropped, and the committed
capture is the difference between them.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FIXTURE_DIR.parents[2]
#: The runs sit directly in this directory; `tests/fixtures/` is their root.
OUTPUT_ROOT = FIXTURE_DIR
EVIDENCE_ROOT = FIXTURE_DIR.parent
CAPTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "captures"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from capture_shapes import edited_post_capture  # noqa: E402

from x2knwldg.io import dumps_json, sha256_text, write_json  # noqa: E402
from x2knwldg.twitter import acquire, evidence, extract  # noqa: E402
from x2knwldg.twitter.normalize import post_from  # noqa: E402

# Frozen so regenerating the fixtures is byte-identical and CI can prove it.
# Obviously not a real ingestion time, and deliberately the same value the
# YouTube run fixtures carry.
FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"

FIXTURE_NOTE = (
    "Synthetic test fixture — the capture and its raw evidence are real measured "
    "bytes, the knowledge units are mechanical quotations built for this file. "
    "Regenerate with tests/fixtures/twitter-runs/build_fixtures.py."
)

#: For a case whose *responses* were written rather than recorded. The first
#: clause of the note above is a claim about provenance, and it would be false
#: here — a fixture that mislabels its own evidence is the one thing this
#: directory cannot afford, since every other file in it is trusted precisely
#: because that sentence is true.
CONSTRUCTED_NOTE = (
    "Synthetic test fixture — the provider responses under raw/ were WRITTEN FOR "
    "THIS FIXTURE, not recorded: a synthetic account, a post id no snowflake has "
    "reached, and a facet list carrying one deliberately wrong offset. Nothing "
    "here is a claim about a real post or a real provider answer. Regenerate "
    "with tests/fixtures/twitter-runs/build_fixtures.py."
)

EXTRACTION_METADATA = {
    "model": "none — mechanical fixture extraction",
    "fixture": True,
    "note": "One quote unit per available post, cited by the span it was taken from.",
}

#: Case name, the capture it is built from, and what the case exists to prevent.
#: The table is §11's, in its order, and the notes are carried here because a
#: reader of the fixture directory should not have to find the plan to know why
#: a case is in it.
CASES: tuple[tuple[str, str, str], ...] = (
    (
        "single-post",
        "pass-single-post-en",
        "The baseline: a claim carrying a post id, a codepoint span and an "
        "excerpt that re-slices exactly.",
    ),
    (
        "persian-rtl",
        "pass-single-post-fa",
        "418 characters carrying ZWNJ, Persian digits, a NBSP and paragraph "
        "breaks. Any normalization on the excerpt path breaks the re-slice here.",
    ),
    (
        "persian-rtl-ltr-run",
        "pass-single-post-fa-video",
        "The bidi case with an embedded LTR t.co link, and media with no "
        "alt_text: extraction must not claim to know what the video shows.",
    ),
    (
        "self-thread",
        "pass-thread-terminal-anchor",
        "Root-first over ten items from parent_links, first item with no "
        "parent_post_id. Order derived from parent links, never arrival order.",
    ),
    (
        "partial-thread",
        "partial-thread-dangling-chain",
        "A truncated chain must not present itself as though it began at a "
        "root. Also the tombstone-inside-a-thread shape.",
    ),
    (
        "edit",
        None,
        "An edit history read as content, or the prior ids fetched. Extraction "
        "cites text.canonical only and names them omitted.",
    ),
    (
        "tombstone",
        "fail-unavailable-post",
        "Zero source claims and nothing invented from an item with no author, "
        "timestamp or text — and FAIL surviving into the canonical outputs.",
    ),
    (
        "quote",
        "pass-quote-post",
        "A quoted post becoming embedded content or a fetch. It is a separate "
        "cited source relation (ADR 0007 decision 8).",
    ),
    (
        "facets",
        None,
        "A span written from an offset nobody re-sliced. Three facets go in and "
        "two come out: the UTF-16 reading of the same link is in bounds, is "
        "wrong, and must be dropped — and @x2k must not be located inside "
        "@x2knwldg.",
    ),
)

#: Where the two constructed responses for the ``facets`` case live. Outside
#: any run directory on purpose: :func:`build` deletes a run before rebuilding
#: it, and an input stored inside its own output is an input that survives
#: exactly one run of the builder.
INPUT_DIR = FIXTURE_DIR / "inputs"

#: The route the constructed responses are attributed to. Tier 1 for the x-cli
#: record, and the corroborating surface for the document that carries the
#: facets — because that is where a facet comes from (D-218, ``T-225``), and
#: attributing it to the local route would be a claim about x-cli that the five
#: committed ``__xcli_guest`` responses contradict.
_GUEST = {"route": "xcli_guest", "tier": 1, "surface": "guest_graphql"}
_FX = {"route": "fxtwitter", "tier": 0, "surface": "fxtwitter"}


def facet_capture() -> dict[str, Any]:
    """The ``facets`` case, assembled from ``inputs/`` through the real normalizer.

    Built by calling :func:`~x2knwldg.twitter.normalize.post_from` with the
    facets the corroborating document carries, which is the same call
    ``tests/fixtures/captures/build_captures.py`` makes and the same one
    ``T-225`` would make at acquisition time. So the committed ``capture.json``
    is the normalizer's own output over committed input: if the guard's answer
    changes, this file stops rebuilding byte for byte and
    ``test_re_running_the_builder_is_byte_identical`` says so.
    """
    xcli_path = INPUT_DIR / "facets_astral__xcli_guest.json"
    fx_path = INPUT_DIR / "facets_astral__fxtwitter.json"
    record = json.loads(xcli_path.read_text(encoding="utf-8"))[0]
    fx = json.loads(fx_path.read_text(encoding="utf-8"))
    raw_text = fx["tweet"]["raw_text"]
    if raw_text["text"] != record["text"]:
        # Different text, different offsets. The builder refuses rather than
        # normalizing spans against a string they do not index.
        raise SystemExit("the two facets/ responses disagree about the authored text")

    completeness = {
        "status": "corroborated",
        "corroborated_by": [_FX],
        "agreement": "identical",
        "note": "constructed fixture; both responses carry the same authored text",
    }
    post = post_from(record, _GUEST, completeness, raw_text["facets"])
    return {
        "schema_version": "1.0",
        "acquisition": {
            "provider": {
                "tool": "tamnd/x-cli",
                "version": "0.5.0",
                "version_string": (
                    "x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z, darwin/arm64)"
                ),
                "binary_sha256": (
                    "6cb6b7f9b5fdb2366f113919423e87b4ddf9d41ce10bfc65b43614bed9987c97"
                ),
                "licence": "AGPL-3.0",
            },
            "requested_at": "2026-01-01T00:00:00Z",
            "routes_read": [
                {
                    **_GUEST,
                    "outcome": "ok",
                    "request_shape": f"x tweet {record['id']} --tier guest -o json",
                },
                {
                    **_FX,
                    "outcome": "ok",
                    "request_shape": f"https://api.fxtwitter.com/i/status/{record['id']}",
                },
            ],
            "network": {"via_tunnel": True, "note": "constructed fixture; nothing was read"},
        },
        "raw_evidence": [
            _constructed_evidence(xcli_path, "xcli_guest"),
            _constructed_evidence(fx_path, "fxtwitter"),
        ],
        "anchor": {
            "post_id": record["id"],
            "role": "single_post",
            "terminal_claim": "none",
        },
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


def _constructed_evidence(path: Path, route: str) -> dict[str, Any]:
    """A ``raw_evidence`` entry for a response that was written, not recorded.

    ``sha256_raw`` equals ``sha256_sanitized`` and ``sanitization_removed`` is
    empty, and both are *true* rather than convenient: these bytes were never
    sanitized because nothing in them is credential-shaped, and the equality is
    the checkable claim the contract asks the two digests to make.
    """
    text = path.read_text(encoding="utf-8")
    return {
        "route": route,
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256_raw": sha256_text(text),
        "sha256_sanitized": sha256_text(text),
        "sanitization_removed": [],
    }


#: Cases whose capture is constructed in-process rather than read from
#: ``tests/fixtures/captures/``. Keyed by case name, so adding one does not mean
#: adding a branch to :func:`_capture_for`.
CONSTRUCTED: dict[str, Any] = {
    # D-222: no measured route produces an edit history.
    "edit": edited_post_capture,
    "facets": facet_capture,
}

#: Of those, the cases whose ``raw/`` bytes were written rather than recorded.
#: ``edit`` is not one: its capture is constructed, but the two responses under
#: it are the committed ``single_post_en`` recordings.
CONSTRUCTED_RESPONSES = frozenset({"facets"})


def _capture_for(case: str, name: str | None) -> dict[str, Any]:
    if name is None:
        # Built in the process rather than committed as a claim about what a
        # provider returned. See `CONSTRUCTED`.
        build = CONSTRUCTED[case]
        result = build()
        assert isinstance(result, dict)
        return result
    return json.loads((CAPTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _rehome_evidence(capture: dict[str, Any], run_dir: Path) -> list[tuple[Path, str]]:
    """Copy the capture's evidence into the run's own ``raw/``, and repoint it.

    Returns the files to write. Each entry keeps the committed ``sha256_raw``
    and ``sanitization_removed`` — claims about bytes that were sanitized before
    they were ever committed, which cannot be recomputed from what is on disk —
    and its ``sha256_sanitized`` is recomputed from the copied text and compared
    with what the capture states. A mismatch is a build failure: it would mean
    the fixture's capture no longer describes the evidence beside it.
    """
    files: list[tuple[Path, str]] = []
    for entry in capture["raw_evidence"]:
        source = PROJECT_ROOT / entry["path"]
        destination = run_dir / acquire.RAW_DIR_NAME / source.name
        prepared = evidence.prepare(
            raw=source.read_bytes(),
            destination=destination,
            relative_to=EVIDENCE_ROOT,
            route=entry["route"],
        )
        if prepared.record["sha256_sanitized"] != entry["sha256_sanitized"]:
            raise SystemExit(
                f"{source} no longer hashes to what {capture['anchor']['post_id']} "
                f"records for it: {prepared.record['sha256_sanitized']} != "
                f"{entry['sha256_sanitized']}"
            )
        entry["path"] = prepared.record["path"]
        files.append((prepared.path, prepared.text))
    return files


def _span(text: str) -> tuple[int, int]:
    """The span one mechanical unit cites: the post's opening, from character 0.

    The first line where that is substantial enough to be evidence, and
    otherwise as much of the post as fits in 200 characters, cut on a word
    boundary. Both are exact prefixes, so ``canonical[start:end]`` is the
    excerpt by construction rather than by careful editing.
    """
    first_line = text.split("\n", 1)[0].rstrip()
    if len(first_line.strip()) >= 8:
        return 0, len(first_line)
    if len(text) <= 200:
        return 0, len(text.rstrip())
    cut = text[:200].rsplit(" ", 1)[0].rstrip()
    return 0, len(cut or text[:200])


def _bundle(capture: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    """The bundle a model pass would have produced for this capture.

    One `quote` unit per available post, one `synthesis` unit over them, and the
    coverage audit those two facts imply. The audit resolves
    ``coverage_not_audited`` because it has now run; it does not touch the
    ``source_unavailable`` omission or the ``capture_text_truncated`` gap, which
    are the pipeline's to state and which the apply gate re-imposes anyway.
    """
    units: list[dict[str, Any]] = []
    cited: dict[str, str] = {}
    for item in capture["items"]:
        text = extract.canonical_text(item)
        if not extract.is_available(item) or not text:
            continue
        start, end = _span(text)
        unit_id = f"KU-{len(units) + 1:06d}"
        units.append(
            {
                "id": unit_id,
                "kind": "quote",
                "source_class": "source",
                "content": text[start:end],
                "normalized_statement": text[start:end],
                "confidence": 0.9,
                "source": {
                    "post_id": item["post_id"],
                    "start_char": start,
                    "end_char": end,
                    "evidence_excerpt": text[start:end],
                },
                "attribution": {
                    "speaker": (item.get("author") or {}).get("username"),
                    "attribution_type": "direct",
                },
            }
        )
        cited[item["post_id"]] = unit_id

    if units:
        units.append(
            {
                "id": "KU-D-0001",
                "kind": "synthesis",
                "source_class": "derived",
                "content": (
                    f"This run quotes {len(units)} post(s) captured from "
                    f"{capture['anchor']['post_id']}."
                ),
                "normalized_statement": (
                    f"This run quotes {len(units)} post(s) captured from "
                    f"{capture['anchor']['post_id']}."
                ),
                "confidence": 0.7,
                "derived_from": sorted(cited.values()),
                "derivation_note": "Counts the source units this fixture's extraction produced.",
            }
        )

    items: list[dict[str, Any]] = []
    for entry in coverage["items"]:
        audited = dict(entry)
        unit_id = cited.get(entry["post_id"])
        if unit_id is not None:
            audited["status"] = "covered"
            audited["knowledge_units"] = [unit_id]
            # `coverage_not_audited` is what the scaffold minted to say no audit
            # had run. It has now. Anything else the scaffold minted stays.
            audited["unresolved_items"] = [
                item
                for item in entry["unresolved_items"]
                if item["type"] != "coverage_not_audited"
            ]
        items.append(audited)

    unresolved = sum(len(entry["unresolved_items"]) for entry in items)
    complete = capture["coverage"]["status"] == "PASS" and not unresolved
    relationships = (
        [
            {
                "from": units[0]["id"],
                "to": "KU-D-0001",
                "relation": "supports",
                "confidence": 0.8,
                "source_class": "derived",
            }
        ]
        if len(units) > 1
        else []
    )
    return {
        "extraction_metadata": dict(EXTRACTION_METADATA),
        "knowledge_units": units,
        "relationships": relationships,
        "coverage": {
            "status": "PASS" if complete else "PARTIAL",
            "audit_attempts": 1,
            "items": items,
        },
    }


def _label(run_dir: Path, note: str) -> None:
    """Mark the run synthetic and freeze its two clock-stamped fields."""
    path = run_dir / "metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["fixture"] = True
    metadata["fixture_note"] = note
    metadata["imported_at"] = FIXTURE_TIMESTAMP
    metadata["extracted_at"] = FIXTURE_TIMESTAMP
    write_json(path, metadata)


def build(case: str, capture_name: str | None) -> tuple[str, str]:
    run_dir = OUTPUT_ROOT / case
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / acquire.RAW_DIR_NAME).mkdir(parents=True)

    capture = _capture_for(case, capture_name)
    for path, text in _rehome_evidence(capture, run_dir):
        path.write_text(text, encoding="utf-8")
    (run_dir / extract.CAPTURE_FILENAME).write_text(dumps_json(capture), encoding="utf-8")

    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    bundle_path = run_dir / "work" / "extraction_bundle.json"
    write_json(bundle_path, _bundle(capture, coverage))
    extract.apply_extraction_bundle(run_dir, bundle_path)

    # Labelled before the final validation rather than after it, so
    # `validation.json` is a report about the files as they are committed.
    _label(run_dir, CONSTRUCTED_NOTE if case in CONSTRUCTED_RESPONSES else FIXTURE_NOTE)
    result = extract.validate_run(run_dir)
    coverage_status = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))["status"]
    return result["status"], coverage_status


def main() -> None:
    for case, capture_name, _ in CASES:
        status, coverage_status = build(case, capture_name)
        source = capture_name or f"{CONSTRUCTED[case].__module__}.{CONSTRUCTED[case].__name__}()"
        print(f"{case}: validation={status} coverage={coverage_status}  ← {source}")
    digest = sha256_text(
        "".join(
            sorted(
                f"{path.relative_to(FIXTURE_DIR)}:{sha256_text(path.read_text(encoding='utf-8'))}\n"
                for case, _, _ in CASES
                for path in (OUTPUT_ROOT / case).rglob("*")
                if path.is_file()
            )
        )
    )
    print(f"{len(CASES)} runs, tree digest {digest[:16]}")


if __name__ == "__main__":
    main()
