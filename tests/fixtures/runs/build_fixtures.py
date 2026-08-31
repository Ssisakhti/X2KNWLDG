"""Regenerate the labelled test-only run fixtures in this directory (T-006).

    .venv/bin/python tests/fixtures/runs/build_fixtures.py

The fixtures exist because the real sample under ``output/`` is gitignored, so
on any other machine the contract tests that project a real run onto the v1
index model would silently skip — a green suite that proved nothing. They also
give the honest-status UI something to render: risk **R11** is that ``PARTIAL``
and ``FAIL`` have never existed on disk, so no code has ever had to display
them.

Every run here is **synthetic**. The transcript text is written for this file,
the knowledge units are about the fixture itself, and every ``metadata.json``
carries ``"fixture": true``. Nothing in this directory is evidence about any
real video, and no test may present it as such.

The three runs are produced the way the pipeline produces a real one — import,
apply an extraction bundle, finalize — so their shapes cannot drift from what
the pipeline actually writes:

``pass-run``     validation PASS, coverage PASS
``partial-run``  validators pass, coverage PARTIAL — one window left uncovered
``fail-run``     a finalized run whose evidence excerpt no longer appears in its
                 segment, so provenance fails and validation is FAIL
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FIXTURE_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from x2knwldg.artifacts import apply_extraction_bundle, finalize_run  # noqa: E402
from x2knwldg.io import write_json  # noqa: E402
from x2knwldg.pipeline import import_transcript, validate_run  # noqa: E402

# Frozen so regenerating the fixtures is byte-identical and CI can prove it.
# The value is obviously not a real ingestion time.
FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"

FIXTURE_NOTE = (
    "Synthetic test fixture — not real evidence about any video. "
    "Regenerate with tests/fixtures/runs/build_fixtures.py."
)

TRANSCRIPT = """1
00:00:00,000 --> 00:00:30,000
A knowledge unit must carry the evidence it rests on.

2
00:00:30,000 --> 00:01:00,000
Coverage is audited window by window across the whole timeline.

3
00:01:00,000 --> 00:01:30,000
A run reports PARTIAL when the timeline is not fully accounted for.
"""

TRANSCRIPT_END_SEC = 90.0

EVIDENCE = "a knowledge unit must carry the evidence it rests on."


def _units(video_id: str, segment_id: str) -> list[dict]:
    return [
        {
            "id": "KU-000001",
            "kind": "principle",
            "source_class": "source",
            "content": "A knowledge unit must carry the evidence it rests on.",
            "normalized_statement": "A knowledge unit must carry the evidence it rests on.",
            "confidence": 0.9,
            "source": {
                "video_id": video_id,
                "segment_id": segment_id,
                "start_sec": 0.0,
                "end_sec": 30.0,
                "evidence_excerpt": EVIDENCE,
            },
        },
        {
            "id": "KU-D-0001",
            "kind": "synthesis",
            "source_class": "derived",
            "content": "Evidence-bearing units are what make a run auditable.",
            "normalized_statement": "Evidence-bearing units are what make a run auditable.",
            "confidence": 0.7,
            "derived_from": ["KU-000001"],
            "derivation_note": "Restates KU-000001 as the property it gives the run.",
        },
    ]


RELATIONSHIPS = [
    {
        "from": "KU-000001",
        "to": "KU-D-0001",
        "relation": "supports",
        "confidence": 0.8,
        "source_class": "derived",
    }
]

PASS_COVERAGE = {
    "status": "PASS",
    "audit_attempts": 1,
    "windows": [
        {
            "window_id": "W-0001",
            "start_sec": 0.0,
            "end_sec": TRANSCRIPT_END_SEC,
            "status": "covered",
            "knowledge_units": ["KU-000001"],
            "omitted_items": [],
            "unresolved_items": [],
        }
    ],
}

PARTIAL_COVERAGE = {
    "status": "PARTIAL",
    "audit_attempts": 3,
    "windows": [
        {
            "window_id": "W-0001",
            "start_sec": 0.0,
            "end_sec": 45.0,
            "status": "covered",
            "knowledge_units": ["KU-000001"],
            "omitted_items": [],
            "unresolved_items": [],
        },
        {
            "window_id": "W-0002",
            "start_sec": 45.0,
            "end_sec": TRANSCRIPT_END_SEC,
            "status": "uncovered",
            "knowledge_units": [],
            "omitted_items": [],
            "unresolved_items": [
                {
                    "window_id": "W-0002",
                    "note": "Three audit attempts did not resolve this window; it stays uncovered.",
                }
            ],
        },
    ],
}


def _build_run(work_root: Path, video_id: str, coverage: dict) -> Path:
    transcript_file = work_root / f"{video_id}.srt"
    transcript_file.write_text(TRANSCRIPT, encoding="utf-8")
    run_dir = import_transcript(
        transcript_file,
        work_root,
        video_id=video_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"TEST FIXTURE ({video_id}) — synthetic, not real evidence",
        channel="X2KNWLDG test fixtures",
        language="en",
    )
    segments = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))
    segment_id = segments["segments"][0]["segment_id"]
    bundle_path = run_dir / "work" / "extraction_bundle.json"
    write_json(
        bundle_path,
        {
            "extraction_metadata": {"model": "none — handwritten fixture", "fixture": True},
            "knowledge_units": _units(video_id, segment_id),
            "relationships": RELATIONSHIPS,
            "coverage": dict(coverage),
        },
    )
    apply_extraction_bundle(run_dir, bundle_path)
    finalize_run(run_dir)
    return run_dir


def _label(run_dir: Path) -> None:
    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["fixture"] = True
    metadata["fixture_note"] = FIXTURE_NOTE
    metadata["imported_at"] = FIXTURE_TIMESTAMP
    metadata["extracted_at"] = FIXTURE_TIMESTAMP
    write_json(metadata_path, metadata)


def _break_provenance(run_dir: Path) -> None:
    """Make the evidence excerpt unfindable in its segment, as a corrupted or
    hand-edited run would be. validate_run then reports FAIL honestly."""
    path = run_dir / "knowledge_units.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["units"][0]["source"]["evidence_excerpt"] = (
        "this sentence is not in the transcript, which is the point of this fixture"
    )
    write_json(path, document)
    result = validate_run(run_dir)
    if result["status"] != "FAIL":
        raise SystemExit(f"fail-run fixture is not FAIL: {result['status']}")


def _publish(run_dir: Path, name: str) -> None:
    target = FIXTURE_DIR / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(run_dir, target)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        work_root = Path(directory)
        for name, video_id, coverage in (
            ("pass-run", "fixture-pass", PASS_COVERAGE),
            ("partial-run", "fixture-partial", PARTIAL_COVERAGE),
            ("fail-run", "fixture-fail", PASS_COVERAGE),
        ):
            run_dir = _build_run(work_root, video_id, coverage)
            if name == "fail-run":
                _break_provenance(run_dir)
            _label(run_dir)
            _publish(run_dir, name)
            status = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))["status"]
            coverage_status = json.loads(
                (run_dir / "coverage.json").read_text(encoding="utf-8")
            )["status"]
            print(f"{name}: validation={status} coverage={coverage_status}")


if __name__ == "__main__":
    main()
