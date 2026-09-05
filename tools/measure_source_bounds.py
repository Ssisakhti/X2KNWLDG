"""Measure the corpus the Source Map's two bounds are set against (``T-251``).

    python tools/measure_source_bounds.py
    python tools/measure_source_bounds.py --json

Two numbers in ``x2knwldg.constants`` govern automatic source synthesis, and
both exist because of a named risk rather than a preference:

``MAX_SOURCE_CANDIDATES``
    Risk **R28** — candidate discovery grows quadratically. An all-pairs walk
    over *n* sources is ``n(n-1)`` ordered comparisons, and each comparison is a
    model pass over two whole knowledge-unit sets.

``MAX_SOURCE_RELATION_BASIS``
    Risk **R27** — a source edge overclaims a whole-source verdict. A basis is
    the *qualified* ground for one relation; past a certain size it has stopped
    qualifying anything and is restating the source.

Neither number is readable off a design document, so this measures the corpus
they are set against: how many sources exist, how many knowledge units each
holds, what an all-pairs walk would actually cost over them, and how many bytes
one basis entry occupies when it is built from real identifiers.

Stdlib only, and **read-only**: it opens canonical files, counts, and prints.
It writes nothing, and it never touches ``raw/``. The convention is
``tools/generate_api_types.py``'s — a contract tool the core package can run on
a bare install (ADR 0001 invariant 5).

The corpus is every committed fixture run plus every run under ``output/`` when
one is present. ``output/`` is gitignored, so the second half differs per clone;
the report says which runs it saw, so a quoted number can always be traced back
to what produced it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: The run trees the measurement reads, in report order. The committed fixtures
#: are first because they are the half every clone has.
CORPUS_ROOTS = (
    ("fixture", PROJECT_ROOT / "tests" / "fixtures" / "runs"),
    ("fixture", PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"),
    ("ingested", PROJECT_ROOT / "output"),
)

#: Not a run: the cross-source projection over all of them, and the canonical
#: synthesis directory. ``io.discover_run_dirs`` skips both by name.
NOT_A_RUN = frozenset({"library", "synthesis"})

#: The byte budget one relation's basis is measured against. The Map draws one
#: relation detail at a time, so this is a *detail panel's* payload rather than
#: a whole graph's — an order of magnitude under `MAX_GRAPH_EDGES`'s own budget.
BASIS_BYTE_BUDGET = 32 * 1024


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _runs() -> Iterator[tuple[str, Path]]:
    for origin, root in CORPUS_ROOTS:
        if not root.is_dir():
            continue
        for run_dir in sorted(root.iterdir()):
            if not run_dir.is_dir() or run_dir.name.startswith(".") or run_dir.name in NOT_A_RUN:
                continue
            if (run_dir / "metadata.json").is_file():
                yield origin, run_dir


def measure() -> dict[str, Any]:
    """The corpus, counted. Every derived figure is arithmetic over this."""
    sources: list[dict[str, Any]] = []
    ku_ids: list[str] = []

    for origin, run_dir in _runs():
        metadata = _read_json(run_dir / "metadata.json")
        if not isinstance(metadata, dict):
            continue
        knowledge = _read_json(run_dir / "knowledge_units.json")
        units = knowledge.get("units") if isinstance(knowledge, dict) else None
        units = [unit for unit in units if isinstance(unit, dict)] if isinstance(units, list) else []
        source_units = [unit for unit in units if unit.get("source_class") == "source"]
        for unit in units:
            local_id = unit.get("id")
            if isinstance(local_id, str):
                ku_ids.append(local_id)
        declared = metadata.get("source_type")
        source_type = declared if isinstance(declared, str) and declared else "youtube"
        sources.append(
            {
                "origin": origin,
                "run": run_dir.name,
                "source_id": f"{source_type}:{metadata.get('video_id')}",
                "source_type": source_type,
                "knowledge_units": len(units),
                "source_units": len(source_units),
            }
        )

    counts = [source["knowledge_units"] for source in sources] or [0]
    n = len(sources)

    # An all-pairs walk, stated as the two things it costs: the number of
    # ordered source comparisons, and the number of knowledge-unit pairs those
    # comparisons would have to look at. Ordered, not unordered: a relation is
    # directional, and `critiques` is not its own inverse.
    ordered_pairs = n * (n - 1)
    ku_pair_total = sum(a * b for i, a in enumerate(counts) for j, b in enumerate(counts) if i != j)
    largest_pair = max(
        (a * b for i, a in enumerate(counts) for j, b in enumerate(counts) if i != j),
        default=0,
    )

    # One basis entry, serialized the way the container writes it, using the
    # longest identifiers the corpus actually holds. `separators` matches
    # `io.dumps_json`'s compact form; a pretty-printed file is larger, and the
    # bound is about a *response* body.
    widest = max(ku_ids, key=len) if ku_ids else "KU-000001"
    entry = {
        "from_ku_id": widest,
        "to_ku_id": widest,
        "relation_type": "explicitly_references",
    }
    entry_bytes = len(json.dumps(entry, separators=(",", ":")).encode("utf-8"))

    return {
        "sources": sources,
        "totals": {
            "sources": n,
            "knowledge_units": sum(counts),
            "max_knowledge_units_per_source": max(counts),
            "min_knowledge_units_per_source": min(counts),
        },
        "all_pairs": {
            "ordered_source_pairs": ordered_pairs,
            "knowledge_unit_pairs": ku_pair_total,
            "largest_single_pair": largest_pair,
        },
        "basis_entry": {
            "widest_knowledge_unit_id": widest,
            "bytes": entry_bytes,
            "byte_budget": BASIS_BYTE_BUDGET,
            "entries_within_budget": BASIS_BYTE_BUDGET // entry_bytes,
        },
    }


def report(measured: dict[str, Any]) -> str:
    lines = ["Source Map bounds — measured corpus", ""]
    lines.append(f"{'origin':<10} {'run':<28} {'source id':<34} {'KUs':>5} {'source':>7}")
    for source in measured["sources"]:
        lines.append(
            f"{source['origin']:<10} {source['run']:<28} {source['source_id']:<34} "
            f"{source['knowledge_units']:>5} {source['source_units']:>7}"
        )
    totals = measured["totals"]
    all_pairs = measured["all_pairs"]
    basis = measured["basis_entry"]
    lines += [
        "",
        f"sources                       {totals['sources']}",
        f"knowledge units               {totals['knowledge_units']}",
        f"knowledge units per source    {totals['min_knowledge_units_per_source']}"
        f"–{totals['max_knowledge_units_per_source']}",
        "",
        "an all-pairs walk over this corpus (R28 — what the candidate bound refuses)",
        f"  ordered source pairs        {all_pairs['ordered_source_pairs']}",
        f"  knowledge-unit pairs        {all_pairs['knowledge_unit_pairs']}",
        f"  largest single pair         {all_pairs['largest_single_pair']}",
        "",
        "one basis entry (R27 — what the basis bound pages)",
        f"  widest KU id in corpus      {basis['widest_knowledge_unit_id']}",
        f"  serialized bytes            {basis['bytes']}",
        f"  entries in {basis['byte_budget']} bytes      {basis['entries_within_budget']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="Print the measurement as JSON.")
    args = parser.parse_args(argv)
    measured = measure()
    print(json.dumps(measured, indent=2) if args.json else report(measured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
