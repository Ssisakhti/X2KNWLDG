# Test-only run fixtures

**Nothing in this directory is real evidence.** Every run here is synthetic: the
transcript was written for these tests, the knowledge units are about the fixture
itself, and each `metadata.json` carries `"fixture": true` with a `fixture_note`
saying so. No report, answer, or UI may ever present this content as knowledge
extracted from a real video.

Delivered by `T-006`; closes risk **R11**.

| Run | `validation.json` | `coverage.json` | What it is for |
|---|---|---|---|
| `pass-run` | `PASS` | `PASS` | The happy path, and the only run a fresh clone is guaranteed to have |
| `partial-run` | `PARTIAL` | `PARTIAL` | Second window left uncovered after three audit attempts |
| `fail-run` | `FAIL` | `PASS` | A finalized run whose evidence excerpt no longer appears in its segment |

`fail-run` is deliberately the awkward shape: `report.md`, `graph.json`, and the
Obsidian export all exist and look finished, while `validation.json` says `FAIL`.
A UI that infers status from "the files are there" will pass its tests against
`pass-run` and lie about this one.

## Why they are committed

`output/` is gitignored, so on any machine but the one that ingested the sample
the projection tests in `tests/test_index_schemas.py` would skip — a green suite
that proved nothing. Those tests now run over these fixtures always, and over the
real sample additionally when it is present.

## Regenerating

```bash
.venv/bin/python tests/fixtures/runs/build_fixtures.py
```

The generator drives the real pipeline — `import_transcript`, then
`apply_extraction_bundle`, then `finalize_run` — so a fixture cannot drift from
the shape the pipeline actually writes. The `FAIL` run is produced by finalizing a
valid run and then breaking one evidence excerpt, because
`apply_extraction_bundle` correctly refuses to write a bundle that fails
validation.

Statuses are asserted by the generator itself and again in
`test_fixture_runs_are_labelled_as_synthetic` and
`test_partial_and_fail_runs_are_projected_as_they_are`.

## What now depends on them

`T-115` took these three runs through the HTTP surface, which is what the
honest-status UI reads. `test_api_honest_status` serves each fixture over both
repository implementations and checks that the status the API reports is the one
`pipeline.validate_run` and the canonical files hold — that `PARTIAL` and `FAIL`
survive to a client unchanged, that a run which did not pass is still listed,
searchable and readable rather than hidden, and that `fail-run`'s
finished-looking `report.md`, `graph.json` and Obsidian export do not make it a
`PASS`. That last one is the fixture's reason for existing, stated as an
assertion.
