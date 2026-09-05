"""Regression tests for confirmed transcript-ingestion data loss and corruption.

Every test here reproduces a defect that an external audit demonstrated by
execution. ``transcript.json`` is the canonical extraction input (WORKFLOW.md
section 2), so a cue silently dropped, an extent silently shrunk, or a ``<``
silently eaten on the way in is not recoverable later in the pipeline.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from x2knwldg.coverage import create_pending_coverage
from x2knwldg.io import read_json, write_json
from x2knwldg.transcripts import (
    TranscriptError,
    captions_from_items,
    clean_text,
    comparable_text,
    parse_timestamp,
    parse_transcript_file,
    transcript_end_sec,
    transcript_integrity,
)


def _write(directory: str, name: str, text: str) -> Path:
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return path


class CleanTextTests(unittest.TestCase):
    """Case 03: ``<[^>]+>`` ate every inequality, threshold and generic."""

    def test_comparison_operators_are_not_markup(self):
        for value in (
            "if x < 5 and y > 3",
            "revenue grew <10% but >5%",
            "List<String> generic",
            "a < b < c",
            "temperature < -40 degrees",
        ):
            with self.subTest(value=value):
                self.assertEqual(clean_text(value), value)

    def test_caption_markup_is_still_removed(self):
        self.assertEqual(
            clean_text(
                "<00:00:01.000><c.colorE5E5E5> hello</c> "
                "<v.loud Alice>there</v> <b>bold</b> <i>tilt</i> <lang en>x</lang>"
            ),
            "hello there bold tilt x",
        )

    def test_escaped_markup_stays_text(self):
        self.assertEqual(clean_text("compare &lt;b&gt; with &amp; and 3 &gt; 2"),
                         "compare <b> with & and 3 > 2")

    def test_markup_in_a_vtt_cue_is_stripped_but_operators_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "ops.vtt",
                "WEBVTT\n\n"
                "00:00:00.000 --> 00:00:02.000\n"
                "<b>Set</b> the flag when x < 5 and y > 3.\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(captions[0]["text"], "Set the flag when x < 5 and y > 3.")


class VttBlockSkipTests(unittest.TestCase):
    """Case 06.1: a block judged by its first line dropped real cues."""

    def test_hls_header_glued_to_the_first_cue_keeps_that_cue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "hls.vtt",
                "WEBVTT\n"
                "X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:900000\n"
                "00:00:02.000 --> 00:00:03.000\n"
                "first cue\n\n"
                "00:00:04.000 --> 00:00:05.000\n"
                "second cue\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(
                [(caption["end_sec"], caption["text"]) for caption in captions],
                [(3.0, "first cue"), (5.0, "second cue")],
            )
            self.assertNotIn("original_id", captions[0])

    def test_cue_identifier_beginning_with_note_is_not_a_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "noteid.vtt",
                "WEBVTT\n\n"
                "NOTEID-1\n"
                "00:00:02.000 --> 00:00:03.000\n"
                "first\n\n"
                "STYLEGUIDE\n"
                "00:00:04.000 --> 00:00:05.000\n"
                "second\n\n"
                "REGIONAL\n"
                "00:00:06.000 --> 00:00:07.000\n"
                "third\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(
                [caption["text"] for caption in captions], ["first", "second", "third"]
            )
            self.assertEqual(captions[0]["original_id"], "NOTEID-1")

    def test_real_note_style_and_region_blocks_are_still_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "meta.vtt",
                "WEBVTT\n\n"
                "NOTE this is a comment\nwith a second line\n\n"
                "STYLE\n::cue { color: yellow }\n\n"
                "REGION\nid=fred width=40%\n\n"
                "00:00:02.000 --> 00:00:03.000\n"
                "only cue\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual([caption["text"] for caption in captions], ["only cue"])


class WhitespaceInsideCueTests(unittest.TestCase):
    """Case 06.3: a whitespace-only line inside a cue split and lost the rest."""

    def test_srt_cue_containing_a_whitespace_only_line_keeps_every_cue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "ws.srt",
                "1\n00:00:00,000 --> 00:00:04,500\nfirst line\n   \nsecond line\n\n"
                "2\n00:00:04,500 --> 00:00:09,000\nlater cue\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 2)
            self.assertEqual(captions[0]["text"], "first line second line")
            self.assertEqual(captions[1]["text"], "later cue")
            self.assertEqual(captions[1]["original_id"], "2")

    def test_whitespace_only_separator_between_cues_does_not_merge_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "sep.srt",
                "1\n00:00:00,000 --> 00:00:04,500\nfirst\n \n"
                "2\n00:00:04,500 --> 00:00:09,000\nsecond\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(
                [(caption["end_sec"], caption["text"]) for caption in captions],
                [(4.5, "first"), (9.0, "second")],
            )


class SilentCueTests(unittest.TestCase):
    """Case 06.2: a cue whose text cleans to empty shrank the audited extent."""

    def _tail_silence(self, directory: str) -> Path:
        return _write(
            directory,
            "silence.vtt",
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:05.000\nspoken words\n\n"
            "00:09:55.000 --> 00:10:00.000\n \n",
        )

    def test_a_trailing_silent_cue_cannot_shrink_the_reported_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            captions = parse_transcript_file(self._tail_silence(directory), language="en")
            integrity = transcript_integrity(captions, max_gap_sec=1200)
            self.assertEqual(integrity["stats"]["duration_sec"], 600.0)
            self.assertEqual(integrity["status"], "PASS")

    def test_a_silent_cue_does_not_shrink_the_audited_window_set(self):
        with tempfile.TemporaryDirectory() as directory:
            captions = parse_transcript_file(self._tail_silence(directory), language="en")
            coverage = create_pending_coverage(captions, "abc123def45", window_sec=300)
            self.assertEqual(len(coverage["windows"]), 2)
            self.assertEqual(coverage["windows"][-1]["end_sec"], 600.0)
            self.assertTrue(
                all(window["caption_ids"] for window in coverage["windows"]),
                "a window was audited with no captions attached",
            )

    def test_a_silent_cue_is_marked_rather_than_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            captions = parse_transcript_file(self._tail_silence(directory), language="en")
            self.assertEqual(captions[-1]["text"], "")
            self.assertTrue(captions[-1]["non_speech"])

    def test_an_entry_with_neither_text_nor_timing_is_still_skipped(self):
        captions = captions_from_items(
            [{}, {"text": "real", "start_sec": 0, "end_sec": 1}], "test", "en"
        )
        self.assertEqual(len(captions), 1)

    def test_empty_text_without_the_marker_is_still_an_integrity_error(self):
        integrity = transcript_integrity(
            [{"segment_id": "cap_000001", "start_sec": 0, "end_sec": 1, "text": ""}]
        )
        self.assertEqual(integrity["status"], "FAIL")
        self.assertIn("empty_text", {error["code"] for error in integrity["errors"]})


class ZeroLengthCaptionTests(unittest.TestCase):
    """Case 06.4: json3 events with no duration, orphaned from every window."""

    def test_json3_event_without_a_duration_gets_a_non_zero_extent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "captions.json",
                json.dumps(
                    {
                        "events": [
                            {"tStartMs": 0, "segs": [{"utf8": "first"}]},
                            {"tStartMs": 4000, "segs": [{"utf8": "second"}]},
                            {"tStartMs": 8000, "segs": [{"utf8": "last"}]},
                        ]
                    }
                ),
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 3)
            for caption in captions:
                with self.subTest(caption=caption["segment_id"]):
                    self.assertGreater(caption["duration_sec"], 0)
            self.assertEqual(captions[0]["end_sec"], 4.0)

    def test_a_zero_length_caption_is_still_assigned_to_a_window(self):
        captions = [
            {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 0.0, "text": "at zero"},
            {"segment_id": "cap_000002", "start_sec": 10.0, "end_sec": 20.0, "text": "middle"},
            {"segment_id": "cap_000003", "start_sec": 20.0, "end_sec": 20.0, "text": "at the end"},
        ]
        coverage = create_pending_coverage(captions, "abc123def45", window_sec=300)
        assigned = {
            caption_id
            for window in coverage["windows"]
            for caption_id in window["caption_ids"]
        }
        self.assertEqual(assigned, {caption["segment_id"] for caption in captions})

    def test_a_zero_length_caption_on_a_window_boundary_lands_in_one_window(self):
        captions = [
            {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 10.0, "text": "a"},
            {"segment_id": "cap_000002", "start_sec": 300.0, "end_sec": 300.0, "text": "boundary"},
            {"segment_id": "cap_000003", "start_sec": 590.0, "end_sec": 600.0, "text": "b"},
        ]
        coverage = create_pending_coverage(captions, "abc123def45", window_sec=300)
        placements = [
            window["window_id"]
            for window in coverage["windows"]
            if "cap_000002" in window["caption_ids"]
        ]
        self.assertEqual(placements, ["CW-0002"])


class FirstGapTests(unittest.TestCase):
    """Case 06.5: ``previous_end`` started at a falsy 0.0, hiding the first gap."""

    def test_silence_before_the_first_caption_raises_a_gap_warning(self):
        captions = [
            {"segment_id": "cap_000001", "start_sec": 3600.0, "end_sec": 3605.0, "text": "late"}
        ]
        integrity = transcript_integrity(captions, max_gap_sec=120)
        gaps = [warning for warning in integrity["warnings"] if warning["code"] == "large_gap"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["start_sec"], 0)
        self.assertEqual(gaps[0]["end_sec"], 3600.0)

    def test_a_transcript_that_starts_promptly_raises_no_gap_warning(self):
        captions = [
            {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 5.0, "text": "prompt"},
            {"segment_id": "cap_000002", "start_sec": 5.0, "end_sec": 9.0, "text": "next"},
        ]
        integrity = transcript_integrity(captions, max_gap_sec=120)
        self.assertEqual(
            [], [w for w in integrity["warnings"] if w["code"] == "large_gap"]
        )


class NonFiniteNumberTests(unittest.TestCase):
    """NaN/Infinity passed every check and reached canonical JSON."""

    def test_integrity_rejects_non_finite_timing(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                integrity = transcript_integrity(
                    [
                        {
                            "segment_id": "cap_000001",
                            "start_sec": 0.0,
                            "end_sec": value,
                            "text": "text",
                        }
                    ]
                )
                self.assertEqual(integrity["status"], "FAIL")
                self.assertIn(
                    "invalid_timing", {error["code"] for error in integrity["errors"]}
                )

    def test_integrity_stats_stay_serializable_when_timing_is_non_finite(self):
        integrity = transcript_integrity(
            [
                {
                    "segment_id": "cap_000001",
                    "start_sec": 0.0,
                    "end_sec": math.inf,
                    "text": "text",
                }
            ]
        )
        self.assertTrue(math.isfinite(integrity["stats"]["duration_sec"]))

    def test_parsing_rejects_a_non_finite_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "nan.json",
                '{"captions": [{"start_sec": 0, "end_sec": NaN, "text": "boom"}]}',
            )
            with self.assertRaises(TranscriptError):
                parse_transcript_file(path, language="en")

    def test_captions_from_items_rejects_a_non_finite_duration(self):
        with self.assertRaises(TranscriptError):
            captions_from_items(
                [{"start_sec": 0, "duration_sec": math.inf, "text": "boom"}], "test", "en"
            )

    def test_write_json_refuses_non_finite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            with self.assertRaises(ValueError):
                write_json(path, {"duration_sec": math.nan})
            self.assertFalse(path.exists())

    def test_read_json_refuses_non_finite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "in.json", '{"duration_sec": Infinity}')
            with self.assertRaises(ValueError):
                read_json(path)


class WriteJsonCleanupTests(unittest.TestCase):
    def test_a_failed_write_leaves_no_temp_file_behind(self):
        class Unserializable:
            pass

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaises(TypeError):
                write_json(output / "canonical.json", {"value": Unserializable()})
            self.assertEqual([], sorted(path.name for path in output.iterdir()))

    def test_a_successful_write_round_trips_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / "canonical.json", {"video_id": "abc123def45"})
            self.assertEqual(
                ["canonical.json"], sorted(path.name for path in output.iterdir())
            )
            self.assertEqual(
                read_json(output / "canonical.json"), {"video_id": "abc123def45"}
            )


class TimestampAndTimedTextTests(unittest.TestCase):
    def test_an_empty_timestamp_raises_a_transcript_error(self):
        for value in ("", "   ", "\t"):
            with self.subTest(value=value):
                with self.assertRaises(TranscriptError):
                    parse_timestamp(value)

    def test_an_srt_cue_missing_its_end_time_raises_a_transcript_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "broken.srt", "1\n00:00:00,000 --> \ntext\n")
            with self.assertRaises(TranscriptError):
                parse_transcript_file(path, language="en")

    def test_bracketed_caption_text_is_not_mistaken_for_a_timing_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "timed.txt",
                "[00:00:00 - 00:00:05] Welcome to the talk.\n"
                "[Applause - laughter]\n"
                "[00:00:05 - 00:00:10] Now the first point.\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 2)
            self.assertEqual(captions[0]["text"], "Welcome to the talk. [Applause - laughter]")
            self.assertEqual(captions[1]["start_sec"], 5.0)


class CueTimingLineTests(unittest.TestCase):
    """D-076 — ``-->`` inside a caption is text, not a cue timing line.

    ``_cue_chunks`` located cues with ``if "-->" in line``, so a caption whose
    own words contain ``-->`` was read as a timing line and
    ``parse_timestamp`` rejected the **whole file** with
    ``Invalid timestamp: 'The'``. The module had already solved this exact
    class of problem for ``[Applause - laughter]`` by restricting
    ``_TIMED_TEXT`` to timestamp shapes; the same guard was simply missing here.
    """

    def test_an_arrow_in_a_caption_does_not_reject_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "arrow.srt",
                "1\n00:00:00,000 --> 00:00:05,000\nThe mapping A --> B is important.\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 1)
            self.assertEqual(captions[0]["text"], "The mapping A --> B is important.")
            self.assertEqual(captions[0]["end_sec"], 5.0)

    def test_an_arrow_in_a_vtt_caption_keeps_every_cue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "arrow.vtt",
                "WEBVTT\n\n"
                "00:00:00.000 --> 00:00:05.000\nInput --> output is the whole idea.\n\n"
                "00:00:05.000 --> 00:00:10.000\nAnd A --> B --> C chains.\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 2)
            self.assertEqual(captions[0]["text"], "Input --> output is the whole idea.")
            self.assertEqual(captions[1]["text"], "And A --> B --> C chains.")

    def test_a_cue_whose_end_is_damaged_is_still_reported(self):
        """Only the *left* side is anchored, so a real cue with a broken end
        still reaches ``parse_timestamp`` instead of becoming body text."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "broken.srt", "1\n00:00:00,000 --> oops\ntext\n")
            with self.assertRaises(TranscriptError):
                parse_transcript_file(path, language="en")

    def test_the_timing_detector_and_the_parser_accept_the_same_timestamps(self):
        """Three patterns for one grammar, so they are asserted equal here.

        ``_TIMED_TEXT`` used to carry a fourth spelling allowing four leading
        digits where the parser allows two, so ``[1234:56 - 1300:00]`` was
        detected as a header and then refused by ``parse_timestamp``, rejecting
        the whole file.
        """
        from x2knwldg.transcripts import _CUE_TIMING, _TIMED_TEXT, _TIMESTAMP

        accepted = ["0:00", "00:00", "00:00:00", "00:00:00,000", "1:02:03.45", "9999:00:00.000"]
        rejected = ["The", "A --> B", "", "00", "x:00:00", "00:000:00", "1234:56"]
        for value in accepted:
            self.assertIsNotNone(_TIMESTAMP.match(value), value)
            self.assertIsNotNone(_CUE_TIMING.match(f"{value} --> {value}"), value)
            self.assertIsNotNone(_TIMED_TEXT.match(f"[{value} - {value}] text"), value)
        for value in rejected:
            self.assertIsNone(_CUE_TIMING.match(f"{value} --> 00:00:01,000"), value)
            self.assertIsNone(_TIMED_TEXT.match(f"[{value} - 00:00:01,000] text"), value)

    def test_a_bracket_that_is_not_a_timestamp_reads_as_text(self):
        """The stated intent of the header grammar's restriction.

        ``[1234:56 - 1300:00]`` matched the header shape and then failed the
        parser, and the *whole file* was rejected — for a line the comment says
        should read as ordinary bracketed caption text.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "brackets.md",
                "[00:00:00 - 00:00:05] A real header.\n"
                "[1234:56 - 1300:00] Not a timestamp, so this is text.\n",
            )
            captions = parse_transcript_file(path, language="en")
            self.assertEqual(len(captions), 1)
            self.assertIn("Not a timestamp", captions[0]["text"])


class CorruptCanonicalTests(unittest.TestCase):
    """D-077 — a damaged canonical file is a finding, not a traceback.

    ``max((c.get("end_sec", 0) for c in captions), default=0)`` existed four
    times at three different guard levels. The loose copies raised
    ``AttributeError`` on a caption that is a string and ``TypeError`` on one
    whose ``end_sec`` is ``null`` — because ``max`` then compares ``None`` with
    a float — and both escaped ``validate`` and ``finalize`` as raw tracebacks.
    There is now one implementation, ``transcripts.transcript_end_sec``.
    """

    def test_a_caption_that_is_not_an_object_is_named(self):
        result = transcript_integrity(["not a caption"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("caption_not_object", {e["code"] for e in result["errors"]})

    def test_captions_that_are_not_an_array_are_named(self):
        for captions in ({"cap_1": {}}, "captions", 7, None):
            with self.subTest(captions=captions):
                result = transcript_integrity(captions)
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("captions_not_array", {e["code"] for e in result["errors"]})

    def test_the_duration_of_a_damaged_transcript_is_zero_not_a_crash(self):
        for captions in (
            ["oops"],
            [{"start_sec": 0.0, "end_sec": None}],
            [{"start_sec": 0.0, "end_sec": "5"}],
            [{"start_sec": 0.0, "end_sec": float("nan")}],
            [{"start_sec": 0.0, "end_sec": True}],
            "captions",
            None,
        ):
            with self.subTest(captions=captions):
                self.assertEqual(transcript_end_sec(captions), 0.0)

    def test_a_damaged_caption_does_not_hide_a_healthy_one(self):
        captions = ["oops", {"start_sec": 0.0, "end_sec": 12.5, "text": "hi"}]
        self.assertEqual(transcript_end_sec(captions), 12.5)
        self.assertEqual(transcript_integrity(captions)["stats"]["duration_sec"], 12.5)

    def test_the_duration_helper_is_the_one_every_caller_uses(self):
        """The consolidation itself: no caller may keep a private copy."""
        import re
        from pathlib import Path

        import x2knwldg.artifacts
        import x2knwldg.pipeline
        import x2knwldg.transcripts
        import x2knwldg.validators

        pattern = re.compile(r'max\(\s*\(?\s*caption\.get\("end_sec"')
        for module in (
            x2knwldg.artifacts,
            x2knwldg.pipeline,
            x2knwldg.validators,
            x2knwldg.transcripts,
        ):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertIsNone(
                pattern.search(source),
                f"{module.__name__} has its own copy of the duration expression",
            )


if __name__ == "__main__":
    unittest.main()


class CoverageWindowBoundTests(unittest.TestCase):
    """D-097 — the window end has one real edge, not two.

    `min(duration, (index + 1) * window_sec)` could never bind: with
    `window_count = ceil(duration / window_sec)`, every index below the last
    puts `(index + 1) * window_sec` strictly below `duration`. A guard that
    cannot fire reads as a bound the caller has to think about.
    """

    def test_windows_are_contiguous_and_end_at_the_duration(self):
        for duration in (1.0, 59.9, 60.0, 60.1, 119.0, 600.0, 3601.0):
            with self.subTest(duration=duration):
                captions = [
                    {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": duration, "text": "x"}
                ]
                windows = create_pending_coverage(captions, "vid")["windows"]
                self.assertEqual(windows[0]["start_sec"], 0.0)
                self.assertEqual(windows[-1]["end_sec"], round(duration, 3))
                for previous, following in zip(windows, windows[1:], strict=False):
                    self.assertEqual(previous["end_sec"], following["start_sec"])

    def test_no_window_reaches_past_the_duration(self):
        """What the dead `min` was there to prevent, asserted directly."""
        for duration in (0.5, 30.0, 60.0, 90.0, 601.0):
            with self.subTest(duration=duration):
                captions = [
                    {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": duration, "text": "x"}
                ]
                windows = create_pending_coverage(captions, "vid")["windows"]
                for window in windows:
                    self.assertLessEqual(window["end_sec"], round(duration, 3))
                    self.assertLess(window["start_sec"], window["end_sec"] + 1e-9)


class SeparatorlessSrtTests(unittest.TestCase):
    """D-165: SRT written without blank separators between cues.

    Ordinary output from real muxers, and the trim heuristic that removes the
    next cue's identifier from this cue's text needed a blank line to fire. So
    every cue absorbed the next cue's index number — and the corruption landed
    in the canonical ``transcript.json``, which is the extraction input and,
    through the segments, the text every evidence excerpt is matched against.
    """

    SEPARATED = (
        "1\n00:00:01,000 --> 00:00:03,000\nOne.\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\nTwo.\n\n"
        "3\n00:00:05,000 --> 00:00:07,000\nThree.\n"
    )
    RUN_TOGETHER = (
        "1\n00:00:01,000 --> 00:00:03,000\nOne.\n"
        "2\n00:00:03,000 --> 00:00:05,000\nTwo.\n"
        "3\n00:00:05,000 --> 00:00:07,000\nThree.\n"
    )

    def _captions(self, text):
        with tempfile.TemporaryDirectory() as directory:
            return parse_transcript_file(_write(directory, "cues.srt", text))

    def test_the_text_is_the_same_with_and_without_blank_separators(self):
        expected = [(1.0, 3.0, "One."), (3.0, 5.0, "Two."), (5.0, 7.0, "Three.")]
        for label, text in (
            ("with separators", self.SEPARATED),
            ("without separators", self.RUN_TOGETHER),
        ):
            with self.subTest(label):
                captions = self._captions(text)
                self.assertEqual(
                    [(c["start_sec"], c["end_sec"], c["text"]) for c in captions], expected
                )

    def test_the_identifiers_survive_too(self):
        captions = self._captions(self.RUN_TOGETHER)
        self.assertEqual([c.get("original_id") for c in captions], ["1", "2", "3"])

    def test_a_caption_ending_in_a_number_keeps_it_when_a_blank_line_follows(self):
        """Only a bare integer *immediately* before a timing line is an index."""
        text = (
            "1\n00:00:01,000 --> 00:00:03,000\nThe answer is 42\n\n"
            "2\n00:00:03,000 --> 00:00:05,000\nTwo.\n"
        )
        self.assertEqual([c["text"] for c in self._captions(text)], ["The answer is 42", "Two."])


class WideFractionTests(unittest.TestCase):
    """D-165: the fraction was capped at three digits.

    ``00:00:01,0000`` matched no timing grammar, so every timing line fell
    through to body text and the file was rejected as *"No timestamped cues
    were found"* — contradicting the docstring's promise that a damaged timing
    line reaches ``parse_timestamp`` and is reported.
    """

    def test_a_four_digit_fraction_is_read_as_a_decimal_fraction(self):
        self.assertEqual(parse_timestamp("00:00:01,0000"), 1.0)
        self.assertEqual(parse_timestamp("00:00:01.2500"), 1.25)
        self.assertEqual(parse_timestamp("00:00:01,5"), 1.5)

    def test_a_file_using_them_parses_rather_than_being_rejected(self):
        text = "1\n00:00:01,0000 --> 00:00:02,5000\nWide fraction.\n"
        with tempfile.TemporaryDirectory() as directory:
            captions = parse_transcript_file(_write(directory, "wide.srt", text))
        self.assertEqual(
            [(c["start_sec"], c["end_sec"], c["text"]) for c in captions],
            [(1.0, 2.5, "Wide fraction.")],
        )


class EmptyTranscriptTests(unittest.TestCase):
    """D-167: timing, no words, ``PASS``, exit ``0``.

    A caption source that renames its text field produces cues that clean away
    to nothing, and ``_canonical_caption`` marks each one ``non_speech`` — the
    ``[music]`` concession — which is exactly what disarms the ``empty_text``
    check. ``character_count`` was already computed and read by nothing.
    """

    def _captions(self, texts):
        return captions_from_items(
            [
                {"text": text, "start": float(index * 10), "duration": 10.0}
                for index, text in enumerate(texts)
            ],
            language="en",
            source="youtube_caption",
        )

    def test_a_transcript_with_no_text_at_all_fails(self):
        captions = self._captions(["", "", ""])
        result = transcript_integrity(captions)
        self.assertEqual(result["stats"]["character_count"], 0)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("transcript_has_no_text", {e["code"] for e in result["errors"]})

    def test_the_music_concession_still_holds_for_a_single_cue(self):
        """One non-speech cue among real ones keeps its timing and passes."""
        captions = self._captions(["Something said.", "[music]", "Something else."])
        result = transcript_integrity(captions)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertGreater(result["stats"]["character_count"], 0)
        self.assertEqual(len(captions), 3, "the silent cue keeps its place in the timeline")

    def test_an_empty_caption_list_is_not_a_textless_transcript(self):
        """Nothing to say about a transcript with no captions; other checks own that."""
        result = transcript_integrity([])
        self.assertNotIn("transcript_has_no_text", {e["code"] for e in result["errors"]})


class MediaDurationCoverageTests(unittest.TestCase):
    """D-168: coverage was measured against the transcript, not the video.

    ``fetch_metadata`` discarded ``duration`` from the yt-dlp info dict, so
    ``duration_sec`` became the caption span, the windows were minted over that
    span, and ``timeline_not_fully_covered`` compared coverage against it too.
    A caption track covering the first ten minutes of a two-hour talk therefore
    yielded a fully covered timeline — and no comparison between those three
    numbers could ever detect the truncation, because all three derived from
    the same truncated number.
    """

    #: Ten minutes of captions on a two-hour video.
    CAPTIONS = [
        {
            "segment_id": f"cap_{index:06d}",
            "start_sec": float(index * 60),
            "end_sec": float((index + 1) * 60),
            "text": "Something said.",
        }
        for index in range(10)
    ]

    def test_windows_are_minted_over_the_video_when_its_length_is_known(self):
        captions_only = create_pending_coverage(self.CAPTIONS, "vid")
        self.assertEqual(len(captions_only["windows"]), 2, "600s at 300s per window")

        whole_video = create_pending_coverage(self.CAPTIONS, "vid", duration_sec=7200.0)
        self.assertEqual(len(whole_video["windows"]), 24, "7200s at 300s per window")
        self.assertEqual(whole_video["windows"][-1]["end_sec"], 7200.0)

    def test_the_windows_past_the_captions_have_nothing_to_audit(self):
        document = create_pending_coverage(self.CAPTIONS, "vid", duration_sec=7200.0)
        with_captions = [w for w in document["windows"] if w["caption_ids"]]
        self.assertEqual(len(with_captions), 2)
        self.assertTrue(
            all(not w["caption_ids"] for w in document["windows"][2:]),
            "twenty-two windows of video no caption covers, stated rather than hidden",
        )

    def test_a_shorter_reported_duration_never_shrinks_the_timeline(self):
        """The captions are evidence; a duration that contradicts them loses."""
        document = create_pending_coverage(self.CAPTIONS, "vid", duration_sec=60.0)
        self.assertEqual(document["windows"][-1]["end_sec"], 600.0)


class RefusalTests(unittest.TestCase):
    """Every refusal this module can raise, executed once.

    Eight ``raise TranscriptError`` statements had no test that reached them,
    and they are not incidental: together they are the gate CLAUDE.md states as
    "never accept untimed plain text as strict YouTube provenance". A gate whose
    branches are never run is a gate nobody has opened to check which way it
    swings — a predicate inverted here would let an untimed file through and
    2233 passing tests would have said nothing.

    Each case names the message, because the message is what the operator acts
    on: "give me a timestamped file" and "this file is not UTF-8" call for
    different repairs.
    """

    def test_a_caption_with_neither_end_nor_duration_is_refused(self):
        """``_canonical_caption``: a cue with a start and no extent."""
        with self.assertRaises(TranscriptError) as caught:
            captions_from_items([{"start_sec": 0.0, "text": "hello"}], "test", "en")
        self.assertIn("end_sec or duration", str(caught.exception))

    def test_a_subtitle_file_with_no_cues_is_refused(self):
        """``_parse_srt_or_vtt``: prose in a ``.srt``, with no timing anywhere."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "notes.srt", "Just some notes.\n\nAnd more notes.\n")
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("No timestamped cues", str(caught.exception))

    def test_transcript_json_that_is_neither_object_nor_array_is_refused(self):
        """``_json_items``: a bare scalar at the top of a ``.json``."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "t.json", '"a transcript"')
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("must be an object or an array", str(caught.exception))

    def test_transcript_json_with_no_recognized_caption_list_is_refused(self):
        """``_json_items``: an object carrying none of the four known keys."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "t.json", json.dumps({"lines": [{"text": "hi"}]}))
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("no recognized caption list", str(caught.exception))

    def test_malformed_transcript_json_is_refused_by_name(self):
        """``_parse_json``: the decoder's own complaint is carried through."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "t.json", "{not json")
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("Invalid transcript JSON", str(caught.exception))

    def test_a_caption_list_holding_nothing_usable_is_refused(self):
        """``captions_from_items``: entries that are not captions at all.

        The list is present and non-empty, which is exactly why this refusal
        exists: "there were items" is not "there were captions".
        """
        with self.assertRaises(TranscriptError) as caught:
            captions_from_items(["a line", 7, None], "test", "en")  # type: ignore[list-item]
        self.assertIn("No usable timestamped captions", str(caught.exception))

        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "t.json", json.dumps({"captions": []}))
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("no usable timestamped captions", str(caught.exception))

    def test_untimed_plain_text_is_refused(self):
        """``_parse_timed_text``: the gate CLAUDE.md names in as many words.

        A ``.txt`` or ``.md`` of prose has no timing, so nothing extracted from
        it could ever cite a moment. It is refused with the header shape the
        operator has to supply, rather than accepted and filed at second zero.
        """
        for suffix in (".txt", ".md"):
            with self.subTest(suffix=suffix):
                with tempfile.TemporaryDirectory() as directory:
                    path = _write(
                        directory,
                        f"notes{suffix}",
                        "He opens by saying the model is wrong.\nThen he explains why.\n",
                    )
                    with self.assertRaises(TranscriptError) as caught:
                        parse_transcript_file(path)
                self.assertIn("[HH:MM:SS - HH:MM:SS]", str(caught.exception))

    def test_a_transcript_that_is_not_utf8_is_refused(self):
        """``parse_transcript_file``: decoded, not mangled into replacement chars."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cues.srt"
            path.write_bytes(
                b"1\n00:00:00,000 --> 00:00:02,000\nca\xa0ption\n"
            )
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
        self.assertIn("UTF-8", str(caught.exception))

    def test_an_unsupported_extension_is_refused_by_name(self):
        """``parse_transcript_file``: and an extensionless file says so too."""
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "captions.docx", "anything")
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(path)
            self.assertIn(".docx", str(caught.exception))

            bare = _write(directory, "captions", "anything")
            with self.assertRaises(TranscriptError) as caught:
                parse_transcript_file(bare)
            self.assertIn("(no extension)", str(caught.exception))


