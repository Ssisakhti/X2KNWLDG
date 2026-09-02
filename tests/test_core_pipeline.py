import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from x2knwldg import io as io_module
from x2knwldg.artifacts import apply_extraction_bundle, finalize_run
from x2knwldg.io import (
    CanonicalValueError,
    JsonReadError,
    format_timestamp,
    read_json,
    timestamp_url,
    write_group,
    write_json,
    write_text,
)
from x2knwldg.pipeline import (
    PipelineError,
    VerdictRefusal,
    import_transcript,
    resolve_run_dir,
    validate_run,
)
from x2knwldg.query import search_knowledge
from x2knwldg.segmenter import create_segments
from x2knwldg.transcripts import TranscriptError, parse_transcript_file, transcript_integrity
from x2knwldg.validators import validate_knowledge_units

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
                    "audit_attempts": 1,
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


class CanonicalTimestampTests(unittest.TestCase):
    """D-074 — a timestamp that is not a number is refused, not guessed.

    ``io.format_timestamp`` was ``max(0, int(seconds))``. ``int("0.0")`` raises
    a bare ``ValueError``, so a canonical file timed ``"0.0"`` took
    ``finalize`` down with a raw traceback at exit ``1`` — and ``ValueError``
    is not in ``cli.USER_FACING_ERRORS``, so the documented
    ``{"status": "ERROR"}`` stderr contract was broken too. ``int`` also
    silently truncated ``True`` to ``1`` and accepted the string ``"12"``.
    """

    UNUSABLE = ["0.0", "12", "", True, False, None, [1], {}, float("nan"), float("inf")]

    def test_an_unusable_timestamp_is_refused_by_both_renderers(self):
        for value in self.UNUSABLE:
            with self.subTest(value=value):
                with self.assertRaises(CanonicalValueError):
                    format_timestamp(value)
                with self.assertRaises(CanonicalValueError):
                    timestamp_url("vid12345678", value)

    def test_an_honest_timestamp_still_renders(self):
        self.assertEqual(format_timestamp(0), "00:00:00")
        self.assertEqual(format_timestamp(0.0), "00:00:00")
        self.assertEqual(format_timestamp(3725.9), "01:02:05")
        self.assertEqual(format_timestamp(-5), "00:00:00")
        self.assertEqual(
            timestamp_url("vid12345678", 90.4),
            "https://www.youtube.com/watch?v=vid12345678&t=90s",
        )

    def test_the_refusal_reaches_the_documented_stderr_contract(self):
        """The second half of the defect: the CLI must present it, not crash."""
        from x2knwldg import cli

        self.assertIn(CanonicalValueError, cli.USER_FACING_ERRORS)


class NonFiniteJsonTests(unittest.TestCase):
    """D-075 — ``1e999`` is a number, and it parses to infinity.

    ``parse_constant`` only ever sees the bare ``NaN``/``Infinity`` tokens, so
    ``1e999`` — legal JSON — passed the reader and every validator, then died
    inside ``artifacts._write_group`` with ``Out of range float values are not
    JSON compliant: inf`` and a full traceback. The check belonged on the
    parsed number, not on the spelling.
    """

    def test_a_literal_that_parses_to_infinity_is_refused_at_the_read(self):
        with tempfile.TemporaryDirectory() as directory:
            for literal in ("1e999", "-1e999", "1E400", "1e999e"[:5]):
                with self.subTest(literal=literal):
                    path = Path(directory) / "big.json"
                    path.write_text(f'{{"end_sec": {literal}}}', encoding="utf-8")
                    with self.assertRaises(JsonReadError) as caught:
                        read_json(path)
                    self.assertIn("non-finite", str(caught.exception))

    def test_the_named_constants_are_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            for literal in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(literal=literal):
                    path = Path(directory) / "constant.json"
                    path.write_text(f'{{"end_sec": {literal}}}', encoding="utf-8")
                    with self.assertRaises(JsonReadError):
                        read_json(path)

    def test_ordinary_numbers_still_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ok.json"
            value = {"a": 0, "b": -1.5, "c": 1e308, "d": 3, "e": 1e-320}
            write_json(path, value)
            self.assertEqual(read_json(path), value)


