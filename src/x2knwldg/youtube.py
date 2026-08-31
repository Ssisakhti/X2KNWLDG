"""Native YouTube caption acquisition.

Every call in here reaches the network, and until now not one of them was
bounded: no socket timeout on any request, and whole caption files read into
memory with ``read_text()`` whatever their size. A hung or hostile host could
park the process indefinitely, and a large caption track was read before anyone
asked how large it was. The three constants below are the bounds; they are
module-level so a caller can see them and a test can tighten them.

Whisper and WhisperX are never a fallback (``AGENTS.md``). When captions cannot
be had, this module raises and the CLI asks the user for a file.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

from .pipeline import PipelineError, extract_video_id, import_transcript
from .transcripts import json3_duration

#: Seconds any single network read may block before the call is abandoned. It
#: bounds *each* socket operation, not the whole fetch, which is the guarantee
#: worth having: a host that answers slowly still finishes, a host that stops
#: answering does not hold the process.
NETWORK_TIMEOUT_SEC = 30

#: The largest caption file this module will read into memory. A json3 caption
#: track for a very long video is a few megabytes; anything past this is not a
#: transcript, and finding that out from the size on disk costs nothing while
#: finding it out from ``read_text()`` costs the whole file.
MAX_CAPTION_BYTES = 16 * 1024 * 1024

#: The most caption cues one video may yield. Ten hours of dense speech is well
#: under this; a stream that keeps producing them is refused rather than
#: accumulated.
MAX_CAPTIONS = 250_000


def _dependency_error() -> PipelineError:
    return PipelineError(
        "YouTube caption support is not installed. Install the 'youtube' optional dependency "
        "or provide an SRT/VTT/JSON transcript file."
    )


def _too_many_captions() -> PipelineError:
    return PipelineError(
        f"Caption track exceeds the {MAX_CAPTIONS}-cue bound; refusing to keep reading it"
    )


def ydl_options(**overrides: Any) -> dict[str, Any]:
    """Options for every ``YoutubeDL`` this module constructs.

    One place, so a new call site cannot be the one that forgets the timeout.
    ``socket_timeout`` is yt-dlp's own documented parameter ("time to wait for
    unresponsive hosts, in seconds"); ``retries`` is bounded for the same
    reason, since the default retry loop multiplies whatever the timeout is.
    """
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": NETWORK_TIMEOUT_SEC,
        "retries": 2,
    }
    options.update(overrides)
    return options


def bounded_http_client() -> Any | None:
    """A ``requests`` session whose every call carries a default timeout.

    ``youtube_transcript_api`` builds its own ``requests.Session`` and calls it
    with no ``timeout``, which in ``requests`` means "block forever". The
    library's only injection point is ``http_client=``, so the bound goes in a
    session that supplies the default itself. ``None`` when ``requests`` is
    absent — the caller then constructs the API unbounded rather than failing,
    because a missing transitive dependency is not this function's error to
    raise.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover - requests ships with the extra
        return None

    class _BoundedSession(requests.Session):  # type: ignore[misc, name-defined]
        def request(self, *args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", NETWORK_TIMEOUT_SEC)
            return super().request(*args, **kwargs)

    return _BoundedSession()


def _transcript_api(factory: Any) -> Any:
    """Construct the transcript API with the bounded session when it takes one.

    ``http_client=`` arrived with ``youtube_transcript_api`` 1.x. An older
    build raises ``TypeError`` for it, and an unbounded API is still better
    than no captions, so that case falls back rather than failing.
    """
    session = bounded_http_client()
    if session is not None:
        try:
            return factory(http_client=session)
        except TypeError:  # pragma: no cover - only on a pre-1.x install
            pass
    return factory()


def _read_caption_file(path: Path) -> Any:
    """Read a caption file after checking how big it is, not before."""
    size = path.stat().st_size
    if size > MAX_CAPTION_BYTES:
        raise PipelineError(
            f"Caption file is {size} bytes, over the {MAX_CAPTION_BYTES}-byte bound; "
            "refusing to read it into memory"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_native_transcript(url: str, preferred_languages: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_error: Exception | None = None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise _dependency_error() from exc

    video_id = extract_video_id(url)
    if not video_id:
        raise PipelineError("Could not extract a YouTube video ID")
    api = _transcript_api(YouTubeTranscriptApi)
    languages = preferred_languages or []
    try:
        if languages:
            fetched = api.fetch(video_id, languages=languages)
        else:
            transcripts = list(api.list(video_id))
            if not transcripts:
                raise PipelineError("No YouTube captions are available")
            manual = next((item for item in transcripts if not item.is_generated), None)
            fetched = (manual or transcripts[0]).fetch()
    except Exception as exc:
        api_error = exc
    else:
        language = getattr(fetched, "language_code", None) or "unknown"
        items = []
        for item in fetched:
            if len(items) >= MAX_CAPTIONS:
                raise _too_many_captions()
            if isinstance(item, dict):
                text = item.get("text")
                start = item.get("start")
                duration = item.get("duration")
            else:
                text = getattr(item, "text", "")
                start = getattr(item, "start", None)
                duration = getattr(item, "duration", None)
            items.append({"text": text, "start": start, "duration": duration, "language": language})
        return items, {"video_id": video_id, "language": language, "url": url}

    try:
        from yt_dlp import YoutubeDL

        with TemporaryDirectory(prefix="x2knwldg-subs-") as directory:
            with YoutubeDL(ydl_options()) as ydl:
                info = ydl.extract_info(url, download=False)
            manual = info.get("subtitles") or {}
            automatic = info.get("automatic_captions") or {}
            available = manual if manual else automatic
            if not available:
                raise PipelineError("No native or automatic caption tracks are listed")
            preferred = preferred_languages or []
            language = next((lang for lang in preferred if lang in available), None)
            language = language or next(iter(available))
            output_template = str(Path(directory) / "captions")
            options = ydl_options(
                writesubtitles=bool(manual),
                writeautomaticsub=not bool(manual),
                subtitleslangs=[language],
                subtitlesformat="json3",
                outtmpl=output_template,
            )
            with YoutubeDL(options) as ydl:
                ydl.extract_info(url, download=True)
            files = list(Path(directory).glob("captions*.json3"))
            if not files:
                raise PipelineError("yt-dlp did not produce a JSON3 caption file")
            data = _read_caption_file(files[0])
            items = []
            for event in data.get("events", []):
                if "tStartMs" not in event:
                    continue
                if len(items) >= MAX_CAPTIONS:
                    raise _too_many_captions()
                text = "".join(
                    segment.get("utf8", "")
                    for segment in event.get("segs", [])
                    if isinstance(segment, dict)
                )
                duration = event.get("dDurationMs")
                items.append(
                    {
                        "text": text,
                        "start": event["tStartMs"] / 1000,
                        "duration": (duration / 1000) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else 0.0,
                        "language": language,
                    }
                )
            # A json3 event may omit dDurationMs. A zero-length caption is
            # orphaned from every coverage window, so give it the same inferred
            # extent transcripts.py gives the file-import path.
            for position, item in enumerate(items):
                if item["duration"] > 0:
                    continue
                next_start = (
                    items[position + 1]["start"] if position + 1 < len(items) else None
                )
                item["duration"] = json3_duration(item["start"], next_start)
            if not items:
                raise PipelineError("yt-dlp caption file contained no usable timed events")
            return items, {"video_id": video_id, "language": language, "url": url}
    except Exception as ytdlp_error:
        raise PipelineError(
            f"Native YouTube captions unavailable (API: {api_error}; yt-dlp: {ytdlp_error})"
        ) from ytdlp_error


def fetch_metadata(url: str) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        return {}
    try:
        with YoutubeDL(ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title"),
            "channel": info.get("uploader") or info.get("channel"),
            "language": info.get("language"),
        }
    except Exception:
        return {}


def process_youtube_url(
    url: str,
    output_root: Path,
    preferred_languages: list[str] | None = None,
) -> Path:
    items, transcript_metadata = fetch_native_transcript(url, preferred_languages)
    metadata = fetch_metadata(url)
    language = transcript_metadata["language"]
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump({"segments": items}, handle, ensure_ascii=False)
        temporary = Path(handle.name)
    try:
        return import_transcript(
            temporary,
            output_root,
            video_id=transcript_metadata["video_id"],
            video_url=url,
            title=metadata.get("title"),
            channel=metadata.get("channel"),
            language=language,
            source="youtube_caption",
        )
    finally:
        temporary.unlink(missing_ok=True)
