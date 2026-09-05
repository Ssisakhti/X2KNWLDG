# Source synthesis model v1

The two **derived** record families of the Source Map ([ADR 0008](../../../docs/adr/0008-source-level-knowledge-map.md),
D-246–D-247). Frozen by `T-251`; the gates that produce them are `T-252` and `T-253`.

| File | Describes |
|---|---|
| `primitives.schema.json` | Shared primitives: identifiers, the two relation vocabularies, scope, run status, digests, supported narrative |
| `source_knowledge.schema.json` | One readable Persian account of one source — `output/<run-id>/source_knowledge.json` |
| `source_relation.schema.json` | One qualified, directional relation between two sources, with its knowledge-unit basis |
| `source_relations.schema.json` | The container — `output/synthesis/source_relations.json` |

Draft **JSON Schema 2020-12**. Every `$id` is
`https://x2knwldg.local/schemas/synthesis/v1/<file>`, and cross-references are relative, so
the set resolves as a unit from any base.

The primitives file is `primitives.schema.json`, not `common.schema.json`, and every
reference — including a document's references into its own `$defs` — is written with the
owning filename rather than as a bare `#/$defs/...`. That makes a `$ref` string name exactly
one document across the whole contract, which is not a style preference:
`tools/generate_api_types.py` resolves references by that string alone, so a second
`common.schema.json` anywhere would have silently resolved a synthesis primitive to the index
model's identically-named one. The generator now refuses a duplicate reference key outright,
and this naming is what keeps it from ever having to.

## Why this is not `schemas/v1/`

[`schemas/v1/README.md`](../../v1/README.md) says in its second paragraph that those schemas
"describe **nothing that the pipeline writes**". Both records here *are* files the pipeline
writes, so putting them there would make that sentence false and point the dependency
backwards — the index layer is derived *from* canonical files, not the other way round.

The precedent is [`schemas/capture/v1/`](../../capture/v1/README.md), which is a pipeline
contract in its own versioned directory for exactly the same reason. Like that one, this set
is self-contained: it references `schemas/v1/` nowhere, and its identifier patterns mirror
`src/x2knwldg/ids.py` rather than importing a definition from the index model.

The mirroring is guarded. `tests/test_source_map_schemas.py` fails the moment a pattern, a
bound or a vocabulary here disagrees with `src/x2knwldg/constants.py` or `src/x2knwldg/ids.py`,
which is the same drift guard `test_canonical_relation_vocabulary_matches_constants` puts on
the index model.

## Versioning

The same doctrine as everywhere else: **the version is the directory**.

- Additive optional field, or a pattern widened to accept strictly more → edit in place.
- New required field, removed field, narrowed type, changed meaning → create
  `schemas/synthesis/v2/` and leave `v1` answering for every record that names it.

## What each constraint refuses

Every constraint exists to make one specific dishonest record unrepresentable rather than
merely discouraged. The pointed ones:

| Constraint | The lie it prevents |
|---|---|
| `supportList` has `minItems: 1` | A Persian statement that reads as knowledge from the source while resting on nothing. An empty list asserts derived provenance and shows no work — the same refusal `adapters.base._derived_refs` makes one layer down |
| `basis` has `minItems: 1` | "These two sources disagree" as a whole-document verdict. The basis is what makes a source edge checkable, and risk **R27** is precisely the edge without one |
| `SourceRelation` has no `confidence` property, under `additionalProperties: false` | A number nothing produced. Confidence is not merely omitted here, it is unrepresentable; adding it later requires a defined producer and a validator (D-247) |
| `provenance_class` is `const: "derived"` | An automatic relation presenting itself as source-grounded. Even `explicitly_references` is an aggregation the sources never made |
| `sourceRelationType` is its own eight-value enum | A knowledge-unit relation being read as a whole-source verdict. `supports` exists in both vocabularies and means a different-sized claim in each |
| `runStatus` omits `UNKNOWN` | A brief summarising a run whose validators never ran |
| `generated_from` digests are required | A brief or a relation that silently goes on describing a run that has since changed |
| `candidates` is required on the container | An empty `relations` list reading as "nothing is related" when the truth is "that pair was never compared". Risk **R28**'s omissions are counted, never implied |
| `basis` has no `maxItems` | Truncating the canonical record to fit a screen. The response pages it and states `basis_total` and `basis_returned`; the file on disk keeps the whole basis |

## What JSON Schema cannot say

These rules need a second document in hand and are therefore the apply gates' (`T-252`,
`T-253`), each pinned by a committed invalid fixture in
[`tests/fixtures/source-map/`](../../../tests/fixtures/source-map/README.md):

