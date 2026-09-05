# `web/` — the Knowledge Canvas frontend

Vite + React + TypeScript over the frozen read-only API. Scaffolded by `T-008`,
which deliberately chose no framework; `T-109`–`T-114` chose these and built the
Library and the Reader on them.

```bash
cd web
npm ci             # reproducible install from package-lock.json
npm run lint       # eslint — the hooks rules a type checker cannot express
npm run typecheck  # tsc --noEmit — the check CI runs
npm test           # vitest, jsdom
npm run dev:api    # the real API over the committed run fixtures, on :8931
npm run dev        # Vite on 127.0.0.1:5173, proxying /api to that server
npm run build      # production bundle into dist/

npm run browser           # the gate: the built bundle in a real browser (T-209, T-215)
npm run typecheck:browser # and the gate's own types
npm run typecheck:scripts # and the capture/measurement scripts' (D-203)
```

The capture and measurement scripts are `npm` scripts rather than
`npx tsx …` invocations, and that is D-203: `tsx` appeared in the lockfile only
as an optional peer of Vite, so every documented `npx tsx web/scripts/…`
silently fetched an unpinned copy from the registry at run time — an
undeclared, unversioned execution dependency in the path that produces the
acceptance captures. It is a declared devDependency now, and each command has
one name:

```bash
npm run mockups:layout    # real forceAtlas2 -> layout.json
npm run mockups:capture   # the approved captures
npm run mockups:review    # the page they are compared on
npm run mockups:baseline  # the shipped UI, for comparison
npm run measure:orbit     # the composition, read back off a browser
```

The browser gate starts both servers itself — the API over the committed run
fixtures and `vite preview` over a fresh build — so `npm run browser` needs
nothing running. Two variables move it:

