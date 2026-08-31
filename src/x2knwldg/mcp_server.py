"""The MCP tool surface.

Three rules govern everything below, and they are the reason the tools are
plain module-level functions with the registration bolted on afterwards rather
than closures hidden inside ``if MCPServer is not None:``.

1. **The root is proven, never assumed.** ``pipeline.project_root`` falls back
   to the working directory (D-039), which is the right default and a terrible
   silent failure: pointed at the wrong directory the server used to answer
   ``list_ingested_videos`` with ``[]`` — "you have no videos" — when the truth
   was "I am looking in the wrong place". :func:`_checked_project_root` refuses
   instead, and :func:`main` refuses *before* the server starts.
2. **Nothing raw crosses the boundary.** Every tool goes through
   :func:`_boundary`, which turns whatever went wrong into one
   :class:`McpToolError` carrying a D-030 code, with host filesystem paths
   redacted out of the message. Absolute paths never appear in a *successful*
   reply either: a run is identified by its id and its project-relative path.
3. **An externally supplied name is resolved, never joined.** A run id goes
   through ``pipeline.resolve_run_dir`` ([ADR 0003](../../docs/adr/0003-reject-unsafe-identifiers.md));
   the two tool parameters that are filesystem paths go through
   :func:`_checked_input_path`, which proves the resolved path still sits under
   the project root (ADR 0003 invariant 5).

Being importable without the ``mcp`` extra is deliberate: the tools are the
behaviour, the decorators are only registration, and a test suite that can only
run the tools on a machine with the optional dependency installed is how this
module came to have no tests at all.
"""

from __future__ import annotations

import json
import re
import tempfile
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from .pipeline import PipelineError, import_transcript, project_root, resolve_run_dir, validate_run
from .io import write_json
from .coverage import caption_in_window

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - exercised only without optional dependency
    MCPServer = None  # type: ignore[assignment]


#: The one root-resolution rule (D-039): explicit, then ``X2KNWLDG_PROJECT_ROOT``,
#: then the working directory. The env var is read there and nowhere else.
PROJECT_ROOT = project_root()

#: What makes a directory *this* project rather than whatever directory the
#: server happened to start in. Each one is something this module itself serves
#: or reads, so a root missing them cannot answer a single tool honestly.
PROJECT_MARKERS = ("WORKFLOW.md", "prompts", "schemas/extraction_bundle.schema.json")

#: D-030's taxonomy, as the codes this server puts on the wire. ``invalid_id``
#: is a refused identifier (never dressed up as absence), ``not_found`` a
#: well-formed name for nothing, ``unavailable`` a record whose file will not
#: read, ``index_unavailable`` a project that cannot be served at all, and
#: ``invalid_request`` an argument refused before anything was read.
ERROR_CODES = frozenset(
    {"invalid_id", "not_found", "unavailable", "index_unavailable", "invalid_request",
     "internal_error"}
)

#: Anything still shaped like an absolute path after the named roots are
#: replaced. The lookbehind keeps it off the tail of a placeholder we just
#: wrote, so ``<project>/output/x`` survives intact.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w>])(?:/[A-Za-z0-9._\- ]+){2,}")


