from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .pipeline import (
    PipelineError,
    extract_video_id,
    import_transcript,
    prepare_inbox,
    validate_run,
)


def _add_import_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("transcript", type=Path, help="Timestamped SRT, VTT, JSON, TXT, or MD")
    parser.add_argument("--video-id", help="YouTube video ID or stable local identifier")
    parser.add_argument("--video-url", help="Original YouTube URL")
    parser.add_argument("--title")
    parser.add_argument("--channel")
    parser.add_argument("--language", default="unknown")
    parser.add_argument("--output", type=Path, default=Path("output"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x2knwldg",
        description="Timestamp-preserving, auditable video knowledge pipeline",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    import_parser = commands.add_parser(
        "import-transcript", help="Import a timestamped transcript without Whisper"
    )
    _add_import_options(import_parser)

    process_parser = commands.add_parser(
        "process", help="Process a local transcript or fetch native YouTube captions"
    )
    process_parser.add_argument("source", help="Transcript path or YouTube URL")
    process_parser.add_argument("--video-id")
    process_parser.add_argument("--video-url")
    process_parser.add_argument("--title")
    process_parser.add_argument("--channel")
    process_parser.add_argument("--language", default="unknown")
    process_parser.add_argument("--preferred-language", action="append", default=[])
    process_parser.add_argument("--output", type=Path, default=Path("output"))
    process_parser.add_argument("--inbox", type=Path, default=Path("inbox"))

    validate_parser = commands.add_parser("validate", help="Validate one canonical video output")
    validate_parser.add_argument("run_dir", type=Path)

    apply_parser = commands.add_parser(
        "apply-bundle", help="Validate and store model-produced knowledge, relations, and coverage"
    )
    apply_parser.add_argument("run_dir", type=Path)
    apply_parser.add_argument("bundle", type=Path)

    finalize_parser = commands.add_parser(
        "finalize", help="Generate report, graph, and Obsidian files from canonical data"
    )
    finalize_parser.add_argument("run_dir", type=Path)

    status_parser = commands.add_parser("status", help="List local video processing status")
    status_parser.add_argument("--output", type=Path, default=Path("output"))

    search_parser = commands.add_parser(
        "search", help="Search canonical knowledge first, then exact transcript captions"
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--video-id")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--output", type=Path, default=Path("output"))

    library_parser = commands.add_parser(
        "rebuild-library", help="Rebuild the cumulative cross-video graph and concept registry"
    )
    library_parser.add_argument("--output", type=Path, default=Path("output"))
    return parser


def _run_import(args: argparse.Namespace) -> int:
    video_id = args.video_id or extract_video_id(args.video_url or "")
    if not video_id:
        raise PipelineError("Provide --video-id or a YouTube --video-url")
    run_dir = import_transcript(
        args.transcript,
        args.output,
        video_id=video_id,
        video_url=args.video_url,
        title=args.title,
        channel=args.channel,
        language=args.language,
    )
    print(json.dumps({"status": "IMPORTED", "output": str(run_dir)}, ensure_ascii=False))
    return 0


def _run_process(args: argparse.Namespace) -> int:
    source_path = Path(args.source).expanduser()
    if source_path.is_file():
        args.transcript = source_path
        return _run_import(args)
    if not args.source.startswith(("https://", "http://")):
        raise PipelineError(f"Source is neither a file nor a URL: {args.source}")
    from .youtube import process_youtube_url

    video_id = extract_video_id(args.source)
    if not video_id:
        raise PipelineError("Could not extract a YouTube video ID from the URL")
    try:
        run_dir = process_youtube_url(
            args.source, args.output, preferred_languages=args.preferred_language or None
        )
    except PipelineError as exc:
        inbox = prepare_inbox(args.inbox, video_id, args.source)
        print(
            json.dumps(
                {
                    "status": "TRANSCRIPT_REQUIRED",
                    "reason": str(exc),
                    "inbox": str(inbox),
                    "whisper_fallback": False,
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps({"status": "IMPORTED", "output": str(run_dir)}, ensure_ascii=False))
    return 0


def _run_status(output: Path) -> int:
    output = output.expanduser().resolve()
    rows = []
    if output.exists():
        for metadata_file in sorted(output.glob("*/metadata.json")):
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            coverage_file = metadata_file.parent / "coverage.json"
            coverage = (
                json.loads(coverage_file.read_text(encoding="utf-8"))
                if coverage_file.exists()
                else {"status": "MISSING"}
            )
            rows.append(
                {
                    "video_id": metadata.get("video_id"),
                    "title": metadata.get("title"),
                    "coverage": coverage.get("status"),
                    "path": str(metadata_file.parent),
                }
            )
    print(json.dumps({"videos": rows}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "import-transcript":
            return _run_import(args)
        if args.command == "process":
            return _run_process(args)
        if args.command == "validate":
            result = validate_run(args.run_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in {"PASS", "PARTIAL"} else 1
        if args.command == "apply-bundle":
            from .artifacts import apply_extraction_bundle

            result = apply_extraction_bundle(args.run_dir, args.bundle)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in {"PASS", "PARTIAL"} else 1
        if args.command == "finalize":
            from .artifacts import finalize_run

            result = finalize_run(args.run_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in {"PASS", "PARTIAL"} else 1
        if args.command == "status":
            return _run_status(args.output)
        if args.command == "search":
            from .query import search_knowledge

            results = search_knowledge(
                args.output, args.query, video_id=args.video_id, limit=args.limit
            )
            print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rebuild-library":
            from .library import rebuild_library

            print(json.dumps(rebuild_library(args.output), ensure_ascii=False, indent=2))
            return 0
    except PipelineError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