1. Every id in `based_on` names a knowledge unit the run actually holds. — `T-252`
2. Every basis entry's unit belongs to the endpoint that claims it. — `T-253`. Both
   fixture runs use `KU-000001`, so an id can look right and be owned by the wrong side;
   the committed case for this was itself honest by accident until `T-253`'s gate accepted
   it, and it now names a unit that is real elsewhere in the corpus and absent from the
   endpoint claiming it.
3. `status` is not stronger than the run's own `validation.json`. — `T-252`
4. Ids are unique *by id* — `uniqueItems` compares whole records, so two key points that
   differ only in wording but share `SP-001` pass the schema and are refused by the gate.
   — `T-252`

Three more belong to the same family and are in no schema at all:

5. **`generated_from` must match the files as they are now.** Each gate recomputes the digests
   and refuses a document that disagrees, and neither ever stamps them in itself — filling them
   in would file a brief generated against yesterday's units as though it described today's,
   hiding precisely what the field exists to expose (D-259).
6. **An `explicitly_references` relation must be corroborated.** The discovery route that reads
   a capture's `external_references` is the only thing in the project that knows one source
   names another, so a claimed reference the corpus cannot resolve is refused rather than taken
   on the model's word (D-267).
7. **The pair must have been a candidate.** A relation for an ordered pair discovery never
   proposed means the comparison pass looked past its candidate list, which is the all-pairs
   walk the bound exists to prevent (D-264).

`from_source_id != to_source_id` is of the same kind and is refused earlier still:
`ids.source_relation_id` will not mint an id for a self-relation, so such a record has no way
to acquire the `id` its own schema requires.

## Bounds

Two numbers govern the pipeline that fills these records, both in
`src/x2knwldg/constants.py` and both measured rather than chosen from a design document:

| Constant | Governs | Risk |
|---|---|---|
| `MAX_SOURCE_CANDIDATES` | Counterpart sources one source's synthesis pass compares | R28 |
| `MAX_SOURCE_RELATION_BASIS` | Basis entries one relation carries in one API response | R27 |

Re-measure the corpus they are set against with:

```bash
python tools/measure_source_bounds.py
```

## Validating

```bash
.venv/bin/python -m pytest tests/test_source_map_schemas.py -q
```

The tests skip cleanly without `jsonschema`, which is a `dev` extra, because the core package
installs and tests with zero dependencies (ADR 0001 invariant 5).

## Consumers

- `T-252` — ✅ delivered. `prompts/06_source_knowledge.md` produces the document,
  `x2knwldg apply-source-knowledge` is the gate, `validators.validate_source_knowledge`
  states every rule including the four this directory cannot, `synthesis.brief_state` is
  the read side, and the adapters project the artifact and its currency for a run that has
  one. The shape rules here are enforced **again** in that validator on purpose: the core
  package is zero-dependency and applies no JSON Schema at runtime, so a document refused
  only by these files is a document refused only in CI.
- `T-253` — ✅ delivered. `x2knwldg.candidates.discover` proposes pairs through two
  deterministic routes and names the third as unimplemented; `prompts/07_source_relations.md`
  compares them; `x2knwldg apply-source-relations` is the atomic gate that writes
  `output/synthesis/source_relations.json`. `validators.validate_source_relations` enforces the
  shape here **again** at runtime and adds what no schema can hold: basis ownership,
  corroboration for an explicit reference, direction against the grounds, endpoint digests,
  and — the rule that keeps the walk bounded — that the pair was a candidate at all. The
  container gained one additive optional field, `pairs_in_corpus` (D-265).
- `T-254` — ✅ delivered. Three rebuildable SQLite tables — `source_entities`,
  `source_briefs` and `source_relations` — and the two read-only endpoints,
  `GET /api/source-graph` and `GET /api/source-graph/neighborhood/{source_id}` (D-269–D-276).
  Both records described here now reach a client: a brief through
  `SourceKnowledgeAvailability`, which carries it in the `available` and `stale` states and
  `null` in `unavailable` (D-273), and a relation through `SourceRelationSummary` on the graph
  and `SourceRelationDetail` in a neighbourhood, whose basis is bounded by
  `MAX_SOURCE_RELATION_BASIS` with both counts stated.

  Two fields of these records are deliberately **not** projected. `generated_from` has no member
  in either response shape, so the endpoint carries neither digest; and per-relation staleness —
  which `artifacts.source_relations_state` computes from exactly those digests — has no member
  either, so nothing is filtered on it and nothing claims freshness (D-274). A reader that needs
  to know whether a relation still describes its endpoints reads the canonical file, not the
  API, until a later contract version gives it a channel.