class McpToolError(RuntimeError):
    """The only error type a tool lets out.

    Carries a D-030 ``code`` so a client can tell "that id is not an id" from
    "no such run" from "this project cannot be served", and a ``message`` that
    has already been through :func:`_redact`. Raising anything else out of a
    tool is a bug; :func:`_boundary` converts it rather than trusting it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _redact(text: str) -> str:
    """Strip host filesystem paths out of a message before it leaves the process.

    An MCP client is on the other side of a process boundary and has no
    business learning the operator's home directory, temp directory, or where
    the project is checked out. The named roots go first, longest first so a
    temp dir nested under home is not half-replaced; whatever still looks
    absolute afterwards is a path we did not anticipate and is reduced to its
    last segment.
    """
    replacements: list[tuple[str, str]] = []
    for label, candidate in (
        ("<project>", PROJECT_ROOT),
        ("<home>", Path.home()),
        ("<tmp>", Path(tempfile.gettempdir())),
    ):
        try:
            resolved = str(Path(candidate).expanduser().resolve())
        except (OSError, RuntimeError):  # pragma: no cover - unreadable home
            continue
        if len(resolved) > 1:
            replacements.append((resolved, label))
    for needle, label in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(needle, label)
    return _ABSOLUTE_PATH_RE.sub(lambda match: f"<path>/{match.group(0).rsplit('/', 1)[-1]}", text)


def _checked_project_root() -> Path:
    """The project root, or a refusal.

    ``project_root()`` answers "where would the project be", not "is there a
    project there". Answering tools from a directory holding none of
    :data:`PROJECT_MARKERS` produces an empty library and a confident tone, which
    is the dishonesty this whole surface is meant to avoid: an empty answer
    presented as a fact about the user's data when it is a fact about the
    server's configuration.
    """
    missing = [marker for marker in PROJECT_MARKERS if not (PROJECT_ROOT / marker).exists()]
    if missing:
        raise McpToolError(
            "index_unavailable",
            "The configured project root is not an X2KNWLDG project (missing: "
            f"{', '.join(missing)}). Set X2KNWLDG_PROJECT_ROOT to the project "
            "directory, or start the server from it. Refusing rather than "
            "reporting an empty library.",
        )
    return PROJECT_ROOT


def _output_root() -> Path:
    return _checked_project_root() / "output"


def _run_dir(video_id: str) -> Path:
    """Every tool argument that names a run is resolved here, never joined raw
    onto a path (risk R14, ADR 0003).

    The refusal and the absence are different answers on purpose: a rejected id
    is ``invalid_id`` and a well-formed id naming nothing is ``not_found``
    (D-030). Collapsing them would hide a traversal attempt behind an ordinary
    "no such video".
    """
    try:
        run_dir = resolve_run_dir(_output_root(), video_id)
    except PipelineError as exc:
        raise McpToolError("invalid_id", f"Not a usable video id: {video_id!r}") from exc
    if not run_dir.is_dir():
        raise McpToolError("not_found", f"No ingested video with id {video_id!r}")
    return run_dir


def _checked_input_path(value: str, *, what: str) -> Path:
    """A filesystem path that arrived from an MCP client.

    Two tool parameters are paths rather than ids, so ``resolve_run_dir`` is not
    the check for them — but its *behaviour* is (ADR 0003 invariant 5): resolve,
    then prove the result still sits under the root, then refuse if it does not.
    A relative path is taken against the project root, so a client never has to
    know, or learn, where the project lives on this machine.
    """
    root = _checked_project_root()
    if not value or "\x00" in value:
        raise McpToolError("invalid_request", f"{what} is empty or contains a null byte")
    candidate = Path(value).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if root not in resolved.parents:
        raise McpToolError(
            "invalid_request",
            f"{what} must name a file inside the project directory: {value!r}",
        )
    if not resolved.is_file():
        raise McpToolError("not_found", f"{what} does not name a readable file: {value!r}")
    return resolved


def _relative(path: Path) -> str:
    """A run's location as the client may see it: relative to the project root.

    Risk R15's rule, reused rather than restated — ``adapters.project_relative``
    is the project's one implementation. Imported lazily so importing this
    module stays as cheap as the zero-dependency core.
    """
    from .adapters import project_relative

    root = _checked_project_root()
    try:
        return project_relative(path, root)
    except Exception as exc:  # AdapterError, whose message carries both paths
        raise McpToolError(
            "internal_error", "Resolved a run outside the project root"
        ) from exc


_Tool = TypeVar("_Tool", bound=Callable[..., Any])


def _boundary(function: _Tool) -> _Tool:
    """Convert anything a tool raises into one redacted :class:`McpToolError`.

    Without this, a corrupt ``coverage.json`` reached the client as a
    ``JSONDecodeError`` naming the absolute path of the file, and an unexpected
    bug reached it as a traceback-shaped string. The client gets a code it can
    branch on and a message it can show; the operator's filesystem stays on the
    operator's machine.
    """

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except McpToolError:
            raise
        except PipelineError as exc:
            raise McpToolError("invalid_request", _redact(str(exc))) from exc
        except FileNotFoundError as exc:
            name = Path(exc.filename).name if exc.filename else "a canonical file"
            raise McpToolError("not_found", f"Missing canonical file: {name}") from exc
        except OSError as exc:
            raise McpToolError("unavailable", _redact(str(exc))) from exc
        except ValueError as exc:  # json.JSONDecodeError included
            raise McpToolError("unavailable", _redact(str(exc))) from exc
        except Exception as exc:  # pragma: no cover - the genuinely unexpected
            raise McpToolError(
                "internal_error", f"{type(exc).__name__}: {_redact(str(exc))}"
            ) from exc

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@_boundary
def import_timestamped_transcript(
    transcript_path: str,
    video_id: str,
    video_url: str = "",
    title: str = "",
    channel: str = "",
    language: str = "unknown",
) -> dict[str, Any]:
    """Import an SRT, VTT, or JSON transcript without invoking Whisper."""
    run_dir = import_transcript(
        _checked_input_path(transcript_path, what="transcript_path"),
        _output_root(),
        video_id=video_id,
        video_url=video_url or None,
        title=title or None,
        channel=channel or None,
        language=language,
    )
    return {"status": "IMPORTED", "video_id": run_dir.name, "path": _relative(run_dir)}


@_boundary
def list_ingested_videos() -> list[dict[str, Any]]:
    """List locally ingested videos and their current coverage status."""
    from .cli import _status_row

    rows: list[dict[str, Any]] = []
    for metadata_path in sorted(_output_root().glob("*/metadata.json")):
        # One damaged run must not make every other video invisible, and must
        # not be reported as covered either. `_status_row` is the CLI's answer
        # to exactly that; one implementation, so `status` and this tool cannot
        # disagree about what a run's state is.
        row = _status_row(metadata_path)
        row["path"] = _relative(metadata_path.parent)
        rows.append(row)
    return rows


@_boundary
def get_extraction_segment(video_id: str, segment_id: str) -> dict[str, Any]:
    """Read one prepared transcript segment with exact caption provenance."""
    path = _run_dir(video_id) / "segments.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    for segment in document.get("segments", []):
        if segment.get("segment_id") == segment_id:
            return segment
    raise McpToolError("not_found", f"Unknown segment: {segment_id!r}")


@_boundary
def get_coverage_window(video_id: str, window_id: str) -> dict[str, Any]:
    """Read one audit window together with the exact overlapping transcript captions."""
    run_dir = _run_dir(video_id)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
    windows = coverage.get("windows", [])
    for index, window in enumerate(windows):
        if window.get("window_id") != window_id:
            continue
        # Same membership rule coverage.py audits by, so a zero-length
        # caption is never audited-but-invisible here.
        captions = [
            caption
            for caption in transcript.get("captions", [])
            if caption_in_window(
                {
                    "start_sec": caption.get("start_sec", 0),
                    "end_sec": caption.get("end_sec", 0),
                },
                window.get("start_sec", 0),
                window.get("end_sec", 0),
                index == len(windows) - 1,
            )
        ]
        return {"window": window, "captions": captions}
    raise McpToolError("not_found", f"Unknown coverage window: {window_id!r}")


@_boundary
def validate_video_output(video_id: str) -> dict[str, Any]:
    """Validate transcript, knowledge units, relations, and coverage."""
    return validate_run(_run_dir(video_id))


@_boundary
def apply_extraction_bundle(video_id: str, bundle_path: str) -> dict[str, Any]:
    """Validate and store a JSON bundle containing knowledge units, relations, and coverage."""
    from .artifacts import apply_extraction_bundle as apply_bundle

    run_dir = _run_dir(video_id)
    return apply_bundle(run_dir, _checked_input_path(bundle_path, what="bundle_path"))


@_boundary
def apply_extraction_data(video_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate and store extraction data directly, without requiring a separate file connector."""
    from .artifacts import apply_extraction_bundle as apply_bundle

    # Resolved *and* proven to exist before anything is written. This used to
    # write the bundle first, so a typo'd id left a phantom `output/<typo>/work/`
    # directory behind on the way to the error — and the next `list_ingested_videos`
    # then had a run-shaped thing to trip over.
    run_dir = _run_dir(video_id)
    if not (run_dir / "transcript.json").is_file():
        raise McpToolError(
            "not_found",
            f"{video_id!r} has no transcript.json; import a transcript before applying a bundle",
        )
    bundle_path = run_dir / "work" / "mcp_extraction_bundle.json"
    write_json(bundle_path, bundle)
    return apply_bundle(run_dir, bundle_path)


