from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .pipeline import import_transcript, resolve_run_dir, validate_run
from .io import write_json

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - exercised only without optional dependency
    MCPServer = None  # type: ignore[assignment]


PROJECT_ROOT = Path(os.environ.get("X2KNWLDG_PROJECT_ROOT", Path.cwd())).expanduser().resolve()


def _output_root() -> Path:
    return PROJECT_ROOT / "output"


def _run_dir(video_id: str) -> Path:
    """Every tool argument that names a run is resolved here, never joined raw
    onto a path (risk R14)."""
    return resolve_run_dir(_output_root(), video_id)


if MCPServer is not None:
    mcp = MCPServer("X2KNWLDG")

    @mcp.tool()
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
            Path(transcript_path),
            _output_root(),
            video_id=video_id,
            video_url=video_url or None,
            title=title or None,
            channel=channel or None,
            language=language,
        )
        return {"status": "IMPORTED", "output": str(run_dir)}

    @mcp.tool()
    def list_ingested_videos() -> list[dict[str, Any]]:
        """List locally ingested videos and their current coverage status."""
        rows: list[dict[str, Any]] = []
        for metadata_path in sorted(_output_root().glob("*/metadata.json")):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            coverage_path = metadata_path.parent / "coverage.json"
            coverage = (
                json.loads(coverage_path.read_text(encoding="utf-8"))
                if coverage_path.exists()
                else {"status": "MISSING"}
            )
            rows.append(
                {
                    "video_id": metadata.get("video_id"),
                    "title": metadata.get("title"),
                    "coverage": coverage.get("status"),
                    "path": str(metadata_path.parent),
                }
            )
        return rows

    @mcp.tool()
    def get_extraction_segment(video_id: str, segment_id: str) -> dict[str, Any]:
        """Read one prepared transcript segment with exact caption provenance."""
        path = _run_dir(video_id) / "segments.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        for segment in document.get("segments", []):
            if segment.get("segment_id") == segment_id:
                return segment
        raise ValueError(f"Unknown segment: {segment_id}")

    @mcp.tool()
    def get_coverage_window(video_id: str, window_id: str) -> dict[str, Any]:
        """Read one audit window together with the exact overlapping transcript captions."""
        run_dir = _run_dir(video_id)
        coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
        transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
        for window in coverage.get("windows", []):
            if window.get("window_id") != window_id:
                continue
            captions = [
                caption
                for caption in transcript.get("captions", [])
                if caption.get("end_sec", 0) > window.get("start_sec", 0)
                and caption.get("start_sec", 0) < window.get("end_sec", 0)
            ]
            return {"window": window, "captions": captions}
        raise ValueError(f"Unknown coverage window: {window_id}")

    @mcp.tool()
    def validate_video_output(video_id: str) -> dict[str, Any]:
        """Validate transcript, knowledge units, relations, and coverage."""
        return validate_run(_run_dir(video_id))

    @mcp.tool()
    def apply_extraction_bundle(video_id: str, bundle_path: str) -> dict[str, Any]:
        """Validate and store a JSON bundle containing knowledge units, relations, and coverage."""
        from .artifacts import apply_extraction_bundle as apply_bundle

        return apply_bundle(_run_dir(video_id), Path(bundle_path))

    @mcp.tool()
    def apply_extraction_data(video_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        """Validate and store extraction data directly, without requiring a separate file connector."""
        from .artifacts import apply_extraction_bundle as apply_bundle

        run_dir = _run_dir(video_id)
        bundle_path = run_dir / "work" / "mcp_extraction_bundle.json"
        write_json(bundle_path, bundle)
        return apply_bundle(run_dir, bundle_path)

    @mcp.tool()
    def finalize_video(video_id: str) -> dict[str, Any]:
        """Generate the Markdown report, graph, and Obsidian files from canonical data."""
        from .artifacts import finalize_run

        return finalize_run(_run_dir(video_id))

    @mcp.tool()
    def search_video_knowledge(
        query: str, video_id: str = "", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search canonical knowledge first and raw captions second, preserving source links."""
        from .query import search_knowledge

        return search_knowledge(
            _output_root(), query, video_id=video_id or None, limit=limit
        )

    @mcp.tool()
    def rebuild_cross_video_library() -> dict[str, Any]:
        """Rebuild the cumulative graph and canonical concept registry across local videos."""
        from .library import rebuild_library

        return rebuild_library(_output_root())

    @mcp.resource("x2knwldg://workflow")
    def workflow_resource() -> str:
        """The vendor-neutral extraction workflow."""
        return (PROJECT_ROOT / "WORKFLOW.md").read_text(encoding="utf-8")

    @mcp.resource("x2knwldg://schema/extraction-bundle")
    def extraction_schema_resource() -> str:
        """JSON Schema for the final extraction bundle."""
        return (PROJECT_ROOT / "schemas" / "extraction_bundle.schema.json").read_text(
            encoding="utf-8"
        )

    @mcp.resource("x2knwldg://prompt/{prompt_name}")
    def extraction_prompt_resource(prompt_name: str) -> str:
        """One numbered extraction-pass prompt (01 through 05)."""
        allowed = {
            "01_segment_extraction",
            "02_normalize_deduplicate",
            "03_relationships",
            "04_derived_synthesis",
            "05_coverage_audit",
        }
        if prompt_name not in allowed:
            raise ValueError(f"Unknown extraction prompt: {prompt_name}")
        return (PROJECT_ROOT / "prompts" / f"{prompt_name}.md").read_text(encoding="utf-8")

    @mcp.prompt()
    def extract_video_knowledge(video_id: str) -> str:
        """Prepare an auditable, extract-first workflow for one ingested video."""
        return f"""Process video {video_id} using x2knwldg://workflow.
Read every prepared segment with get_extraction_segment, run the five prompt passes from the project,
audit every coverage window with get_coverage_window, and repair missing meaningful units up to three
total audit attempts. Keep source and derived units separate. Apply the finished bundle with
apply_extraction_data, then call finalize_video and validate_video_output. Never report complete unless
both validation and coverage are PASS."""
else:
    mcp = None


def main() -> None:
    if mcp is None:
        raise SystemExit("Install the MCP extra first: pip install -e '.[mcp]'")
    mcp.run()


if __name__ == "__main__":
    main()
