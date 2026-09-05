# Source Map — Product, Data, and Delivery Specification

**Status:** accepted for implementation planning  
**Date:** 2026-09-05  
**Implementation owner:** Claude Code  
**Authority:** [ADR 0008](adr/0008-source-level-knowledge-map.md), decisions D-244–D-250

## 1. Outcome

Add a source-level view above the existing Knowledge Unit (KU) graph. A YouTube video, an
X/Twitter post or self-thread, and eventually a book or article each appear as one source
node. Selecting a source turns only that node into a readable knowledge card and exposes its
qualified incoming and outgoing source relationships.

This is not a larger KU, a replacement for the existing Knowledge Map, or a user-authored
Canvas. It is an automatic, read-only projection over validated source knowledge:

```text
Source Map              one node per acquired source; cross-source synthesis
    ↓ open source
Reader / structure      source, chapters/items/transcript, validation state
    ↓ inspect evidence
Knowledge Map           KUs, concepts, exact evidence and canonical relations
    ↓ arrange manually
Canvas                  user selection, layout, notes and user relations
```

The first implementation supports only the source types that the pipeline already supports:
YouTube and public X/Twitter. Book, PDF, EPUB, Medium and arbitrary-web ingestion remain
unsupported until their own capture contracts, locators, validators and adapters exist.

## 2. Product contract

### 2.1 Navigation and modes

Keep one top-level Map destination. Add an addressable mode switch:

- `Sources` — the new Source Map;
- `Knowledge` — the existing KU/concept map, unchanged.

The URL owns the mode and selection so reload and browser history are deterministic. The
existing Knowledge Map URL grammar and entity selection must not be reinterpreted. A source
selection resolves to the already reserved global entity identity
`<source-type>:<external-id>:source` and opens the same source in Library/Reader.

### 2.2 Explore

Explore shows the source topology with compact marks, exact source titles only when density
allows, filters, search, and honest counts. It must not render a field of article cards.

- One acquired run is one source node.
- Chapters, posts in a self-thread, transcript segments, KUs and concepts are not Source Map
  nodes.
- A cover or thumbnail is shown only when a canonical captured artifact provides it. The UI
  does not guess one or fetch one opportunistically.
- A missing brief or failed relationship build is stated; an empty projection is not presented
  as evidence that no relationships exist.

### 2.3 Focus: one readable node

Focus reuses the approved Directional Orbit composition:

- selected source at the visual centre;
- incoming relationships on the left and outgoing relationships on the right;
- actual hop count controls distance;
- unrelated loaded topology remains faint;
- only the selected source becomes a full semantic HTML card;
- neighbours remain compact previews; every returned neighbour and relationship also appears
  in a complete semantic DOM list.

The selected card contains, in this order:

1. original title, author/channel, source type and validation/coverage state;
2. Persian thesis;
3. Persian key points;
4. limitations, tensions or unresolved points when present;
5. relationship groups, with direction, type, scope and number of supporting grounds;
6. actions to open the Reader, inspect supporting KUs, or return to Explore.

`PASS`, `PARTIAL` and `FAIL` remain visible. A brief derived from a `PARTIAL` run is visibly
partial and never described as a complete account of the source.

### 2.4 Relationship interaction

An edge pill names the relationship verbatim and shows a basis count, for example
`critiques · 3 grounds`. Activating it opens the semantic relationship detail:

- source and target titles in the recorded direction;
- relationship type and scope;
- Persian rationale;
- each supporting KU pair with links to exact evidence;
- any contrary or mixed basis;
- provenance class (`derived` for every automatic source relationship);
- truncation/availability state if the API returns only part of the basis.

Colour is never the sole carrier of direction, provenance or status. Text, arrow/port shape,
line style and accessible labels carry the same distinctions.

### 2.5 Rendering decision

Keep Sigma.js/Graphology for both Map modes. Rich HTML for every node would fight the global
graph renderer and make density unbounded. The existing bounded DOM-overlay model already
matches the requirement: one selected readable card, at most one Peek, compact neighbour
previews, and a full semantic companion list. React Flow remains reserved for the editable
Canvas.