@_boundary
def finalize_video(video_id: str) -> dict[str, Any]:
    """Generate the Markdown report, graph, and Obsidian files from canonical data."""
    from .artifacts import finalize_run

    return finalize_run(_run_dir(video_id))


@_boundary
def search_video_knowledge(
    query: str, video_id: str = "", limit: int = 10
) -> dict[str, Any]:
    """Search canonical knowledge first and raw captions second, preserving source links."""
    from .query import search_knowledge

    unreadable: list[dict[str, str]] = []
    results = search_knowledge(
        _output_root(),
        query,
        video_id=video_id or None,
        limit=limit,
        unreadable=unreadable,
    )
    # `unreadable` names the runs a scan could not read. An agent reading these
    # results has to be able to tell "no such knowledge" from "could not look".
    return {"results": results, "unreadable": unreadable}


@_boundary
def rebuild_cross_video_library() -> dict[str, Any]:
    """Rebuild the cumulative graph and canonical concept registry across local videos."""
    from .library import rebuild_library

    return rebuild_library(_output_root())


# ---------------------------------------------------------------------------
# Resources and prompts
# ---------------------------------------------------------------------------

#: The five numbered passes, in the order `WORKFLOW.md` §3 runs them. An
#: allow-list, because a resource template parameter is an externally supplied
#: name reaching a filesystem join like any other.
EXTRACTION_PROMPTS = (
    "01_segment_extraction",
    "02_normalize_deduplicate",
    "03_relationships",
    "04_derived_synthesis",
    "05_coverage_audit",
)


