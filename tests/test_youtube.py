"""Tests for ``x2knwldg.youtube`` — the one module that reaches the network.

It had no tests. Not "thin tests": none. Three other test modules import it
solely to ``monkeypatch`` ``process_youtube_url`` out of the way, so every line
inside it — the ``youtube_transcript_api`` path, the ``yt-dlp`` fallback, the
json3 duration inference, the two option dictionaries — had never run under
test at all. That is why the missing socket timeouts could only be found by
reading.

Rules this file keeps:

* **No network.** ``yt_dlp``, ``youtube_transcript_api`` and ``requests`` are
  replaced with fakes injected into ``sys.modules``, so these tests behave
  identically whether or not the ``youtube`` extra is installed — including in
  the bare-core CI job. An autouse fixture makes any real socket call an error,
  so "no network" is enforced rather than asserted in a docstring.
* **No clock, no randomness, no ordering luck.**
* **``output/`` is never touched.** Runs are created under ``tmp_path``.
* **Whisper is never a fallback** (``AGENTS.md``), and one test holds the line.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from x2knwldg import youtube
from x2knwldg.pipeline import PipelineError

REAL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
REAL_ID = "dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# No network, enforced
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any real socket in this module is a test bug, not a slow test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test in test_youtube.py tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _install(monkeypatch: pytest.MonkeyPatch, name: str, module: ModuleType | None) -> None:
    """Put *module* in ``sys.modules`` under *name*, or ``None`` to make the
    import fail. ``monkeypatch`` restores whatever was there."""
    monkeypatch.setitem(sys.modules, name, module)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FetchedTranscript(list):
    """What ``youtube_transcript_api`` hands back: an iterable with a language."""

    def __init__(self, items: list[Any], language_code: str = "en") -> None:
        super().__init__(items)
        self.language_code = language_code


def _transcript_api_module(
    *,
    fetched: Any = None,
    listed: list[Any] | None = None,
    error: Exception | None = None,
    accepts_http_client: bool = True,
    record: dict[str, Any] | None = None,
) -> ModuleType:
    module = ModuleType("youtube_transcript_api")

    class YouTubeTranscriptApi:
        def __init__(self, http_client: Any = None) -> None:
            if http_client is not None and not accepts_http_client:
                raise TypeError("unexpected keyword argument 'http_client'")
            if record is not None:
                record["http_client"] = http_client

        def fetch(self, video_id: str, languages: Any = ("en",)) -> Any:
            if record is not None:
                record["fetch"] = (video_id, list(languages))
            if error is not None:
                raise error
            return fetched

        def list(self, video_id: str) -> Any:
            if record is not None:
                record["list"] = video_id
            if error is not None:
                raise error
            return list(listed or [])

    module.YouTubeTranscriptApi = YouTubeTranscriptApi  # type: ignore[attr-defined]
    return module


def _ytdlp_module(
    *,
    info: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    raw_caption_text: str | None = None,
    constructed: list[dict[str, Any]] | None = None,
    error: Exception | None = None,
) -> ModuleType:
    module = ModuleType("yt_dlp")
    recorded = constructed if constructed is not None else []

    class YoutubeDL:
        def __init__(self, options: dict[str, Any]) -> None:
            self.options = options
            recorded.append(options)

        def __enter__(self) -> YoutubeDL:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            if error is not None:
                raise error
            if download and "outtmpl" in self.options:
                language = self.options["subtitleslangs"][0]
                target = Path(f"{self.options['outtmpl']}.{language}.json3")
                if raw_caption_text is not None:
                    target.write_text(raw_caption_text, encoding="utf-8")
                elif events is not None:
                    target.write_text(json.dumps({"events": events}), encoding="utf-8")
            return dict(info or {})

    module.YoutubeDL = YoutubeDL  # type: ignore[attr-defined]
    return module


def _requests_module() -> ModuleType:
    module = ModuleType("requests")
    calls: list[dict[str, Any]] = []

    class Session:
        def request(self, method: str, url: str, **kwargs: Any) -> Any:
            calls.append({"method": method, "url": url, **kwargs})
            return SimpleNamespace(status_code=200)

    module.Session = Session  # type: ignore[attr-defined]
    module.calls = calls  # type: ignore[attr-defined]
    return module


# ---------------------------------------------------------------------------
# The bounds exist and are used
# ---------------------------------------------------------------------------


def test_the_bounds_are_declared_and_positive() -> None:
    assert youtube.NETWORK_TIMEOUT_SEC > 0
    assert youtube.MAX_CAPTION_BYTES > 0
    assert youtube.MAX_CAPTIONS > 0


def test_every_ytdl_option_set_carries_a_socket_timeout() -> None:
    """``socket_timeout`` is yt-dlp's own documented parameter. Without it a
    host that stops answering holds the process indefinitely."""
    options = youtube.ydl_options()
    assert options["socket_timeout"] == youtube.NETWORK_TIMEOUT_SEC
    assert options["retries"] == 2
    assert options["skip_download"] is True


def test_ydl_options_overrides_do_not_drop_the_timeout() -> None:
    options = youtube.ydl_options(writesubtitles=True, subtitlesformat="json3")
    assert options["socket_timeout"] == youtube.NETWORK_TIMEOUT_SEC
    assert options["writesubtitles"] is True


def test_both_ytdlp_calls_in_the_fallback_carry_the_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The inspect call *and* the download call. A timeout on one of two
    network calls bounds nothing."""
    constructed: list[dict[str, Any]] = []
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(error=RuntimeError("api down")),
    )
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "hello"}]}],
            constructed=constructed,
        ),
    )
    items, metadata = youtube.fetch_native_transcript(REAL_URL)
    assert items and metadata["video_id"] == REAL_ID
    assert len(constructed) == 2, constructed
    for options in constructed:
        assert options["socket_timeout"] == youtube.NETWORK_TIMEOUT_SEC