## 3. Data contract

### 3.1 Source node

Reuse the existing `Source` record and the reserved `EntityRef.entity_type = "source"`.
Adapters emit exactly one source entity per run:

```json
{
  "global_id": "youtube:pqlWNihgdjI:source",
  "entity_type": "source",
  "source_id": "youtube:pqlWNihgdjI",
  "local_id": "source",
  "label": "The original source title",
  "provenance_class": "source",
  "canonical_path": "output/pqlWNihgdjI/metadata.json"
}
```

The label is the original title, never a generated summary. Source nodes do not require
membership edges to every KU; Reader and the existing source-entity endpoint provide the
drill-down.

### 3.2 `source_knowledge.json`

Introduce one canonical **derived** artifact per run after extraction, normalization,
relationship extraction and coverage audit. It is readable knowledge, not evidence.

Minimum v1 shape:

```json
{
  "schema_version": "1.0",
  "source_id": "youtube:pqlWNihgdjI",
  "status": "PASS",
  "thesis": {
    "content": "روایت فارسیِ فشرده از مدعای محوری منبع",
    "based_on": ["KU-001", "KU-014"]
  },
  "key_points": [
    {
      "id": "SP-001",
      "content": "نکتهٔ اصلی به فارسی",
      "based_on": ["KU-004", "KU-009"]
    }
  ],
  "limitations_or_tensions": [],
  "generated_from": {
    "knowledge_units_sha256": "...",
    "relationships_sha256": "...",
    "coverage_sha256": "..."
  }
}
```

Rules:

- every narrative field follows the permanent Persian output-language policy;
- every thesis, point and limitation has a non-empty `based_on` list of existing KU ids;
- evidence excerpts remain in the KUs and are never copied, translated or normalized here;
- generation happens only after extraction and coverage, never before them;
- model output enters through a gated apply operation; code must not write around it;
- validators reject unknown KUs, empty support, stale input hashes, source mismatch, duplicate
  point ids and a status stronger than the underlying run;
- finalization/indexing may project this artifact but must not silently synthesize it;
- a missing artifact is an honest `unavailable` brief, not an empty successful one.

Add `source_knowledge` to the artifact vocabulary only when the schema, apply gate, validator,
adapter and fixtures land together. They landed together: `T-251` delivered the schema
(`schemas/synthesis/v1/source_knowledge.schema.json`) and the fixtures, and `T-252` delivered the
gate, the validator and the adapter projection, at which point `source_knowledge` joined
`Artifact.kind`. The record is emitted only for a run that has a brief (D-257).

### 3.3 `SourceRelation`

Do not overload a KU-level `IndexedRelation`. Add a versioned source-relation record with a
separate vocabulary and qualified basis:

```json
{
  "id": "SR-...",
  "from_source_id": "twitter:...",
  "to_source_id": "youtube:...",
  "relation_type": "critiques",
  "scope": "partial",
  "provenance_class": "derived",
  "rationale": "این رشته‌توییت سه ادعای مشخص ویدیو را نقد می‌کند.",
  "basis": [
    {
      "from_ku_id": "KU-006",
      "to_ku_id": "KU-021",
      "relation_type": "contradicts"
    }
  ],
  "generated_from": {
    "from_run_digest": "...",
    "to_run_digest": "..."
  }
}
```

Allowed v1 relationship types:

- `explicitly_references`
- `responds_to`
- `critiques`
- `supports`
- `contradicts`
- `extends`
- `applies`
- `overlaps_with`

`scope` is `partial` or `broad`. It qualifies how much of the sources the basis supports; it
does not claim a numeric coverage percentage. Multiple records between the same two sources
are allowed when the supported semantics differ.

All automatic source relations are `derived`, including `explicitly_references`: the cited
link may be source-grounded, but promoting it into a source-to-source relationship is a
derived aggregation. `responds_to` and influence-like language require an explicit reference
or source-grounded statement; chronology, concept overlap or semantic similarity alone are
insufficient.

