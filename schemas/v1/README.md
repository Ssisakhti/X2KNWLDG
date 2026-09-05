# Index model v1

Source-neutral schemas for the **derived** index and API layer of the Knowledge Canvas
([ADR 0001](../../docs/adr/0001-local-web-ui.md), canvas plan §10). Delivered by `T-002`.

These schemas describe **nothing that the pipeline writes**. Canonical files under
`output/<source-id>/` keep their own contract — `schemas/extraction_bundle.schema.json`,
`src/x2knwldg/validators.py`, and the build spec — and no record here may change,
constrain, or reinterpret one.

| File | Describes |
|---|---|
| `common.schema.json` | Shared primitives: identifier forms, provenance class, run status, project-relative path, controlled vocabularies |
| `source.schema.json` | One ingested source — one `output/<source-id>/` directory seen through an adapter |
| `artifact.schema.json` | One file or remote representation belonging to a source |
| `locator.schema.json` | A precise position inside an artifact |
| `entity_ref.schema.json` | The addressable handle for a knowledge unit, concept, artifact, segment, or user object |
| `indexed_relation.schema.json` | One edge, addressing both endpoints by global id |

Draft: **JSON Schema 2020-12**. Every `$id` is
`https://x2knwldg.local/schemas/v1/<file>` and cross-references are relative, so the set
resolves as a unit from any base — see `_registry` in `tests/test_index_schemas.py`.

## Versioning

The version is the **directory**. `v1` records carry `"schema_version": "1.0"`.

- **Additive, optional field** → edit in place, no new directory.
- **Widened pattern or bound that accepts strictly more** → edit in place: no stored
  record is invalidated. D-017 is the precedent.
- **New required field, removed field, narrowed type, or changed meaning** → create
  `schemas/v2/`, leave `v1` untouched, and migrate readers deliberately. A stored record
  must always be readable by the schema version it names.

`locator.schema.json` is the one file with no `schema_version` of its own: a locator is
always embedded in a record that carries one.

## The two identifier forms

Both are real, both are required, and neither replaces the other (D-011, ADR 0001
invariant 4).

| Form | Shape | Where it is identity |
|---|---|---|
| Global id | `<source-type>:<external-id>:<local-id>` | Index, API, board files |
| Library id | `<video-id>:<knowledge-unit-id>`, or `concept:<hash>` | `output/library/graph.json`, and the `kg_navigator` skill, which mandates it |

`EntityRef` carries both, so the two vocabularies can be asserted against each other
instead of drifting apart (risk R12). Parse a global id with a two-limit split on `:` —
or, better, with `ids.parse_global_id`. Convert between the forms with
`ids.global_id_from_library_id` and `ids.library_id_from_global_id`, which are exact
inverses. `library.py` must keep emitting the two-part form as the node `id`; changing it
breaks `.claude/commands/kg_navigator.md`. Since `T-003` its nodes also carry an additive
`source_type` and `global_id`, and its concepts an additive `global_id`.

An identifier segment may begin with `-` or `_`, because a YouTube id is base64url and
legitimately does (D-017). A leading dot is barred, so no segment can be `.` or `..`.

Canonical concepts are cross-source, so they use the reserved source type `library` with
external id `concepts`: `library:concepts:<hash>`.

## Rules the schemas enforce

- **Status is copied, never computed.** `runStatus` admits `UNKNOWN` for a missing file
  precisely so nothing has to be guessed, and `PARTIAL`/`FAIL` can never be widened to
  `PASS` by an adapter with an opinion.
- **Paths are project-relative.** Absolute host paths and `..` are rejected by pattern.
  `output/library/status.json` and `videos.json` contain absolute paths today; the index
  must not carry them forward (risk R15).
- **Provenance is structural.** A source-class knowledge unit must have a locator; a
  derived one must have `derived_from` and a `derivation_note`; user content may not
  claim a canonical path, and a user relation may not carry a confidence.
- **Three relation vocabularies stay apart.** `canonical` is restricted to the 16 types in
  `constants.RELATION_TYPES`; `library_synthetic` covers only `derived_from` and
  `expresses_concept`, which `library.py` invents and which are deliberately *not*
  canonical relations; `user` is free-form and workspace-only.
- **A locator is never partially specified.** Each branch is closed and requires its own
  coordinates outright.

## What the schemas cannot say

JSON Schema cannot compare two fields, so three invariants are the **adapter's**
obligation:

1. `global_id` equals `source_type:external_id:local_id`.
2. `Source.id` equals `source_type:external_id`.
3. A `time_range` locator has `end_sec >= start_sec`.

`T-003` implemented them in `src/x2knwldg/ids.py` as `check_entity_ref_ids`,
`check_source_ids`, and `check_locator`. Build identifiers with `make_global_id`
/ `make_source_id` rather than with an f-string, and the first two hold by
construction. The module is stdlib-only, so the core package stays
zero-dependency; its patterns and length bounds mirror `common.schema.json` and
are drift-tested in `tests/test_ids.py`.

## Vocabularies are mirrored, and drift-tested

`canonicalRelationType` and `knowledgeKind` duplicate `src/x2knwldg/constants.py` so that
the schemas stand alone for TypeScript generation (`T-005`). The duplication is guarded:
`test_canonical_relation_vocabulary_matches_constants` and
`test_knowledge_kind_vocabulary_matches_constants` fail the moment the two disagree.
When you add a kind or a relation type, edit `constants.py` **and** `common.schema.json`.

## Consumers

- `T-004` — YouTube adapter, the first producer of these records. The projection in
  `tests/test_index_schemas.py::_project_sample` is a shape probe standing in until it
  exists, and should be deleted in favour of a call into the real adapter.
- `T-005` — the frozen API contract in [`schemas/api/v1/`](../api/v1/README.md). Every
  response body is a `$ref` into this directory rather than a restatement of it, and
  `types.d.ts` declares `Locator` as a discriminated union tagged by `type`.
- `T-101`–`T-103` — the SQLite index. Note that the canonical `value` field on statistic
  units is polymorphic (`int` or `list[float]`), which is why no numeric column for it
  appears here (risk R16).
- `T-251` — the first producer of `entity_type: "source"`, which this model has reserved since
  `T-002`. One per acquired run, addressed as `<source-type>:<external-id>:source` through
  `ids.source_entity_global_id`. It is validated against `entity_ref.schema.json` like any
  other entity and is deliberately **not** in `IndexRecords.by_model()`: the index, the API and
  the Knowledge Map are unchanged by it, which is what D-249 requires and what D-251 makes
  structural rather than a filter. `IndexRecords.by_model_with_source_entities()` is the view
  for a caller that wants to hold every record to these schemas at once.

## Validating

```bash
.venv/bin/python -m pytest tests/test_index_schemas.py tests/test_ids.py -q
```

`tests/test_index_schemas.py` skips cleanly when `jsonschema` is absent, because the core
package installs and tests with zero dependencies (ADR 0001 invariant 5); `jsonschema`
lives in the `dev` extra. `tests/test_ids.py` runs either way — only its one
schema-validation test skips — because `ids.py` is stdlib-only.
