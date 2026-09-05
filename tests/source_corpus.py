"""A two-medium corpus in which a canonical concept actually spans both media.

`T-253` needs one thing the committed fixtures cannot provide: a **discoverable**
YouTube↔X pair. Discovery's cross-medium route is the shared canonical concept,
and `library._concept_key` only keys units whose ``kind`` is one of
``CONCEPT_KINDS``. Every committed Twitter run emits ``quote`` and ``synthesis``
units — deliberately, because that builder's docstring says inventing analytical
claims about real posts "would put words in real authors' mouths in a file that
is committed forever" — so no committed corpus can produce a cross-medium
concept, and none should be edited into producing one.

So the corpus is built **in the test process**, which is this project's own
answer to exactly this problem: ``tests/capture_shapes.py`` constructs the edit
capture in-process rather than committing one, "so nothing on disk claims to be
evidence". Nothing here is committed either.

**No provider bytes are fabricated.** The X run is the committed ``single-post``
fixture, copied, with its preserved ``raw/`` evidence and its ``capture.json``
byte for byte as they are. The only thing that differs is the **bundle** — model
output by definition — and within it a single field: ``kind`` goes from
``quote`` to ``principle``. The unit's ``content`` and ``normalized_statement``
stay what the committed fixture already made them, which is the post's own text
verbatim, so the corpus puts no words in anyone's mouth. It says the post says
what the post says, and files it under a kind that is also a concept kind.

The YouTube run is synthetic in the ordinary way ``tests/fixtures/runs/`` is: an
invented transcript, an invented id, ``fixture: true``. Its transcript contains
that same sentence, and its unit normalizes to it — which is the whole mechanism
under test. Two runs of different media converging on one canonical statement
become a candidate; that is what a shared concept *is*.

Stdlib only apart from the package itself.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from x2knwldg.artifacts import apply_extraction_bundle
from x2knwldg.io import write_json
from x2knwldg.library import rebuild_library
from x2knwldg.pipeline import import_transcript
from x2knwldg.twitter.extract import apply_extraction_bundle as apply_twitter_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TWITTER_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs" / "single-post"

#: The sentence both runs normalize to, and therefore the canonical concept that
#: spans them. It is the X post's own text, verbatim — not a claim written about
#: it. `library._concept_key` reads ``normalized_statement``, so this string
#: appearing on a concept-kind unit in each run is what makes them one concept.
SHARED_STATEMENT = "just setting up my twttr"

#: The YouTube side is synthetic and says so, exactly as the committed run
#: fixtures do. The transcript carries the shared sentence so the unit that
#: normalizes to it is grounded in evidence rather than asserted.
TRANSCRIPT = f"""1
00:00:00,000 --> 00:00:30,000
The first post on the service read: {SHARED_STATEMENT}.

