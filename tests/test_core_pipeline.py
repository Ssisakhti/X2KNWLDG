import json
import shutil
import tempfile
import unittest
from pathlib import Path

from x2knwldg.pipeline import (
    PipelineError,
    import_transcript,
    resolve_run_dir,
    validate_run,
)
from x2knwldg.artifacts import apply_extraction_bundle, finalize_run
from x2knwldg.segmenter import create_segments
from x2knwldg.transcripts import TranscriptError, parse_transcript_file, transcript_integrity
from x2knwldg.validators import validate_knowledge_units
from x2knwldg.query import search_knowledge


FIXTURES = Path(__file__).parent / "fixtures"


class TranscriptTests(unittest.TestCase):
    def test_srt_preserves_timing(self):
        captions = parse_transcript_file(FIXTURES / "sample.srt", language="en")
        self.assertEqual(len(captions), 3)
        self.assertEqual(captions[0]["start_sec"], 0)
        self.assertEqual(captions[0]["end_sec"], 4.5)
        self.assertEqual(captions[0]["source"], "imported_srt")

    def test_vtt_cleans_markup_and_entities(self):
        captions = parse_transcript_file(FIXTURES / "sample.vtt", language="en")
        self.assertEqual(captions[0]["text"], "First caption.")
        self.assertEqual(captions[1]["text"], "Second & final caption.")
        self.assertEqual(captions[1]["original_id"], "cue-b")

    def test_plain_text_without_timestamps_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.txt"
            path.write_text("Plain transcript without timing", encoding="utf-8")
            with self.assertRaises(TranscriptError):
                parse_transcript_file(path)

    def test_integrity_surfaces_long_gap(self):
        captions = parse_transcript_file(FIXTURES / "sample.srt")
        result = transcript_integrity(captions, max_gap_sec=60)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(any(item["code"] == "large_gap" for item in result["warnings"]))


class SegmentTests(unittest.TestCase):
    def test_segments_preserve_caption_ids_and_overlap(self):
        captions = [
            {
                "segment_id": f"cap_{index:06d}",
                "start_sec": index * 30,
                "end_sec": (index + 1) * 30,
                "text": f"Caption {index}.",
            }
            for index in range(20)
        ]
        segments = create_segments(captions, target_sec=180, min_sec=120, max_sec=240, overlap_sec=30)
        self.assertGreater(len(segments), 1)
        self.assertTrue(set(segments[0]["caption_ids"]) & set(segments[1]["caption_ids"]))


