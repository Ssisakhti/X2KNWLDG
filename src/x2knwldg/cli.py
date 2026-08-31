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
    project_root,
    validate_run,
)

# ADR 0001 invariant 9: the local service binds loopback only. Enforced here, at
# the boundary where a host first arrives from outside the process, so `T-116`
# inherits the rule rather than having to remember it.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# The `ui` extra (pyproject.toml). Probed by name, never imported at module
# scope: invariant 5 is that `import x2knwldg.cli` needs nothing optional.
UI_DEPENDENCIES = ("fastapi", "uvicorn")


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

    ui_parser = commands.add_parser(
        "ui", help="Serve the local Knowledge Canvas on loopback (not wired yet - T-116)"
    )
    ui_parser.add_argument(
        "--root",
        type=Path,
        help="Project root. Defaults to $X2KNWLDG_PROJECT_ROOT, then the working directory",
    )
    ui_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Loopback address to bind. Only 127.0.0.1, ::1, and localhost are accepted",
    )
    ui_parser.add_argument(
        "--port",
        type=int,
        help="Port to bind. Omit to let the OS choose a free one at bind time",
    )
    ui_parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
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


def _missing_ui_dependencies() -> list[str]:
    """Names from the `ui` extra that are not importable.

    Uses ``find_spec`` rather than ``import``: probing must not execute a web
    framework just to report that it is present.
    """
    from importlib.util import find_spec

    missing = []
    for name in UI_DEPENDENCIES:
        try:
            found = find_spec(name) is not None
        except (ImportError, ValueError):  # pragma: no cover - broken install
            found = False
        if not found:
            missing.append(name)
    return missing


def _run_ui(args: argparse.Namespace) -> int:
    """`T-008` stub. `T-116` wires the five steps of canvas plan section 8.3.

    Steps 1 and 2 of that contract are real here — the root is resolved and the
    bind address is checked — because both are refusals, and a refusal is worth
    having before the thing it guards exists. Steps 3 to 5 need the server
    (`T-105`-`T-108`), so this reports `UI_NOT_IMPLEMENTED` and exits 2 rather
    than starting something that cannot serve. It never prints a URL it is not
    listening on.
    """
    if args.host not in LOOPBACK_HOSTS:
        raise PipelineError(
            f"The UI binds loopback only; refusing host {args.host!r}. "
            f"Accepted: {', '.join(sorted(LOOPBACK_HOSTS))}"
        )
    if args.port is not None and not 1 <= args.port <= 65535:
        raise PipelineError(f"Port out of range: {args.port}")

    root = project_root(args.root)
    if not root.is_dir():
        raise PipelineError(f"Project root does not exist: {root}")

    missing = _missing_ui_dependencies()
    if missing:
        raise PipelineError(
            f"The 'ui' extra is not installed (missing: {', '.join(missing)}). "
            "Install it with: pip install 'x2knwldg[ui]'"
        )

    print(
        json.dumps(
            {
                "status": "UI_NOT_IMPLEMENTED",
                "root": str(root),
                "host": args.host,
                "port": args.port,
                "open_browser": not args.no_open,
                "blocked_on": ["T-105", "T-106", "T-107", "T-108", "T-116"],
                "reason": (
                    "T-008 scaffolds the command, the 'ui' extra, and web/. "
                    "The local server lands with T-105-T-108 and is wired here by T-116."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2


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
        if args.command == "ui":
            return _run_ui(args)
    except PipelineError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
