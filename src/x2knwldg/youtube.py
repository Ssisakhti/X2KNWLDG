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
import math
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

from .io import scrub_host_paths
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

# Acquisition-wide default, not merely a CLI convenience. Any future caller of
# this module inherits the same English-first policy unless it deliberately
# supplies another ordered list (or an empty list to accept any language).
DEFAULT_PREFERRED_LANGUAGES = ("en",)


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


def _impersonation_options() -> dict[str, Any]:
    """Return yt-dlp's typed Chrome target when its optional stack is present."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
    except ImportError:
        # Dependency reporting belongs to the caller. Keeping this import lazy
        # also preserves the package's zero-dependency core and test fakes.
        return {}
    # Translated automatic captions can require the same browser-like HTTP
    # fingerprint as YouTube's player. The `youtube` extra declares the bounded
    # curl-cffi transport that yt-dlp uses for this option.
    return {"impersonate": ImpersonateTarget.from_str("chrome")}


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
    except ImportError:  # pragma: no cover - the `youtube` extra declares it (D-112)
        return None

    class _BoundedSession(requests.Session):
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
    languages = list(
        DEFAULT_PREFERRED_LANGUAGES
        if preferred_languages is None
        else preferred_languages
    )
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
        items: list[dict[str, Any]] = []
        for item in fetched:
            if len(items) >= MAX_CAPTIONS:
                raise _too_many_captions()
            # D-167: both spellings used to default to empty — `.get("text")`
            # to `None` and `getattr(item, "text", "")` to `""` — so a caption
            # API that renames its text field produced a full-length transcript
            # of nothing, every cue marked `non_speech`, reported as a
            # successful import at exit `0`. A field that is *absent* is a
            # library that changed under us; a field that is *empty* is a
            # `[music]` cue. Only the second is a caption.
            if isinstance(item, dict):
                if "text" not in item:
                    raise _renamed_caption_field(sorted(item))
                text = item["text"]
                start = item.get("start")
                duration = item.get("duration")
            else:
                if not hasattr(item, "text"):
                    raise _renamed_caption_field(
                        sorted(name for name in dir(item) if not name.startswith("_"))
                    )
                text = item.text
                start = getattr(item, "start", None)
                duration = getattr(item, "duration", None)
            items.append({"text": text, "start": start, "duration": duration, "language": language})
        return items, {"video_id": video_id, "language": language, "url": url}

    try:
        from yt_dlp import YoutubeDL

        with TemporaryDirectory(prefix="x2knwldg-subs-") as directory:
            impersonation = _impersonation_options()
            with YoutubeDL(ydl_options(**impersonation)) as ydl:
                info = ydl.extract_info(url, download=False)
            manual = info.get("subtitles") or {}
            automatic = info.get("automatic_captions") or {}
            if not manual and not automatic:
                raise PipelineError("No native or automatic caption tracks are listed")
            preferred = languages
            selected_language: str | None = None
            use_manual = False
            for lang in preferred:
                if lang in manual:
                    selected_language = lang
                    use_manual = True
                    break
                if lang in automatic:
                    selected_language = lang
                    break
            if preferred and selected_language is None:
                available_languages = sorted(set(manual) | set(automatic))
                raise PipelineError(
                    "None of the preferred YouTube caption languages are available "
                    f"(preferred: {preferred}; available: {available_languages})"
                )
            if selected_language is None:
                # Reached only when the caller passed an *empty* preference
                # list, which is the documented way to say "any language". Any
                # is not the same as whichever, and `next(iter(...))` answered
                # with whatever order yt-dlp happened to build the dict in — so
                # the same video could be ingested in Spanish today and German
                # tomorrow, with `metadata.language` recording the accident
                # rather than a decision. Sorted, so "any" is at least the same
                # any on every run and a re-ingestion is comparable with the
                # first one. Manual still wins over automatic: that is a
                # judgement about caption quality, not about ordering.
                pool = manual if manual else automatic
                use_manual = bool(manual)
                selected_language = sorted(pool)[0]
            output_template = str(Path(directory) / "captions")
            options = ydl_options(
                **impersonation,
                writesubtitles=use_manual,
                writeautomaticsub=not use_manual,
                subtitleslangs=[selected_language],
                subtitlesformat="json3",
                outtmpl=output_template,
            )
            with YoutubeDL(options) as ydl:
                ydl.extract_info(url, download=True)
            # `sorted`, because `glob` yields in directory order and `files[0]`
            # then decides which track becomes *the* transcript by whatever the
            # filesystem happened to return first. yt-dlp names the file
            # `captions.<lang>.json3`, and a directory that ends up holding more
            # than one — a re-run into the same temporary directory, a language
            # tag yt-dlp spells two ways — silently picked one. The transcript
            # is the evidence every claim in the run is checked against, so
            # which file it came from cannot be an accident of enumeration
            # order.
            files = sorted(Path(directory).glob("captions*.json3"))
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
                        "language": selected_language,
                    }
                )
            # A json3 event may omit dDurationMs. A zero-length caption is
            # orphaned from every coverage window, so give it the same inferred
            # extent transcripts.py gives the file-import path.
            for position, item in enumerate(items):
                start = float(item["start"])
                if float(item["duration"]) > 0:
                    continue
                next_start = (
                    float(items[position + 1]["start"])
                    if position + 1 < len(items)
                    else None
                )
                item["duration"] = json3_duration(start, next_start)
            if not items:
                raise PipelineError("yt-dlp caption file contained no usable timed events")
            return items, {"video_id": video_id, "language": selected_language, "url": url}
    except PipelineError:
        # This module's own refusals are already the precise answer, and they
        # were being overwritten. "None of the preferred YouTube caption
        # languages are available (preferred: ['en']; available: ['de', 'fr'])"
        # names a fact the operator can act on — pass `--preferred-language de`,
        # or supply a transcript — and the `MAX_CAPTIONS` bound says the track
        # is not a transcript at all. Both were caught by the broad handler
        # below and re-reported as "Native YouTube captions unavailable", which
        # is the one thing that was *not* true: the captions were there and this
        # module declined them. A refusal this module worded on purpose is
        # raised as worded.
        raise
    except Exception as ytdlp_error:
        # Everything else: yt-dlp's own hierarchy, its HTTP stack, a missing
        # `yt_dlp` import. Those really do mean the captions could not be had,
        # and the message carries both attempts because either could be the
        # reason.
        raise PipelineError(
            f"Native YouTube captions unavailable (API: {api_error}; yt-dlp: {ytdlp_error})"
        ) from ytdlp_error


def fetch_metadata(url: str) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        # D-099: named for the same reason a failed fetch is. "The extra is not
        # installed" and "the fetch was blocked" both produce no title, and
        # only one of them is fixed by installing something.
        return {"metadata_error": "yt-dlp is not installed; install the `youtube` extra"}
    try:
        with YoutubeDL(ydl_options(**_impersonation_options())) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        # D-099: this was `except Exception: return {}`, which collapsed a
        # network failure, a geo-block, an age gate, a bot check and a yt-dlp
        # API change into the same answer — "no title, no channel, no
        # language" — leaving three silent `None`s in `metadata.json` and no
        # way to tell which had happened. The metadata is genuinely optional
        # (a transcript is what this project needs); *why* it is absent is not,
        # so it is named rather than dropped, which is D-045's rule applied to
        # the one fetch that had escaped it.
        #
        # Still broad on purpose: yt-dlp raises its own hierarchy plus whatever
        # its HTTP stack does, and the caller's contract is "carry on without
        # the metadata". What changed is that carrying on now says so.
        return {"metadata_error": scrub_host_paths(f"{type(exc).__name__}: {exc}")}
    return {
        "title": info.get("title") if info else None,
        "channel": (info.get("uploader") or info.get("channel")) if info else None,
        "language": info.get("language") if info else None,
        # D-168: `duration` was in the info dict and was dropped, so
        # `duration_sec` became the *caption* span and coverage was measured
        # against the transcript rather than against the video. A caption track
        # covering the first ten minutes of a two-hour talk yielded a fully
        # covered timeline — and the check could not detect the truncation,
        # because both sides of the comparison derived from the same truncated
        # number.
        "media_duration_sec": _media_duration(info),
    }


def _media_duration(info: Any) -> float | None:
    """The video's own length in seconds, when yt-dlp reported one."""
    duration = info.get("duration") if isinstance(info, dict) else None
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        return None
    duration = float(duration)
    return duration if math.isfinite(duration) and duration > 0 else None


def _renamed_caption_field(available: list[str]) -> PipelineError:
    """A caption carrying no ``text`` field at all — the library changed."""
    return PipelineError(
        "A caption snippet carries no `text` field; the transcript API has "
        f"changed its shape. Fields present: {', '.join(available) or 'none'}"
    )


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
            # D-099: so `metadata.json` can say *why* the title is unknown.
            metadata_error=metadata.get("metadata_error"),
            # D-168: the video's own length, so coverage is audited against the
            # video rather than against however much of it the captions cover.
            media_duration_sec=metadata.get("media_duration_sec"),
        )
    finally:
        temporary.unlink(missing_ok=True)