class PipelineTests(unittest.TestCase):
    def test_import_creates_canonical_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = import_transcript(
                FIXTURES / "sample.vtt",
                Path(directory),
                video_id="abc123def45",
                video_url="https://www.youtube.com/watch?v=abc123def45",
                language="en",
            )
            expected = {
                "metadata.json",
                "transcript.json",
                "segments.json",
                "knowledge_units.json",
                "relationships.json",
                "coverage.json",
                "report.md",
                "graph.json",
                "validation.json",
            }
            self.assertTrue(expected.issubset({path.name for path in run_dir.iterdir()}))
            transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
            self.assertEqual(transcript["captions"][1]["end_sec"], 5.5)
            coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
            self.assertEqual(coverage["status"], "PARTIAL")
            self.assertEqual(coverage["windows"][0]["status"], "pending")

    def test_import_never_overwrites_existing_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            import_transcript(FIXTURES / "sample.vtt", output, video_id="abc123def45")
            with self.assertRaises(PipelineError):
                import_transcript(FIXTURES / "sample.vtt", output, video_id="abc123def45")

    def test_valid_bundle_finalizes_report_graph_and_obsidian(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = import_transcript(
                FIXTURES / "sample.vtt", root / "output", video_id="abc123def45", language="en"
            )
            bundle = {
                "knowledge_units": [
                    {
                        "id": "KU-000001",
                        "kind": "claim",
                        "source_class": "source",
                        "content": "This is the first claim.",
                        "confidence": 0.99,
                        "source": {
                            "video_id": "abc123def45",
                            "segment_id": "seg_0001",
                            "start_sec": 0,
                            "end_sec": 2,
                            "evidence_excerpt": "First caption.",
                        },
                    }
                ],
                "relationships": [],
                "coverage": {
                    "status": "PASS",
                    "windows": [
                        {
                            "window_id": "CW-0001",
                            "start_sec": 0,
                            "end_sec": 5.5,
                            "status": "covered",
                            "knowledge_units": ["KU-000001"],
                            "omitted_items": [],
                            "unresolved_items": [],
                        }
                    ],
                },
            }
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            validation = apply_extraction_bundle(run_dir, bundle_path)
            self.assertEqual(validation["status"], "PASS")
            result = finalize_run(run_dir)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((run_dir / "vault" / "videos" / "abc123def45.md").exists())
            graph = json.loads((run_dir / "graph.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["nodes"][0]["id"], "KU-000001")
            self.assertIn("KU-000001", (run_dir / "report.md").read_text(encoding="utf-8"))
            results = search_knowledge(root / "output", "first claim", video_id="abc123def45")
            self.assertEqual(results[0]["type"], "knowledge_unit")
            self.assertEqual(results[0]["id"], "KU-000001")
            self.assertIn("&t=0s", results[0]["source_url"])


class RunLookupTests(unittest.TestCase):
    """A caller-supplied id must never reach a path join unchecked (risk R14)."""

    ESCAPES = [
        "../secrets",
        "..",
        ".",
        "../../etc/passwd",
        "/etc/passwd",
        "a/b",
        "a\\b",
        "",
        "   ",
        ".hidden",
        "run:1",
    ]

    def test_identifier_that_escapes_the_output_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            root.mkdir()
            for video_id in self.ESCAPES:
                with self.subTest(video_id=video_id):
                    with self.assertRaises(PipelineError):
                        resolve_run_dir(root, video_id)

    def test_ordinary_identifier_resolves_inside_the_output_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            (root / "abc123def45").mkdir(parents=True)
            resolved = resolve_run_dir(root, "abc123def45")
            self.assertEqual(resolved.name, "abc123def45")
            self.assertEqual(resolved.parent, root.resolve())

    def test_missing_run_still_resolves_so_callers_report_their_own_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            root.mkdir()
            self.assertEqual(resolve_run_dir(root, "neverIngested").name, "neverIngested")

    def test_search_rejects_a_traversing_video_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            root.mkdir()
            with self.assertRaises(PipelineError):
                search_knowledge(root, "anything", video_id="../..")


class ValidatorTests(unittest.TestCase):
    def test_derived_unit_requires_sources_and_note(self):
        result = validate_knowledge_units(
            {
                "units": [
                    {
                        "id": "KU-D-1",
                        "kind": "synthesis",
                        "source_class": "derived",
                        "content": "A synthesis",
                        "confidence": 0.8,
                    }
                ]
            }
        )
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("missing_derived_from", codes)
        self.assertIn("missing_derivation_note", codes)

    def test_unit_id_that_cannot_become_a_global_id_is_rejected(self):
        """An unaddressable id must fail validation, not crash the library rebuild (D-018)."""
        for bad_id in ("KU 1", "KU:1", "..", ".hidden", "KU/1"):
            with self.subTest(unit_id=bad_id):
                result = validate_knowledge_units(
                    {
                        "units": [
                            {
                                "id": bad_id,
                                "kind": "claim",
                                "source_class": "derived",
                                "content": "A synthesis",
                                "derived_from": [bad_id],
                                "derivation_note": "Because.",
                                "confidence": 0.8,
                            }
                        ]
                    }
                )
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("invalid_id", {error["code"] for error in result["errors"]})


if __name__ == "__main__":
    unittest.main()


class RunVerdictTests(unittest.TestCase):
    """``validate_run``'s aggregate verdict, and what ``finalize_run`` does with it.

    These cover the two branches at ``pipeline.validate_run`` that assign
    ``FAIL`` and ``PARTIAL``. Both were previously unreachable from this suite:
    replacing the ``FAIL`` assignment with ``if False:`` left the whole suite
    green, because every assertion on a ``"FAIL"`` status was made against
    ``validate_knowledge_units`` — a *section* validator — rather than against
    the run-level aggregation that the CLI, the MCP server and ``finalize_run``
    all consume. ``validate_run`` had four production call sites and no test.

    The labelled fixtures from ``T-006`` supply the inputs, so nothing here has
    to hand-build a broken run.
    """

    def _writable_copy(self, directory, name):
        """A writable copy of a committed fixture run.

        ``validate_run`` writes ``validation.json`` as a side effect, so it
        cannot be pointed at ``tests/fixtures/runs/`` — other contract tests
        assert those files are never touched.
        """
        target = Path(directory) / name
        shutil.copytree(FIXTURES / "runs" / name, target)
        return target

    def test_a_run_whose_evidence_is_absent_from_the_transcript_validates_as_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._writable_copy(directory, "fail-run")
            result = validate_run(run_dir)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["provenance"]["status"], "FAIL")
            codes = {error["code"] for error in result["provenance"]["errors"]}
            self.assertIn("evidence_excerpt_not_in_segment", codes)

    def test_a_run_with_incomplete_coverage_validates_as_partial(self):
        """Every section passes; only ``coverage.json``'s own status is short of PASS."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._writable_copy(directory, "partial-run")
            result = validate_run(run_dir)
            self.assertEqual(result["status"], "PARTIAL")
            sections = [
                value["status"]
                for value in result.values()
                if isinstance(value, dict) and "status" in value
            ]
            self.assertEqual(set(sections), {"PASS"})

    def test_a_complete_run_validates_as_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._writable_copy(directory, "pass-run")
            self.assertEqual(validate_run(run_dir)["status"], "PASS")

    def test_finalize_refuses_a_failing_run_and_leaves_its_artifacts_alone(self):
        """WORKFLOW.md section 5 validates *before* final artifacts are generated.

        ``finalize_run`` used to compute the verdict and write regardless, so a
        run citing evidence absent from the transcript still produced a full
        vault, a ``report.md`` that mentioned no failure, and — through
        ``rebuild_library`` — a poisoned cumulative graph.
        """
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._writable_copy(directory, "fail-run")
            # validation.json is excluded: validate_run legitimately refreshes it
            # before the refusal, which is the run's own report being kept current.
            def snapshot():
                return {
                    path.relative_to(run_dir).as_posix(): path.stat().st_mtime_ns
                    for path in sorted(run_dir.rglob("*"))
                    if path.is_file() and path.name != "validation.json"
                }

            before = snapshot()
            with self.assertRaises(PipelineError) as caught:
                finalize_run(run_dir)
            self.assertIn("validation", str(caught.exception))
            self.assertEqual(before, snapshot(), "a refused finalize rewrote an artifact")
            self.assertFalse(
                (run_dir.parent / "library").exists(),
                "a refused finalize rebuilt the cumulative library",
            )

    def test_finalize_still_completes_for_an_honestly_partial_run(self):
        """PARTIAL is a real deliverable (WORKFLOW.md section 4.5), not a failure."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._writable_copy(directory, "partial-run")
            result = finalize_run(run_dir)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue((run_dir / "report.md").exists())

    def test_finalize_refuses_a_video_id_that_would_escape_the_run_directory(self):
        """The vault filenames are built from ``metadata['video_id']``.

        ``metadata.json`` is an ordinary canonical file rather than immutable
        evidence, so its contents are not automatically safe to put in a path.
        An unchecked id escaped ``output/`` at arbitrary depth and overwrote any
        ``<name>.md`` — including the instruction files at the repository root.
        """
        for bad_id in ("../../../../ESCAPED", "..", "a/b", ".hidden", "", "abc\n"):
            with self.subTest(video_id=bad_id):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    run_dir = self._writable_copy(root, "pass-run")
                    metadata = json.loads(
                        (run_dir / "metadata.json").read_text(encoding="utf-8")
                    )
                    metadata["video_id"] = bad_id
                    (run_dir / "metadata.json").write_text(
                        json.dumps(metadata), encoding="utf-8"
                    )
                    with self.assertRaises(PipelineError) as caught:
                        finalize_run(run_dir)
                    self.assertIn("video_id", str(caught.exception))
                    self.assertEqual(
                        [], list(root.rglob("ESCAPED.md")), "the id escaped the run directory"
                    )