2
00:00:30,000 --> 00:01:00,000
Everything after it was built on that one line.
"""

YOUTUBE_ID = "fixture-source-map"
FIXTURE_NOTE = (
    "Synthetic test corpus built in-process by tests/source_corpus.py — not real "
    "evidence about any video, post or author, and never written to the repository."
)


@dataclass(frozen=True)
class Corpus:
    """A project root holding one YouTube run and one X run, plus the library."""

    project_root: Path
    youtube_source_id: str
    twitter_source_id: str

    @property
    def output(self) -> Path:
        return self.project_root / "output"

    def run_dir(self, source_id: str) -> Path:
        return self.output / source_id.split(":", 1)[1]


def _youtube_run(output: Path, work: Path) -> str:
    transcript = work / f"{YOUTUBE_ID}.srt"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    run_dir = import_transcript(
        transcript,
        output,
        video_id=YOUTUBE_ID,
        video_url=f"https://www.youtube.com/watch?v={YOUTUBE_ID}",
        title="TEST FIXTURE (source map corpus) — synthetic, not real evidence",
        channel="X2KNWLDG test fixtures",
        language="en",
    )
    segments = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))
    segment = segments["segments"][0]
    bundle = run_dir / "work" / "extraction_bundle.json"
    write_json(
        bundle,
        {
            "extraction_metadata": {"model": "none — in-process fixture", "fixture": True},
            "knowledge_units": [
                {
                    "id": "KU-000001",
                    # A concept kind, which is what makes this unit join a
                    # canonical concept at all (`library.CONCEPT_KINDS`).
                    "kind": "principle",
                    "source_class": "source",
                    "content": SHARED_STATEMENT,
                    "normalized_statement": SHARED_STATEMENT,
                    "confidence": 0.9,
                    "source": {
                        "video_id": YOUTUBE_ID,
                        "segment_id": segment["segment_id"],
                        "start_sec": 0.0,
                        "end_sec": 30.0,
                        "evidence_excerpt": SHARED_STATEMENT,
                    },
                },
                {
                    "id": "KU-D-0001",
                    "kind": "synthesis",
                    "source_class": "derived",
                    "content": "آن یک جمله، نقطهٔ آغاز همهٔ آنچه پس از آن ساخته شد بود.",
                    "normalized_statement": "That one line was the starting point.",
                    "confidence": 0.6,
                    "derived_from": ["KU-000001"],
                    "derivation_note": "برداشتی از KU-000001 دربارهٔ اهمیت آن جمله.",
                },
            ],
            "relationships": [
                {
                    "from": "KU-000001",
                    "to": "KU-D-0001",
                    "relation": "supports",
                    "confidence": 0.8,
                    "source_class": "derived",
                }
            ],
            "coverage": {
                "status": "PASS",
                "audit_attempts": 1,
                "windows": [
                    {
                        "window_id": "W-0001",
                        "start_sec": 0.0,
                        "end_sec": 60.0,
                        "status": "covered",
                        "knowledge_units": ["KU-000001"],
                        "omitted_items": [],
                        "unresolved_items": [],
                    }
                ],
            },
        },
    )
    apply_extraction_bundle(run_dir, bundle)
    _label(run_dir)
    return f"youtube:{YOUTUBE_ID}"


def _twitter_run(output: Path) -> str:
    """The committed fixture, copied, re-extracted with one field changed.

    ``capture.json`` and everything under ``raw/`` are the committed bytes and
    are not touched. What is re-applied is the fixture's **own** bundle with
    ``kind`` changed from ``quote`` to ``principle`` — a statement about how the
    unit is classified, not about what the post says.
    """
    run_dir = output / "twitter-single-post"
    shutil.copytree(TWITTER_FIXTURE, run_dir)

    bundle = json.loads(
        (run_dir / "work" / "extraction_bundle.json").read_text(encoding="utf-8")
    )
    for unit in bundle["knowledge_units"]:
        if unit["source_class"] == "source":
            assert unit["normalized_statement"] == SHARED_STATEMENT, (
                "the committed fixture's unit no longer carries the post's own text, so "
                "this corpus would be asserting something the post does not say"
            )
            unit["kind"] = "principle"

    bundle_path = run_dir / "work" / "extraction_bundle.json"
    write_json(bundle_path, bundle)
    apply_twitter_bundle(run_dir, bundle_path)

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    return f"twitter:{metadata['video_id']}"


def _label(run_dir: Path) -> None:
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    metadata["fixture"] = True
    metadata["fixture_note"] = FIXTURE_NOTE
    write_json(run_dir / "metadata.json", metadata)


def build(tmp_path: Path) -> Corpus:
    """Build the corpus under *tmp_path* and rebuild its library."""
    project_root = tmp_path / "project"
    output = project_root / "output"
    output.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)

    youtube_source_id = _youtube_run(output, work)
    twitter_source_id = _twitter_run(output)
    rebuild_library(output)

    return Corpus(
        project_root=project_root,
        youtube_source_id=youtube_source_id,
        twitter_source_id=twitter_source_id,
    )
