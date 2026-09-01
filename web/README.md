# `web/` — the Knowledge Canvas frontend

Vite + React + TypeScript over the frozen read-only API. Scaffolded by `T-008`,
which deliberately chose no framework; `T-109`–`T-114` chose these and built the
Library and the Reader on them.

```bash
cd web
npm ci             # reproducible install from package-lock.json
npm run typecheck  # tsc --noEmit — the check CI runs
npm test           # vitest, jsdom
npm run dev:api    # the real API over the committed run fixtures, on :8931
npm run dev        # Vite on 127.0.0.1:5173, proxying /api to that server
npm run build      # production bundle into dist/
```

## What is here

| Path | Holds |
|---|---|
| `src/api/contract.ts` | The single re-export of the generated API types. Untouched by `T-109` |
| `src/api/client.ts` | The typed client for the eleven operations, and the runtime path table the compiler checks against the contract |
| `src/api/errors.ts` | The D-030 taxonomy as something the UI can branch on |
| `src/api/canonical.ts` | Defensive readers for the canonical bytes the byte channel serves |
| `src/api/vocabulary.ts` | The controlled vocabularies as values a `<select>` can enumerate |
| `src/api/useAsync.ts`, `src/api/usePaged.ts` | One request, and cursor paging |
| `src/i18n/` | Catalogues and the locale/`dir` provider (`T-110`) |
| `src/styles/` | Design tokens and the stylesheet, logical properties throughout |
| `src/components/` | Provenance and status badges (`T-113`), the media panel (`T-114`), the virtualized list, the report renderer |
| `src/views/` | Library (`T-111`) and Reader (`T-112`) |
| `scripts/dev_api.py` | Stands up the real server over the committed fixtures |

## The API types

The frontend's types are **generated** from the frozen contract into a committed
`schemas/api/v1/types.d.ts` (D-029). Import them from `src/api/contract.ts`:

```ts
import type { Source, SearchResponse, Endpoints } from "../api/contract";
```

Never hand-edit the generated file, and never reach up the tree from
application code — `contract.ts` is the one place that path lives (D-038).
Regenerate with:

```bash
python tools/generate_api_types.py          # rewrite
python tools/generate_api_types.py --check  # fail if stale
```

`tests/test_api_types.py` fails if the committed file drifts from the generator,
and `tests/test_ui_scaffold.py` fails if anything but `contract.ts` reaches
outside this directory.

### The path table is checked, not trusted

`types.d.ts` is types only, so `client.ts` needs runtime path strings. They are
declared as `{ [K in OperationId]: Endpoints[K]["path"] }`, which means the
compiler checks every literal against the frozen contract and refuses a table
that has drifted from it or forgotten an operation. A path this code could not
spell correctly is a build failure rather than a 404.

**The API is frozen: eleven `GET` endpoints.** Widening it is
`schemas/api/v1/openapi.json` first, a regenerated declaration second, and this
directory third — never this directory alone.

## Why `skipLibCheck` is `false`

TypeScript's default is to skip `.d.ts` files, which would skip the only file in
this project that CI is here to check. With it off — and with the declarations
listed as a root file in `include` — `npm run typecheck` type-checks the
generated contract itself. That is the whole of risk **R17**.

If `skipLibCheck` is ever turned on, R17 reopens silently. It is also why this
directory declares its own ambient module types in `src/env.d.ts` rather than
adding a large ambient type package to the program.

## Developing against the real API

Track C is not limited to a mock, and a mock is the weaker oracle: it agrees
with whatever the frontend assumed. `create_app` serves all eleven endpoints
over real fixture runs, so development and the integration checks both run
against it.

```bash
npm run dev:api                                    # terminal one
npm run dev                                        # terminal two
X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test   # runs the integration checks too
```

`scripts/dev_api.py` copies the committed `PASS` / `PARTIAL` / `FAIL` run
fixtures into a scratch project outside the repository, builds the SQLite index
over it, and serves that on loopback. `--project-root PATH` serves an existing
project instead, and `--no-index` reaches the `absent` index state deliberately
— which is how the `503 index_unavailable` rendering is checked by eye.

Without `X2KNWLDG_API_BASE` the integration files skip, so `npm test` stays
hermetic and needs no server.

## Boundaries this directory inherits

From [ADR 0001](../docs/adr/0001-local-web-ui.md) — these are not style
preferences, and each one has a test:

- `output/<id>/raw/` is never written. The UI reads canonical files only, and
  only through the API.
- Run status comes from `validation.json` and `coverage.json` alone. Never
  recomputed, never coerced toward `PASS`. `RunStatusPanel` shows the copied
  triple, so a failing run whose coverage passed shows both.
- Never render an invented timestamp, quote, evidence excerpt, confidence, or
  coverage value. A missing value renders through `Missing`, visibly. There is
  no `?? 0` in `src/lib/format.ts`, and the tests are there to keep it that way.
- Provenance is never signalled by colour alone (invariant 10). Every badge
  carries a glyph, a word, and a border style as well as a colour.
- English is the default UI language, and `dir` switching plus logical CSS
  properties are in the first component rather than a retrofit (D-012, `T-110`).
  `src/styles/logical.test.ts` fails on a physical inline-axis property.
- Nothing is requested from an external host by default. The YouTube embed is a
  facade until the user loads it, `EMBED_HOSTS` is the allowlist, and a report's
  links become anchors only for `http`, `https` and `mailto`.
- The report is rendered as React nodes, never as HTML. There is no
  `dangerouslySetInnerHTML` in this directory and there must not be one.

## Distinctions the UI is required to hold

| Distinction | Where it lives |
|---|---|
| `400 invalid_id` vs `404 not_found` vs `404 unavailable` vs `503 index_unavailable` | `ErrorState`, and `ApiFailure` carries the code |
| An **unbuilt** index vs an **empty** library | `IndexStatusPanel` plus the `index_unavailable` branch — asserted in `src/views/LibraryView.test.tsx` |
| `page.total: null` (not counted) vs `0` (counted, none) | `usePaged` keeps `null` and renders it as "not counted" |
| A `transcript_caption` hit has no `global_id` (D-023) | `SearchResults` links it to source and timestamp only, and says why |
| An `external` artifact has no local bytes (`T-114`) | `localMedium` accepts only a non-external, pathed, available artifact |
| `runs` absent (not reported) vs `runs.skipped: []` (nothing skipped) — D-050 | `IndexStatusPanel` |
| The adapter's `unmappable_artifacts` and `unreadable_files` — D-045 | `SourceCard` flags them, `AdapterDiagnostics` names them |

## Known gaps

- **No cross-source knowledge-unit list.** The frozen contract filters units per
  source, so the Library's `kind` / source class / confidence filters are served
  by asking each listed source separately, and each group reports its own total.
  No aggregate count is shown, because the server never computed one. A
  cross-source entity list taking those filters would be a contract change.
- **No entity page.** `/api/entities/{entity_id}` is served and unused: nothing
  in the Library or the Reader needs to address one entity on its own yet. The
  Map (`T-201`) is its first consumer.
- **The graph endpoints are unused.** They belong to `T-201`.
