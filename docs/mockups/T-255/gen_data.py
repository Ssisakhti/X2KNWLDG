"""Generate docs/mockups/T-255/data.js from the two source-graph reads.

Run it from a clone:

    .venv/bin/python docs/mockups/T-255/gen_data.py

Every body in `data.js` comes out of `IndexRepository.source_graph` and
`source_neighborhood` over a project this script builds from **committed
fixtures only**. It reads nothing under `output/`, so the mockups reproduce in
any clone -- which `docs/mockups/T-211/gen_data.py` does not, because it reads a
run that has since left this machine's `output/`. That is R15's shape surviving
the fix meant to close it: its *paths* were made repository-relative and the
*data* they name was not.

The repository payload is what the route puts in `data`: `routes/source_graph.py`
"does not compute `truncated`, `counts` or `basis_returned` -- those come out of
the payload the repository built". So a body here is the served body with the
envelope (`api_version`, `schema_version`, `page`) left off, and `page` is
recorded separately where a picture needs it.

Two corpora, and the difference between them is the whole reason this file has a
docstring.

**served/** is `tests/source_map_corpus.py` -- four runs, three gated Persian
briefs and the one gated relation `tests/fixtures/source-map/valid/synthesis/`
holds. Nothing in it is invented. It is also, measured, four nodes and **one**
edge, which is not a picture of a graph.

**dense/** is every committed fixture run that declares a distinct source -- ten
of them, across both media -- with a `source_relations.json` this script writes.
Those relations are **SYNTHETIC and the pages say so on their face.** What is
real in them is everything a machine can derive: the ids come from
`ids.source_relation_id` over the endpoints, the endpoint digests come from
`candidates.discover`'s own report, and every basis entry names knowledge-unit
ids that exist in the run that claims them. What is invented is the editorial
judgement -- that this source critiques that one -- and its Persian rationale.

Why they are invented rather than discovered: `candidates.discover` over these
ten sources proposes **three** unordered pairs, all `youtube:fixture-*` to
`youtube:fixture-*` through one shared canonical concept, and **no cross-medium
pair at all**. Every committed Twitter run emits `quote` and `synthesis` units
rather than concept kinds -- `tests/source_corpus.py` explains why that is
deliberate and must not be edited away -- so a corpus of committed fixtures
cannot yield a dense or cross-medium relation set honestly. Three edges over a
FAIL run is the ceiling, and it is measured here rather than assumed.

Nothing this script writes reaches `output/`, the vault, or any canonical file.
It writes exactly one file: `data.js` beside itself.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

FIXTURE_RUNS = ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = ROOT / "tests" / "fixtures" / "twitter-runs"
SOURCE_MAP = ROOT / "tests" / "fixtures" / "source-map" / "valid"

#: `tw-edit` and `tw-single-post` declare the **same** source (`twitter:20`):
#: one is the other's edit history. A project holds one run per source, so the
#: dense corpus takes `single-post` and says here why the other is absent.
DENSE_SKIP = frozenset({"edit"})

#: The three committed briefs, and the run each was generated against. A brief
#: invented here would carry a digest of nothing and report `stale` on sight.
BRIEFS = {
    "pass-run": "youtube-source_knowledge.json",
    "partial-run": "partial-source_knowledge.json",
    "twitter-quote": "twitter-source_knowledge.json",
}

#: The one **gated** relation, carried into the dense corpus unchanged so the
#: dense picture holds exactly one edge that is not synthetic and can mark it.
GATED_RELATION = SOURCE_MAP / "synthesis" / "source_relations.json"

# ---------------------------------------------------------------------------
# The synthetic relation set. Ids, digests and basis units are derived; the
# judgement and the rationale are written. See the module docstring.
# ---------------------------------------------------------------------------

YT_PASS = "youtube:fixture-pass"
YT_PARTIAL = "youtube:fixture-partial"
YT_FAIL = "youtube:fixture-fail"
TW_QUOTE = "twitter:2094039408081068233"
TW_THREAD = "twitter:2094037638856454625"
TW_PARTIAL = "twitter:1795393908886712425"
TW_FA = "twitter:2027781710667010262"
TW_FA_LTR = "twitter:1580541310636883972"
TW_FIRST = "twitter:20"
TW_TOMB = "twitter:999999999999999999"

#: ``(from, to, source relation type, scope, basis size, KU relation type,
#:   Persian rationale)``. The rationales are written for this mockup and are
#: not canonical text; they exercise Persian body copy at real lengths.
SYNTHETIC: tuple[tuple[str, str, str, str, int, str, str], ...] = (
    (TW_THREAD, YT_PASS, "supports", "broad", 3, "is_evidence_for",
     "این رشته‌پست (thread) همان ادعای مرکزی ویدیو را با گزارش لحظه‌به‌لحظهٔ یک رویداد پشتیبانی می‌کند؛ گسترهٔ نسبت «broad» است، چون بیش از یک جفت واحد دانش آن را می‌سازد."),
    (YT_PARTIAL, YT_PASS, "extends", "partial", 2, "refines",
     "این منبع همان چارچوب را یک گام جلوتر می‌برد و تنها بر دو جفت واحد دانش تکیه دارد، پس گستره جزئی (partial) است."),
    (YT_PASS, TW_PARTIAL, "applies", "partial", 2, "exemplifies",
     "ویدیو قاعده‌ای را می‌گوید و این رشته‌پستِ ناقص آن را در یک مورد مشخص به کار می‌بندد؛ چون رشته ناقص ثبت شده، ادعا فراتر از دو جفت پشتیبان نمی‌رود."),
    (YT_PASS, TW_FA, "overlaps_with", "broad", 2, "related_to",
     "هر دو منبع یک موضوع مشترک را پوشش می‌دهند بی‌آنکه یکی دیگری را نقل کند؛ هم‌پوشانی است، نه استناد."),
    (YT_PASS, YT_FAIL, "contradicts", "partial", 1, "contradicts",
     "یک جفت واحد دانش این دو منبع را در تقابل می‌گذارد. منبع مقابل وضعیت FAIL دارد، پس این یال دربارهٔ اعتبار آن چیزی نمی‌گوید."),
    (TW_THREAD, TW_QUOTE, "explicitly_references", "partial", 1, "related_to",
     "پستِ نقل‌قول به همین رشته ارجاع می‌دهد؛ ارجاع صریح است، اما همچنان استنتاجی (derived) به شمار می‌رود، چون خودِ منبع‌ها این نسبت را نساخته‌اند."),
    (TW_PARTIAL, TW_FIRST, "responds_to", "partial", 1, "related_to",
     "این رشته در پاسخ به نخستین پست منتشرشده در این سکو نوشته شده است."),
    (TW_FA, TW_FA_LTR, "overlaps_with", "broad", 2, "related_to",
     "دو منبع فارسی‌زبان با موضوع نزدیک؛ هیچ‌کدام دیگری را نقل نکرده است."),
    (YT_PARTIAL, TW_THREAD, "supports", "partial", 2, "supports",
     "دو جفت واحد دانش، ادعای این رشته را از سمت یک منبع دیگر تأیید می‌کنند."),
    (TW_FA_LTR, YT_PARTIAL, "applies", "partial", 1, "exemplifies",
     "این منبع همان روش را در زمینه‌ای دیگر به کار می‌بندد."),
    (TW_FIRST, YT_FAIL, "overlaps_with", "partial", 1, "related_to",
     "هم‌پوشانی موضوعی محدود؛ یک جفت واحد دانش پشتیبان آن است."),
    (YT_FAIL, TW_PARTIAL, "responds_to", "broad", 1, "related_to",
     "این منبع به پرسشی که در آن رشته مطرح شده پاسخ می‌دهد."),
    (TW_QUOTE, TW_FA, "supports", "partial", 2, "supports",
     "دو جفت واحد دانش، گزارهٔ مشترک این دو پست را پشتیبانی می‌کنند."),
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_id(run: Path) -> str:
    metadata = _read(run / "metadata.json")
    declared = metadata.get("source_type")
    if declared is None:
        declared = "twitter" if "author_username" in metadata else "youtube"
    return f"{declared}:{metadata['video_id']}"


def _units(run: Path) -> list[str]:
    document = _read(run / "knowledge_units.json")
    return [unit["id"] for unit in document["units"]]


def _served(tmp: Path) -> dict[str, Any]:
    """The `T-254` corpus, its four bodies, its bound and its stale state."""
    import source_map_corpus as corpus
    from x2knwldg.repository import (
        MemoryRepository,
        SourceGraphQuery,
        SourceNeighborhoodQuery,
    )

    root = tmp / "served"
    root.mkdir(parents=True)
    corpus.build(root)
    repo = MemoryRepository.from_project(root)

    graph = repo.source_graph(SourceGraphQuery())
    bounded = repo.source_graph(SourceGraphQuery(limit=1))
    focus = {
        source_id: repo.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_id)
        ).payload()
        for source_id in corpus.SOURCE_IDS
    }

    # `stale` is not in the corpus as built: it costs one edit to a run's
    # knowledge units and a re-read. The oracle recomputes the state from the
    # run, so no re-scan is needed here -- a scan is what the *stored* copy
    # needs, and `T-254` proved the two agree.
    units = root / "output" / "pass-run" / "knowledge_units.json"
    document = _read(units)
    document["units"][0]["confidence"] = 0.55
    units.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    stale = MemoryRepository.from_project(root).source_neighborhood(
        SourceNeighborhoodQuery(source_id=corpus.YOUTUBE_PASS)
    ).payload()

    return {
        "graph": graph.payload(),
        "page": {"limit": graph.limit, "total": graph.total, "next_cursor": graph.next_cursor},
        "bounded": bounded.payload(),
        "bounded_page": {
            "limit": bounded.limit,
            "total": bounded.total,
            "next_cursor": bounded.next_cursor,
        },
        "focus": focus,
        "stale": stale,
        "relation_id": corpus.RELATION_ID,
        "unknown_source": corpus.UNKNOWN_SOURCE,
    }


def _dense_corpus(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Every committed fixture run that declares a distinct source."""
    from x2knwldg.library import rebuild_library

    output = root / "output"
    output.mkdir(parents=True)
    seen: dict[str, str] = {}
    units: dict[str, list[str]] = {}
    for tree, prefix in ((FIXTURE_RUNS, ""), (TWITTER_RUNS, "tw-")):
        for run in sorted(tree.iterdir()):
            if not run.is_dir() or not (run / "metadata.json").exists():
                continue
            if prefix and run.name in DENSE_SKIP:
                continue
            source_id = _source_id(run)
            if source_id in seen:
                continue
            name = f"{prefix}{run.name}"
            seen[source_id] = name
            shutil.copytree(run, output / name)
            units[source_id] = _units(run)
    for name, brief in BRIEFS.items():
        target = output / name
        if target.is_dir():
            shutil.copy2(SOURCE_MAP / brief, target / "source_knowledge.json")
    rebuild_library(output)
    return sorted(seen), units