Store accepted records in `output/synthesis/source_relations.json`, whose contract is
`schemas/synthesis/v1/source_relations.schema.json`. `io.NOT_A_RUN` names that directory beside
`library/`, so run discovery can never mistake it for an ingested source. This is canonical
derived synthesis, not raw evidence and not user workspace state. Write atomically through a gated
apply command and validate it before rebuilding `output/library/`. The library graph remains
a disposable projection.

## 4. Automatic relationship pipeline

Run source synthesis after a new or changed source has a validated `PASS` or `PARTIAL`
extraction. The local UI and API stay read-only; automation belongs to the pipeline/agent
workflow, not a browser write shortcut.

```text
validated source
  → deterministic candidate discovery
  → bounded KU-pair comparison
  → model proposes qualified SourceRelation records
  → apply gate validates endpoints, basis and hashes
  → atomic synthesis update
  → rebuild source projection/index
```

Candidate discovery may use:

1. explicit links, citations or named source references preserved in canonical artifacts;
2. shared canonical concepts;
3. local FTS retrieval over source KUs and source knowledge.

**As implemented by `T-253`: (1) and (2) only.** Route (3) is not built, and every candidate
report names it as unimplemented alongside the two that ran, so a small candidate set is never
readable as evidence that nothing is related (D-262). Route (1) reads a capture's
`external_references` and therefore contributes nothing for a YouTube from-endpoint, which the
report also states.

A candidate is not a relationship. Candidate score/rank is internal retrieval data and must
not appear as relation strength, importance or confidence. Avoid an all-pairs comparison: use
declared, measured bounds and report candidates omitted by the bound. Re-evaluate a pair only
when either recorded run digest changes or the synthesis contract version changes.

The comparison pass receives canonical KUs and their exact locators, not only the source
brief. It may emit no relation. Each emitted record must pass these checks:

- both source endpoints exist and differ;
- every basis KU exists and belongs to its stated endpoint source;
- the source-level direction is compatible with every supporting pair;
- `rationale` is Persian and does not make claims stronger than `scope` and `basis`;
- an explicit-reference relation points to captured evidence of that reference;
- mixed or contrary support is retained or causes a narrower/multiple relation, never hidden;
- no confidence is invented. Add confidence later only with a defined producer and validator.

Source synthesis does not reopen or reinterpret a run's coverage result. If upstream evidence
repair re-enters the existing coverage audit, its existing maximum of three total attempts
still applies. A failed or partial synthesis remains visible as such and does not weaken the
underlying source run.

## 5. API and index projection

Extend the read-only v1 API additively; do not change the existing Knowledge Map responses.

Proposed endpoints:

```text
GET /api/source-graph
GET /api/source-graph/neighborhood/{source_id}
```

**Both are implemented by `T-254`** (D-269–D-276); what follows was the proposal and is now the
description.

The global response returns source `EntityRef` nodes, source relation summaries and honest
paging/completeness counts. The neighbourhood response returns the selected source, its
`source_knowledge`, qualified relationships and their bounded basis details. If basis is
bounded in the response, include `basis_total` and `basis_returned`; never silently truncate.

The path parameter is the **two-part source id** the rest of the project addresses a run by, not
the three-part global id of the source node; the node's global id comes back as `center_id`, so
a client that batches requests attributes the answer without constructing an id of its own.

Add repository methods rather than reading canonical files in routes. The SQLite representation
is rebuildable from the source adapters, per-run `source_knowledge.json`, and the canonical
cross-source synthesis file. Deleting the index and rebuilding must produce an equivalent
Source Map.

## 6. Books without global-graph complexity

The source abstraction deliberately makes books ordinary at the top level:

- one edition/acquired book is one source node;
- parts and chapters are internal structure and Reader navigation, not global source nodes;
- the selected book card shows thesis and key points, plus a collapsed structure summary;
- chapter/section detail is loaded on demand;
- KU evidence remains below the source and structure layers;
- source relationships use qualified KU basis exactly like video/thread relationships.

