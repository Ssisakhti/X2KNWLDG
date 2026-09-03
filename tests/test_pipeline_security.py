"""Regression tests for the audited defects in ``pipeline.py`` and ``cli.py``.

Every test here was written against a *proven* failure, and each one is
phrased so that reverting the fix — including by the exact source mutation the
audit used — turns it red.

The five defects, in the order they appear below:

1. ``extract_video_id`` matched its host with ``"youtube.com" in hostname``, so
   ``youtube.com.evil.example`` and ``notyoutube.com`` both yielded a real
   11-character id. ``cli._run_process`` read that non-``None`` id as "this is
   a YouTube URL" and handed the *whole URL* to ``yt_dlp``, whose generic
   extractor fetches whatever it is given: an SSRF, and captions from an
   attacker's host filed under a genuine YouTube id.
2. ``validate_run`` never cross-checked ``coverage.json`` against
   ``knowledge_units.json``, so emptying the unit store while coverage kept
   claiming ``covered`` still reported ``PASS``.
3. ``validate_run``'s ``FAIL`` and ``PARTIAL`` branches had no test caller at
   all — the audit replaced ``if not validators_pass:`` with ``if False:`` and
   deleted the ``PARTIAL`` branch, and the suite stayed green both times.
4. ``_safe_identifier`` *rewrote* ids (``my.video.2024`` → ``my_video_2024``)
   that every lookup path rejects, creating runs at addresses nothing could
   retrieve them by, and silently colliding.
5. An interrupted import left ``raw/`` behind and every later retry died on
   ``FileExistsError``; and the CLI caught only ``PipelineError``, exited ``0``
   for ``PARTIAL``, and let one corrupt ``metadata.json`` take down ``status``
   for every video.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from x2knwldg import cli
from x2knwldg.ids import is_id_part
from x2knwldg.pipeline import (
    PipelineError,
    RunAlreadyExists,
    extract_video_id,
    import_transcript,
    is_youtube_url,
    resolve_run_dir,
    validate_run,
)
from x2knwldg.transcripts import TranscriptError

FIXTURES = Path(__file__).parent / "fixtures"
RUNS = FIXTURES / "runs"
SAMPLE = FIXTURES / "sample.vtt"

#: A real, well-formed YouTube id. Every hostile URL below carries this exact
#: id, because that is what made the defect dangerous: the id was genuine and
#: only the host was the attacker's.
REAL_ID = "dQw4w9WgXcQ"


def run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Invoke ``cli.main`` and return ``(exit code, stdout, stderr)``."""
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def writable_run(tmp_path: Path, name: str) -> Path:
    """A writable copy of a committed fixture run.

    ``validate_run`` writes ``validation.json``, so it must never be pointed at
    ``tests/fixtures/runs/`` — other tests assert those files are untouched.
    """
    target = tmp_path / name
    shutil.copytree(RUNS / name, target)
    return target


# ---------------------------------------------------------------------------
# 1. The YouTube host allowlist  (pipeline.extract_video_id, cli._run_process)
# ---------------------------------------------------------------------------

#: The two the audit proved, plus the userinfo trick and the same idea spelled
#: several other ways. Each one returned ``REAL_ID`` before the fix.
HOSTILE_URLS = [
    # Proven by the audit.
    f"https://youtube.com.evil.example/watch?v={REAL_ID}",
    f"https://notyoutube.com/watch?v={REAL_ID}",
    # Userinfo: the host a client connects to is `evil.example`.
    f"https://youtube.com@evil.example/watch?v={REAL_ID}",
    f"https://www.youtube.com:pass@evil.example/watch?v={REAL_ID}",
    # Subdomain, suffix, and infix variations on the same substring.
    f"https://evil-youtube.com/watch?v={REAL_ID}",
    f"https://youtube.com.attacker.test/shorts/{REAL_ID}",
    f"https://xyoutube.com/watch?v={REAL_ID}",
    f"https://youtube.company/watch?v={REAL_ID}",
    f"https://youtu.be.evil.example/{REAL_ID}",
    # The string in the path rather than the host.
    f"http://evil.example/youtube.com/watch?v={REAL_ID}",
    # An extra trailing dot is not the absolute-DNS form of a real host.
    f"https://youtube.com../watch?v={REAL_ID}",
]

#: Hosts YouTube actually serves. Each must still yield the id.
LEGITIMATE_URLS = [
    f"https://www.youtube.com/watch?v={REAL_ID}",
    f"https://youtube.com/watch?v={REAL_ID}",
    f"https://m.youtube.com/watch?v={REAL_ID}",
    f"https://music.youtube.com/watch?v={REAL_ID}",
    f"https://www.youtube.com/shorts/{REAL_ID}",
    f"https://www.youtube.com/embed/{REAL_ID}",
    f"https://www.youtube-nocookie.com/embed/{REAL_ID}",
    f"https://youtu.be/{REAL_ID}",
    f"https://www.youtu.be/{REAL_ID}",
    # Case and the absolute-DNS trailing dot are the same host.
    f"https://WWW.YouTube.COM/watch?v={REAL_ID}",
    f"https://www.youtube.com./watch?v={REAL_ID}",
    # Extra query parameters, and a timestamp fragment.
    f"https://www.youtube.com/watch?v={REAL_ID}&t=42s&list=PLabc",
]

#: Things the audit found correctly rejected, which must stay rejected.
NON_YOUTUBE_SOURCES = [
    "file:///etc/passwd",
    "file://localhost/etc/passwd",
    "javascript:alert(1)",
    f"ytsearch:{REAL_ID}",
    "ytsearch1:some query",
    "https://example.com/",
    "https://vimeo.com/123456789",
    "http://127.0.0.1:8080/watch?v=" + REAL_ID,
    "",
    "   ",
    "https://",
]


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_a_lookalike_host_yields_no_video_id(url: str) -> None:
    """The whole defect: a genuine id extracted from an attacker's host."""
    assert extract_video_id(url) is None


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_a_lookalike_host_is_not_a_youtube_url(url: str) -> None:
    assert is_youtube_url(url) is False


@pytest.mark.parametrize("url", LEGITIMATE_URLS)
def test_a_real_youtube_url_still_yields_its_id(url: str) -> None:
    assert extract_video_id(url) == REAL_ID
    assert is_youtube_url(url) is True


@pytest.mark.parametrize("source", NON_YOUTUBE_SOURCES)
def test_a_non_youtube_source_yields_no_video_id(source: str) -> None:
    assert extract_video_id(source) is None
    assert is_youtube_url(source) is False


