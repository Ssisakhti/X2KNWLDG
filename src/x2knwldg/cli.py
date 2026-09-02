"""The ``x2knwldg`` command line.

Exit codes
----------

The pipeline's whole point is that a run which is not a pass cannot be
mistaken for one, and an exit code is the only thing a shell or a CI job
reads. ``PARTIAL`` used to exit ``0``, so no check could tell it from
``PASS``; every refusal, including the ``ui`` command's, shared ``1`` with
every real error. The codes below are the
same in every command that produces them.

=====  ==========================================================
Code   Meaning
=====  ==========================================================
``0``  ``PASS`` — the command succeeded, and any run it validated
       passed validation *and* coverage.
``1``  ``ERROR`` — the command refused or failed: a bad argument,
       a missing or corrupt canonical file, an id that is not an
       id, a run directory already in use, a missing extra. A
       JSON object with ``"status": "ERROR"`` goes to stderr.
``2``  Usage error. Reserved by ``argparse``, which exits ``2``
       for an unknown flag or a missing argument, so nothing
       semantic is given this code.
``3``  ``PARTIAL`` — every validator passed and coverage is
       honestly incomplete (``WORKFLOW.md`` §4.5). A real
       deliverable, and not a pass: completion may not be
       claimed on it.
``4``  ``FAIL`` — the run validated as failing.
``5``  ``TRANSCRIPT_REQUIRED`` — no native captions. ``inbox/``
       now holds instructions; supply a timestamped transcript.
       Whisper is never a fallback.
``6``  ``UI_NOT_BUILT`` — ``ui`` accepted its arguments and the
       server is ready, but ``web/dist`` holds no built frontend
       to serve. Distinct from ``1`` so a wrapper can run the
       build rather than report a broken install.
=====  ==========================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .ids import IdError
from .io import CanonicalValueError
from .pipeline import (
    PipelineError,
    RunAlreadyExists,
    VerdictRefusal,
    extract_video_id,
    import_transcript,
    is_youtube_url,
    prepare_inbox,
    project_root,
    validate_run,
)
from .query import UnsearchableRun
from .transcripts import TranscriptError

# ADR 0001 invariant 9: the local service binds loopback only. Enforced here, at
# the boundary where a host first arrives from outside the process, so `T-116`
# inherits the rule rather than having to remember it.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# The `ui` extra (pyproject.toml). Probed by name, never imported at module
# scope: invariant 5 is that `import x2knwldg.cli` needs nothing optional.
UI_DEPENDENCIES = ("fastapi", "uvicorn")

# The `youtube` extra. `fetch_native_transcript` needs at least one of them;
# with neither, no URL can be processed and that is a broken install, not a
# video without captions.
YOUTUBE_DEPENDENCIES = ("youtube_transcript_api", "yt_dlp")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2  # argparse's own, reproduced here so nothing else claims it
EXIT_PARTIAL = 3
EXIT_FAIL = 4
EXIT_TRANSCRIPT_REQUIRED = 5
EXIT_UI_NOT_BUILT = 6

#: One mapping, so `validate`, `apply-bundle` and `finalize` cannot drift into
#: disagreeing about what a verdict is worth.
VERDICT_EXIT_CODES = {"PASS": EXIT_OK, "PARTIAL": EXIT_PARTIAL, "FAIL": EXIT_FAIL}

# Errors a command may legitimately meet while handling user-supplied data.
# `PipelineError` alone left the documented transcript path — a malformed SRT,
# a VTT with no timings — exiting on a raw traceback, because `parse_transcript_file`
# raises `TranscriptError`. `IdError` arrives the same way from `ids.py`, and
# `OSError` from an unreadable file or directory.
USER_FACING_ERRORS = (
    PipelineError,
    TranscriptError,
    IdError,
    UnsearchableRun,
    # D-074: a canonical file timed "0.0" reached `io.format_timestamp` and
    # took `finalize` down with a raw traceback, outside this tuple and so
    # outside the documented `{"status": "ERROR"}` stderr contract.
    CanonicalValueError,
    OSError,
    json.JSONDecodeError,
)


def verdict_exit_code(status: str) -> int:
    """The exit code for a run verdict. An unknown verdict is never a pass."""
    return VERDICT_EXIT_CODES.get(status, EXIT_ERROR)


def _fail(status: str, message: str, **extra: object) -> None:
    payload: dict[str, object] = {"status": status, "message": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def _missing_dependencies(names: tuple[str, ...]) -> list[str]:
    """Which of *names* are not importable.

    ``find_spec`` rather than ``import``: probing must not execute an optional
    dependency just to report that it is present.
    """
    from importlib.util import find_spec

    missing = []
    for name in names:
        try:
            found = find_spec(name) is not None
        except (ImportError, ValueError):  # pragma: no cover - broken install
            found = False
        if not found:
            missing.append(name)
    return missing


#: Shown by ``x2knwldg --help``. The same table as this module's docstring:
#: a caller writing a shell check should not have to read the source.
EXIT_CODE_HELP = """\
exit codes:
  0  PASS                 the command succeeded; a validated run passed
                          validation and coverage
  1  ERROR                the command refused or failed (bad argument, missing
                          or corrupt canonical file, invalid id, run directory
                          already in use, missing optional extra)
  2  usage error          argparse: unknown flag or missing argument
  3  PARTIAL              validators passed, coverage is honestly incomplete
                          (WORKFLOW.md section 4.5). A deliverable, not a pass
  4  FAIL                 the run validated as failing
  5  TRANSCRIPT_REQUIRED  no native captions; supply a timestamped transcript
                          in the inbox directory this command names
  6  UI_NOT_BUILT         `ui` accepted its arguments and the server is
                          ready, but web/dist holds no built frontend to
                          serve. Build it: cd web && npm ci && npm run build

