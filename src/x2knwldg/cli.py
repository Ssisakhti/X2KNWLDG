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
``7``  ``PROVIDER_UNAVAILABLE`` — ``capture``'s pinned provider is
       not installed, or the binary at the pinned path is not the
       pinned build. Nothing was run and nothing was written; the
       answer is an install or a deliberate re-pin (D-208).
``8``  ``PROVIDER_UNREACHABLE`` — the read could not be completed
       for a reason that says nothing about the provider or the
       post: the tunnel this path depends on (D-209) is down, the
       request timed out, or X rate-limited the read. Nothing was
       written; the stderr envelope names which. Retry later —
       and note that this is **not** ``9``.
``9``  ``PROVIDER_DRIFT`` — the provider answered and the answer
       could not be used: not JSON, not a ``tweet`` record, or
       missing a field the capture contract requires. Distinct
       from ``8`` because D-209 requires that a routine network
       drop never read as the provider having changed.
=====  ==========================================================

``capture`` reports its coverage verdict through the same ``0``/``3``/``4`` the
rest of the pipeline uses, so a ``PARTIAL`` thread cannot be mistaken for a
whole one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .ids import IdError
from .io import CanonicalValueError, JsonReadError, discover_run_dirs
from .pipeline import (
    PipelineError,
    RunAlreadyExists,
    VerdictRefusal,
    extract_video_id,
    import_transcript,
    is_youtube_url,
    prepare_inbox,
    project_root,
)
from .query import UnsearchableRun
from .transcripts import TranscriptError