def test_fetch_metadata_carries_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed: list[dict[str, Any]] = []
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"title": "T", "uploader": "C", "language": "en"}, constructed=constructed
        ),
    )
    assert youtube.fetch_metadata(REAL_URL) == {
        "title": "T",
        "channel": "C",
        "language": "en",
    }
    assert constructed[0]["socket_timeout"] == youtube.NETWORK_TIMEOUT_SEC


# ---------------------------------------------------------------------------
# The transcript API session is bounded
# ---------------------------------------------------------------------------


def test_the_bounded_session_supplies_a_default_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``youtube_transcript_api`` calls its session with no ``timeout``, which
    in ``requests`` means "block forever". The default goes in the session."""
    requests = _requests_module()
    _install(monkeypatch, "requests", requests)
    session = youtube.bounded_http_client()
    assert session is not None
    session.request("GET", "https://example.invalid/")
    assert requests.calls[0]["timeout"] == youtube.NETWORK_TIMEOUT_SEC


def test_the_bounded_session_does_not_override_an_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _requests_module()
    _install(monkeypatch, "requests", requests)
    youtube.bounded_http_client().request("GET", "https://example.invalid/", timeout=1)
    assert requests.calls[0]["timeout"] == 1


def test_without_requests_the_session_is_absent_rather_than_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, "requests", None)
    assert youtube.bounded_http_client() is None


def test_the_transcript_api_is_constructed_with_the_bounded_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, "requests", _requests_module())
    record: dict[str, Any] = {}
    module = _transcript_api_module(fetched=_FetchedTranscript([]), record=record)
    youtube._transcript_api(module.YouTubeTranscriptApi)
    assert record["http_client"] is not None


def test_an_api_that_rejects_http_client_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older ``youtube_transcript_api`` has no injection point. Unbounded
    captions beat no captions, so that case falls back rather than failing."""
    _install(monkeypatch, "requests", _requests_module())
    record: dict[str, Any] = {}
    module = _transcript_api_module(accepts_http_client=False, record=record)
    assert youtube._transcript_api(module.YouTubeTranscriptApi) is not None
    assert record["http_client"] is None


# ---------------------------------------------------------------------------
# The caption-size bound
# ---------------------------------------------------------------------------


def test_an_oversized_caption_file_is_refused_before_it_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(youtube, "MAX_CAPTION_BYTES", 32)
    oversized = tmp_path / "captions.en.json3"
    oversized.write_text(json.dumps({"events": [{"tStartMs": 0}] * 100}), encoding="utf-8")
    with pytest.raises(PipelineError) as caught:
        youtube._read_caption_file(oversized)
    assert "over the 32-byte bound" in str(caught.value)