For EPUB, a future adapter should preserve the package manifest, spine reading order and
navigation document rather than flattening or inventing chapters. For PDF, use a captured
outline when available; absence of an outline must remain absence. Page, bounding-box, text
span, EPUB spine/document and CFI-like locators may be added only when canonical capture can
reproduce and validate them.

This yields one consistent disclosure path:

```text
book source → actual captured structure → chapter/section → KU → exact evidence
```

The Source Map phase does not implement book acquisition or claim it is supported. It makes
the source-level contract medium-neutral so a future book adapter does not change the Map.

## 7. Accessibility and honest states

- Every visually conveyed node/edge relationship is also programmatically determinable or
  available as text.
- The source card uses semantic headings and lists and preserves Persian/English bidi text.
- Pointer, keyboard and touch produce the same selection and relationship detail.
- Reduced motion affects camera/layout animation as in the existing Map.
- WebGL failure leaves the complete semantic source/relationship list usable.
- Loading, empty, partial, truncated, refused and unavailable states remain distinct.
- Counts describe returned, drawn and omitted items separately.

## 8. Delivery plan for Claude Code

### T-251 — Contracts and fixtures ✅ done (D-251–D-256)

- source entity emission added to both adapters — one per run, whatever the run's status, into
  `IndexRecords.source_entities`, a fifth record family `by_model()` does not expose so that no
  existing payload moves (D-251);
- `schemas/synthesis/v1/` holds `primitives`, `source_knowledge`, `source_relation` and the
  `source_relations` container — a pipeline contract in its own versioned directory, because
  `schemas/v1/` describes nothing the pipeline writes (D-253);
- `ids.source_relation_id` is the deterministic id: `SR-` and 16 hex digits of a SHA-256 over
  the two endpoints, the relation type and the scope — and **not** the basis, so accumulating
  evidence updates one record rather than minting a second (D-252);
- `tests/fixtures/source-map/` holds three briefs across both media (including a `PARTIAL`),
  three containers (one relation, none, bounded) and 22 invalid documents, each with a sidecar
  naming its single lie and whether the schema or a later gate refuses it;
- eight source-graph response shapes are frozen as OpenAPI **components with no new paths**, and
  `types.d.ts` is regenerated; the served surface is still exactly eleven `GET` endpoints, and
  `T-254` added the two operations (D-254).

**The frozen bounds.** Measured by `tools/measure_source_bounds.py`, not chosen (D-255):

| Constant | Value | Bounds | Never silent because |
|---|---|---|---|
| `MAX_SOURCE_CANDIDATES` | 25 | Counterpart sources one source's pass compares | `candidates.considered` / `omitted` / `bound` are required on the container |
| `MAX_SOURCE_RELATION_BASIS` | 200 | Basis entries one relation carries in one response | `basis_total` and `basis_returned` are both required on the detail shape |

Re-measure rather than quoting: `output/` is gitignored, so the ingested half of the corpus
differs per clone and the tool names the runs it saw.

### T-252 — Source knowledge apply gate ✅ done (D-257–D-261)

- `prompts/06_source_knowledge.md` is the post-coverage pass, and
  `x2knwldg apply-source-knowledge <run-dir> <document>` is the gate — one for both media,
  with no `MEDIUM_PROFILES` row, because a thesis and its supporting units are not a
  statement about video or posts (D-258);
- `validators.validate_source_knowledge` checks support against the run's own unit ids,
  the three digests against the files as they are now, `status` by rank against
  `validation.json`, and the narrative as a one-directional Perso-Arabic **script** check
  described as exactly that (D-260). It also states the whole shape, because the package
  applies no JSON Schema at runtime;
- the adapters project the artifact and its currency, both **only when a run has one**, so
  no existing record moved (D-257); `synthesis.brief_state` is the read side and the
  source of the `available` / `unavailable` / `stale` vocabulary §5 already froze;
- the gate never stamps `generated_from` in (D-259), a refused brief leaves the run
  byte-identical, and a successful one changes exactly one file and does not restamp
  `extracted_at`.

Not done here, deliberately: no `validation.json` section (D-261), no `WORKFLOW.md` entry
(§8.9 — `T-257`), and no surface renders a brief until `T-256`.

