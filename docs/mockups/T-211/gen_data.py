"""Generate docs/mockups/T-211/data.js from the real canonical output.

Every record here is copied from output/, never invented. The only computed
values are x/y layout positions, which are presentation, exactly as
graphProjection.MapNodeAttributes treats them.
"""
import collections
import json
import pathlib

# The repository root, derived from this file's own location rather than typed.
# It used to be an absolute path under one developer's home directory, which is
# R15's shape exactly: a committed generator that only runs on the machine it
# was written on. `docs/mockups/T-211/gen_data.py` is three directories down,
# and `capture_mockups.ts` beside it resolves its own paths the same way.
ROOT = pathlib.Path(__file__).resolve().parents[3]
g = json.loads((ROOT / "output/library/graph.json").read_text())
units = {u["id"]: u for u in json.loads((ROOT / "output/pqlWNihgdjI/knowledge_units.json").read_text())["units"]}
meta = json.loads((ROOT / "output/pqlWNihgdjI/metadata.json").read_text())

nodes = {n["id"]: n for n in g["nodes"]}
edges = g["edges"]
CENTRE = "pqlWNihgdjI:KU-000028"

# ---- EntityRef, exactly the fields schemas/api/v1 defines -------------------
def entity_ref(node):
    lid = node.get("local_id") or node["id"].split(":", 1)[1]
    unit = units.get(lid)
    ref = {
        "schema_version": "1.0",
        "global_id": node["global_id"],
        "source_type": node["source_type"],
        "external_id": node.get("video_id") or "concepts",
        "local_id": lid,
        "library_id": node["id"],
        "source_id": (f"youtube:{node['video_id']}" if node.get("video_id") else None),
        "entity_type": "concept" if node["kind"] == "canonical_concept" else "knowledge_unit",
        "provenance_class": node["source_class"],
        "kind": node["kind"],
        "label": node["label"],
        "confidence": unit.get("confidence") if unit else None,
        "locator": None,
        "derived_from": unit.get("derived_from") if unit else None,
        "derivation_note": unit.get("derivation_note") if unit else None,
        "canonical_path": ("output/pqlWNihgdjI/knowledge_units.json" if unit
                           else "output/library/concepts.json"),
    }
    if unit and "source" in unit:
        s = unit["source"]
        ref["locator"] = {
            "type": "time_range",
            "artifact_id": f"youtube:{s['video_id']}:transcript",
            "start_sec": s["start_sec"],
            "end_sec": s["end_sec"],
            "segment_id": s.get("segment_id"),
            "excerpt": s.get("evidence_excerpt"),
        }
    return ref

def indexed_relation(e):
    canonical = e["relation"] not in ("derived_from", "expresses_concept")
    frm, to = nodes[e["from"]], nodes[e["to"]]
    return {
        "schema_version": "1.0",
        "id": f"{frm['global_id']}|{e['relation']}|{to['global_id']}",
        "from_id": frm["global_id"],
        "to_id": to["global_id"],
        "relation": e["relation"],
        "relation_vocabulary": "canonical" if canonical else "library_synthetic",
        "provenance_class": e["source_class"],
        "confidence": e.get("confidence"),
        "source_id": (f"youtube:{e['video_id']}" if e.get("video_id") else None),
        "canonical_path": ("output/pqlWNihgdjI/relationships.json" if canonical
                           else "output/library/graph.json"),
        "intentional_self_loop": False,
    }

# ---- layout, produced by the PRODUCTION path -------------------------------
# web/scripts/mockup_layout.ts runs the real seedPosition + graphology +
# forceAtlas2(inferSettings, 200 iterations) that MapSession.relax() runs, and
# writes layout.json. Positions are presentation, exactly as
# graphProjection.MapNodeAttributes treats x/y -- never data.
layout = json.loads((ROOT / "docs/mockups/T-211/layout.json").read_text())
ids = list(nodes)
missing = [i for i in ids if nodes[i]["global_id"] not in layout]
if missing:
    raise SystemExit(f"layout.json is stale, {len(missing)} node(s) absent; "
                     "re-run npm --prefix web run mockups:layout")

# Fit to the stage's aspect rather than to a square, so a wide viewport is
# filled rather than letterboxed. Clip to the 2nd/98th percentile first: a
# stray component must not shrink the whole field around it.
def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(q * (len(ordered) - 1))))]