# ADR 0001 invariant 9: the local service binds loopback only. Enforced here, at
# the boundary where a host first arrives from outside the process, so `T-116`
# inherits the rule rather than having to remember it.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# The `ui` extra (pyproject.toml). Probed by name, never imported at module
# scope: invariant 5 is that `import x2knwldg.cli` needs nothing optional.
# `starlette` is here because `server/app.py` and `server/errors.py` import it
# at module scope, not because `fastapi` happens to bring it: a probe that
# names only two of the three tells a user with a broken install to fix the
# wrong thing, and `pyproject.toml`'s `ui` extra is asserted to be exactly this
# tuple, so the declaration and the probe cannot drift apart.
UI_DEPENDENCIES = ("fastapi", "starlette", "uvicorn")

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
EXIT_PROVIDER_UNAVAILABLE = 7
EXIT_PROVIDER_UNREACHABLE = 8
EXIT_PROVIDER_DRIFT = 9

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
    # `io.JsonReadError` is the package's one strict-read error: absent,
    # unreadable, malformed, or a document whose shape is not the one the
    # caller has to be able to rely on. `query.run_documents` raises it for a
    # damaged canonical file — a `knowledge_units.json` holding `[]` used to
    # escape as `AttributeError` — and it is a `ValueError`, so the tuple's
    # `json.JSONDecodeError` entry did not cover it.
    JsonReadError,
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
  7  PROVIDER_UNAVAILABLE `capture`: the pinned acquisition provider is not
                          installed, or the binary at the pinned path is not
                          the pinned build. Nothing was run
  8  PROVIDER_UNREACHABLE `capture`: the read could not be completed and
                          nothing was learned — the tunnel is down, the request
                          timed out, or X rate-limited it. Retry later
  9  PROVIDER_DRIFT       `capture`: the provider answered and the answer was
                          unusable. Never reported for a network failure

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
        description="Evidence-preserving, auditable source-to-knowledge pipeline",
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

    validate_parser = commands.add_parser("validate", help="Validate one canonical source run")
    validate_parser.add_argument("run_dir", type=Path)

    apply_parser = commands.add_parser(
        "apply-bundle", help="Validate and store model-produced knowledge, relations, and coverage"
    )
    apply_parser.add_argument("run_dir", type=Path)
    apply_parser.add_argument("bundle", type=Path)

    source_knowledge_parser = commands.add_parser(
        "apply-source-knowledge",
        help="Validate and store the readable Persian brief for one already-validated run",
    )
    source_knowledge_parser.add_argument("run_dir", type=Path)
    source_knowledge_parser.add_argument(
        "document",
        type=Path,
        help=(
            "The model's source_knowledge.json, produced by prompts/06_source_knowledge.md "
            "after apply-bundle has written this run's knowledge, relations and coverage"
        ),
    )

    candidates_parser = commands.add_parser(
        "source-candidates",
        help="List the bounded, deterministic candidate source pairs worth comparing",
    )
    candidates_parser.add_argument("--output", type=Path, default=Path("output"))

    relations_parser = commands.add_parser(
        "apply-source-relations",
        help="Validate and store model-proposed relations between whole sources",
    )
    relations_parser.add_argument(
        "document",
        type=Path,
        help=(
            "The model's source_relations.json, produced by "
            "prompts/07_source_relations.md over the output of source-candidates"
        ),
    )
    relations_parser.add_argument("--output", type=Path, default=Path("output"))

    finalize_parser = commands.add_parser(
        "finalize", help="Generate report, graph, and Obsidian files from canonical data"
    )
    finalize_parser.add_argument("run_dir", type=Path)

    status_parser = commands.add_parser("status", help="List local source processing status")
    status_parser.add_argument("--output", type=Path, default=Path("output"))

    search_parser = commands.add_parser(
        "search", help="Search canonical knowledge first, then exact transcript captions"
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--video-id")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--output", type=Path, default=Path("output"))

    library_parser = commands.add_parser(
        "rebuild-library", help="Rebuild the cumulative cross-source graph and concept registry"
    )
    library_parser.add_argument("--output", type=Path, default=Path("output"))

    capture_parser = commands.add_parser(
        "capture",
        help="Acquire one public X post, or a self-thread from its last post",
        description=(
            "Acquire one public X post, or one same-author self-thread, through the "
            "pinned local provider and write it as a schemas/capture/v1/ capture beside "
            "its immutable raw evidence. Credential-free: no X account, cookie, token or "
            "browser profile is used, needed, or read. Leaves an initialized run -- a "
            "metadata.json and an item-based coverage.json scaffolded to PARTIAL -- so "
            "apply-bundle, validate and finalize can be run against it next. A post "
            "that already has a capture is refused rather than re-acquired."
        ),
    )
    capture_parser.add_argument("reference", help="A post id, or an https://x.com/<user>/status/<id> URL")
    capture_parser.add_argument(
        "--thread",
        action="store_true",
        help=(
            "Walk the self-thread upward from this post to its root. Give the thread's "
            "LAST post: descendants cannot be enumerated credential-free (D-206), so a "
            "root anchor is reported PARTIAL"
        ),
    )
    capture_parser.add_argument(
        "--tier",
        choices=["guest", "0"],
        default="guest",
        help=(
            "Read tier. 'guest' (Tier 1) is the default and the qualified read; Tier 0 "
            "was measured truncating long posts silently (D-207)"
        ),
    )
    capture_parser.add_argument("--output", type=Path, default=Path("output"))
    capture_parser.add_argument(
        "--xcli",
        type=Path,
        help=(
            "Path to the pinned x-cli binary. Defaults to $X2KNWLDG_XCLI, then "
            "~/.local/bin/x. PATH is never searched, and the digest must match the pin"
        ),
    )
    capture_parser.add_argument("--timeout", type=float, default=30.0)
    capture_parser.add_argument(
        "--max-bytes",
        type=int,
        default=1_048_576,
        help="Refuse a response larger than this, rather than truncating it",
    )
    tunnel = capture_parser.add_mutually_exclusive_group()
    tunnel.add_argument(
        "--via-tunnel",
        dest="via_tunnel",
        action="store_true",
        default=None,
        help=(
            "State that this acquisition runs over the tunnel Phase 2.2 depends on "
            "(D-209). Required, as --via-tunnel or --no-tunnel, or via "
            "$X2KNWLDG_VIA_TUNNEL: the capture records it and this command cannot "
            "measure it"
        ),
    )
    tunnel.add_argument("--no-tunnel", dest="via_tunnel", action="store_false", default=None)
    capture_parser.add_argument(
        "--tunnel-note", help="Free text recorded beside via_tunnel, e.g. the egress it uses"
    )

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

    from .youtube import DEFAULT_PREFERRED_LANGUAGES, process_youtube_url

    # English is the default caption requirement for URL acquisition. The
    # YouTube module refuses to fall back silently to another language when
    # English is absent. An explicit ``--preferred-language`` list replaces
    # this default rather than being appended after it, so the operator always
    # has the final say.
    try:
        run_dir = process_youtube_url(
            args.source,
            args.output,
            preferred_languages=(
                args.preferred_language or list(DEFAULT_PREFERRED_LANGUAGES)
            ),
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
    aliases: list[tuple[Path, Path]] = []
    if output.exists():
        # `io.discover_run_dirs`, not a fourth `glob` (D-158): a convenience
        # symlink was listed as a second, identical video, and `library/` and
        # dotted staging directories were listed as videos at all. The aliases
        # are named rather than dropped, because "the same run under another
        # name" is a true and useful thing to say.
        run_directories, aliases = discover_run_dirs(output)
        for run_dir in run_directories:
            rows.append(_status_row(run_dir / "metadata.json"))
    unreadable = sum(1 for row in rows if "error" in row)
    print(
        json.dumps(
            {
                "videos": rows,
                "unreadable": unreadable,
                "aliases": [
                    {"path": link.name, "same_run_as": held.name}
                    for link, held in aliases
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return EXIT_OK


#: Truthy spellings of ``X2KNWLDG_VIA_TUNNEL``. An operator's standing
#: statement about this machine, set once in a shell profile, so the flag is not
#: retyped on every acquisition. Anything else — including an unset variable —
#: is not a statement, and :func:`_run_capture` refuses rather than assuming.
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _via_tunnel(explicit: bool | None) -> bool:
    """Whether this acquisition runs over the tunnel — stated, never inferred.

    D-209 is on the record because an environment premise was *taken* rather
    than established: the measurements were described as coming from Iran when
    they came through an always-on tunnel, and only an after-the-fact check
    found it. The capture schema requires ``via_tunnel`` and offers no "unknown",
    and this command genuinely cannot measure it — a ``utun`` interface existing
    is not proof that traffic routes through it, and asking a third party for
    the egress address would be a network request made to describe a network
    request. So the operator states it, and the capture records what was stated.
    """
    if explicit is not None:
        return explicit
    stated = os.environ.get("X2KNWLDG_VIA_TUNNEL", "").strip().lower()
    if stated in _TRUTHY:
        return True
    if stated in _FALSY:
        return False
    raise PipelineError(
        "Say whether this acquisition runs over the tunnel Phase 2.2 depends on: pass "
        "--via-tunnel or --no-tunnel, or set X2KNWLDG_VIA_TUNNEL=1/0. The capture records "
        "it (D-209) and this command cannot measure it, so it will not guess."
    )


def _run_capture(args: argparse.Namespace) -> int:
    """Acquire one post or self-thread. See this module's docstring for the codes."""
    from .twitter.acquire import (
        AcquisitionError,
        ProviderDrift,
        RateLimited,
        TransientFailure,
        acquire,
    )
    from .twitter.provider import TIERS, ProviderRefusal, verify

    # Stated before anything is spawned: a refusal to guess must not cost a
    # request, and `capture` is the only command in this CLI that reaches the
    # network on the user's behalf.
    via_tunnel = _via_tunnel(args.via_tunnel)

    try:
        provider = verify(args.xcli)
    except ProviderRefusal as exc:
        _fail("PROVIDER_UNAVAILABLE", str(exc), reason=exc.reason)
        return EXIT_PROVIDER_UNAVAILABLE

    try:
        result = acquire(
            args.reference,
            provider=provider,
            output_root=args.output,
            via_tunnel=via_tunnel,
            tunnel_note=args.tunnel_note,
            tier=TIERS[args.tier],
            thread=args.thread,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
    except TransientFailure as exc:
        # Nothing was learned and nothing was written, so the answer is to retry
        # later. The envelope names which of the two it was; the exit code says
        # only what a wrapper has to act on.
        status = "PROVIDER_RATE_LIMITED" if isinstance(exc, RateLimited) else (
            "PROVIDER_UNREACHABLE"
        )
        _fail(status, str(exc))
        return EXIT_PROVIDER_UNREACHABLE
    except ProviderDrift as exc:
        _fail("PROVIDER_DRIFT", str(exc))
        return EXIT_PROVIDER_DRIFT
    except ProviderRefusal as exc:
        # A verified provider can still refuse mid-run: an id that never went
        # through `parse_reference`, or a subcommand outside the allowlist. Both
        # are this package's fault rather than the user's, and neither is a
        # statement about the post.
        _fail("PROVIDER_UNAVAILABLE", str(exc), reason=exc.reason)
        return EXIT_PROVIDER_UNAVAILABLE
    except AcquisitionError as exc:
        _fail("ERROR", str(exc), error=type(exc).__name__)
        return EXIT_ERROR

    # Warnings go to stderr, so stdout stays one JSON document a caller can
    # pipe. A root anchor's warning is the one D-206 requires: the capture is
    # honest, and it is not what the user probably wanted.
    for warning in result.warnings:
        print(json.dumps({"status": "WARNING", "message": warning}, ensure_ascii=False),
              file=sys.stderr)
    # `T-229`: the capture becomes a run here, so the journey does not stop at
    # a file no command can read. `acquire` stays pure acquisition -- it writes
    # evidence and nothing else -- and this is the step that gives the run its
    # `metadata.json` and its scaffolded, item-based `coverage.json`, which is
    # what `discover_run_dirs`, `status`, `apply-bundle` and the library all
    # key on. It is the analogue of `import-transcript` for this medium, and
    # `initialize_run` refuses a run that already has canonical outputs, so a
    # re-run says so rather than overwriting an extraction.
    from .artifacts import initialize_capture_run

    initialize_capture_run(result.run_dir)
    scaffold = json.loads(
        (result.run_dir / "coverage.json").read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            {
                "status": result.coverage_status,
                "capture": str(result.capture_path),
                "run_dir": str(result.run_dir),
                "items": len(result.capture["items"]),
                "raw_evidence": [str(path) for path in result.evidence_paths],
                "routes_read": len(result.capture["acquisition"]["routes_read"]),
                # What to do next, because a capture that has become a run is
                # not obviously one: `coverage.json` is scaffolded and reports
                # `coverage_not_audited` against every item until an extraction
                # is applied, so this status is honestly not a pass yet.
                "run_coverage": scaffold.get("status"),
                "next": (
                    "extract with prompts/twitter/, then: x2knwldg apply-bundle "
                    f"{result.run_dir} <bundle.json>"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return verdict_exit_code(result.coverage_status)


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
            # `T-229`, D-243: the run says which medium it is and the dispatch
            # is in `artifacts`, not here. This called `pipeline.validate_run`
            # outright, so it reported every Twitter run as broken for having
            # no transcript -- a correct validator applied to the wrong medium.
            from .artifacts import validate_any_run

            result = validate_any_run(args.run_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return verdict_exit_code(result["status"])
        if args.command == "apply-bundle":
            from .artifacts import apply_bundle_to_any_run

            result = apply_bundle_to_any_run(args.run_dir, args.bundle)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return verdict_exit_code(result["status"])
        if args.command == "apply-source-knowledge":
            # `T-252`. A gate, like `apply-bundle`: a brief that fails
            # validation is refused rather than written. The exit code is the
            # *run's* standing verdict, re-read rather than recomputed — writing
            # an account of a run does not re-grade it, so a brief over a
            # `PARTIAL` run still exits 3.
            from .artifacts import apply_source_knowledge

            result = apply_source_knowledge(args.run_dir, args.document)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return verdict_exit_code(result["status"])
        if args.command == "source-candidates":
            # Read-only and deterministic: it opens canonical files and counts.
            # The report is what `prompts/07_source_relations.md` consumes, and
            # what the apply gate recomputes rather than trusts.
            from .candidates import discover

            report = discover(args.output)
            print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
            return EXIT_OK
        if args.command == "apply-source-relations":
            # `T-253`. A gate, like the other two: a document that fails
            # validation is refused rather than written. Its exit code is its
            # own — unlike the per-run gates, this command is about the corpus
            # and there is no single run verdict for it to report.
            from .artifacts import apply_source_relations

            result = apply_source_relations(args.document, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK
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
        if args.command == "capture":
            return _run_capture(args)
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