Completion may be claimed only on 0."""


#: The options ``import-transcript`` and ``process`` share. Declared once,
#: because ``process`` reaches ``_run_import`` for a local file and the two
#: commands have to agree about every one of them: a default that drifted —
#: ``--language`` or ``--output`` differing between them — would change what a
#: documented invocation does with nothing to catch it.
def _add_shared_import_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video-id", help="YouTube video ID or stable local identifier")
    parser.add_argument("--video-url", help="Original YouTube URL")
    parser.add_argument("--title")
    parser.add_argument("--channel")
    parser.add_argument("--language", default="unknown")
    parser.add_argument("--output", type=Path, default=Path("output"))


def _add_import_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("transcript", type=Path, help="Timestamped SRT, VTT, JSON, TXT, or MD")
    _add_shared_import_options(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x2knwldg",
        description="Timestamp-preserving, auditable video knowledge pipeline",
        epilog=EXIT_CODE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    _add_shared_import_options(process_parser)
    process_parser.add_argument("--preferred-language", action="append", default=[])
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
        "ui", help="Serve the local Knowledge Canvas on loopback"
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
    return EXIT_OK


def _run_process(args: argparse.Namespace) -> int:
    source_path = Path(args.source).expanduser()
    if source_path.is_file():
        args.transcript = source_path
        return _run_import(args)
    if not args.source.startswith(("https://", "http://")):
        raise PipelineError(f"Source is neither a file nor a URL: {args.source}")

    # Exact-host membership, before anything fetches anything. `extract_video_id`
    # returning an id is not evidence that the URL belongs to YouTube — under the
    # old substring host test it happily returned a real 11-character id for
    # `https://youtube.com.evil.example/watch?v=<id>`, and the *full URL* was
    # then handed to yt_dlp's generic extractor. That fetched the attacker's
    # host (SSRF) and filed whatever came back under a genuine YouTube id.
    if not is_youtube_url(args.source):
        raise PipelineError(
            f"Not a YouTube URL, refusing to fetch it: {args.source}. "
            "Pass a transcript file, or use --video-id with import-transcript."
        )
    video_id = extract_video_id(args.source)
    if not video_id:
        raise PipelineError("Could not extract a YouTube video ID from the URL")

    # A broken install is not a video without captions. Checked before the fetch
    # so the answer is "install the extra", not "go find a transcript yourself".
    missing = _missing_dependencies(YOUTUBE_DEPENDENCIES)
    if len(missing) == len(YOUTUBE_DEPENDENCIES):
        raise PipelineError(
            f"The 'youtube' extra is not installed (missing: {', '.join(missing)}). "
            "Install it with: pip install 'x2knwldg[youtube]' — or import a "
            "timestamped transcript with: x2knwldg import-transcript"
        )

    from .youtube import process_youtube_url

    try:
        run_dir = process_youtube_url(
            args.source, args.output, preferred_languages=args.preferred_language or None
        )
    except RunAlreadyExists:
        # The captions were fetched fine; this id is already taken. Asking for a
        # transcript would be a lie — the same collision would reject it.
        raise
    except (TranscriptError, PipelineError) as exc:
        # What is left really is "YouTube has no usable captions for this video".
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
        return EXIT_TRANSCRIPT_REQUIRED
    print(json.dumps({"status": "IMPORTED", "output": str(run_dir)}, ensure_ascii=False))
    return EXIT_OK


def _status_row(metadata_file: Path) -> dict[str, object]:
    """One video's status row, or a row saying why it could not be read.

    One corrupt ``metadata.json`` used to take the whole listing down with an
    uncaught ``JSONDecodeError``: a single damaged run made every *other*
    video invisible. A run that cannot be read is reported as unreadable —
    named, never silently dropped, and never reported as covered.
    """
    row: dict[str, object] = {
        "video_id": metadata_file.parent.name,
        "title": None,
        "coverage": "UNREADABLE",
        "path": str(metadata_file.parent),
    }
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        row["error"] = f"{metadata_file.name}: {exc}"
        return row
    if isinstance(metadata, dict):
        row["video_id"] = metadata.get("video_id", metadata_file.parent.name)
        row["title"] = metadata.get("title")
    else:
        row["error"] = f"{metadata_file.name}: not a JSON object"
        return row

    coverage_file = metadata_file.parent / "coverage.json"
    if not coverage_file.exists():
        row["coverage"] = "MISSING"
        return row
    try:
        coverage = json.loads(coverage_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        row["error"] = f"{coverage_file.name}: {exc}"
        return row
    row["coverage"] = coverage.get("status") if isinstance(coverage, dict) else "UNREADABLE"
    return row


def _run_status(output: Path) -> int:
    output = output.expanduser().resolve()
    rows = []
    if output.exists():
        for metadata_file in sorted(output.glob("*/metadata.json")):
            rows.append(_status_row(metadata_file))
    unreadable = sum(1 for row in rows if "error" in row)
    print(
        json.dumps(
            {"videos": rows, "unreadable": unreadable}, ensure_ascii=False, indent=2
        )
    )
    return EXIT_OK


def _missing_ui_dependencies() -> list[str]:
    """Names from the `ui` extra that are not importable."""
    return _missing_dependencies(UI_DEPENDENCIES)


def _run_ui(args: argparse.Namespace) -> int:
    """The five steps of canvas plan section 8.3, wired (`T-116`).

    Order is the contract, not a preference:

    1. **The bind address is refused first**, before the dependency probe. If
       the probe came first, ADR 0001 invariant 9 would go unenforced on every
       machine that has not installed the extra -- the check would only run
       where it was least needed.
    2. The root is resolved by ``pipeline.project_root`` and nowhere else
       (D-039), and must exist.
    3. The ``ui`` extra is probed and named if absent.
    4. The index is **refreshed**, not merely checked. Nothing else in the CLI
       builds one, so a project that had never been indexed could otherwise
       only ever be served an honest `503`; and the scan is incremental, so an
       unchanged project pays a stat walk rather than a rebuild.
    5. The socket is bound, and only then is a URL printed and a browser
       opened. ``--port`` is optional so the OS may choose a free one, which
       cannot be known before the bind.

    A project with no built frontend stops between 4 and 5 with
    ``EXIT_UI_NOT_BUILT``. That is a *next step*, not a breakage: the API is
    fine, the index is fine, and the fix is one `npm run build`. It keeps its
    own code for the reason exit `5` has one -- a wrapper that cannot tell
    "run this command next" from "your install is broken" reports the wrong
    thing to whoever reads it.
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

    # Lazily, inside the dispatch branch: `server` owns every import of the
    # `ui` extra (D-055), and importing this CLI must not pull the framework
    # in on a bare core install.
    from .server import serve as ui

    assets = ui.assets_dir(root)
    if assets is None:
        print(
            json.dumps(
                {
                    "status": "UI_NOT_BUILT",
                    "root": str(root),
                    "expected": str(Path(*ui.ASSETS_SUBPATH) / ui.ASSETS_ENTRY),
                    "message": (
                        "No built frontend to serve. Build it with: "
                        "cd web && npm ci && npm run build"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_UI_NOT_BUILT

    from .index.scanner import refresh_index
    from .index.search import document_indexer

    # `index_documents` is what fills `documents` and the FTS5 tables. Without
    # it the scan still produces a complete, correct index of sources,
    # artifacts, entities and relations -- and `/api/search` answers `0` for
    # every query, because the corpus it searches was never written. Nothing
    # else about the UI looks wrong, which is exactly why this has to be wired
    # here rather than remembered: `T-103` pairs the two, and every other
    # caller in the tree passes them together.
    report = refresh_index(root, index_documents=document_indexer(root))

    sock, listening = ui.bind(args.host, args.port)
    print(
        json.dumps(
            {
                "status": "SERVING",
                "url": listening.url,
                "root": str(root),
                "host": listening.host,
                "port": listening.port,
                "open_browser": not args.no_open,
                "index": {
                    "runs_discovered": report.runs_discovered,
                    "runs_indexed": report.runs_indexed,
                    "runs_skipped": report.runs_skipped,
                    # Named, never merely counted -- the D-043 rule. An empty
                    # list here means nothing was skipped, which is a different
                    # claim from not having looked.
                    "skipped_runs": [dict(entry) for entry in report.skipped_runs],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    try:
        ui.serve(
            project_root=root,
            assets=assets,
            sock=sock,
            listening=listening,
            open_browser=not args.no_open,
        )
    except KeyboardInterrupt:  # pragma: no cover - interactive
        pass
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run one command and return its exit code. See this module's docstring."""
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
            return verdict_exit_code(result["status"])
        if args.command == "apply-bundle":
            from .artifacts import apply_extraction_bundle

            result = apply_extraction_bundle(args.run_dir, args.bundle)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return verdict_exit_code(result["status"])
        if args.command == "finalize":
            from .artifacts import finalize_run

            result = finalize_run(args.run_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return verdict_exit_code(result["status"])
        if args.command == "status":
            return _run_status(args.output)
        if args.command == "search":
            from .query import search_knowledge

            unreadable: list[dict[str, str]] = []
            results = search_knowledge(
                args.output,
                args.query,
                video_id=args.video_id,
                limit=args.limit,
                unreadable=unreadable,
            )
            # A run this could not read is named, never absorbed: a short result
            # list and a damaged library must not look the same.
            print(
                json.dumps(
                    {"results": results, "unreadable": unreadable},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return EXIT_OK
        if args.command == "rebuild-library":
            from .library import rebuild_library

            print(json.dumps(rebuild_library(args.output), ensure_ascii=False, indent=2))
            return EXIT_OK
        if args.command == "ui":
            return _run_ui(args)
    except VerdictRefusal as exc:
        # D-082: caught before `USER_FACING_ERRORS`, which would have made this
        # exit `1`. A run that validated as failing is a *result* to report —
        # the stderr envelope says `FAIL`, not `ERROR`, and the exit code comes
        # from `VERDICT_EXIT_CODES` like every other statement of a verdict.
        _fail(exc.status, str(exc))
        return verdict_exit_code(exc.status)
    except USER_FACING_ERRORS as exc:
        # Not `PipelineError` alone. `parse_transcript_file` raises
        # `TranscriptError` for every malformed SRT/VTT/JSON — the *documented*
        # import path — and `ids.py` raises `IdError`; both used to leave the
        # CLI on a raw traceback. An unreadable file is `OSError`, and a corrupt
        # canonical file `JSONDecodeError`. Programming errors keep their
        # traceback: this tuple is the surface a user's input can reach.
        _fail("ERROR", str(exc), error=type(exc).__name__)
        return EXIT_ERROR
    parser.error("Unknown command")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
