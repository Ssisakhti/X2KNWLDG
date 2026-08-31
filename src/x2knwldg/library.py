from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from . import ids
from .io import read_json_or_reason, write_json


CONCEPT_KINDS = {"concept", "definition", "framework", "principle", "mental_model"}

#: The ``kind`` given to the cross-source nodes this module synthesises. It is
#: deliberately outside ``constants.KNOWLEDGE_KINDS``: a canonical concept is not
#: a knowledge unit, and the two are counted separately in ``status.json``.
CONCEPT_NODE_KIND = "canonical_concept"


def _concept_key(unit: dict[str, Any]) -> str:
    value = str(unit.get("canonical_concept") or unit.get("normalized_statement") or unit.get("content") or "")
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _run_dirs(output_root: Path) -> list[Path]:
    return [path.parent for path in sorted(output_root.glob("*/metadata.json"))]


def _read_list(path: Path, key: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The list of objects under *key* in the JSON document at *path*.

    Returns the items it could read and a list of plain-language problems, never
    an exception: one damaged run must not be able to abort a rebuild of the
    whole library. This is the same tolerance ``adapters.read_optional_json``
    was written for — "a half-finished or damaged run must still be indexable
    and still be displayed honestly" — with the addition that what was wrong is
    *returned* rather than discarded, so the caller can record it.
    """
    document, reason = read_json_or_reason(path)
    if reason is not None:
        return [], [reason]
    if not isinstance(document, dict):
        return [], [f"{path.name} is not a JSON object"]
    value = document.get(key)
    if value is None:
        return [], [f"{path.name} states no {key!r}"]
    if not isinstance(value, list):
        return [], [f"{path.name} states a {key!r} that is not a list"]
    items = [item for item in value if isinstance(item, dict)]
    problems = []
    if len(items) != len(value):
        problems.append(f"{path.name}: {len(value) - len(items)} {key} entries are not objects")
    return items, problems


def rebuild_library(output_root: Path) -> dict[str, Any]:
    """Rebuild the cumulative cross-video graph, concept registry and status.

    Two rules govern everything below, and both are about honesty rather than
    completeness:

    **A run is never dropped in silence.** ``relationships.json`` used to be a
    precondition for indexing a run at all, so a run that had units but no
    relationships file vanished from ``graph.json``, from ``videos.json``, and
    from the ``videos`` count in ``status.json`` — while ``adapt_run`` indexed
    the very same run without complaint. Two code paths for one fact, and the
    silent one was the one a reader saw. Now the run is indexed from whatever it
    does have, and whatever it does not have is named in ``status.json``.

    **A damaged run is visible, not fatal.** Every read goes through
    ``io.read_json_or_reason`` and every id is built inside a guard, so a
    truncated ``knowledge_units.json`` costs its own run's nodes and nothing
    else. ``status.json`` then carries ``runs_discovered``, ``runs_indexed``,
    ``runs_skipped`` and the reason for each, because a count that quietly
    omits a run is a claim of completeness the library has not got.

    Nothing here invents a value: an edge nobody measured carries
    ``confidence: null`` (D-025), not a confident-looking ``1.0``.
    """
    output_root = output_root.expanduser().resolve()
    library_dir = output_root / "library"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    concepts_by_key: dict[str, dict[str, Any]] = {}
    videos: list[dict[str, Any]] = []
    skipped_runs: list[dict[str, Any]] = []
    incomplete_runs: list[dict[str, Any]] = []
    knowledge_node_count = 0

    run_dirs = _run_dirs(output_root)
    for run_dir in run_dirs:
        relative = run_dir.relative_to(output_root).as_posix()
        metadata, reason = read_json_or_reason(run_dir / "metadata.json")
        if reason is not None:
            skipped_runs.append({"relative_path": relative, "reason": reason})
            continue
        if not isinstance(metadata, dict):
            skipped_runs.append(
                {"relative_path": relative, "reason": "metadata.json is not a JSON object"}
            )
            continue
        video_id = metadata.get("video_id")
        if not isinstance(video_id, str) or not ids.is_id_part(video_id):
            # Without an addressable video id there is no library id to give
            # this run's units, so it cannot be indexed at all. Skipping is the
            # only option left; skipping *quietly* is not.
            skipped_runs.append(
                {
                    "relative_path": relative,
                    "reason": f"metadata.json declares an unusable video_id: {video_id!r}",
                }
            )
            continue
        declared_type = metadata.get("source_type")
        source_type = (
            declared_type
            if isinstance(declared_type, str) and declared_type
            else ids.DEFAULT_SOURCE_TYPE
        )
        problems: list[str] = []

        units, unit_problems = _read_list(run_dir / "knowledge_units.json", "units")
        problems.extend(unit_problems)
        unusable_units = 0
        for unit in units:
            local_id = unit.get("id")
            try:
                # The two-part form stays the node id: kg_navigator.md mandates
                # it. The three-part global id (D-011) is added alongside, never
                # instead.
                library_id = ids.make_library_id(video_id, local_id)
                global_id = ids.make_global_id(source_type, video_id, local_id).value
            except ids.IdError:
                # D-018 keeps these out of a validated run; a run reached this
                # module without being validated is exactly the case this arm
                # exists for.
                unusable_units += 1
                continue
            nodes.append(
                {
                    "id": library_id,
                    "local_id": local_id,
                    "video_id": video_id,
                    "source_type": source_type,
                    "global_id": global_id,
                    "label": unit.get("normalized_statement") or unit.get("content"),
                    "kind": unit.get("kind"),
                    "source_class": unit.get("source_class"),
                }
            )
            knowledge_node_count += 1
            derived_from = unit.get("derived_from")
            for source_id in derived_from if isinstance(derived_from, list) else []:
                try:
                    to_id = ids.make_library_id(video_id, source_id)
                except ids.IdError:
                    problems.append(
                        f"knowledge_units.json: {local_id!r} derives from an unusable id "
                        f"{source_id!r}"
                    )
                    continue
                edges.append(
                    {
                        "from": library_id,
                        "relation": "derived_from",
                        "to": to_id,
                        "source_class": "derived",
                        # The unit's own confidence, copied verbatim, and null
                        # when the unit states none. The old default of 0 was a
                        # measurement nobody took (D-025).
                        "confidence": unit.get("confidence"),
                    }
                )
            if unit.get("kind") in CONCEPT_KINDS:
                key = _concept_key(unit)
                if key:
                    concept = concepts_by_key.setdefault(
                        key,
                        {
                            "id": ids.make_concept_library_id(
                                hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
                            ),
                            "canonical_label": unit.get("normalized_statement") or unit.get("content"),
                            "aliases": set(),
                            "occurrences": [],
                        },
                    )
                    aliases = unit.get("aliases")
                    if isinstance(aliases, list):
                        concept["aliases"].update(alias for alias in aliases if isinstance(alias, str))
                    concept["occurrences"].append(library_id)
        if unusable_units:
            problems.append(
                f"knowledge_units.json: {unusable_units} units have an id that cannot "
                "become a library id (D-018)"
            )

        relationships, relationship_problems = _read_list(
            run_dir / "relationships.json", "relationships"
        )
        problems.extend(relationship_problems)
        unusable_edges = 0
        for edge in relationships:
            try:
                from_id = ids.make_library_id(video_id, edge.get("from"))
                to_id = ids.make_library_id(video_id, edge.get("to"))
            except ids.IdError:
                unusable_edges += 1
                continue
            edges.append({**edge, "from": from_id, "to": to_id, "video_id": video_id})
        if unusable_edges:
            problems.append(
                f"relationships.json: {unusable_edges} relationships name an endpoint "
                "that cannot become a library id"
            )

        videos.append(
            {
                "video_id": video_id,
                "title": metadata.get("title"),
                "channel": metadata.get("channel"),
                # Absolute, for humans and the CLI. It is a host path: it breaks
                # when the project moves, so the index must read relative_path
                # instead and never trust this one (risk R15).
                "path": str(run_dir),
                "relative_path": relative,
                # Always present, empty when the run indexed whole, so a reader
                # of videos.json alone can still tell a complete run from a
                # partial one.
                "problems": problems,
            }
        )
        if problems:
            incomplete_runs.append(
                {"relative_path": relative, "video_id": video_id, "problems": problems}
            )

    concepts = []
    for concept in concepts_by_key.values():
        concept["aliases"] = sorted(concept["aliases"])
        # A canonical concept is cross-source, so it lives in the reserved
        # library:concepts namespace (D-016) rather than in any one source.
        concept["global_id"] = ids.global_id_from_library_id(concept["id"]).value
        concepts.append(concept)
        nodes.append(
            {
                "id": concept["id"],
                "source_type": ids.LIBRARY_SOURCE_TYPE,
                "global_id": concept["global_id"],
                "label": concept["canonical_label"],
                "kind": CONCEPT_NODE_KIND,
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
                    # No confidence about this edge exists in any canonical
                    # file. It is grouped by a normalised string key, which is a
                    # match rule, not a measurement — so the edge states that it
                    # has no confidence rather than claiming a perfect one.
                    # D-025 forbids exactly this fabrication for derived_from;
                    # the same reason applies here, and the index schema already
                    # permits a null confidence on a library-synthetic edge.
                    "confidence": None,
                }
            )

    write_json(library_dir / "graph.json", {"nodes": nodes, "edges": edges})
    write_json(library_dir / "concepts.json", {"concepts": concepts})
    write_json(library_dir / "videos.json", {"videos": videos})
    result = {
        "videos": len(videos),
        # Counted as the nodes are built rather than re-derived from the ``kind``
        # string afterwards: a unit that happens to state kind
        # "canonical_concept" would otherwise be subtracted from the unit count
        # and never added to the concept count, and both numbers are read by
        # humans as facts.
        "knowledge_nodes": knowledge_node_count,
        "canonical_concepts": len(concepts),
        "edges": len(edges),
        # A count that omits a run without saying so is a claim of completeness
        # the library has not got. These four fields are what make ``videos``
        # readable: it is the number indexed, not the number found.
        "runs_discovered": len(run_dirs),
        "runs_indexed": len(videos),
        "runs_skipped": len(skipped_runs),
        "skipped_runs": skipped_runs,
        "incomplete_runs": incomplete_runs,
        "path": str(library_dir),
        "relative_path": library_dir.relative_to(output_root).as_posix(),
    }
    write_json(library_dir / "status.json", result)
    return result
