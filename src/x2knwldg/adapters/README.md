# Source adapters

Delivered by `T-004`. An adapter maps one canonical run directory onto the v1
index model in [`schemas/v1/`](../../../schemas/v1/README.md) — the seam that
[ADR 0001](../../../docs/adr/0001-local-web-ui.md) item 7 promises: *adding a
source must require an adapter and possibly a node renderer, never a frontend
rewrite.*

| File | Holds |
|---|---|
| `base.py` | The contract: `SourceAdapter`, `IndexRecords`, and the four rules every adapter obeys |
| `youtube.py` | `YouTubeAdapter` — `output/<video-id>/` — and `adapt_library` for `output/library/` |
| `__init__.py` | The `ADAPTERS` registry, `get_adapter`, `adapt_run`, `adapt_project` |

```python
from pathlib import Path
from x2knwldg.adapters import adapt_project

records = adapt_project(Path.cwd())
records.by_model()   # {"source": [...], "artifact": [...], "entity_ref": [...], "indexed_relation": [...]}
```

## An adapter is a reader

It opens canonical files, copies values, and returns records. It never writes,
and `output/<id>/raw/` — immutable evidence — is only stat-ed and hashed.
`tests/test_adapters.py::test_mapping_does_not_touch_the_run` is the guard.

## The four rules, enforced in `base.py`

1. **Identifiers are built, never spelled.** Every id goes through
   [`ids.py`](../ids.py); `check_records` re-asserts the three cross-field
   invariants plus two more — an artifact belongs to the source it names, and no
   two records claim one global id (risk R12).
2. **Paths are project-relative.** `project_relative` *refuses* a path outside
   the project root rather than storing an absolute host path (risk R15).
   `output/library/status.json` and `videos.json` hold absolute paths; nothing
   here reads them.
3. **Status is copied.** `read_status` maps a missing, unreadable, or
   unrecognised validator file to `UNKNOWN`. It has no branch that can turn a
   `PARTIAL` or a `FAIL` into anything else (ADR 0001 invariant 2).
4. **A guess is a refusal.** A media type is stated only when it is IANA
   registered — `.srt` has none, so it is `null`. `raw/source.<ext>` is
   discovered, because `pipeline.import_transcript` names it after the imported file. What
   cannot be mapped without inventing a value raises `AdapterError` instead.

## What v1 maps, and what it deliberately does not

Entities are emitted for **knowledge units** and **canonical concepts** only.
`caption`, `segment`, and `coverage_window` stay reserved in the
`EntityRef.entity_type` vocabulary and unemitted: each already has a canonical
representation the Reader and the indexer read directly, and none has a consumer
needing a global handle yet. Because the enum reserves the names, adding them
later needs no `schemas/v2/`.

Coverage-window membership is not an `IndexedRelation` either — expressing it
would mean inventing a fourth relation vocabulary, which is a schema change.

## Adding a source type

1. Subclass `SourceAdapter` in a new module; set `source_type` and `version`.
2. Implement `detect` and `adapt_run`, building every id through `ids.py` and
   every path through `self.relative`.
3. Return `check_records(IndexRecords(...))`.
4. Register the class in `ADAPTERS`.
5. Add fixtures under `tests/fixtures/runs/` and let the contract tests in
   `tests/test_index_schemas.py` run over them.

Nothing in `base.py`, in the schemas, or in the frontend should need to change.
If it does, that is the signal that the generic model is missing something —
fix the model, not the adapter.

## Tests

| File | Asks |
|---|---|
| `tests/test_index_schemas.py` | Do the adapter's records satisfy the v1 schemas? (needs `jsonschema`, a `dev` extra) |
| `tests/test_adapters.py` | What does the adapter refuse, omit, and never invent? (stdlib only — runs on a bare core install) |