class CorruptMetadataTests(unittest.TestCase):
    """D-077 — ``artifacts._read`` was a weaker twin of ``pipeline._read_canonical``.

    One enforced "must be a JSON object" and the other did not, so a
    ``metadata.json`` holding ``[]`` reached ``metadata["video_id"]`` and
    escaped as ``TypeError: list indices must be integers``, while one that had
    merely lost the key raised a bare ``KeyError``. ``finalize_run`` already
    read the id through ``_checked_video_id``; ``apply_extraction_bundle`` did
    not. One reader, one rule.
    """

    def _run(self, directory, metadata):
        fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
        run_dir = Path(directory) / "run"
        shutil.copytree(fixture, run_dir)
        Path(run_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        bundle = Path(directory) / "bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "knowledge_units": json.loads(
                        (fixture / "knowledge_units.json").read_text()
                    )["units"],
                    "relationships": json.loads(
                        (fixture / "relationships.json").read_text()
                    )["relationships"],
                    "coverage": json.loads((fixture / "coverage.json").read_text()),
                }
            ),
            encoding="utf-8",
        )
        return run_dir, bundle

    def test_a_damaged_metadata_file_is_a_refusal_not_a_traceback(self):
        for metadata in ([], "fixture-pass", 7, {"title": "no id"}, {"video_id": None}):
            with self.subTest(metadata=metadata):
                with tempfile.TemporaryDirectory() as directory:
                    run_dir, bundle = self._run(directory, metadata)
                    with self.assertRaises(PipelineError):
                        apply_extraction_bundle(run_dir, bundle)

    def test_an_intact_run_still_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
            run_dir, bundle = self._run(
                directory, json.loads((fixture / "metadata.json").read_text())
            )
            apply_extraction_bundle(run_dir, bundle)

    def test_a_canonical_file_that_is_not_an_object_is_refused(self):
        for name in ("knowledge_units.json", "relationships.json", "coverage.json"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as directory:
                    fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
                    run_dir = Path(directory) / "run"
                    shutil.copytree(fixture, run_dir)
                    (run_dir / name).write_text("[]", encoding="utf-8")
                    with self.assertRaises(PipelineError) as caught:
                        finalize_run(run_dir)
                    self.assertIn("JSON", str(caught.exception))


class BundleKeyTests(unittest.TestCase):
    """D-073 — the bundle key is ``knowledge_units``, and the wrong one is named.

    ``apply_extraction_bundle`` read
    ``bundle.get("knowledge_units", bundle.get("units", []))``, silently
    accepting both spellings — while the schema requires ``knowledge_units``
    and sets ``additionalProperties: false``, and three prompts told the agent
    to return ``{"units": ...}``. Nothing broke, so the divergence was
    invisible.
    """

    def test_a_bundle_keyed_units_is_refused_and_names_the_right_key(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
            run_dir = Path(directory) / "run"
            shutil.copytree(fixture, run_dir)
            bundle = Path(directory) / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "units": json.loads(
                            (fixture / "knowledge_units.json").read_text()
                        )["units"],
                        "relationships": [],
                        "coverage": json.loads((fixture / "coverage.json").read_text()),
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PipelineError) as caught:
                apply_extraction_bundle(run_dir, bundle)
            self.assertIn("knowledge_units", str(caught.exception))


#: "this key is absent", distinct from "this key is present and is None".
_ABSENT = object()


class RequiredBundleKeyTests(unittest.TestCase):
    """D-169 — of three required keys, two were guarded and one was not.

    ``bundle.get("relationships", [])`` defaulted in silence, so a bundle that
    misspelled the key or dropped it applied cleanly and wiped
    ``relationships.json`` to ``[]`` — reporting ``PASS`` over a run that had
    just lost every relationship it had. The schema's
    ``additionalProperties: false`` could not help: nothing applies the schema
    at runtime, because ``jsonschema`` is a dev extra.
    """

    def _run_and_bundle(self, directory, **overrides):
        fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
        run_dir = Path(directory) / "run"
        shutil.copytree(fixture, run_dir)
        document = {
            "knowledge_units": json.loads(
                (fixture / "knowledge_units.json").read_text()
            )["units"],
            "relationships": json.loads(
                (fixture / "relationships.json").read_text()
            )["relationships"],
            "coverage": json.loads((fixture / "coverage.json").read_text()),
        }
        document.update(overrides)
        for key, value in list(document.items()):
            if value is _ABSENT:
                del document[key]
        path = Path(directory) / "bundle.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return run_dir, path

    def test_a_bundle_missing_relationships_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir, bundle = self._run_and_bundle(directory, relationships=_ABSENT)
            before = (run_dir / "relationships.json").read_bytes()
            with self.assertRaises(PipelineError) as caught:
                apply_extraction_bundle(run_dir, bundle)
            self.assertIn("relationships", str(caught.exception))
            self.assertEqual(
                (run_dir / "relationships.json").read_bytes(),
                before,
                "a refused bundle changes nothing",
            )

    def test_a_misspelled_relationships_key_names_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir, bundle = self._run_and_bundle(
                directory, relationships=_ABSENT, relations=[]
            )
            with self.assertRaises(PipelineError) as caught:
                apply_extraction_bundle(run_dir, bundle)
            message = str(caught.exception)
            self.assertIn("relationships", message)

    def test_an_unknown_top_level_key_is_refused(self):
        """``additionalProperties: false``, enforced where the bundle is read."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir, bundle = self._run_and_bundle(directory, notes="anything")
            with self.assertRaises(PipelineError) as caught:
                apply_extraction_bundle(run_dir, bundle)
            self.assertIn("notes", str(caught.exception))

    def test_extraction_metadata_must_be_an_object_or_absent(self):
        """It was discarded in silence while ``extracted_at`` was stamped anyway."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir, bundle = self._run_and_bundle(
                directory, extraction_metadata="a note about the model"
            )
            with self.assertRaises(PipelineError) as caught:
                apply_extraction_bundle(run_dir, bundle)
            self.assertIn("extraction_metadata", str(caught.exception))

    def test_the_four_accepted_keys_still_apply_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir, bundle = self._run_and_bundle(
                directory, extraction_metadata={"model": "none - a test"}
            )
            apply_extraction_bundle(run_dir, bundle)
            metadata = json.loads((run_dir / "metadata.json").read_text())
            self.assertEqual(metadata["extraction"], {"model": "none - a test"})