def test_a_caption_file_inside_the_bound_is_read(tmp_path: Path) -> None:
    path = tmp_path / "captions.en.json3"
    path.write_text(json.dumps({"events": []}), encoding="utf-8")
    assert youtube._read_caption_file(path) == {"events": []}


def test_the_ytdlp_path_refuses_an_oversized_caption_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube, "MAX_CAPTION_BYTES", 16)
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(error=RuntimeError("api down")),
    )
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "x" * 200}]}],
        ),
    )
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "16-byte bound" in str(caught.value)


def test_the_caption_count_is_bounded_on_the_api_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube, "MAX_CAPTIONS", 3)
    fetched = _FetchedTranscript(
        [{"text": f"c{i}", "start": float(i), "duration": 1.0} for i in range(10)]
    )
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(fetched=fetched),
    )
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL, ["en"])
    assert "3-cue bound" in str(caught.value)


def test_the_caption_count_is_bounded_on_the_ytdlp_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube, "MAX_CAPTIONS", 2)
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(error=RuntimeError("api down")),
    )
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[
                {"tStartMs": i * 1000, "dDurationMs": 1000, "segs": [{"utf8": f"c{i}"}]}
                for i in range(20)
            ],
        ),
    )
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "2-cue bound" in str(caught.value)


# ---------------------------------------------------------------------------
# fetch_native_transcript — the API path
# ---------------------------------------------------------------------------


def test_a_missing_extra_is_reported_as_a_missing_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, "youtube_transcript_api", None)
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "'youtube' optional dependency" in str(caught.value)


def test_a_url_with_no_video_id_is_refused_before_any_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(fetched=_FetchedTranscript([]), record=record),
    )
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript("https://example.com/not-a-video")
    assert "Could not extract a YouTube video ID" in str(caught.value)
    assert "fetch" not in record and "list" not in record


def test_preferred_languages_go_straight_to_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    record: dict[str, Any] = {}
    fetched = _FetchedTranscript(
        [{"text": "hello", "start": 0.0, "duration": 2.0}], language_code="de"
    )
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(fetched=fetched, record=record),
    )
    items, metadata = youtube.fetch_native_transcript(REAL_URL, ["de", "en"])
    assert record["fetch"] == (REAL_ID, ["de", "en"])
    assert metadata == {"video_id": REAL_ID, "language": "de", "url": REAL_URL}
    assert items == [{"text": "hello", "start": 0.0, "duration": 2.0, "language": "de"}]


def test_a_manual_track_is_preferred_over_a_generated_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = SimpleNamespace(
        is_generated=True,
        fetch=lambda: _FetchedTranscript([{"text": "auto", "start": 0.0, "duration": 1.0}]),
    )
    manual = SimpleNamespace(
        is_generated=False,
        fetch=lambda: _FetchedTranscript([{"text": "human", "start": 0.0, "duration": 1.0}]),
    )
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(listed=[generated, manual]),
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL)
    assert items[0]["text"] == "human"


def test_the_first_track_is_used_when_none_is_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = SimpleNamespace(
        is_generated=True,
        fetch=lambda: _FetchedTranscript([{"text": "auto-1", "start": 0.0, "duration": 1.0}]),
    )
    second = SimpleNamespace(
        is_generated=True,
        fetch=lambda: _FetchedTranscript([{"text": "auto-2", "start": 1.0, "duration": 1.0}]),
    )
    _install(
        monkeypatch, "youtube_transcript_api", _transcript_api_module(listed=[first, second])
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL)
    assert items[0]["text"] == "auto-1"


