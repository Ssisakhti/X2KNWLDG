from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .io import write_json


CONCEPT_KINDS = {"concept", "definition", "framework", "principle", "mental_model"}


def _concept_key(unit: dict[str, Any]) -> str:
    value = str(unit.get("canonical_concept") or unit.get("normalized_statement") or unit.get("content") or "")
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _run_dirs(output_root: Path) -> list[Path]:
    return [path.parent for path in sorted(output_root.glob("*/metadata.json"))]


def rebuild_library(output_root: Path) -> dict[str, Any]:
    output_root = output_root.expanduser().resolve()
    library_dir = output_root / "library"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    concepts_by_key: dict[str, dict[str, Any]] = {}
    videos: list[dict[str, Any]] = []

    for run_dir in _run_dirs(output_root):
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        knowledge_path = run_dir / "knowledge_units.json"
        relationships_path = run_dir / "relationships.json"
        if not knowledge_path.exists() or not relationships_path.exists():
            continue
        video_id = metadata["video_id"]
        videos.append(
            {
                "video_id": video_id,
                "title": metadata.get("title"),
                "channel": metadata.get("channel"),
                "path": str(run_dir),
            }
        )
        units = json.loads(knowledge_path.read_text(encoding="utf-8")).get("units", [])
        for unit in units:
            global_id = f"{video_id}:{unit['id']}"
            nodes.append(
                {
                    "id": global_id,
                    "local_id": unit["id"],
                    "video_id": video_id,
                    "label": unit.get("normalized_statement") or unit.get("content"),
                    "kind": unit.get("kind"),
                    "source_class": unit.get("source_class"),
                }
            )
            for source_id in unit.get("derived_from", []):
                edges.append(
                    {
                        "from": global_id,
                        "relation": "derived_from",
                        "to": f"{video_id}:{source_id}",
                        "source_class": "derived",
                        "confidence": unit.get("confidence", 0),
                    }
                )
            if unit.get("kind") in CONCEPT_KINDS:
                key = _concept_key(unit)
                if key:
                    concept = concepts_by_key.setdefault(
                        key,
                        {
                            "id": f"concept:{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}",
                            "canonical_label": unit.get("normalized_statement") or unit.get("content"),
                            "aliases": set(),
                            "occurrences": [],
                        },
                    )
                    concept["aliases"].update(unit.get("aliases", []))
                    concept["occurrences"].append(global_id)
        relationships = json.loads(relationships_path.read_text(encoding="utf-8")).get(
            "relationships", []
        )
        for edge in relationships:
            edges.append(
                {
                    **edge,
                    "from": f"{video_id}:{edge['from']}",
                    "to": f"{video_id}:{edge['to']}",
                    "video_id": video_id,
                }
            )

    concepts = []
    for concept in concepts_by_key.values():
        concept["aliases"] = sorted(concept["aliases"])
        concepts.append(concept)
        nodes.append(
            {
                "id": concept["id"],
                "label": concept["canonical_label"],
                "kind": "canonical_concept",
                "source_class": "derived",
            }
        )
        for occurrence in concept["occurrences"]:
            edges.append(
                {
                    "from": occurrence,
                    "relation": "expresses_concept",
                    "to": concept["id"],
                    "source_class": "derived",
                    "confidence": 1.0,
                }
            )

    write_json(library_dir / "graph.json", {"nodes": nodes, "edges": edges})
    write_json(library_dir / "concepts.json", {"concepts": concepts})
    write_json(library_dir / "videos.json", {"videos": videos})
    result = {
        "videos": len(videos),
        "knowledge_nodes": sum(1 for node in nodes if node.get("kind") != "canonical_concept"),
        "canonical_concepts": len(concepts),
        "edges": len(edges),
        "path": str(library_dir),
    }
    write_json(library_dir / "status.json", result)
    return result