### T-253 — Automatic source relationships ✅ done (D-262–D-268)

- `src/x2knwldg/candidates.py` implements bounded discovery through **two** deterministic
  routes — a resolved explicit reference and a shared canonical concept — bounded per
  from-source (D-263). The third route this section permits, local FTS retrieval, is **not
  implemented**, and is named as such in every report rather than producing nothing
  silently (D-262);
- `prompts/07_source_relations.md` is the comparison pass, and `x2knwldg source-candidates`
  is what it starts from;
- `x2knwldg apply-source-relations` is the atomic gate. It **re-runs discovery** and refuses
  a relation for a pair nothing proposed, along with counts that disagree with a fresh run —
  which is what turns "avoid an all-pairs comparison" into a check (D-264);
- every check this section lists is enforced and cased individually: endpoints exist and
  differ, each basis unit belongs to its stated endpoint, direction is not contradicted by
  every ground (D-266), the rationale is Persian, an explicit reference is corroborated
  rather than asserted (D-267), mixed support survives, and no confidence is representable;
- candidate and omission counts are recorded and **not** taken on trust; the report carries
  no score, rank or similarity, asserted by a test.

The container gained one additive optional field, `pairs_in_corpus`, so an empty result can
be read: `omitted` keeps its frozen meaning of "what the bound left out", and the new field
says how many ordered pairs existed at all (D-265).

The phase's cross-medium acceptance clause is proved over a corpus built **in the test
process** (`tests/source_corpus.py`), because no committed corpus can produce a cross-medium
canonical concept and fabricating provider bytes to get one is what D-222 forbids (D-268).

### T-254 — Repository, index and API ✅ done (D-269–D-276)

- **Three tables, in migration 2** (D-269): `source_entities` from the adapters' fifth record
  family, `source_briefs` from each run's `source_knowledge.json` through
  `synthesis.brief_state`, and `source_relations` from `output/synthesis/source_relations.json`.
  All three are rebuildable and none is read by any existing payload, so ADR 0001 invariant 3
  still holds of the whole cache. The synthesis file keeps no `runs` row and is re-read on every
  scan: it belongs to no run, so no per-run digest could decide it was unchanged (D-270);
- **two protocol methods**, `source_graph` and `source_neighborhood`, implemented over SQLite
  and over the cache-free oracle. This is the only widening `IndexRepository` has had, and it
  was a contract change first — ADR 0002 invariant 3 forbids an implementation widening it;
- **the two operations**, `GET /api/source-graph` and
  `GET /api/source-graph/neighborhood/{source_id}`, in
  `src/x2knwldg/server/routes/source_graph.py`. Adding them is what made every declared
  component reachable again and retired the exemption `T-251` left behind (D-254);
- the graph pages over **nodes**, so a source that relates to nothing still appears exactly once
  in a full walk. `relations_omitted` counts both the bound's cut and a relation naming a source
  the index does not hold, because an edge to a node the client has no record for asserts a node
  that does not exist (D-271);
- the neighbourhood takes a `limit` and **no `depth`**, and the limit binds both directions
  together in id order before the split, so a bound cannot erase one direction while the other
  is short of it (D-272);
- a `stale` brief is **carried** with the state saying so, and the frozen
  `SourceKnowledgeAvailability` description — whose two sentences had frozen in contradiction —
  now says which state carries a document (D-273);
- **memory/SQLite and rebuild equivalence** are proved by `tests/test_sqlite_equivalence.py`:
  `snapshot()` asks both endpoints in *every* scenario, and §9b adds five more over
  `tests/source_map_corpus.py`, a corpus that actually holds all three record families. Deleting
  `.x2knwldg/` and rebuilding differs on **0** observations, and a re-extracted run makes its
  brief `stale` on both paths;
- **no Knowledge Map payload moved**: `tests/test_source_map_regression.py` and
  `test_the_source_layer_left_the_knowledge_map_where_it_was` hold the HTTP and the seam ends of
  D-249.