def test_a_bare_local_identifier_is_still_accepted() -> None:
    """``--video-url`` is optional; a bare id must keep working."""
    assert extract_video_id(REAL_ID) == REAL_ID
    assert extract_video_id("local-lecture-01") == "local-lecture-01"
    assert extract_video_id("short") is None  # under six characters


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_process_refuses_a_lookalike_host_without_fetching_it(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal has to happen *before* anything reaches ``yt_dlp``.

    Returning an id was treated as proof the URL was YouTube's, so the SSRF is
    only closed if the fetch never starts.
    """
    import x2knwldg.youtube as youtube

    def must_not_run(*args: object, **kwargs: object) -> Path:  # pragma: no cover
        raise AssertionError(f"the pipeline fetched an attacker-controlled URL: {url}")

    monkeypatch.setattr(youtube, "process_youtube_url", must_not_run)
    code, _, err = run_cli(
        [
            "process",
            url,
            "--output",
            str(tmp_path / "output"),
            "--inbox",
            str(tmp_path / "inbox"),
        ],
        capsys,
    )
    assert code == cli.EXIT_ERROR
    assert json.loads(err)["status"] == "ERROR"
    # It must not be dressed up as "go find a transcript for this video"
    # either: no run and no inbox may be created for the attacker's host.
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "inbox").exists()


def test_process_checks_the_host_itself_and_not_only_the_extracted_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI must not delegate "is this YouTube?" to "did an id come back?".

    Those are different questions, and conflating them is the whole defect:
    ``extract_video_id`` answers "does this string contain a plausible id",
    which an attacker controls completely. Here it is forced to answer yes for
    a hostile host, and the fetch must still never start.
    """
    import x2knwldg.youtube as youtube

    hostile = f"https://youtube.com.evil.example/watch?v={REAL_ID}"

    def must_not_run(*args: object, **kwargs: object) -> Path:  # pragma: no cover
        raise AssertionError("the host check was skipped because an id was returned")

    monkeypatch.setattr(cli, "extract_video_id", lambda value: REAL_ID)
    monkeypatch.setattr(youtube, "process_youtube_url", must_not_run)
    code, _, err = run_cli(
        [
            "process",
            hostile,
            "--output",
            str(tmp_path / "output"),
            "--inbox",
            str(tmp_path / "inbox"),
        ],
        capsys,
    )
    assert code == cli.EXIT_ERROR
    assert "evil.example" in json.loads(err)["message"]


# ---------------------------------------------------------------------------
# 2. validate_run re-links coverage.json to knowledge_units.json
# ---------------------------------------------------------------------------


def test_coverage_naming_a_nonexistent_unit_fails_the_run(tmp_path: Path) -> None:
    """The audit's exact reproduction: empty the unit store, keep the claim.

    ``coverage.json`` still says ``covered`` and names ``KU-000001``; nothing
    by that id exists any more. Coverage asserting evidence that is not there
    is the fabrication AGENTS.md forbids, and it used to report ``PASS``.
    """
    run_dir = writable_run(tmp_path, "pass-run")
    assert validate_run(run_dir)["status"] == "PASS", "the fixture must start out passing"

    knowledge = json.loads((run_dir / "knowledge_units.json").read_text(encoding="utf-8"))
    knowledge["units"] = []
    (run_dir / "knowledge_units.json").write_text(json.dumps(knowledge), encoding="utf-8")

    result = validate_run(run_dir)
    assert result["status"] == "FAIL"
    assert result["coverage"]["status"] == "FAIL"
    codes = {error["code"] for error in result["coverage"]["errors"]}
    assert "coverage_references_unknown_unit" in codes


def test_the_failing_verdict_is_written_to_validation_json(tmp_path: Path) -> None:
    """``validation.json`` is the run's standing verdict; it must not lag."""
    run_dir = writable_run(tmp_path, "pass-run")
    knowledge = json.loads((run_dir / "knowledge_units.json").read_text(encoding="utf-8"))
    knowledge["units"] = []
    (run_dir / "knowledge_units.json").write_text(json.dumps(knowledge), encoding="utf-8")
    validate_run(run_dir)
    on_disk = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "FAIL"


def test_coverage_naming_one_missing_unit_among_several_still_fails(tmp_path: Path) -> None:
    """A single dangling reference is enough; it need not be all of them."""
    run_dir = writable_run(tmp_path, "pass-run")
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    coverage["windows"][0]["knowledge_units"].append("KU-999999")
    (run_dir / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")

    result = validate_run(run_dir)
    assert result["status"] == "FAIL"
    dangling = {
        error.get("value")
        for error in result["coverage"]["errors"]
        if error["code"] == "coverage_references_unknown_unit"
    }
    assert dangling == {"KU-999999"}


def test_a_coverage_pass_that_omits_a_source_unit_fails(tmp_path: Path) -> None:
    """The other direction of the same cross-check.

    ``apply_extraction_bundle`` already refuses this at write time; the
    canonical files can be edited afterwards, so the standing verdict has to
    refuse it too.
    """
    run_dir = writable_run(tmp_path, "pass-run")
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    coverage["windows"][0]["knowledge_units"] = []
    coverage["windows"][0]["omitted_items"] = [
        {"type": "other_explained", "note": "Claimed as accounted for."}
    ]
    (run_dir / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")

    result = validate_run(run_dir)
    assert result["status"] == "FAIL"
    codes = {error["code"] for error in result["coverage"]["errors"]}
    assert "coverage_pass_omits_source_units" in codes


def test_an_honest_partial_is_not_punished_by_the_cross_check(tmp_path: Path) -> None:
    """A PARTIAL run has uncovered windows by definition. That is not a defect."""
    run_dir = writable_run(tmp_path, "partial-run")
    result = validate_run(run_dir)
    assert result["coverage"]["status"] == "PASS"
    assert result["status"] == "PARTIAL"


# ---------------------------------------------------------------------------
# 3. Every branch of validate_run's verdict is reachable and correct
# ---------------------------------------------------------------------------
#
# `validate_run` has four production call sites — the CLI, the MCP server,
# `apply_extraction_bundle` and `finalize_run` — and had no test caller. These
# call it directly. Each of the two mutations the audit used is named against
# the test that now kills it.


def test_a_complete_run_validates_as_pass(tmp_path: Path) -> None:
    assert validate_run(writable_run(tmp_path, "pass-run"))["status"] == "PASS"


def test_a_run_with_a_failing_section_validates_as_fail(tmp_path: Path) -> None:
    """Kills ``if not validators_pass:`` → ``if False:``.

    ``fail-run``'s own ``coverage.json`` says ``PASS``, so with the ``FAIL``
    branch disabled the verdict would fall through the ``PARTIAL`` test and
    land on ``PASS`` — a run citing evidence absent from its transcript,
    reported as a pass.
    """
    result = validate_run(writable_run(tmp_path, "fail-run"))
    assert result["status"] == "FAIL"
    assert result["provenance"]["status"] == "FAIL"
    assert "evidence_excerpt_not_in_segment" in {
        error["code"] for error in result["provenance"]["errors"]
    }


def test_a_failing_section_is_never_softened_to_partial(tmp_path: Path) -> None:
    """FAIL means invalid. PARTIAL means honestly incomplete. Not interchangeable."""
    assert validate_run(writable_run(tmp_path, "fail-run"))["status"] != "PARTIAL"


def test_a_run_with_incomplete_coverage_validates_as_partial(tmp_path: Path) -> None:
    """Kills the deletion of the ``PARTIAL`` branch.

    Every section passes and only ``coverage.json``'s own status is short of
    ``PASS``; without the branch the run reports ``PASS`` and completion could
    be claimed on it, which CLAUDE.md forbids outright.
    """
    result = validate_run(writable_run(tmp_path, "partial-run"))
    assert result["status"] == "PARTIAL"
    sections = {
        value["status"]
        for key, value in result.items()
        if isinstance(value, dict) and "status" in value
    }
    assert sections == {"PASS"}, "PARTIAL must not depend on any section failing"


def test_a_run_whose_coverage_says_partial_is_never_reported_as_pass(tmp_path: Path) -> None:
    run_dir = writable_run(tmp_path, "partial-run")
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["status"] != "PASS"
    assert validate_run(run_dir)["status"] != "PASS"


def test_the_three_verdicts_are_distinct(tmp_path: Path) -> None:
    """All three branches are live, and no two fixtures agree."""
    verdicts = {
        name: validate_run(writable_run(tmp_path, name))["status"]
        for name in ("pass-run", "partial-run", "fail-run")
    }
    assert verdicts == {"pass-run": "PASS", "partial-run": "PARTIAL", "fail-run": "FAIL"}


def test_a_corrupt_canonical_file_is_a_refusal_not_a_traceback(tmp_path: Path) -> None:
    run_dir = writable_run(tmp_path, "pass-run")
    (run_dir / "coverage.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PipelineError) as caught:
        validate_run(run_dir)
    assert "coverage.json" in str(caught.value)


def test_a_missing_canonical_file_names_itself(tmp_path: Path) -> None:
    run_dir = writable_run(tmp_path, "pass-run")
    (run_dir / "segments.json").unlink()
    with pytest.raises(PipelineError) as caught:
        validate_run(run_dir)
    assert "segments.json" in str(caught.value)


# ---------------------------------------------------------------------------
# 4. _safe_identifier refuses instead of rewriting  (D-020)
# ---------------------------------------------------------------------------

#: Ids the old normaliser rewrote into something else. Each produced a run at
#: an address no lookup path would ever accept.
REWRITTEN_IDS = [
    "my video 2024",  # -> my_video_2024
    "../escape",  # -> _escape
    "../../etc/passwd",  # -> _etc_passwd
    "a/b",  # -> a_b
    "run:1",  # -> run_1
    ".hidden",  # -> hidden
    "..",  # -> raised, but only by accident of stripping
    "",
    "   ",
    "abc\n",
    "café",  # -> caf
    "a" * 300,  # -> truncated to 80, so unretrievable by its own name
]


@pytest.mark.parametrize("video_id", REWRITTEN_IDS)
def test_an_id_that_would_have_been_rewritten_is_refused(
    video_id: str, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    with pytest.raises(PipelineError):
        import_transcript(SAMPLE, output, video_id=video_id)
    assert not output.exists() or list(output.iterdir()) == [], (
        "a refused id still created something on disk"
    )


@pytest.mark.parametrize("video_id", ["my.video.2024", "abc123def45", "a", "A-b_c.d", "0"])
def test_an_accepted_id_is_stored_verbatim_and_can_be_looked_back_up(
    video_id: str, tmp_path: Path
) -> None:
    """The invariant the rewriting broke: created implies retrievable.

    ``my.video.2024`` used to be stored as ``my_video_2024`` while every
    lookup path — ``resolve_run_dir``, ``ids.is_id_part``, the v1 schemas —
    went on accepting the dotted form and finding nothing there.
    """
    output = tmp_path / "output"
    run_dir = import_transcript(SAMPLE, output, video_id=video_id)
    assert run_dir.name == video_id
    assert resolve_run_dir(output, video_id) == run_dir
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["video_id"] == video_id


def test_two_distinct_ids_can_no_longer_collide_on_one_directory(tmp_path: Path) -> None:
    """``my.video`` and ``my/video`` both normalised to ``my_video``."""
    output = tmp_path / "output"
    first = import_transcript(SAMPLE, output, video_id="my.video")
    with pytest.raises(PipelineError):
        import_transcript(SAMPLE, output, video_id="my/video")
    assert [path.name for path in sorted(output.iterdir())] == ["my.video"]
    assert (first / "transcript.json").exists()


def test_the_creating_rule_and_the_lookup_rule_agree(tmp_path: Path) -> None:
    """D-020: the two sides must not disagree about which ids exist.

    Anything ``import_transcript`` accepts, ``resolve_run_dir`` must resolve;
    anything ``resolve_run_dir`` rejects, ``import_transcript`` must refuse.
    """
    output = tmp_path / "output"
    output.mkdir()
    for video_id in REWRITTEN_IDS:
        with pytest.raises(PipelineError):
            resolve_run_dir(output, video_id)
        with pytest.raises(PipelineError):
            import_transcript(SAMPLE, output, video_id=video_id)


# ---------------------------------------------------------------------------
# 5a. An interrupted import is re-runnable
# ---------------------------------------------------------------------------


def test_an_import_retried_over_leftover_raw_debris_succeeds(tmp_path: Path) -> None:
    """The proven dead end: ``raw/`` exists, so every retry died on FileExistsError.

    An import interrupted between ``raw_dir.mkdir()`` and the first canonical
    write left the directory behind. There is no canonical ``transcript.json``,
    so the run does not exist — but the retry could not proceed either, with no
    way forward but a manual ``rm -rf``.
    """
    output = tmp_path / "output"
    debris = output / "abc123def45" / "raw"
    debris.mkdir(parents=True)
    (debris / "source.srt").write_text("half-written debris", encoding="utf-8")

    run_dir = import_transcript(SAMPLE, output, video_id="abc123def45", language="en")

    assert (run_dir / "transcript.json").exists()
    assert (run_dir / "raw" / "source.vtt").exists()
    assert not (run_dir / "raw" / "source.srt").exists(), "stale evidence survived the retry"


def test_a_retry_leaves_no_debris_from_the_interrupted_attempt(tmp_path: Path) -> None:
    output = tmp_path / "output"
    debris = output / "abc123def45" / "raw"
    debris.mkdir(parents=True)
    (debris / "leftover.json").write_text("{}", encoding="utf-8")
    run_dir = import_transcript(SAMPLE, output, video_id="abc123def45", language="en")
    assert {path.name for path in (run_dir / "raw").iterdir()} == {
        "source.vtt",
        "transcript.json",
        "transcript.md",
    }


def test_a_symlinked_raw_directory_is_replaced_rather_than_refused(tmp_path: Path) -> None:
    """``is_dir()`` follows the link, so the symlink arm was unreachable.

    A symlinked ``raw/`` took the ``rmtree`` branch, and ``rmtree`` refuses a
    symbolic link with ``OSError: [Errno None] None`` — which the CLI prints
    verbatim, telling the operator nothing about what is wrong or what to do.
    The link is removed and the run gets a real directory; what the link
    pointed at is left alone, because it is not this run's evidence.
    """
    output = tmp_path / "output"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("not this run's evidence", encoding="utf-8")
    run_dir = output / "abc123def45"
    run_dir.mkdir(parents=True)
    (run_dir / "raw").symlink_to(elsewhere, target_is_directory=True)

    imported = import_transcript(SAMPLE, output, video_id="abc123def45", language="en")

    assert not (imported / "raw").is_symlink()
    assert (imported / "raw" / "source.vtt").exists()
    assert (elsewhere / "keep.txt").exists(), "the link's target was not walked"


def test_a_completed_run_is_still_never_overwritten(tmp_path: Path) -> None:
    """Re-runnability may not become "clobbers finished evidence".

    ``raw/`` is immutable evidence *of a run that exists*; the completion guard
    is what tells the two apart.
    """
    output = tmp_path / "output"
    run_dir = import_transcript(SAMPLE, output, video_id="abc123def45", language="en")
    before = (run_dir / "raw" / "source.vtt").read_bytes()
    with pytest.raises(RunAlreadyExists):
        import_transcript(SAMPLE, output, video_id="abc123def45", language="en")
    assert (run_dir / "raw" / "source.vtt").read_bytes() == before


def test_a_retry_with_a_bad_transcript_destroys_nothing(tmp_path: Path) -> None:
    """Clearing ``raw/`` happens after parsing, so a bad retry is inert."""
    output = tmp_path / "output"
    debris = output / "abc123def45" / "raw"
    debris.mkdir(parents=True)
    (debris / "source.srt").write_text("debris", encoding="utf-8")
    untimed = tmp_path / "untimed.txt"
    untimed.write_text("Plain transcript with no timings at all.", encoding="utf-8")

    # The point is that the debris survives the refusal, but naming the type
    # makes it a stronger claim: a transcript with no timings is refused by the
    # documented import path, not by something incidental.
    with pytest.raises(TranscriptError):
        import_transcript(untimed, output, video_id="abc123def45")
    assert (debris / "source.srt").exists()


def test_a_name_collision_is_its_own_error_type(tmp_path: Path) -> None:
    """``cli._run_process`` must be able to tell it from "no captions"."""
    output = tmp_path / "output"
    import_transcript(SAMPLE, output, video_id="abc123def45", language="en")
    with pytest.raises(RunAlreadyExists):
        import_transcript(SAMPLE, output, video_id="abc123def45")
    assert issubclass(RunAlreadyExists, PipelineError)


# ---------------------------------------------------------------------------
# 5b. The CLI error surface
# ---------------------------------------------------------------------------


def test_a_malformed_transcript_is_reported_cleanly_not_as_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented import path raises ``TranscriptError``, not ``PipelineError``.

    Only ``PipelineError`` was caught, so ``x2knwldg import-transcript`` on a
    file with no timings exited on a raw traceback.
    """
    untimed = tmp_path / "transcript.txt"
    untimed.write_text("Plain transcript without any timestamps.", encoding="utf-8")
    code, out, err = run_cli(
        [
            "import-transcript",
            str(untimed),
            "--video-id",
            "abc123def45",
            "--output",
            str(tmp_path / "output"),
        ],
        capsys,
    )
    assert code == cli.EXIT_ERROR
    assert out == ""
    payload = json.loads(err)
    assert payload["status"] == "ERROR"
    assert payload["error"] == "TranscriptError"


def test_validate_on_a_corrupt_run_is_reported_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = writable_run(tmp_path, "pass-run")
    (run_dir / "metadata.json").write_text("{ this is not json", encoding="utf-8")
    code, _, err = run_cli(["validate", str(run_dir)], capsys)
    assert code == cli.EXIT_ERROR
    assert json.loads(err)["status"] == "ERROR"


def test_validate_on_an_absent_run_is_reported_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_cli(["validate", str(tmp_path / "nothing-here")], capsys)
    assert code == cli.EXIT_ERROR
    assert json.loads(err)["status"] == "ERROR"


def test_the_caught_error_surface_covers_the_documented_input_paths() -> None:
    """A guard against the tuple quietly shrinking back to ``PipelineError``."""
    from x2knwldg.ids import IdError
    from x2knwldg.transcripts import TranscriptError

    for error in (PipelineError, TranscriptError, IdError, OSError, json.JSONDecodeError):
        assert issubclass(error, cli.USER_FACING_ERRORS)


# ---------------------------------------------------------------------------
# 5c. `process` distinguishes its failures from "supply a transcript"
# ---------------------------------------------------------------------------


def _process_argv(tmp_path: Path) -> list[str]:
    return [
        "process",
        f"https://www.youtube.com/watch?v={REAL_ID}",
        "--output",
        str(tmp_path / "output"),
        "--inbox",
        str(tmp_path / "inbox"),
    ]


def _pretend_the_youtube_extra_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Satisfy the dependency probe so the test reaches the branch it names.

    `process` checks `YOUTUBE_DEPENDENCIES` *before* it calls
    `process_youtube_url`, and refuses outright when none of them import — the
    right behaviour, and the subject of
    `test_a_missing_youtube_extra_is_not_reported_as_transcript_required`. But it
    means a test that monkeypatches the fetch is silently unreachable on an
    install without the `youtube` extra, which is exactly the install
    ADR 0001 invariant 5 requires the suite to pass on. Pinning the probe to a
    module that is certainly importable keeps the two questions separate: this
    one is about what `process` does once the fetch has run.

    Found by running the suite in the bare core venv of PROJECT_MANAGEMENT
    §7.2, where `test_no_captions_asks_for_a_transcript` failed on empty
    stdout and the collision test passed for the wrong reason — the
    missing-extra error satisfies all four of its assertions without ever
    reaching the collision.
    """
    monkeypatch.setattr(cli, "YOUTUBE_DEPENDENCIES", ("x2knwldg",))


def test_no_captions_asks_for_a_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import x2knwldg.youtube as youtube

    def no_captions(*args: object, **kwargs: object) -> Path:
        raise PipelineError("No YouTube captions are available")

    _pretend_the_youtube_extra_is_installed(monkeypatch)
    monkeypatch.setattr(youtube, "process_youtube_url", no_captions)
    code, out, _ = run_cli(_process_argv(tmp_path), capsys)
    payload = json.loads(out)
    assert code == cli.EXIT_TRANSCRIPT_REQUIRED
    assert payload["status"] == "TRANSCRIPT_REQUIRED"
    assert payload["whisper_fallback"] is False
    assert (Path(payload["inbox"]) / "README.md").exists()


def test_a_name_collision_is_not_reported_as_transcript_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Asking for a transcript here would be a lie.

    The captions were fetched fine; the id is already taken, and the very same
    collision would reject whatever transcript the user then supplied.
    """
    import x2knwldg.youtube as youtube

    def collision(*args: object, **kwargs: object) -> Path:
        raise RunAlreadyExists("Output already exists for dQw4w9WgXcQ")

    _pretend_the_youtube_extra_is_installed(monkeypatch)
    monkeypatch.setattr(youtube, "process_youtube_url", collision)
    code, out, err = run_cli(_process_argv(tmp_path), capsys)
    assert code == cli.EXIT_ERROR
    assert out == ""
    message = json.loads(err)["message"]
    assert json.loads(err)["status"] == "ERROR"
    # Naming the collision is what separates this from the missing-extra
    # refusal, whose four assertions are otherwise identical.
    assert "x2knwldg[youtube]" not in message
    assert not (tmp_path / "inbox").exists(), "a collision created a pointless inbox"


def test_a_missing_youtube_extra_is_not_reported_as_transcript_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken install is not a video without captions."""
    import x2knwldg.youtube as youtube

    def must_not_run(*args: object, **kwargs: object) -> Path:  # pragma: no cover
        raise AssertionError("the fetch ran without the extra installed")

    monkeypatch.setattr(cli, "YOUTUBE_DEPENDENCIES", ("x2knwldg_absent_a", "x2knwldg_absent_b"))
    monkeypatch.setattr(youtube, "process_youtube_url", must_not_run)
    code, out, err = run_cli(_process_argv(tmp_path), capsys)
    assert code == cli.EXIT_ERROR
    assert out == ""
    message = json.loads(err)["message"]
    assert "x2knwldg[youtube]" in message
    assert not (tmp_path / "inbox").exists()


def test_a_source_that_is_neither_a_file_nor_a_url_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_cli(
        ["process", "ytsearch:cats", "--output", str(tmp_path / "output")], capsys
    )
    assert code == cli.EXIT_ERROR
    assert json.loads(err)["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 5d. `status` degrades per video
# ---------------------------------------------------------------------------


def _seed_status_output(tmp_path: Path) -> Path:
    output = tmp_path / "output"
    for name in ("aaa-good-01", "bbb-broken1", "ccc-good-01"):
        import_transcript(SAMPLE, output, video_id=name, language="en")
    return output


def test_one_corrupt_metadata_does_not_hide_every_other_video(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One damaged run used to take the whole listing down with a traceback."""
    output = _seed_status_output(tmp_path)
    (output / "bbb-broken1" / "metadata.json").write_text("{ broken", encoding="utf-8")

    code, out, _ = run_cli(["status", "--output", str(output)], capsys)
    assert code == cli.EXIT_OK
    payload = json.loads(out)
    rows = {row["video_id"]: row for row in payload["videos"]}
    assert set(rows) == {"aaa-good-01", "bbb-broken1", "ccc-good-01"}
    assert rows["aaa-good-01"]["coverage"] == "PARTIAL"
    assert rows["ccc-good-01"]["coverage"] == "PARTIAL"
    assert rows["bbb-broken1"]["coverage"] == "UNREADABLE"
    assert "metadata.json" in rows["bbb-broken1"]["error"]
    assert payload["unreadable"] == 1


def test_a_corrupt_coverage_file_degrades_only_its_own_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _seed_status_output(tmp_path)
    (output / "bbb-broken1" / "coverage.json").write_text("[[[", encoding="utf-8")

    code, out, _ = run_cli(["status", "--output", str(output)], capsys)
    assert code == cli.EXIT_OK
    rows = {row["video_id"]: row for row in json.loads(out)["videos"]}
    assert rows["bbb-broken1"]["coverage"] == "UNREADABLE"
    assert rows["aaa-good-01"]["coverage"] == "PARTIAL"


def test_an_unreadable_run_is_never_reported_as_covered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _seed_status_output(tmp_path)
    (output / "bbb-broken1" / "metadata.json").write_text("null", encoding="utf-8")
    _, out, _ = run_cli(["status", "--output", str(output)], capsys)
    rows = {row["video_id"]: row for row in json.loads(out)["videos"]}
    assert rows["bbb-broken1"]["coverage"] not in {"PASS", "PARTIAL"}


# ---------------------------------------------------------------------------
# 5e. Exit codes: a non-PASS run can never look like a pass
# ---------------------------------------------------------------------------


def test_partial_and_fail_have_distinct_non_zero_exit_codes() -> None:
    codes = cli.VERDICT_EXIT_CODES
    assert codes["PASS"] == 0
    assert codes["PARTIAL"] != 0
    assert codes["FAIL"] != 0
    assert codes["PARTIAL"] != codes["FAIL"]
    assert len(set(codes.values())) == 3


def test_an_unknown_verdict_is_never_a_pass() -> None:
    assert cli.verdict_exit_code("SOMETHING_NEW") == cli.EXIT_ERROR
    assert cli.verdict_exit_code("") == cli.EXIT_ERROR


def test_every_semantic_exit_code_is_distinct() -> None:
    """Including argparse's ``2``, which nothing else may claim."""
    codes = [
        cli.EXIT_OK,
        cli.EXIT_ERROR,
        cli.EXIT_USAGE,
        cli.EXIT_PARTIAL,
        cli.EXIT_FAIL,
        cli.EXIT_TRANSCRIPT_REQUIRED,
        cli.EXIT_UI_NOT_BUILT,
    ]
    assert len(set(codes)) == len(codes)
    assert cli.EXIT_USAGE == 2, "argparse exits 2 on a usage error; nothing may collide with it"


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [("pass-run", 0), ("partial-run", cli.EXIT_PARTIAL), ("fail-run", cli.EXIT_FAIL)],
)
def test_validate_exits_with_the_verdict(
    fixture: str, expected: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``PARTIAL`` used to exit ``0``: no shell or CI check could see it."""
    run_dir = writable_run(tmp_path, fixture)
    code, out, _ = run_cli(["validate", str(run_dir)], capsys)
    assert code == expected
    assert json.loads(out)["status"] == {0: "PASS", 3: "PARTIAL", 4: "FAIL"}[expected]


def test_a_partial_run_does_not_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLAUDE.md: completion may not be claimed unless both report PASS."""
    run_dir = writable_run(tmp_path, "partial-run")
    code, _, _ = run_cli(["validate", str(run_dir)], capsys)
    assert code != 0


def test_finalize_and_validate_agree_on_a_partial_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One verdict-to-code mapping, so the commands cannot drift apart."""
    validate_dir = writable_run(tmp_path, "partial-run")
    finalize_dir = writable_run(tmp_path / "second", "partial-run")
    validate_code, _, _ = run_cli(["validate", str(validate_dir)], capsys)
    finalize_code, _, _ = run_cli(["finalize", str(finalize_dir)], capsys)
    assert validate_code == finalize_code == cli.EXIT_PARTIAL


def test_the_help_documents_the_exit_code_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A caller writing a shell check must not have to read the source."""
    with pytest.raises(SystemExit) as caught:
        cli.main(["--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    for token in ("exit codes", "PARTIAL", "FAIL", "TRANSCRIPT_REQUIRED", "UI_NOT_BUILT"):
        assert token in help_text
    for code in (cli.EXIT_PARTIAL, cli.EXIT_FAIL, cli.EXIT_TRANSCRIPT_REQUIRED):
        assert f"  {code}  " in help_text


def test_the_module_docstring_documents_the_exit_codes() -> None:
    assert cli.__doc__ is not None
    assert "Exit codes" in cli.__doc__
    for token in ("PARTIAL", "FAIL", "TRANSCRIPT_REQUIRED", "UI_NOT_BUILT"):
        assert token in cli.__doc__


# ---------------------------------------------------------------------------
# The containment check itself, which no test used to reach
# ---------------------------------------------------------------------------


def test_a_symlinked_run_that_leaves_the_output_root_is_refused(tmp_path: Path) -> None:
    """``resolve_run_dir``'s second guard, exercised for the first time.

    The audit found this branch unreachable by the suite: every hostile input a
    test supplied died at the earlier ``is_id_part`` gate, so deleting the
    containment check left the suite green. A symlink is the case that reaches
    it — the id is a perfectly legal id, and only resolution reveals that the
    directory it names is somewhere else.
    """
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "stolen.md").write_text("not ours", encoding="utf-8")
    (output / "escapee").symlink_to(outside, target_is_directory=True)

    assert is_id_part("escapee"), "the id itself is legal; only the path escapes"
    with pytest.raises(PipelineError) as caught:
        resolve_run_dir(output, "escapee")
    assert "outside the output root" in str(caught.value)


def test_a_symlink_that_stays_inside_the_output_root_is_accepted(tmp_path: Path) -> None:
    """The control: containment is the rule, not a blanket ban on symlinks."""
    output = tmp_path / "output"
    real = output / "real-run"
    real.mkdir(parents=True)
    (output / "alias").symlink_to(real, target_is_directory=True)
    assert resolve_run_dir(output, "alias") == real.resolve()


# ---------------------------------------------------------------------------
# A URL names one video, or it names none
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        # D-166: the regex was unanchored and used with `.search`, so a
        # malformed id was truncated to its first 11 characters and the fetched
        # captions were filed under **a different real video's id**.
        ("https://www.youtube.com/shorts/dQw4w9WgXcQABC", None),
        ("https://www.youtube.com/embed/dQw4w9WgXcQXYZ123", None),
        ("https://www.youtube.com/anything/shorts/dQw4w9WgXcQ", None),
        # And the three live URL forms that returned `None` while
        # `is_youtube_url` said `True`.
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Unchanged, and asserted here so the anchoring cannot have narrowed
        # them by accident.
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
    ids=lambda value: value if isinstance(value, str) else repr(value),
)
def test_a_youtube_path_names_one_video_or_none(url: str, expected: str | None) -> None:
    assert is_youtube_url(url), "every case here is a YouTube host"
    assert extract_video_id(url) == expected


def test_a_truncated_id_is_never_a_different_real_video(tmp_path: Path) -> None:
    """The consequence, stated as the property that matters.

    `is_youtube_url` exists to stop captions from an attacker's host being
    filed under a real 11-character id. Truncation did the same thing one layer
    in, from a host that really is YouTube.
    """
    real = "dQw4w9WgXcQ"
    assert extract_video_id(f"https://www.youtube.com/shorts/{real}") == real
    for suffix in ("A", "AB", "ABC", "XYZ123", "_", "-"):
        assert extract_video_id(f"https://www.youtube.com/shorts/{real}{suffix}") is None


# ---------------------------------------------------------------------------
# "Immutable evidence" now has a detection story
# ---------------------------------------------------------------------------


def _pass_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "pass-run"
    shutil.copytree(FIXTURES / "runs" / "pass-run", run_dir)
    return run_dir


def test_an_untouched_run_passes_the_evidence_check(tmp_path: Path) -> None:
    result = validate_run(_pass_run(tmp_path))
    assert result["evidence"]["status"] == "PASS"
    assert result["status"] == "PASS"


def test_editing_the_preserved_original_is_detected(tmp_path: Path) -> None:
    """``transcript_hash`` was written once and never read back.

    No write path targets ``raw/`` — that held up under audit — but nothing
    would have noticed if something else did, which is a policy without a
    detection story.
    """
    run_dir = _pass_run(tmp_path)
    raw = run_dir / "raw" / "source.srt"
    raw.write_text(raw.read_text(encoding="utf-8") + "\nforged\n", encoding="utf-8")

    result = validate_run(run_dir)
    assert result["evidence"]["status"] == "FAIL"
    codes = {error["code"] for error in result["evidence"]["errors"]}
    assert codes == {"transcript_hash_mismatch"}
    assert result["status"] == "FAIL"


def test_a_run_whose_evidence_was_edited_cannot_be_finalized(tmp_path: Path) -> None:
    """The verdict has to reach the gate, or detection changes nothing."""
    from x2knwldg.artifacts import finalize_run

    run_dir = _pass_run(tmp_path)
    raw = run_dir / "raw" / "source.srt"
    raw.write_text(raw.read_text(encoding="utf-8") + "\nforged\n", encoding="utf-8")
    with pytest.raises(PipelineError):
        finalize_run(run_dir)


def test_deleting_the_preserved_original_is_detected(tmp_path: Path) -> None:
    run_dir = _pass_run(tmp_path)
    (run_dir / "raw" / "source.srt").unlink()
    result = validate_run(run_dir)
    assert {e["code"] for e in result["evidence"]["errors"]} == {"raw_source_missing"}


def test_two_candidate_originals_are_not_evidence(tmp_path: Path) -> None:
    run_dir = _pass_run(tmp_path)
    shutil.copy2(run_dir / "raw" / "source.srt", run_dir / "raw" / "source.vtt")
    result = validate_run(run_dir)
    assert {e["code"] for e in result["evidence"]["errors"]} == {"raw_source_ambiguous"}


def test_a_run_that_records_no_hash_is_refused(tmp_path: Path) -> None:
    run_dir = _pass_run(tmp_path)
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    del metadata["transcript_hash"]
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    result = validate_run(run_dir)
    assert "transcript_hash_missing" in {e["code"] for e in result["evidence"]["errors"]}


def _rewrite(path: Path, mutate: Callable[[dict], object]) -> None:
    """Rewrite a canonical document the way the pipeline would write it."""
    from x2knwldg.io import dumps_json

    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(dumps_json(document), encoding="utf-8")


FABRICATED = "the speaker endorsed this product without reservation."


def test_a_fabricated_quotation_in_the_canonical_files_cannot_reach_pass(
    tmp_path: Path,
) -> None:
    """D-163. The hole the digest was supposed to close and did not.

    ``transcript_hash`` covered ``raw/source.<ext>`` and was compared back to
    that same file; the second comparison was against ``transcript.json``'s copy
    of the same *string*. Nothing hashed the canonical documents. So a sentence
    the speaker never said could be written into the files extraction reads,
    cited as evidence, and printed into ``report.md`` — with ``raw/`` untouched,
    ``apply-bundle`` returning ``PASS`` and the evidence section returning
    ``{"status": "PASS", "errors": []}``.

    Written the way the pipeline writes, so this is not a test about formatting.
    """
    run_dir = _pass_run(tmp_path)
    _rewrite(
        run_dir / "segments.json",
        lambda doc: doc["segments"][0].update(
            text=doc["segments"][0]["text"] + " " + FABRICATED
        ),
    )
    _rewrite(
        run_dir / "transcript.json",
        lambda doc: doc["captions"][0].update(text=FABRICATED),
    )

    result = validate_run(run_dir)
    assert result["evidence"]["status"] == "FAIL"
    assert result["status"] == "FAIL"
    codes = {error["code"] for error in result["evidence"]["errors"]}
    assert "canonical_hash_mismatch" in codes
    assert "canonical_transcript_disagrees_with_evidence" in codes
    assert "segments_disagree_with_transcript" in codes
    # The premise of the attack: the preserved original was never touched.
    assert FABRICATED not in (run_dir / "raw" / "source.srt").read_text(encoding="utf-8")


def test_editing_only_the_segments_is_detected(tmp_path: Path) -> None:
    """``segments.json`` is the file that matters most, and had no raw copy.

    ``validate_provenance`` matches every evidence excerpt against a *segment's*
    text rather than against the captions, so a fabricated quotation only ever
    had to live here.
    """
    run_dir = _pass_run(tmp_path)
    _rewrite(
        run_dir / "segments.json",
        lambda doc: doc["segments"][0].update(
            text=doc["segments"][0]["text"] + " " + FABRICATED
        ),
    )
    result = validate_run(run_dir)
    assert result["evidence"]["status"] == "FAIL"
    codes = {error["code"] for error in result["evidence"]["errors"]}
    assert "canonical_hash_mismatch" in codes
    assert "segments_disagree_with_transcript" in codes


@pytest.mark.parametrize(
    "damage",
    [
        pytest.param(lambda caption: caption.update(end_sec="oops"), id="end_sec-is-a-string"),
        pytest.param(lambda caption: caption.pop("end_sec"), id="end_sec-is-missing"),
    ],
)
def test_a_damaged_caption_is_reported_rather_than_raised(
    tmp_path: Path, damage: Callable[[dict], object]
) -> None:
    """The recomputation owes damaged captions the answer integrity already gives.

    ``create_segments`` subtracts ``start_sec`` from ``end_sec``, so a caption
    carrying a string there raises ``TypeError`` and one missing the key raises
    ``KeyError``. ``_segment_recomputation_errors`` caught only
    ``PipelineError`` and ``ValueError``, and neither escaping type is in
    ``cli.USER_FACING_ERRORS`` — so ``validate`` died on a raw traceback and
    the documented ``{"status": "ERROR"}`` stderr contract broke on input the
    transcript section reports correctly as ``invalid_timing``.
    """
    run_dir = _pass_run(tmp_path)
    _rewrite(run_dir / "transcript.json", lambda doc: damage(doc["captions"][0]))

    result = validate_run(run_dir)
    assert result["status"] == "FAIL"
    assert "segments_unverifiable" in {
        error["code"] for error in result["evidence"]["errors"]
    }
    # The transcript section names the same caption, so the two readers of
    # these captions agree that the damage is a finding.
    assert "invalid_timing" in {error["code"] for error in result["transcript"]["errors"]}


def test_a_run_is_re_derived_against_the_bounds_it_recorded(tmp_path: Path) -> None:
    """``segments.json`` recorded two of the four bounds it was built with.

    ``min_sec`` and ``max_sec`` were supplied to the recomputation from
    ``constants.py`` rather than read off the run, so a run segmented with any
    other pair — which is what tuning ``SEGMENT_MIN_SEC`` makes every archived
    run — re-derived differently and reported
    ``segments_disagree_with_transcript``: tampering, for a run nobody had
    touched. The "future strategy" escape hatch keys on ``strategy.type``,
    which would not have changed.
    """
    from x2knwldg import constants

    run_dir = import_transcript(
        SAMPLE,
        tmp_path / "output",
        video_id="vid00000001",
        min_segment_sec=30,
        max_segment_sec=90,
        target_segment_sec=60,
    )
    strategy = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))["strategy"]
    assert (strategy["min_sec"], strategy["max_sec"]) == (30, 90)
    assert strategy["min_sec"] != constants.SEGMENT_MIN_SEC, "not the default"

    result = validate_run(run_dir)
    codes = {error["code"] for error in result["evidence"]["errors"]}
    assert "segments_disagree_with_transcript" not in codes
    assert result["evidence"]["status"] == "PASS"


def test_a_run_without_the_recorded_bounds_says_the_defaults_were_assumed(
    tmp_path: Path,
) -> None:
    """Every run written before the two fields existed. Named, not excused.

    Built by removing the two fields from a fresh run, which is the shape a
    run imported before D-203 has on disk. The digests are re-recorded over
    the edited files, because a run that predates the *bounds* does not also
    predate the digests — and leaving them stale would make this a test about
    ``canonical_hash_mismatch`` instead.
    """
    from x2knwldg.io import sha256_text

    run_dir = _pass_run(tmp_path)
    _rewrite(
        run_dir / "segments.json",
        lambda doc: [doc["strategy"].pop(key) for key in ("min_sec", "max_sec")],
    )
    _rewrite(
        run_dir / "metadata.json",
        lambda doc: doc.__setitem__(
            "canonical_hashes",
            {
                name: sha256_text((run_dir / name).read_text(encoding="utf-8"))
                for name in ("transcript.json", "segments.json")
            },
        ),
    )
    strategy = json.loads((run_dir / "segments.json").read_text(encoding="utf-8"))["strategy"]
    assert "min_sec" not in strategy and "max_sec" not in strategy

    result = validate_run(run_dir)
    # The run still validates: the defaults are *assumed*, and the warning
    # below is what says so rather than a failure that blames the run.
    assert result["evidence"]["status"] == "PASS"
    warnings = {warning["code"] for warning in result["evidence"]["warnings"]}
    assert "segments_bounds_not_recorded" in warnings


def test_a_forged_digest_does_not_launder_a_forged_transcript(tmp_path: Path) -> None:
    """The recorded digest is one of three checks, not the only one.

    Rewriting ``metadata.canonical_hashes`` to match the edited files defeats
    check 1 — and check 2 (the preserved ``raw/transcript.json``) and check 3
    (recomputing the segments) are exactly what still stand.
    """
    from x2knwldg.io import sha256_text

    run_dir = _pass_run(tmp_path)
    _rewrite(
        run_dir / "transcript.json",
        lambda doc: doc["captions"][0].update(text=FABRICATED),
    )
    _rewrite(
        run_dir / "segments.json",
        lambda doc: doc["segments"][0].update(text=FABRICATED),
    )
    _rewrite(
        run_dir / "metadata.json",
        lambda doc: doc.__setitem__(
            "canonical_hashes",
            {
                name: sha256_text((run_dir / name).read_text(encoding="utf-8"))
                for name in ("transcript.json", "segments.json")
            },
        ),
    )
    result = validate_run(run_dir)
    assert result["evidence"]["status"] == "FAIL"
    codes = {error["code"] for error in result["evidence"]["errors"]}
    assert "canonical_hash_mismatch" not in codes, "the forged digest does agree"
    assert "canonical_transcript_disagrees_with_evidence" in codes
    assert "segments_disagree_with_transcript" in codes


def test_a_run_recorded_before_the_digests_is_still_checked_and_says_so(
    tmp_path: Path,
) -> None:
    """No migration: every run ever imported carries ``raw/transcript.json``.

    A run with no recorded digests is warned about — the warning names
    re-import as the way to get the exact check — and is still refused if its
    canonical files have moved away from the preserved evidence.
    """
    run_dir = _pass_run(tmp_path)
    _rewrite(run_dir / "metadata.json", lambda doc: doc.pop("canonical_hashes", None))

    result = validate_run(run_dir)
    assert result["evidence"]["status"] == "PASS", "an honest old run still passes"
    assert "canonical_hashes_not_recorded" in {
        warning["code"] for warning in result["evidence"]["warnings"]
    }

    _rewrite(
        run_dir / "segments.json",
        lambda doc: doc["segments"][0].update(text=FABRICATED),
    )
    refused = validate_run(run_dir)
    assert refused["evidence"]["status"] == "FAIL"
    assert "segments_disagree_with_transcript" in {
        error["code"] for error in refused["evidence"]["errors"]
    }


def test_an_import_records_a_digest_over_what_it_writes(tmp_path: Path) -> None:
    """The digests are over the bytes on disk, not over a re-serialisation."""
    from x2knwldg.io import sha256_file

    run_dir = _pass_run(tmp_path)
    recorded = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))[
        "canonical_hashes"
    ]
    assert set(recorded) == {"transcript.json", "segments.json"}
    for name, digest in recorded.items():
        assert digest == sha256_file(run_dir / name), name


def test_deleting_the_preserved_transcript_copy_is_detected(tmp_path: Path) -> None:
    run_dir = _pass_run(tmp_path)
    (run_dir / "raw" / "transcript.json").unlink()
    result = validate_run(run_dir)
    assert "raw_transcript_missing" in {
        error["code"] for error in result["evidence"]["errors"]
    }


def test_the_two_canonical_files_must_agree_about_the_hash(tmp_path: Path) -> None:
    """``metadata.json`` and ``transcript.json`` both carry it; one fact, one value."""
    run_dir = _pass_run(tmp_path)
    transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
    transcript["transcript_hash"] = "0" * 64
    (run_dir / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    result = validate_run(run_dir)
    assert "transcript_hash_disagreement" in {
        e["code"] for e in result["evidence"]["errors"]
    }