class CleanTextIdempotenceTests(unittest.TestCase):
    """``clean_text`` decodes, so cleaning twice invents a string nothing said.

    The defect this pins was in ``validators.validate_provenance``, which ran
    the parse-time cleaner over both the evidence excerpt and the already-clean
    segment text it was matched against. The second ``html.unescape`` decoded
    the stored text a second time, so an excerpt that appears in no canonical
    file of the run matched it and was reported as proven provenance.
    """

    def test_clean_text_is_not_idempotent_and_says_so(self):
        stored = clean_text("the token is &amp;amp; and nothing else")
        self.assertEqual(stored, "the token is &amp; and nothing else")
        self.assertEqual(clean_text(stored), "the token is & and nothing else")
        self.assertNotEqual(clean_text(stored), stored)

    def test_comparable_text_is_idempotent(self):
        for value in (
            "the token is &amp; and nothing else",
            "compare <b> with & and 3 > 2",
            "  spaced\nout ​text ",
            "<c.yellow>markup</c> around it",
        ):
            with self.subTest(value=value):
                once = comparable_text(value)
                self.assertEqual(comparable_text(once), once)

    def test_comparable_text_leaves_entities_alone(self):
        """The one step removed, and the only one."""
        self.assertEqual(
            comparable_text("the token is &amp; and nothing else"),
            "the token is &amp; and nothing else",
        )

    def test_comparable_text_keeps_the_forgiveness_clean_text_granted(self):
        """Markup and whitespace still fold, because both folds are idempotent."""
        self.assertEqual(comparable_text("  <i>carry the evidence</i>\n"), "carry the evidence")
