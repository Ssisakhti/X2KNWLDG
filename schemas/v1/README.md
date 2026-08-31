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
instead of drifting apart (risk R12). Parse a global id with a two-limit split on `:`.
`library.py` must keep emitting the two-part form; changing it breaks
`.claude/commands/kg_navigator.md`.

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
obligation and are asserted in `tests/test_index_schemas.py`:

1. `global_id` equals `source_type:external_id:local_id`.
2. `Source.id` equals `source_type:external_id`.
3. A `time_range` locator has `end_sec >= start_sec`.

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
- `T-005` — the frozen API contract, and TypeScript types generated from it. `Locator`
  uses `type` as its discriminator.
- `T-101`–`T-103` — the SQLite index. Note that the canonical `value` field on statistic
  units is polymorphic (`int` or `list[float]`), which is why no numeric column for it
  appears here (risk R16).

## Validating

```bash
.venv/bin/python -m pytest tests/test_index_schemas.py -q
```

The tests skip cleanly when `jsonschema` is absent, because the core package installs and
tests with zero dependencies (ADR 0001 invariant 5). `jsonschema` lives in the `dev`
extra.