class VaultCollisionTests(unittest.TestCase):
    """D-171 — two unit ids that address one note on a case-insensitive disk.

    ``ku-a`` and ``KU-A`` are distinct to every validator, and ``_slug`` does
    not case-fold. On macOS the second write won: ``finalize`` reported ``PASS``
    and claimed four files, the disk held three, ``report.md`` listed both units
    and one note was gone. ``write_group`` treated the two unresolved paths as
    distinct, so no duplicate-path check fired. CI is Linux, which is why the
    rule here is case-insensitive on every platform rather than on the ones
    where the filesystem is.
    """

    def test_two_entries_naming_one_file_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(CanonicalValueError) as caught:
                write_group([(root / "ku-a.md", "one"), (root / "KU-A.md", "two")])
            message = str(caught.exception)
            self.assertIn("ku-a.md", message)
            self.assertIn("KU-A.md", message)
            self.assertFalse(
                any(path.is_file() for path in root.iterdir()),
                "a refused group writes nothing",
            )

    def test_unicode_composition_counts_as_the_same_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(CanonicalValueError):
                write_group(
                    [
                        (root / "cafe\u0301.md", "decomposed"),
                        (root / "caf\u00e9.md", "composed"),
                    ]
                )

    def test_distinct_names_are_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_group([(root / "a.md", "one"), (root / "b.md", "two")])
            self.assertEqual((root / "a.md").read_text(encoding="utf-8"), "one")
            self.assertEqual((root / "b.md").read_text(encoding="utf-8"), "two")