def test_object_shaped_caption_items_are_read_by_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1.x hands back snippet objects, 0.6 handed back dicts. Both paths run."""
    fetched = _FetchedTranscript(
        [SimpleNamespace(text="snippet", start=1.5, duration=2.5)], language_code="en"
    )
    _install(
        monkeypatch, "youtube_transcript_api", _transcript_api_module(fetched=fetched)
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL, ["en"])
    assert items == [
        {"text": "snippet", "start": 1.5, "duration": 2.5, "language": "en"}
    ]


def test_a_fetched_transcript_without_a_language_code_says_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched = _FetchedTranscript([{"text": "x", "start": 0.0, "duration": 1.0}])
    fetched.language_code = None
    _install(
        monkeypatch, "youtube_transcript_api", _transcript_api_module(fetched=fetched)
    )
    _, metadata = youtube.fetch_native_transcript(REAL_URL, ["en"])
    assert metadata["language"] == "unknown"


# ---------------------------------------------------------------------------
# fetch_native_transcript — the yt-dlp fallback
# ---------------------------------------------------------------------------


def _api_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        "youtube_transcript_api",
        _transcript_api_module(error=RuntimeError("api down")),
    )


def test_automatic_captions_are_used_when_there_are_no_manual_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[dict[str, Any]] = []
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"automatic_captions": {"fr": [{}]}},
            events=[{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "bonjour"}]}],
            constructed=constructed,
        ),
    )
    items, metadata = youtube.fetch_native_transcript(REAL_URL)
    assert metadata["language"] == "fr"
    assert constructed[1]["writeautomaticsub"] is True
    assert constructed[1]["writesubtitles"] is False
    assert items[0]["text"] == "bonjour"


def test_a_preferred_language_is_chosen_from_what_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}], "de": [{}]}},
            events=[{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "hallo"}]}],
        ),
    )
    _, metadata = youtube.fetch_native_transcript(REAL_URL, ["zz", "de"])
    assert metadata["language"] == "de"


def test_no_caption_tracks_at_all_is_a_pipeline_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _api_down(monkeypatch)
    _install(monkeypatch, "yt_dlp", _ytdlp_module(info={}))
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "No native or automatic caption tracks are listed" in str(caught.value)


def test_a_missing_json3_file_is_a_pipeline_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _api_down(monkeypatch)
    _install(monkeypatch, "yt_dlp", _ytdlp_module(info={"subtitles": {"en": [{}]}}))
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "did not produce a JSON3 caption file" in str(caught.value)


def test_a_caption_file_with_no_timed_events_is_a_pipeline_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(info={"subtitles": {"en": [{}]}}, events=[{"segs": [{"utf8": "x"}]}]),
    )
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    assert "no usable timed events" in str(caught.value)


def test_a_missing_ytdlp_reports_both_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    _api_down(monkeypatch)
    _install(monkeypatch, "yt_dlp", None)
    with pytest.raises(PipelineError) as caught:
        youtube.fetch_native_transcript(REAL_URL)
    message = str(caught.value)
    assert "api down" in message and "yt-dlp:" in message


def test_a_zero_length_event_gets_the_inferred_extent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caption with no ``dDurationMs`` would otherwise be orphaned from every
    coverage window — audited but invisible (``WORKFLOW.md`` §2)."""
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[
                {"tStartMs": 0, "segs": [{"utf8": "first"}]},
                {"tStartMs": 4000, "dDurationMs": 1000, "segs": [{"utf8": "second"}]},
            ],
        ),
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL)
    assert items[0]["duration"] > 0
    assert items[0]["start"] + items[0]["duration"] <= items[1]["start"]


def test_a_boolean_duration_is_not_treated_as_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``isinstance(True, int)`` is ``True``; a JSON ``true`` is not 1 second."""
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[{"tStartMs": 0, "dDurationMs": True, "segs": [{"utf8": "x"}]}],
        ),
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL)
    assert items[0]["duration"] != 0.001


def test_events_without_a_start_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(
            info={"subtitles": {"en": [{}]}},
            events=[
                {"segs": [{"utf8": "header"}]},
                {"tStartMs": 1000, "dDurationMs": 500, "segs": [{"utf8": "real"}]},
            ],
        ),
    )
    items, _ = youtube.fetch_native_transcript(REAL_URL)
    assert [item["text"] for item in items] == ["real"]


def test_a_corrupt_caption_file_is_a_pipeline_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _api_down(monkeypatch)
    _install(
        monkeypatch,
        "yt_dlp",
        _ytdlp_module(info={"subtitles": {"en": [{}]}}, raw_caption_text="{not json"),
    )
    with pytest.raises(PipelineError):
        youtube.fetch_native_transcript(REAL_URL)


# ---------------------------------------------------------------------------
# fetch_metadata degrades rather than failing
# ---------------------------------------------------------------------------


def test_metadata_names_the_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-099: this asserted `== {}`, which is what hid the reason.

    `title` and `channel` fall back to "Unknown ...", so an absent fetch and an
    unknown title were indistinguishable in `metadata.json` — and a network
    failure, a geo-block, an age gate, a bot check and a yt-dlp API change were
    indistinguishable from each other.
    """
    _install(monkeypatch, "yt_dlp", None)
    answer = youtube.fetch_metadata(REAL_URL)
    assert answer.get("title") is None
    assert "not installed" in answer["metadata_error"]


