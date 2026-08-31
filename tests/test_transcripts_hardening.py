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
    parse_timestamp,
    parse_transcript_file,
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


if __name__ == "__main__":
    unittest.main()