xs = [layout[nodes[i]["global_id"]]["x"] for i in ids]
ys = [layout[nodes[i]["global_id"]]["y"] for i in ids]
lox, hix = pct(xs, 0.02), pct(xs, 0.98)
loy, hiy = pct(ys, 0.02), pct(ys, 0.98)
cx0, cy0 = (lox + hix) / 2, (loy + hiy) / 2
ASPECT = 2852 / 1632
half_w = max((hix - lox) / 2, (hiy - loy) / 2 * ASPECT) or 1.0
half_h = half_w / ASPECT

def norm(i):
    p = layout[nodes[i]["global_id"]]
    return {"x": round(min(1.06, max(-0.06, (p["x"] - cx0) / (2 * half_w) + 0.5)), 5),
            "y": round(min(1.06, max(-0.06, (p["y"] - cy0) / (2 * half_h) + 0.5)), 5)}

# ---- neighbourhood of the centre, direction + hop, exactly as neighbourhood.ts
out_adj = collections.defaultdict(list)
for e in edges:
    out_adj[e["from"]].append((e["to"], e, "outgoing"))
    out_adj[e["to"]].append((e["from"], e, "incoming"))

# BFS from the centre. `side` is inherited from the hop-1 ancestor: a hop-2 node
# does not touch the centre, so claiming a direction relative to it would be an
# invented field. It sits on the side of the hop-1 node it actually attaches to.
hop = {CENTRE: 0}
side = {}
parent_rel = {}
queue = [CENTRE]
while queue:
    cur = queue.pop(0)
    if hop[cur] >= 2:
        continue
    for other, e, d in out_adj[cur]:
        if other in hop:
            continue
        hop[other] = hop[cur] + 1
        # `d` is the direction of this edge as seen from `cur`.
        parent_rel[other] = (cur, e, d)
        side[other] = d if cur == CENTRE else side[cur]
        queue.append(other)

active = [{"record": indexed_relation(e), "direction": d,
           "otherId": nodes[other]["global_id"]}
          for other, e, d in out_adj[CENTRE]]

related = []
for nid, h in sorted(hop.items(), key=lambda kv: (kv[1], kv[0])):
    if nid == CENTRE:
        continue
    par, e, d = parent_rel[nid]
    related.append({
        "globalId": nodes[nid]["global_id"],
        "record": entity_ref(nodes[nid]),
        "hops": h,
        # The direction of the edge joining this node to its parent, stated from
        # the parent's point of view -- for hop 1 the parent is the centre.
        "toCentre": d,
        "parentId": nodes[par]["global_id"],
        "side": side[nid],
        "relations": [{"record": indexed_relation(e), "direction": d,
                       "otherId": nodes[par]["global_id"]}],
    })

payload = {
    "source": {
        "video_id": meta["video_id"], "title": meta["title"],
        "channel": meta.get("channel"), "duration_sec": meta["duration_sec"],
        "url": meta.get("url"),
    },
    "counts": {"nodes": len(nodes), "edges": len(edges),
               "knowledge_units": 69, "concepts": 17},
    "nodes": [dict(entity_ref(nodes[i]), **norm(i)) for i in ids],
    "edges": [indexed_relation(e) for e in edges],
    "centreId": nodes[CENTRE]["global_id"],
    "centre": entity_ref(nodes[CENTRE]),
    "active": active,
    "related": related,
}

out = ROOT / "docs/mockups/T-211/data.js"
out.write_text(
    "/* Generated from output/library/graph.json + "
    "output/pqlWNihgdjI/knowledge_units.json.\n"
    "   Every field is a real record in schemas/api/v1 EntityRef / IndexedRelation\n"
    "   shape. x/y are computed layout positions only -- presentation, never data.\n"
    "   Regenerate with the script recorded in SPEC.md. */\n"
    "export const DATA = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n",
    encoding="utf-8")
print("wrote", out, out.stat().st_size, "bytes")
print("hop1:", sum(1 for r in related if r['hops'] == 1), "hop2:", sum(1 for r in related if r['hops'] == 2))
print("incoming:", sum(1 for a in active if a['direction'] == 'incoming'),
      "outgoing:", sum(1 for a in active if a['direction'] == 'outgoing'))