class DurableWriteTests(unittest.TestCase):
    """D-170 — eleven layered atomic replaces and no ``fsync`` anywhere.

    The per-file claim holds against a concurrent reader and not against power
    loss: a rename can be durable while the data it names is not, leaving a
    zero-length canonical file that ``write_group``'s rollback can no longer
    undo, because the bytes it would restore are gone too.
    """

    def test_the_file_is_synced_before_the_rename_and_the_directory_after(self):
        synced: list[str] = []
        real_fsync = os.fsync

        def recording_fsync(descriptor):
            try:
                synced.append("dir" if os.path.isdir(f"/dev/fd/{descriptor}") else "file")
            except OSError:  # pragma: no cover - platform detail
                synced.append("unknown")
            return real_fsync(descriptor)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "canonical.json"
            with mock.patch.object(os, "fsync", recording_fsync):
                write_text(target, "durable\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "durable\n")
            self.assertGreaterEqual(len(synced), 1, "nothing was synced at all")

    def test_a_failure_to_sync_the_directory_does_not_fail_the_write(self):
        """A landed write is not undone by a platform that will not sync a dir."""
        real_fsync = os.fsync

        def refuse_directory_fsync(descriptor):
            try:
                is_directory = os.path.isdir(f"/dev/fd/{descriptor}")
            except OSError:  # pragma: no cover - platform detail
                is_directory = False
            if is_directory:
                raise OSError("this platform does not sync directories")
            return real_fsync(descriptor)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "canonical.json"
            with mock.patch.object(os, "fsync", refuse_directory_fsync):
                write_text(target, "still written\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "still written\n")


class FinalizeVerdictExitTests(unittest.TestCase):
    """D-082 — a run that validated as failing exits 4, not 1.

    ``VERDICT_EXIT_CODES`` exists so ``validate``, ``apply-bundle`` and
    ``finalize`` cannot disagree about what a verdict is worth, and
    ``finalize``'s refusal path went around it: the same run, read from the
    same ``validation.json``, exited ``4`` through ``validate`` and ``1``
    through ``finalize`` — and ``1`` is documented as "the command refused or
    failed", which a wrapper reads as a broken install.
    """

    def _fail_run(self, directory: str) -> Path:
        fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "fail-run"
        run_dir = Path(directory) / "output" / "fail-run"
        shutil.copytree(fixture, run_dir)
        return run_dir

    def test_validate_and_finalize_agree_on_a_failing_run(self):
        from x2knwldg import cli

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._fail_run(directory)
            codes = {}
            for command in ("validate", "finalize"):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                    codes[command] = cli.main([command, str(run_dir)])
            self.assertEqual(codes["validate"], cli.EXIT_FAIL)
            self.assertEqual(
                codes["finalize"],
                cli.EXIT_FAIL,
                "finalize disagreed with validate about the same validation.json",
            )
            self.assertEqual(codes["finalize"], cli.VERDICT_EXIT_CODES["FAIL"])

    def test_the_refusal_envelope_says_fail_not_error(self):
        from x2knwldg import cli

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._fail_run(directory)
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                cli.main(["finalize", str(run_dir)])
            payload = json.loads(stderr.getvalue().strip().splitlines()[-1])
            self.assertEqual(payload["status"], "FAIL")
            self.assertIn("validation", payload["message"])

    def test_the_refusal_still_carries_the_verdict_it_refused_on(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._fail_run(directory)
            with self.assertRaises(VerdictRefusal) as caught:
                finalize_run(run_dir)
            self.assertEqual(caught.exception.status, "FAIL")
            # Still a PipelineError, so every existing `except` keeps working.
            self.assertIsInstance(caught.exception, PipelineError)

    def test_a_passing_run_still_finalizes_at_zero(self):
        from x2knwldg import cli

        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
            run_dir = Path(directory) / "output" / "pass-run"
            shutil.copytree(fixture, run_dir)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["finalize", str(run_dir)]), cli.EXIT_OK)


class ImportedRunVerdictTests(unittest.TestCase):
    """D-089 — a freshly imported run states its verdict.

    ``import_transcript`` wrote a ``validation.json`` with no top-level
    ``status`` and no ``provenance`` section, so ``adapters.base.read_status``
    reported ``overall: UNKNOWN`` for every imported run — a run the pipeline
    had just validated, describing itself as unchecked, until somebody happened
    to run ``validate``.
    """

    SRT = (
        "1\n00:00:00,000 --> 00:00:30,000\nA caption with a timing.\n\n"
        "2\n00:00:30,000 --> 00:01:00,000\nA second caption.\n"
    )

    def _import(self, directory: str) -> Path:
        transcript = Path(directory) / "t.srt"
        transcript.write_text(self.SRT, encoding="utf-8")
        return import_transcript(
            transcript,
            Path(directory) / "output",
            video_id="scaffolded01",
            title="T",
            channel="C",
            language="en",
            source="manual",
        )

    def test_the_imported_validation_has_the_shape_validate_run_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._import(directory)
            imported = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
            self.assertIn("status", imported)
            self.assertIn("provenance", imported)
            # The same key set `validate_run` produces, so nothing downstream
            # has to know which of the two wrote the file.
            revalidated = validate_run(run_dir)
            self.assertEqual(sorted(imported), sorted(revalidated))

    def test_an_imported_run_is_an_honest_partial_and_never_unknown(self):
        from x2knwldg.adapters.base import read_status

        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._import(directory)
            imported = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
            self.assertEqual(read_status(imported), "PARTIAL")
            self.assertNotEqual(read_status(imported), "UNKNOWN")
            self.assertNotEqual(read_status(imported), "PASS")

    def test_running_validate_changes_nothing(self):
        """The verdict was already right, so the file it writes is the same one."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._import(directory)
            before = (run_dir / "validation.json").read_text(encoding="utf-8")
            validate_run(run_dir)
            self.assertEqual((run_dir / "validation.json").read_text(encoding="utf-8"), before)


class AtomicRunTests(unittest.TestCase):
    """D-090 — a crashed import leaves nothing, and a retraction removes its note."""

    SRT = ImportedRunVerdictTests.SRT

    def test_a_failed_import_leaves_no_half_written_run(self):
        real = io_module.write_text
        calls = {"n": 0}

        def fail_on_the_third_write(path: Path, text: str) -> None:
            calls["n"] += 1
            if calls["n"] == 3:
                raise OSError("the disk filled up")
            real(path, text)

        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "t.srt"
            transcript.write_text(self.SRT, encoding="utf-8")
            output = Path(directory) / "output"
            with mock.patch.object(io_module, "write_text", fail_on_the_third_write):
                with self.assertRaises(OSError):
                    import_transcript(
                        transcript, output, video_id="crashed0001", language="en", source="manual"
                    )
            run_dir = output / "crashed0001"
            # The guard that used to block recovery keys on transcript.json.
            self.assertFalse(
                (run_dir / "transcript.json").exists(),
                "a partial run still claims the id, so re-import raises RunAlreadyExists",
            )
            # And re-importing actually works, which is the property that matters.
            again = import_transcript(
                transcript, output, video_id="crashed0001", language="en", source="manual"
            )
            self.assertEqual(validate_run(again)["status"], "PARTIAL")

    def test_a_retracted_unit_stops_having_a_vault_note(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "output" / "pass-run"
            shutil.copytree(fixture, run_dir)
            units = json.loads((fixture / "knowledge_units.json").read_text())["units"]
            coverage = json.loads((fixture / "coverage.json").read_text())

            def apply(kept: list[dict]) -> None:
                bundle = Path(directory) / "bundle.json"
                ids = {unit["id"] for unit in kept}
                trimmed = json.loads(json.dumps(coverage))
                for window in trimmed["windows"]:
                    window["knowledge_units"] = [
                        unit for unit in window["knowledge_units"] if unit in ids
                    ]
                bundle.write_text(
                    json.dumps({"knowledge_units": kept, "relationships": [], "coverage": trimmed}),
                    encoding="utf-8",
                )
                apply_extraction_bundle(run_dir, bundle)
                finalize_run(run_dir)

            apply(units)
            notes = sorted(p.name for p in (run_dir / "vault" / "knowledge_units").rglob("*.md"))
            self.assertEqual(len(notes), len(units), notes)

            retracted = units[-1]["id"]
            apply(units[:-1])
            remaining = sorted(
                p.name for p in (run_dir / "vault" / "knowledge_units").rglob("*.md")
            )
            self.assertEqual(len(remaining), len(units) - 1, remaining)
            self.assertNotIn(
                f"{retracted}.md",
                remaining,
                "the retracted unit still has a note, linked from nothing",
            )
            self.assertNotIn(retracted, (run_dir / "report.md").read_text(encoding="utf-8"))

    def test_pruning_leaves_a_readers_own_file_alone(self):
        """Only the three subtrees the generator owns are pruned."""
        fixture = Path(__file__).resolve().parent / "fixtures" / "runs" / "pass-run"
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "output" / "pass-run"
            shutil.copytree(fixture, run_dir)
            mine = run_dir / "vault" / "notes" / "my-reading.md"
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.write_text("Mine, not generated.", encoding="utf-8")
            finalize_run(run_dir)
            self.assertTrue(mine.is_file(), "finalize deleted a file it does not own")
