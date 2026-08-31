from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

from .pipeline import PipelineError, extract_video_id, import_transcript


def _dependency_error() -> PipelineError:
    return PipelineError(
        "YouTube caption support is not installed. Install the 'youtube' optional dependency "
        "or provide an SRT/VTT/JSON transcript file."
    )


def fetch_native_transcript(url: str, preferred_languages: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_error: Exception | None = None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise _dependency_error() from exc

    video_id = extract_video_id(url)
    if not video_id:
        raise PipelineError("Could not extract a YouTube video ID")
    api = YouTubeTranscriptApi()
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
            inspect_options = {"quiet": True, "no_warnings": True, "skip_download": True}
            with YoutubeDL(inspect_options) as ydl:
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
            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": bool(manual),
                "writeautomaticsub": not bool(manual),
                "subtitleslangs": [language],
                "subtitlesformat": "json3",
                "outtmpl": output_template,
            }
            with YoutubeDL(options) as ydl:
                ydl.extract_info(url, download=True)
            files = list(Path(directory).glob("captions*.json3"))
            if not files:
                raise PipelineError("yt-dlp did not produce a JSON3 caption file")
            data = json.loads(files[0].read_text(encoding="utf-8"))
            items = []
            for event in data.get("events", []):
                if "tStartMs" not in event:
                    continue
                text = "".join(
                    segment.get("utf8", "")
                    for segment in event.get("segs", [])
                    if isinstance(segment, dict)
                )
                items.append(
                    {
                        "text": text,
                        "start": event["tStartMs"] / 1000,
                        "duration": event.get("dDurationMs", 0) / 1000,
                        "language": language,
                    }
                )
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
        with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
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
