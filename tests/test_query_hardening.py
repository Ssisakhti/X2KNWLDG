"""Regression tests for the search path's invented values and dead queries.

Four findings from the Phase 0 audit, all in ``query.py``:

* a caption with no ``start_sec`` was filed at second 0 with a fabricated
  ``&t=0s`` deep link — a timestamp for a moment nothing happened at;
* ``metadata["video_id"]`` was indexed directly, so a run whose metadata states
  no id raised a bare ``KeyError`` that escaped the D-030 taxonomy;
* no unicode normalisation, single-character tokens dropped, and scriptless
  writing taken as one token — three ways for a query to match nothing and say
  nothing about why;
* ``max(1, limit)`` answered ``limit=0`` with one result.

Every test here was checked against the pre-fix module before the fix landed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x2knwldg.pipeline import PipelineError
from x2knwldg.query import UnsearchableRun, run_documents, search_knowledge

CAPTION_TEXT = "the segmenter groups captions into windows"
UNIT_TEXT = "windows are audited for coverage"


def write_run(
    root: Path,
    video_id: str | None = "vid1",
    *,
    caption_start: object = 0.0,
    include_caption_start: bool = True,
    unit_start: object = 1.0,
    include_unit_start: bool = True,
    text: str = CAPTION_TEXT,
    content: str = UNIT_TEXT,
) -> Path:
    """One canonical run, with exactly the damage a test asks for."""
    run_dir = root / (video_id or "no-id")
    run_dir.mkdir(parents=True)
    metadata: dict[str, object] = {"title": "A talk"}
    if video_id is not None:
        metadata["video_id"] = video_id
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    source: dict[str, object] = {"segment_id": "SEG-000001", "evidence_excerpt": content}
    if include_unit_start:
        source["start_sec"] = unit_start
    (run_dir / "knowledge_units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "id": "KU-000001",
                        "kind": "claim",
                        "source_class": "source",
                        "content": content,
                        "confidence": 0.9,
                        "source": source,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    caption: dict[str, object] = {"segment_id": "cap_000001", "text": text, "end_sec": 5.0}
    if include_caption_start:
        caption["start_sec"] = caption_start
    (run_dir / "transcript.json").write_text(
        json.dumps({"captions": [caption]}), encoding="utf-8"
    )
    return run_dir


# ---------------------------------------------------------------------------
# The invented timestamp
# ---------------------------------------------------------------------------


def test_a_caption_without_a_timing_is_refused_not_filed_at_zero(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, include_caption_start=False)
    with pytest.raises(UnsearchableRun) as caught:
        run_documents(run_dir)
    assert "cap_000001" in str(caught.value)
    assert "start_sec" in str(caught.value)


@pytest.mark.parametrize("bad", [None, "0", "", True, False, [], {}])
def test_a_caption_timing_that_is_not_a_number_is_refused(tmp_path: Path, bad: object) -> None:
    """A string, a bool or a null is not a timing. ``True`` is an ``int``."""
    run_dir = write_run(tmp_path, caption_start=bad)
    with pytest.raises(UnsearchableRun):
        run_documents(run_dir)


def test_a_real_zero_timing_is_still_a_timing(tmp_path: Path) -> None:
    """The fix must refuse an *absent* timing, not a caption that starts at 0."""
    run_dir = write_run(tmp_path, caption_start=0.0)
    captions = [d for d in run_documents(run_dir) if d.hit["type"] == "transcript_caption"]
    assert len(captions) == 1
    assert captions[0].hit["start_sec"] == 0.0
    assert captions[0].hit["source_url"].endswith("&t=0s")


def test_every_caption_hit_carries_what_the_contract_requires(tmp_path: Path) -> None:
    """``SearchHitTranscriptCaption`` requires ``start_sec`` and ``source_url``.

    That is why a caption with no timing has to be refused rather than emitted
    without them: the frozen contract has no shape for it.
    """
    run_dir = write_run(tmp_path)
    for document in run_documents(run_dir):
        if document.hit["type"] != "transcript_caption":
            continue
        for field in ("type", "video_id", "title", "caption_id", "content",
                      "start_sec", "end_sec", "source_url"):
            assert field in document.hit, field


def test_a_unit_without_a_timing_gets_neither_a_timing_nor_a_link(tmp_path: Path) -> None:
    """The unit half of the same finding: absent, not zero (and no deep link)."""
    run_dir = write_run(tmp_path, include_unit_start=False)
    units = [d for d in run_documents(run_dir) if d.hit["type"] == "knowledge_unit"]
    assert len(units) == 1
    assert "start_sec" not in units[0].hit
    assert "source_url" not in units[0].hit


# ---------------------------------------------------------------------------
# The bare KeyError
# ---------------------------------------------------------------------------


def test_a_run_that_states_no_video_id_does_not_raise_a_key_error(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, video_id=None)
    documents = run_documents(run_dir)          # used to raise KeyError('video_id')
    assert [d.hit["type"] for d in documents] == ["knowledge_unit"]
    assert documents[0].hit["video_id"] is None
    assert "source_url" not in documents[0].hit


def test_a_run_that_states_no_video_id_still_searches_its_units(tmp_path: Path) -> None:
    """Its captions are left out — no honest link exists — but it is not dark."""
    write_run(tmp_path, video_id=None)
    hits = search_knowledge(tmp_path, "coverage")
    assert [hit["type"] for hit in hits] == ["knowledge_unit"]


def test_an_unsearchable_run_is_a_value_error_for_the_repository_seam() -> None:
    """``MemoryRepository`` records an unreadable source and carries on.

    It catches ``(OSError, ValueError)``; a refusal outside that pair would
    escape as a 500 instead, which is the failure this finding was about.
    """
    assert issubclass(UnsearchableRun, ValueError)


# ---------------------------------------------------------------------------
# Queries that used to match nothing
# ---------------------------------------------------------------------------


def test_a_full_width_query_matches_its_composed_form(tmp_path: Path) -> None:
    write_run(tmp_path, content="coverage windows", text="coverage windows")
    assert search_knowledge(tmp_path, "ｃｏｖｅｒａｇｅ")  # NFKC-normalised


def test_a_decomposed_query_matches_its_composed_form(tmp_path: Path) -> None:
    write_run(tmp_path, content="café recording", text="café recording")
    assert search_knowledge(tmp_path, "café")


def test_a_scriptless_query_split_on_a_space_still_matches(tmp_path: Path) -> None:
    """``\\w+`` takes 機械学習 as one token; a query of 機械 学習 shared nothing."""
    write_run(tmp_path, content="機械学習について", text="機械学習について")
    assert search_knowledge(tmp_path, "機械 学習")


def test_a_single_scriptless_character_matches(tmp_path: Path) -> None:
    write_run(tmp_path, content="機械学習", text="機械学習")
    assert search_knowledge(tmp_path, "習")


def test_a_query_of_only_short_words_is_answerable(tmp_path: Path) -> None:
    """Tokens of one character were dropped, so this matched nothing at all."""
    write_run(tmp_path, content="p vs q in the proof", text="p vs q in the proof")
    hits = search_knowledge(tmp_path, "q p")
    assert hits, "a query of one-character words returned nothing"


def test_folding_is_the_same_on_both_sides(tmp_path: Path) -> None:
    """A document written full-width is found by a query written normally."""
    write_run(tmp_path, content="ＣＯＶＥＲＡＧＥ ａｕｄｉｔ", text="ＣＯＶＥＲＡＧＥ ａｕｄｉｔ")
    assert search_knowledge(tmp_path, "coverage audit")


def test_an_ordinary_query_still_ranks_the_unit_above_the_caption(tmp_path: Path) -> None:
    """The scoring rule is unchanged: a caption is worth half a unit."""
    write_run(tmp_path, content="coverage windows", text="coverage windows")
    hits = search_knowledge(tmp_path, "coverage windows")
    assert [hit["type"] for hit in hits] == ["knowledge_unit", "transcript_caption"]


def test_a_query_that_matches_nothing_still_matches_nothing(tmp_path: Path) -> None:
    write_run(tmp_path)
    assert search_knowledge(tmp_path, "kubernetes") == []


# ---------------------------------------------------------------------------
# The limit
# ---------------------------------------------------------------------------


def test_a_limit_of_zero_is_refused_rather_than_answered_with_one(tmp_path: Path) -> None:
    write_run(tmp_path)
    with pytest.raises(PipelineError) as caught:
        search_knowledge(tmp_path, "coverage", limit=0)
    assert "at least 1" in str(caught.value)


@pytest.mark.parametrize("bad", [-1, -100])
def test_a_negative_limit_is_refused(tmp_path: Path, bad: int) -> None:
    write_run(tmp_path)
    with pytest.raises(PipelineError):
        search_knowledge(tmp_path, "coverage", limit=bad)


@pytest.mark.parametrize("bad", ["10", 1.5, None, True])
def test_a_limit_that_is_not_a_whole_number_is_refused(tmp_path: Path, bad: object) -> None:
    """``True`` is an ``int`` in Python, and is not a page size."""
    write_run(tmp_path)
    with pytest.raises(PipelineError):
        search_knowledge(tmp_path, "coverage", limit=bad)  # type: ignore[arg-type]


def test_a_limit_of_one_returns_one(tmp_path: Path) -> None:
    write_run(tmp_path, content="coverage windows", text="coverage windows")
    assert len(search_knowledge(tmp_path, "coverage", limit=1)) == 1


def test_a_limit_larger_than_the_corpus_returns_the_corpus(tmp_path: Path) -> None:
    """There is no arbitrary ceiling here; the data is the bound."""
    write_run(tmp_path, content="coverage windows", text="coverage windows")
    assert len(search_knowledge(tmp_path, "coverage", limit=10_000)) == 2