One gap is deliberate and on the record. `artifacts.source_relations_state` reports a relation
whose endpoint runs have moved as `stale` **individually**, and neither `SourceRelationSummary`
nor `SourceRelationDetail` has a member for it — both are `additionalProperties: false`. Nothing
is filtered on it, because a dropped relation could only be reported as a bound that did not
bind, and nothing claims freshness, because the record says nothing about it. A staleness
channel is a field for a later contract version; `T-256` must not present a relation as current
on the strength of this endpoint alone (D-274).

### T-255 — High-fidelity UX approval

- create Source Explore and Focus mockups from real YouTube/X fixture data;
- cover dark/light, Persian/English, PASS/PARTIAL, dense/mixed relationships and no-WebGL;
- obtain user approval before production UI work.

### T-256 — Source Map UI

- add the addressable Map mode switch;
- reuse Sigma, Directional Orbit, selection/history and semantic companion patterns;
- render one selected source knowledge card and compact neighbours;
- add relationship basis detail and Reader/KU navigation.

### T-257 — Phase gate

- unit, schema, API, frontend and browser tests;
- screenshot review at approved viewports;
- accessibility and reduced-motion checks;
- no raw mutation and byte/equivalence checks for current KU Map outputs;
- update `WORKFLOW.md` only for behavior that is now implemented and validated.

The tasks are serial at the phase boundary: `T-251 → T-252 → T-253 → T-254 → T-255 →
T-256 → T-257`. `T-251`–`T-254` are done; `T-255` is the claimable one. Implementation may parallelize internal tests only when the contract owner
has already frozen the relevant shape.

## 9. Phase acceptance criteria

- Every implemented source appears exactly once in Source Explore.
- Selecting a source exposes a readable Persian brief whose every statement names supporting
  KUs and whose status cannot exceed the run.
- At least one fixture-backed YouTube↔X relationship is generated automatically and exposes
  valid source-owned KU basis; a no-relation fixture emits none.
- Incoming/outgoing direction and mixed/partial scope are stated in text, not only visually.
- Only one full readable source card exists on the graph stage; all returned relationships
  remain accessible in the semantic list.
- Source graph candidate work is bounded and omissions are counted.
- Deleting and rebuilding SQLite produces an equivalent Source Map.
- Existing Knowledge Map/API behavior and all preserved raw evidence remain unchanged.
- The book design is demonstrably one source node with internal drill-down, while book
  acquisition continues to report unsupported.
- Validation and coverage both pass for the phase fixtures; `PARTIAL` and `FAIL` are not
  coerced to `PASS`.

## 10. Research basis

- [W3C PROV-O](https://www.w3.org/TR/2013/REC-prov-o-20130430/) distinguishes entities,
  derivation and named bundles/collections. The design borrows its separation of provenance
  from aggregation without adopting RDF as a storage requirement.
- [Microsoft GraphRAG default dataflow](https://microsoft.github.io/graphrag/index/default_dataflow/)
  and [output model](https://microsoft.github.io/graphrag/index/outputs/) retain links from
  document-level and relationship-level products back to text units. This supports keeping a
  readable source synthesis while retaining KU-level grounds.
- Park et al., [ClaimDiff](https://aclanthology.org/2020.acl-main.406/), model claims and
  sources separately and warn that document-level source voting is too coarse. This supports
  qualified, basis-bearing edges instead of declaring that two whole sources simply agree or
  disagree.
- [Sigma renderers](https://www.sigmajs.org/docs/advanced/renderers/) are WebGL-based; the
  existing bounded semantic DOM overlay is retained for rich selected content.
- [EPUB 3.3](https://www.w3.org/TR/epub-33/) defines the spine reading order and navigation
  document, supporting a book-as-one-source model with preserved internal hierarchy.
- [WCAG: Info and Relationships](https://www.w3.org/WAI/WCAG21/Understanding/info-and-relationships)
  and [WAI complex images](https://www.w3.org/WAI/tutorials/images/complex/) require important
  visual relationships and graph information to have programmatic or complete text
  equivalents; the semantic companion is therefore part of the product, not a fallback extra.
