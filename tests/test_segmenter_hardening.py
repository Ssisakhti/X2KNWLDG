"""The segmenter must honour the contract it advertises (defects S1–S3).

An external audit fuzzed ``create_segments`` 3,000 times and found no caption
loss, no runaway, and deterministic tie-breaking. The module is sound. What it
was not was *honest*: ``max_sec`` was a hint the scorer could overrule, the
coupled-bounds guard raised one opaque sentence for four different mistakes
(and a bare ``TypeError`` for a fifth), and the overlap a single-caption
segment cannot deliver was neither delivered nor mentioned.

These tests pin the contract the module docstring now states, so a future
change has to break a test rather than a promise. Nothing here reads or writes
``output/``.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from x2knwldg import constants
from x2knwldg.segmenter import create_segments

DEFAULT_MAX = constants.SEGMENT_MAX_SEC


def caption(index: int, start: float, end: float, *, ends_thought: bool = True) -> dict[str, Any]:
    return {
        "segment_id": f"cap_{index:06d}",
        "start_sec": float(start),
        "end_sec": float(end),
        "text": f"caption {index}" + ("." if ends_thought else ""),
    }


def uniform(count: int, length: float = 5.0, *, ends_thought: bool = True) -> list[dict[str, Any]]:
    return [
        caption(index, index * length, (index + 1) * length, ends_thought=ends_thought)
        for index in range(count)
    ]


# --------------------------------------------------------------------------
# S1 — max_sec is a bound, not a preference
# --------------------------------------------------------------------------


#: The minimal input that made the old scorer overrule ``max_sec``: a 130s
#: candidate that reaches ``min_sec`` and a 365s one that overruns ``max_sec``
#: by five seconds but ends a sentence. The boundary bonus of 30s bought the
#: overrun a better score (125 - 30 = 95) than the legal end (110), so the
#: segmenter chose a 365s segment with a 130s one available.
OVER_MAX_CAPTIONS = [
    {"segment_id": "cap_000000", "start_sec": 0.0, "end_sec": 130.0, "text": "no full stop here"},
    {"segment_id": "cap_000001", "start_sec": 130.0, "end_sec": 365.0, "text": "ends a thought."},
    {"segment_id": "cap_000002", "start_sec": 365.0, "end_sec": 400.0, "text": "tail."},
]


def test_a_legal_end_is_preferred_over_a_better_scoring_overrun() -> None:
    """REGRESSION: the first segment used to run 365s against a max of 360."""
    first = create_segments(OVER_MAX_CAPTIONS)[0]
    assert first["end_sec"] - first["start_sec"] <= DEFAULT_MAX
    assert first["caption_ids"] == ["cap_000000"]


@pytest.mark.parametrize("seed", range(60))
def test_an_overrun_only_happens_when_no_legal_end_exists(seed: int) -> None:
    """REGRESSION: a fuzz sweep of the bound the old code only suggested.

    A segment may exceed ``max_sec`` only when the caption boundaries offered
    no end inside ``[min_sec, max_sec]`` — which shows up as: drop the final
    caption and what remains is shorter than ``min_sec``. Any other overrun
    means a legal end was available and the scorer overruled the bound, which
    is precisely what it used to do.
    """
    rng = random.Random(seed)
    captions: list[dict[str, Any]] = []
    cursor = 0.0
    for index in range(rng.randint(4, 90)):
        length = rng.choice([0.0, 1.5, 5.0, 40.0, 130.0, 240.0, 400.0])
        captions.append(
            caption(index, cursor, cursor + length, ends_thought=rng.random() < 0.4)
        )
        cursor += length + rng.choice([0.0, 0.5, 30.0])

    by_id = {item["segment_id"]: item for item in captions}
    segments = create_segments(captions)
    for segment in segments:
        length = segment["end_sec"] - segment["start_sec"]
        if length <= DEFAULT_MAX:
            continue
        held = segment["caption_ids"]
        without_last = (
            0.0
            if len(held) == 1
            else by_id[held[-2]]["end_sec"] - segment["start_sec"]
        )
        assert without_last < constants.SEGMENT_MIN_SEC, (
            f"{segment['segment_id']} runs {length}s over a max of {DEFAULT_MAX}s "
            f"while a legal end at {without_last}s was available"
        )


def test_a_single_caption_longer_than_max_is_emitted_whole() -> None:
    """The documented exception. Splitting it would invent a caption id."""
    captions = [caption(0, 0, 1000), caption(1, 1000, 1005)]
    segments = create_segments(captions)
    assert segments[0]["caption_ids"] == ["cap_000000"]
    assert segments[0]["end_sec"] - segments[0]["start_sec"] == 1000


def test_an_overrun_is_taken_at_its_shortest() -> None:
    """When no end respects max_sec, the least violation wins over the score."""
    captions = [
        {"segment_id": "cap_000000", "start_sec": 0.0, "end_sec": 500.0, "text": "long"},
        {"segment_id": "cap_000001", "start_sec": 500.0, "end_sec": 900.0, "text": "longer."},
        {"segment_id": "cap_000002", "start_sec": 900.0, "end_sec": 905.0, "text": "tail."},
    ]
    assert create_segments(captions)[0]["caption_ids"] == ["cap_000000"]


# --------------------------------------------------------------------------
# S2 — the advertised range says which bound is wrong, and rejects non-bounds
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "named"),
    [
        ({"target_sec": 100}, "min_sec"),
        ({"max_sec": 200}, "max_sec"),
        ({"overlap_sec": 120}, "overlap_sec"),
        ({"overlap_sec": 121}, "overlap_sec"),
    ],
)
def test_a_rejected_bound_names_the_pair_that_disagrees(kwargs: dict, named: str) -> None:
    """REGRESSION: one opaque sentence used to cover four different mistakes.

    ``Expected 0 <= overlap < min <= target <= max`` restated the chain without
    saying which link broke, so the caller was told the rule and left to find
    the parameter — and the four bounds are coupled, which is exactly the fact
    the message needed to convey.
    """
    with pytest.raises(ValueError) as raised:
        create_segments(uniform(60), **kwargs)
    message = str(raised.value)
    assert named in message
    assert "Expected 0 <= overlap < min <= target <= max" != message


@pytest.mark.parametrize("bound", ["target_sec", "min_sec", "max_sec", "overlap_sec"])
@pytest.mark.parametrize("value", [None, "240", float("nan"), float("inf"), -1, [240]])
def test_a_bound_that_is_not_a_number_of_seconds_is_a_value_error(
    bound: str, value: Any
) -> None:
    """REGRESSION: a string or None bound raised a bare TypeError from a
    comparison, and NaN raised the opaque message without saying why."""
    with pytest.raises(ValueError) as raised:
        create_segments(uniform(60), **{bound: value})
    assert bound in str(raised.value)


def test_the_bounds_are_reachable_at_their_stated_limits() -> None:
    """The advertised range is closed at both ends: min == target == max and
    an overlap just under min are legal, not accidents of the guard."""
    captions = uniform(120)
    assert create_segments(captions, target_sec=120, min_sec=120, max_sec=120)
    assert create_segments(captions, target_sec=240, min_sec=120, max_sec=360, overlap_sec=119)
    assert create_segments(captions, target_sec=30, min_sec=30, max_sec=30, overlap_sec=0)


def test_the_defaults_are_the_shared_contract_constants() -> None:
    """Drift guard: the four numbers have one home (constants.py)."""
    assert create_segments.__defaults__ == (
        constants.SEGMENT_TARGET_SEC,
        constants.SEGMENT_MIN_SEC,
        constants.SEGMENT_MAX_SEC,
        constants.SEGMENT_OVERLAP_SEC,
    )
    assert (
        constants.SEGMENT_OVERLAP_SEC
        < constants.SEGMENT_MIN_SEC
        <= constants.SEGMENT_TARGET_SEC
        <= constants.SEGMENT_MAX_SEC
    )


# --------------------------------------------------------------------------
# S3 — overlap is caption-granular, and says so
# --------------------------------------------------------------------------


def test_a_single_caption_segment_carries_no_overlap() -> None:
    """Pinned, not fixed — and the docstring now says so.

    Overlap is re-emitted captions. A segment of one caption has only itself to
    re-emit, and re-emitting it would start the next segment where this one
    started, so the walk would not advance. Zero overlap here is the honest
    consequence of atomic captions, not a lapse; this test exists so it stays a
    stated consequence rather than becoming a surprise.
    """
    captions = [caption(0, 0, 200), caption(1, 200, 400), caption(2, 400, 405)]
    segments = create_segments(captions, overlap_sec=60)
    assert segments[0]["caption_ids"] == ["cap_000000"]
    assert segments[1]["caption_ids"][0] == "cap_000001"
    assert segments[1]["start_sec"] == segments[0]["end_sec"]  # no overlap at all


@pytest.mark.parametrize("overlap", [0, 15, 60, 119])
def test_overlap_is_a_floor_quantised_to_one_caption(overlap: float) -> None:
    """The realised overlap is at least what was asked for, and at most that
    plus the length of one caption."""
    length = 5.0
    captions = uniform(200, length)
    segments = create_segments(captions, overlap_sec=overlap)
    # Pairwise: the two sequences differ in length by one on purpose.
    for previous, following in zip(segments, segments[1:], strict=False):
        if len(previous["caption_ids"]) == 1:
            continue
        realised = previous["end_sec"] - following["start_sec"]
        assert overlap <= realised <= overlap + length


# --------------------------------------------------------------------------
# The properties the audit's 3,000-case fuzz established, kept in the suite
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(40))
def test_every_caption_survives_and_the_walk_is_deterministic(seed: int) -> None:
    rng = random.Random(seed + 5000)
    captions: list[dict[str, Any]] = []
    cursor = 0.0
    for index in range(rng.randint(1, 120)):
        length = rng.choice([0.0, 2.0, 5.0, 61.0, 300.0])
        captions.append(
            caption(index, cursor, cursor + length, ends_thought=rng.random() < 0.5)
        )
        cursor += length

    segments = create_segments(captions)
    covered = {caption_id for segment in segments for caption_id in segment["caption_ids"]}
    assert covered == {item["segment_id"] for item in captions}
    assert segments == create_segments(captions)
    assert [segment["segment_id"] for segment in segments] == [
        f"seg_{index + 1:04d}" for index in range(len(segments))
    ]
    starts = [segment["start_sec"] for segment in segments]
    assert starts == sorted(starts)
    ends = [segment["end_sec"] for segment in segments]
    assert ends == sorted(ends)


def test_an_empty_caption_list_is_an_empty_segment_list() -> None:
    assert create_segments([]) == []


# ---------------------------------------------------------------------------
# D-098 — a redundant, text-empty segment is not offered as extraction input
# ---------------------------------------------------------------------------


def test_a_long_non_speech_cue_does_not_mint_an_empty_subset_segment() -> None:
    """The walk could emit a segment whose captions are a *subset* of the
    previous one's and whose text is empty — an input segment with nothing in
    it to extract from, handed to passes 1 and 4 as though it held content.

    Zero occurrences over the 500 realistic transcripts the audit fuzzed;
    specifically a `[music]` cue long enough to reach `max_sec` on its own.
    """
    captions = [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 20.0, "text": "Real speech."},
        # A single non-speech cue that spans more than max_sec on its own.
        {"segment_id": "cap_000002", "start_sec": 20.0, "end_sec": 400.0, "text": "",
         "non_speech": True},
        {"segment_id": "cap_000003", "start_sec": 400.0, "end_sec": 420.0, "text": "More speech."},
    ]
    segments = create_segments(captions)

    empty_subsets = [
        segment
        for index, segment in enumerate(segments)
        if index > 0
        and not segment["text"].strip()
        and set(segment["caption_ids"]) <= set(segments[index - 1]["caption_ids"])
    ]
    assert not empty_subsets, empty_subsets


def test_no_caption_is_lost_when_a_redundant_segment_is_skipped() -> None:
    """The invariant the skip must not break: every caption is in some segment.

    Skipped only when the captions are already carried by the previous
    segment — a text-empty segment covering captions nothing else does is still
    emitted, because dropping *that* would lose them.
    """
    captions = [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 20.0, "text": "Real speech."},
        {"segment_id": "cap_000002", "start_sec": 20.0, "end_sec": 400.0, "text": "",
         "non_speech": True},
        {"segment_id": "cap_000003", "start_sec": 400.0, "end_sec": 420.0, "text": "More speech."},
    ]
    segments = create_segments(captions)
    covered = {caption_id for segment in segments for caption_id in segment["caption_ids"]}
    assert covered == {caption["segment_id"] for caption in captions}


def test_a_transcript_of_only_silence_still_produces_a_segment() -> None:
    """There is no previous segment to be a subset of, so nothing is skipped."""
    captions = [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 400.0, "text": "",
         "non_speech": True},
    ]
    segments = create_segments(captions)
    assert len(segments) == 1
    assert segments[0]["caption_ids"] == ["cap_000001"]


def test_segment_ids_stay_contiguous_when_one_is_skipped() -> None:
    """`seg_0001, seg_0002, …` with no gap: the id is the count, not the loop."""
    captions = [
        {"segment_id": "cap_000001", "start_sec": 0.0, "end_sec": 20.0, "text": "One."},
        {"segment_id": "cap_000002", "start_sec": 20.0, "end_sec": 400.0, "text": "",
         "non_speech": True},
        {"segment_id": "cap_000003", "start_sec": 400.0, "end_sec": 420.0, "text": "Two."},
        {"segment_id": "cap_000004", "start_sec": 420.0, "end_sec": 800.0, "text": "",
         "non_speech": True},
    ]
    segments = create_segments(captions)
    assert [segment["segment_id"] for segment in segments] == [
        f"seg_{index + 1:04d}" for index in range(len(segments))
    ]