@_boundary
def workflow_resource() -> str:
    """The vendor-neutral extraction workflow."""
    return (_checked_project_root() / "WORKFLOW.md").read_text(encoding="utf-8")


@_boundary
def extraction_schema_resource() -> str:
    """JSON Schema for the final extraction bundle."""
    return (
        _checked_project_root() / "schemas" / "extraction_bundle.schema.json"
    ).read_text(encoding="utf-8")


@_boundary
def extraction_prompt_resource(prompt_name: str) -> str:
    """One numbered extraction-pass prompt (01 through 05)."""
    if prompt_name not in EXTRACTION_PROMPTS:
        raise McpToolError("invalid_id", f"Unknown extraction prompt: {prompt_name!r}")
    return (_checked_project_root() / "prompts" / f"{prompt_name}.md").read_text(
        encoding="utf-8"
    )


@_boundary
def extract_video_knowledge(video_id: str) -> str:
    """Prepare an auditable, extract-first workflow for one ingested video."""
    return f"""Process video {video_id} using x2knwldg://workflow.
Read every prepared segment with get_extraction_segment, run the five prompt passes from the project,
audit every coverage window with get_coverage_window, and repair missing meaningful units up to three
total audit attempts. Keep source and derived units separate. Apply the finished bundle with
apply_extraction_data, then call finalize_video and validate_video_output. Never report complete unless
both validation and coverage are PASS."""


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

#: Every callable the server exposes as a tool. Named here rather than only in
#: decorators so a test can walk the surface and prove none of it is unreachable.
TOOLS: tuple[Callable[..., Any], ...] = (
    import_timestamped_transcript,
    list_ingested_videos,
    get_extraction_segment,
    get_coverage_window,
    validate_video_output,
    apply_extraction_bundle,
    apply_extraction_data,
    finalize_video,
    search_video_knowledge,
    rebuild_cross_video_library,
)

#: ``(uri, callable)``. The templated one carries ``{prompt_name}``.
RESOURCES: tuple[tuple[str, Callable[..., Any]], ...] = (
    ("x2knwldg://workflow", workflow_resource),
    ("x2knwldg://schema/extraction-bundle", extraction_schema_resource),
    ("x2knwldg://prompt/{prompt_name}", extraction_prompt_resource),
)

PROMPTS: tuple[Callable[..., Any], ...] = (extract_video_knowledge,)


if MCPServer is not None:
    mcp = MCPServer("X2KNWLDG")
    for _tool in TOOLS:
        mcp.tool()(_tool)
    for _uri, _resource in RESOURCES:
        mcp.resource(_uri)(_resource)
    for _prompt in PROMPTS:
        mcp.prompt()(_prompt)
else:
    mcp = None


def main() -> None:
    if mcp is None:
        raise SystemExit("Install the MCP extra first: pip install -e '.[mcp]'")
    try:
        _checked_project_root()
    except McpToolError as exc:
        # Refuse to start. A server that comes up on the wrong root answers
        # every question with a confident, empty, wrong answer.
        raise SystemExit(f"x2knwldg-mcp: {exc.message}") from exc
    mcp.run()


if __name__ == "__main__":
    main()