def _synthetic_relations(root: Path, units: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The dense edge set: derived ids and digests, written judgements."""
    from x2knwldg import candidates, ids

    report = candidates.discover(root / "output")
    digests = {
        source["source_id"]: source["run_digest"] for source in report.as_dict()["sources"]
    }

    relations: list[dict[str, Any]] = []
    for source, target, relation_type, scope, size, basis_type, rationale in SYNTHETIC:
        from_units = units.get(source) or ["KU-000001"]
        to_units = units.get(target) or ["KU-000001"]
        basis = [
            {
                "from_ku_id": from_units[index % len(from_units)],
                "to_ku_id": to_units[index % len(to_units)],
                "relation_type": basis_type,
            }
            for index in range(size)
        ]
        relations.append(
            {
                "id": ids.source_relation_id(source, target, relation_type, scope),
                "from_source_id": source,
                "to_source_id": target,
                "relation_type": relation_type,
                "scope": scope,
                "provenance_class": "derived",
                "rationale": rationale,
                "basis": basis,
                "generated_from": {
                    "from_run_digest": digests.get(source, "0" * 64),
                    "to_run_digest": digests.get(target, "0" * 64),
                },
                # Not a schema member. `data.js` carries it so the pages can
                # mark which edges are written rather than gated; the container
                # written to disk drops it.
                "__synthetic": True,
            }
        )
    return relations


def _dense(tmp: Path) -> dict[str, Any]:
    from x2knwldg.repository import (
        MemoryRepository,
        SourceGraphQuery,
        SourceNeighborhoodQuery,
    )

    root = tmp / "dense"
    source_ids, units = _dense_corpus(root)
    synthetic = _synthetic_relations(root, units)
    gated = _read(GATED_RELATION)["relations"]

    written = [{k: v for k, v in r.items() if k != "__synthetic"} for r in synthetic]
    synthesis = root / "output" / "synthesis"
    synthesis.mkdir(parents=True, exist_ok=True)
    (synthesis / "source_relations.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "candidates": {
                    "considered": len(written) + len(gated),
                    "omitted": 0,
                    "bound": 25,
                },
                "relations": gated + written,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    repo = MemoryRepository.from_project(root)
    graph = repo.source_graph(SourceGraphQuery())
    focus = {
        source_id: repo.source_neighborhood(
            SourceNeighborhoodQuery(source_id=source_id)
        ).payload()
        for source_id in source_ids
    }
    bounded = repo.source_neighborhood(
        SourceNeighborhoodQuery(source_id=YT_PASS, limit=3)
    )
    return {
        "graph": graph.payload(),
        "page": {"limit": graph.limit, "total": graph.total, "next_cursor": graph.next_cursor},
        "focus": focus,
        "bounded_focus": bounded.payload(),
        "hub": YT_PASS,
        "synthetic_ids": sorted(r["id"] for r in synthetic),
        "gated_ids": sorted(r["id"] for r in gated),
        "discovered_pairs": _discovered(root),
    }


def _discovered(root: Path) -> list[list[str]]:
    """What real discovery proposes over the dense corpus, measured not claimed."""
    from x2knwldg import candidates

    report = candidates.discover(root / "output").as_dict()
    pairs = {
        tuple(sorted((c["from_source_id"], c["to_source_id"])))
        for c in report["candidates"]
    }
    return [list(pair) for pair in sorted(pairs)]


def main() -> int:
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        data = {
            "served": _served(tmp),
            "dense": _dense(tmp),
            "meta": {
                "generated_by": "docs/mockups/T-255/gen_data.py",
                "served_from": "tests/source_map_corpus.py",
                "dense_from": "tests/fixtures/runs/ + tests/fixtures/twitter-runs/",
                "relation_types": sorted(
                    __import__("x2knwldg.constants", fromlist=["x"]).SOURCE_RELATION_TYPES
                ),
                "scopes": sorted(
                    __import__("x2knwldg.constants", fromlist=["x"]).SOURCE_RELATION_SCOPES
                ),
                "bounds": {
                    "MAX_SOURCE_CANDIDATES": 25,
                    "MAX_SOURCE_RELATION_BASIS": 200,
                    "MAX_GRAPH_EDGES": 5000,
                    "DEFAULT_LIMIT": 50,
                    "MAX_LIMIT": 500,
                },
            },
        }

    # The layout input, so `web/scripts/source_mockup_layout.ts` can lay the
    # field out through the PRODUCTION path -- `seedPosition` plus `forceAtlas2`
    # at `MAP_LAYOUT_ITERATIONS` -- rather than through an imitation of it. It
    # reads this file rather than `output/library/graph.json`, which is what
    # keeps the layout reproducible in a clone.
    layout_input = {
        name: {
            "nodes": [node["global_id"] for node in body["graph"]["nodes"]],
            "edges": [
                [
                    f"{relation['from_source_id']}:source",
                    f"{relation['to_source_id']}:source",
                ]
                for relation in body["graph"]["relations"]
            ],
        }
        for name, body in (("served", data["served"]), ("dense", data["dense"]))
    }
    (HERE / "layout_input.json").write_text(
        json.dumps(layout_input, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    body = json.dumps(data, ensure_ascii=False, indent=1)
    (HERE / "data.js").write_text(
        "/*\n"
        " * GENERATED by docs/mockups/T-255/gen_data.py -- do not edit by hand.\n"
        " *\n"
        " * `served` is real throughout: bodies from the two source-graph reads over\n"
        " * tests/source_map_corpus.py, whose briefs and single relation are gated\n"
        " * fixtures. `dense` carries ten real source nodes and one gated relation;\n"
        " * every relation marked `__synthetic` was WRITTEN for this mockup -- real\n"
        " * ids, real endpoint digests, real knowledge-unit ids, invented judgement.\n"
        " * The pages mark them on their face. Nothing here reaches output/.\n"
        " */\n"
        f"export const DATA = {body};\n",
        encoding="utf-8",
    )
    nodes = len(data["dense"]["graph"]["nodes"])
    edges = len(data["dense"]["graph"]["relations"])
    print(f"data.js written: served 4 nodes / 1 edge, dense {nodes} nodes / {edges} edges")
    print(f"real discovery over the dense corpus proposes {len(data['dense']['discovered_pairs'])} pairs:")
    for pair in data["dense"]["discovered_pairs"]:
        print(f"  {pair[0]} -- {pair[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