def test_metadata_names_the_failure_when_the_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, "yt_dlp", _ytdlp_module(error=RuntimeError("boom")))
    answer = youtube.fetch_metadata(REAL_URL)
    assert answer.get("title") is None
    assert "RuntimeError" in answer["metadata_error"]
    assert "boom" in answer["metadata_error"]


def test_the_two_metadata_failures_are_distinguishable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only one of them is fixed by installing something."""
    _install(monkeypatch, "yt_dlp", None)
    absent = youtube.fetch_metadata(REAL_URL)["metadata_error"]
    _install(monkeypatch, "yt_dlp", _ytdlp_module(error=RuntimeError("geo-blocked")))
    blocked = youtube.fetch_metadata(REAL_URL)["metadata_error"]
    assert absent != blocked


def test_a_successful_fetch_names_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, "yt_dlp", _ytdlp_module(info={"title": "T", "channel": "C"}))
    assert "metadata_error" not in youtube.fetch_metadata(REAL_URL)


def test_metadata_falls_back_from_uploader_to_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, "yt_dlp", _ytdlp_module(info={"channel": "Chan"}))
    assert youtube.fetch_metadata(REAL_URL)["channel"] == "Chan"


# ---------------------------------------------------------------------------
# process_youtube_url end to end, with fakes
# ---------------------------------------------------------------------------


def test_process_youtube_url_creates_a_run_under_the_given_output_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fetched = _FetchedTranscript(
        [
            {"text": "first cue", "start": 0.0, "duration": 2.0},
            {"text": "second cue", "start": 2.0, "duration": 2.0},
        ],
        language_code="en",
    )
    _install(
        monkeypatch, "youtube_transcript_api", _transcript_api_module(fetched=fetched)
    )
    _install(
        monkeypatch, "yt_dlp", _ytdlp_module(info={"title": "A Title", "uploader": "A Chan"})
    )
    output = tmp_path / "output"
    run_dir = youtube.process_youtube_url(REAL_URL, output, ["en"])
    assert run_dir == (output / REAL_ID).resolve()
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "A Title"
    assert metadata["channel"] == "A Chan"
    assert metadata["video_id"] == REAL_ID
    transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
    assert [caption["text"] for caption in transcript["captions"]] == [
        "first cue",
        "second cue",
    ]


def test_process_youtube_url_removes_its_temporary_file_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The temp file is deleted whether the import succeeds or raises."""
    fetched = _FetchedTranscript([{"text": "x", "start": 0.0, "duration": 1.0}])
    _install(
        monkeypatch, "youtube_transcript_api", _transcript_api_module(fetched=fetched)
    )
    _install(monkeypatch, "yt_dlp", _ytdlp_module(info={}))
    seen: list[Path] = []

    def failing(path: Path, *args: object, **kwargs: object) -> Path:
        seen.append(Path(path))
        raise PipelineError("no")

    monkeypatch.setattr(youtube, "import_transcript", failing)
    with pytest.raises(PipelineError):
        youtube.process_youtube_url(REAL_URL, tmp_path / "output", ["en"])
    assert seen and not seen[0].exists()


def test_process_youtube_url_never_reaches_the_network_through_a_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The ``no_network`` fixture is the guarantee; this names it."""
    _install(monkeypatch, "youtube_transcript_api", None)
    _install(monkeypatch, "yt_dlp", None)
    with pytest.raises(PipelineError):
        youtube.process_youtube_url(REAL_URL, tmp_path / "output")
    assert not (tmp_path / "output").exists()


# ---------------------------------------------------------------------------
# Whisper is never a fallback
# ---------------------------------------------------------------------------


def test_the_module_never_reaches_for_whisper() -> None:
    """AGENTS.md: never invoke, install, or silently fall back to Whisper.

    Prose about the prohibition is fine; a reference in *code* is not.
    """
    code = [
        line
        for line in Path(youtube.__file__).read_text(encoding="utf-8").splitlines()
        if "whisper" in line.lower()
        and not line.lstrip().startswith("#")
        and "never" not in line.lower()
        and "disabled" not in line.lower()
    ]
    assert code == [], code