```bash
# walk a real ingested project instead of the fixtures
X2KNWLDG_BROWSER_PROJECT_ROOT=.. npm run browser
# use Playwright's bundled Chromium (WebGL2 through SwiftShader) instead of
# the installed Google Chrome the walk is recorded on
X2KNWLDG_BROWSER_CHANNEL= npm run browser
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
| `src/components/` | Provenance and status badges (`T-113`), the media panel (`T-114`), the virtualized list, the report renderer, and the Map's DOM surfaces — legend and filters (`T-205`), search rail, result card and Peek (`T-206`), card overlay, related list, Quick Read and the one relation cue (`T-207`), and the one collapsible panel plus the DOM companion that lists everything the Map draws (`T-208`) |
| `src/views/` | Library (`T-111`), Reader (`T-112`) and Map (`T-204`) |
| [`src/map/`](src/map/README.md) | The Knowledge Map's machinery: deterministic seed positions (`T-202`), the graph projection, progressive snapshot and page walk (`T-203`), the renderer lifecycle and the one Sigma constructor (`T-204`), the style table and label policy (`T-205`), the URL grammar, search and focus/Peek state (`T-206`), the bounded neighbourhood and the on-stage density policy (`T-207`), the honest-state reducers, the outline projection and the motion policy (`T-208`), and the `T-202` renderer gate |
| `scripts/dev_api.py` | Stands up the real server over the committed fixtures |
| `scripts/` (the `.ts` ones) | Tooling for the visual work, none of it a spec: `mockup_layout.ts` and `capture_mockups.ts` render the approved `T-211` compositions, `capture_baseline.ts` photographs the Map they replaced, `measure_orbit.ts` prints the Directional Orbit's numbers off a running build, and `review_sheet.ts` builds the page the two capture sets are compared on (`T-215`) |
| `gate.html` | The `T-202` gate harness, development-only and outside the production build ([why](src/map/README.md)) |
| `browser/` | The browser gate: **47 specs** over the built bundle and the real API — `T-209`'s 31 behavioural ones and `T-215`'s 16 visual-quality scenarios, which also write the captures the compositions are accepted on. Development-only, outside `src/`, and it imports nothing from the application — a spec that imported the number it is checking would agree with whatever the module says. `browser/composition.ts` is the one measurement of a drawn composition, shared with `scripts/measure_orbit.ts` |
| `playwright.config.ts` | What the gate is pointed at: `npm run build` then `vite preview`, with `/api` proxied to `scripts/dev_api.py`. One worker, no retries |

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

**The API is frozen: thirteen `GET` endpoints.** Widening it is
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
with whatever the frontend assumed. `create_app` serves all thirteen endpoints
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
| A graph **page** vs the graph (D-059, D-123) | `MapView` states loaded / counted total, edges drawn, edges **held** for an endpoint that has not arrived, and whether the accumulated graph is whole — from `GraphSnapshot.state`, never recomputed |
| A graph that is empty vs one that could not be **drawn** (D-129) | `MapView` renders the counts before the canvas, and a renderer refusal (no WebGL2, unsized container) as its own stated state |
| An entity id that names **nothing** vs one the Map has not **loaded** (`T-207`) | `/api/entities/{id}`'s `404` is stated in Quick Read; "not loaded on the Map yet" is read from the accumulated graph and said in the related row |
| A neighbour with **no card** on the stage vs no neighbour at all (D-132, R20) | `placeConstellation` returns a counted reason per refusal — not drawn, off the stage, crowded, over budget — and the related list holds every returned neighbour regardless |
| A neighbour that is **two hops** out vs one with a real relation to the focus | The related row names the relation and direction when there is one, and states the hop distance instead of borrowing another entity's relation |
| A neighbourhood the server **cut short** vs a complete one | `truncated` is the server's own statement and is rendered as one; the client never infers it from a length |
| A question **nobody has asked yet** vs a library with no graph (`T-208`, D-139) | `describeGraph` reports `unasked` with nothing counted; the counts panel appears only once a page has been applied, so no zero is printed for a request that has not been answered |
| A **refused** question vs an empty answer (D-139) | The error panel states the refusal, and where earlier pages are still drawn, `map.reading.stale` says out loud that those counts are not an answer to the request that failed |
| A browser with **no WebGL2** vs a renderer that refused **this container** (D-140) | Two states, two messages: the first is permanent for that browser and the second usually resolves on the next layout. `describeCanvas` decides which, from the phase the failure happened in |
| A picture **not drawn yet** vs a stage with **nothing to draw** (D-141) | `describeCanvas` reports `pending` until a live renderer holds the graph and `nothing` when it holds a graph with no node; `role="img"` is written only while there is a picture to label |
| What the Map **draws** vs what a reader can **reach** (D-142) | `MapOutline` lists every drawn entity as a real card with a real Focus button — no pointer, no WebGL2 and no query needed. It is bounded at 25, states what the bound left out, and is deliberately not windowed |
| A panel **put away** vs a panel with **nothing in it** (D-143) | `Disclosure` keeps each panel's count in its own `<summary>`, so folding a panel never hides that it holds something |
| A neighbour **without a card** vs a neighbour whose card would cover another vs one the stage has no room for (D-145) | `placeConstellation` tries all four ways a card can open, keeps it on the stage, and counts the clause that refused it — `no_room` and `crowded` are different answers and neither is `off_stage`. The rectangle it tests is the drawn card, its gap and the mark it points at |
| A selection the camera has **been told about** vs one it has not (D-146) | `MapSession.frame` centres a new focus with its drawn neighbours, once per selection. Before it, `Zoom in` zoomed about the middle of the stage and pushed the selection off screen |
| A container the renderer **refused** vs one it merely finds tiny (D-147) | `allowInvalidContainer: false` refuses only an *exactly* zero dimension, so the stage's CSS minimum is what keeps a two-pixel graph from being reported as a picture — and a refusal releases the context it had already taken |
| "1 hop" vs "2 hops" (D-149) | `interpolate`'s `{count|singular|plural}`, in the English catalogue only: Persian keeps the singular after a numeral |

## Known gaps

- **No cross-source knowledge-unit list.** The frozen contract filters units per
  source, so the Library's `kind` / source class / confidence filters are served
  by asking each listed source separately, and each group reports its own total.
  No aggregate count is shown, because the server never computed one. A
  cross-source entity list taking those filters would be a contract change.
- **Neither completeness list is windowed, on purpose** (`T-208`, D-142). The
  related list renders one card per returned neighbour and the outline renders
  one per drawn node up to a stated page of 25, with the remainder counted and
  a control that lists more. `VirtualList` exists and measures its rows, and it
  is the right tool for the Reader's captions; it is the wrong tool here,
  because a row outside the DOM is a row no screen reader and no in-page search
  can reach — which costs exactly the claim these two lists exist to make. The
  bound is the neighbourhood's own `limit` and `depth` on one side and a stated
  page on the other, and the real 86-node graph's widest fan-out is eight.
- **The Map's DOM path is the primary one, and the canvas is an enhancement.**
  Search, preview, focus, related knowledge, Quick Read and the Reader are all
  reachable with no pointer and no WebGL2. The card overlay is presentation
  only (D-137): it holds no control, and a guard fails if one appears. `T-209`
  walked that path in a browser with `Tab` alone, and again with
  `WebGL2RenderingContext` deleted. What no automated gate can be is a real
  **screen reader**: what is asserted is the roles, names and states one reads.
- **Ten of the thirteen frozen endpoints have a caller.** `T-207` closed the
  two that mattered for the Map: `/api/entities/{entity_id}` backs Quick Read
  and `/api/graph/neighborhood/{entity_id}` backs the constellation and the
  related list. Three have no caller, and each is a row in the client's path
  table, so the compiler still checks its shape. `getArtifact`
  (`/api/artifacts/{artifact_id}`) has none because nothing in the UI reads an
  artifact's *record*: the Reader reads its bytes, through
  `/api/media/{artifact_id}`. `getSourceGraph` and `getSourceNeighborhood` have
  none **yet** — `T-254` served the Source Map, and `T-256` is the Map mode
  that draws it; until then no view exists to call them, and adding a caller
  with nothing to render would be scaffolding pretending to be a feature. This
  bullet said "every" until the census was actually run (D-187).
- **The Map has been walked in a real browser** (`T-209`), and what that cost
  is worth knowing. The gate is `browser/`: the built bundle over the real API
  in Google Chrome on the target machine, and the same specs on a software
  rasteriser. It found a WebGL context leaked by every refused container, a
  camera that had never been told about selection, a density policy whose grid
  refused the cards that fitted and placed the ones that overlapped, an Escape
  key the canvas could not reach, three touch targets smaller than the rule
  claimed, and three English plural errors — none of which jsdom could have
  shown. ADR 0005 § *Walk result* records the measurements; D-145–D-149 record
  what changed.
- **The picture is the last thing on the route to reach the screen.** The counts
  come before the canvas by decision (D-129), so with the title, the filters,
  the counts panel, the camera controls and the search rail above it the stage
  starts about 790 px down a 1440×900 document — and below the fold entirely on
  a phone. Nothing was changed for it: the order is deliberate and the DOM path
  is the primary one. It is recorded as the first thing to reconsider if the Map
  becomes the route people arrive on.
