# T-211 — Visual specification: Explore and Focus

**Status:** **approved 2026-09-03 (D-191)** · **Review viewport:** 2852×1688 · **Binding:** [ADR 0006](../../adr/0006-map-visual-quality.md)

This was the approval gate for Phase 2.1, and it has passed. It changes no production UI.
`T-212` is now claimable, and the order `T-212` → `T-213` → `T-214` → `T-215` is fixed.

From here this file is a **contract, not a proposal**: a deliberate departure from what is
specified here is a change to this file and a note in the decision ledger, not a silent
divergence.

**What `T-215` compares against.** The *sources* in this directory are the reference — the
mockup pages, `mockup.css`, `render.js`, and the extracted `data.js` / `layout.json`. They are
committed; the PNGs they render are not, on the same rule `.gitignore` already applies to the
browser gate's own output. `capture_mockups.ts` reproduces every capture from these sources on
demand, so there is no stored render that can drift from its own source with nothing to notice
it. The approved compositions also live permanently in the published review artifact, which is
the record of what was accepted on 2026-09-03.

The four reference images are not in the repository, so the compositions are derived from
ADR 0006's written characterisation of what each contributes. What each one gave, and what
was deliberately not taken, is recorded in [§9](#9-what-the-references-contributed).

---

## 1. What the review found, measured

The rejected screen is not badly coloured; it is composed as a document. At 2852×1688:

Measured on the real build at 2852×1688 by `capture_baseline.ts`, against the real
project root (86 nodes, 118 edges) — not estimated:

| Measured | Explore | Focus |
|---|---|---|
| Route content column (`.shell__main`, `max-inline-size: 78rem`) | **1248 px** | 1248 px |
| Horizontal space unused | **1604 px** across both margins | 1604 px |
| Stage top edge | **790 px** down the document | 652 px |
| Stage height (`min(70vh, 640px)`) | **640 px** — 38 % of the viewport | 640 px |
| Document height at a 1688 px viewport | 1873 px | **5795 px** |

The last row is the finding. Focusing one entity produces a document **3.4 screens tall**,
so the Search → Focus → Quick Read loop the Map exists for cannot be completed without
roughly 4100 px of scrolling. Above the stage sit `h1` → subtitle → `MapFilters` → counts
panel → control row → `MapSearchRail`; below it, five stacked `<details>` — search,
outline, Quick Read, related, legend. `findMark` in `gate.ts` already records the same
790 px at 1280×720, so this is not a wide-viewport artefact.

`#/map` is **one** route. Explore and Focus are the same DOM in different panel states,
switched by `?focus=<global_id>`. This proposal keeps that exactly: no second route, no
second URL grammar, no second graph store.

---

## 2. The workspace

```
┌──────────────────────────────────────────────────────────── 2852 ────┐
│ app bar                                                        56 px │
├──────────────────────────────────────────────────────────────────────┤
│ ░░ stage — fills the remaining 1632 px, edge to edge ░░              │
│    floating chrome sits ON it; nothing pushes it down                │
└──────────────────────────────────────────────────────────────────────┘
```

- The document never scrolls: `html, body { overflow: hidden }`, the workspace is
  `grid-template-rows: var(--bar-height) 1fr`.
- The app bar keeps `Shell.tsx`'s structure and its `aria-current="page"` accent pill.
- All chrome floats over the stage in bounded surfaces at `--radius-lg` with a 92 %
  `--bg-raised` ground and a 12 px backdrop blur.

**Chrome positions.** Explore: search top-start (420 px), counts top-end, legend
bottom-start, zoom bottom-end. Focus: focus bar top-start, zoom bottom-end, omission note
bottom-start, Quick Read as the one drawer at the inline end (560 px).

All chrome uses **logical** insets, so the whole composition mirrors under `dir="rtl"`
with no second stylesheet (D-012).

---

## 3. Explore

A quiet field. Marks and structure dominate; text appears by semantic zoom, hover,
keyboard focus or selection.

- **Layout** is the production path, not an imitation: `mockup_layout.ts` runs the real
  `seedPosition`, a real graphology graph and the real `forceAtlas2` with `inferSettings`
  at `MAP_LAYOUT_ITERATIONS`, which is what `MapSession.relax()` runs. A hand-rolled
  simulation was tried first and produced a field the renderer never draws.
- **Marks** keep `mapStyle.ts` exactly: shape and base size from `NODE_PROVENANCE_MARK`
  (source circle 9, derived diamond 11, user square 9), hue from `KIND_FAMILY_COLOUR` via
  `KIND_FAMILY`. Mark size scales with the viewport; the ratios do not.
- **Edges** take their head and thickness from `EDGE_VOCABULARY_MARK`. A
  `library_synthetic` edge is **dashed as well as diamond-headed**, because at overview
  scale a head is two pixels and the vocabulary distinction has to survive.
- **Labels**: eight over 86 marks, the density `T-209` measured. Selection is one label
  per `labelGridCellSize`-sized cell, densest node first, then two rejections — a label
  that would overlap another label, and a label that would sit on any mark.
- Ground `#17161a` / `#fbfaf8`, matching `mapStyle`'s stage backgrounds.

---

## 4. Focus — Directional Orbit

The selected card is fixed at the centre of the field. **Incoming relations left, outgoing
right, actual hop as radial distance.**

### Geometry at 2852×1688

| Element | Value |
|---|---|
| Field | viewport width **less the drawer**, so the centre is centred in what remains |
| Centre card | 560 × 232, at the field's centre |
| Hop-1 arm | 400–530 px, widest for the bands level with the centre card |
| Hop-2 arm | hop-1 arm + 300 px |
| Neighbour card | 320 × 148, port on the edge facing the centre |
| Hop-2 chip | 220 × 76 — a mark further out carries less, by design |
| Vertical band | ±560 px, clamped so no card runs under floating chrome |
| Drawer | 560 px, inline end, full height less 16 px |

- **Direction is spelled out, not implied by side.** A bare arrow is the same glyph on
  both sides — the relation flows rightwards *into* the focus on the left and rightwards
  *out of* it on the right — so an arrow alone states position, not direction. Each pill
  reads `exemplifies → focus` or `focus → supports`, and mirrors in RTL.
- **A hop-2 edge leaves the hop-1 card it is actually joined to**, never a phantom point
  on the ring, and its pill names that parent (`KU-000026 → is_part_of`). `parentId` is in
  the data so this is read from the records rather than assumed.
- **Pills are always horizontal** and never rotated onto a path. Each is seated by walking
  its own curve — seven positions along it, then seven perpendicular lifts — until it
  lands on no card and no other pill. A lifted pill keeps a dashed leader back to its edge.
- **Hop rings** are dashed ellipses labelled at the foot, on the vertical axis.
- **Unrelated topology stays present and faint** at `MAP_DIMMED_NODE_OPACITY` × 0.55 —
  never removed, never competing.
- Self-loops would be stated without fabricated direction; `intentional_self_loop` is a
  real field. The sample graph contains none, so none is drawn.

### Quick Read

The one primary drawer, in `MapQuickRead`'s existing six-section order: stored statement →
recorded evidence (`locator.excerpt`, time range, `segment_id`) → active relations →
derivation → provenance and source → technical metadata.

---

## 5. Responsive: three compositions, not one scaled three ways

The orbit needs room for a centre card plus a card on each side. Below that it cannot be
drawn honestly, and the answer is **not** to shrink text until it is unreadable. It is to
place fewer cards and **count** what was left off — the rule `placeConstellation` already
implements with its `StageOmission` reasons.

| Tier | Width | Composition |
|---|---|---|
| `full` | ≥ 2000 px | Orbit, drawer open beside it, all 8 hop-1 and 4 hop-2 placed |
| `compact` | 900–1999 px | Orbit, 2 cards per side, no hop-2, drawer closed to its trigger; **10 omissions counted on screen** |
| `stack` | < 900 px | No orbit. Focus card, then every relation as a row with its direction pill and hop badge — **all 12, none dropped** |

The accounting is asserted in the page: placed + omitted must equal the neighbours
returned, and the mockup logs an error if it does not.

---

## 6. Visual system

Tokens are `tokens.css`'s, unchanged: `--text-xs`…`--text-xl`, `--space-1`…`--space-6`,
`--radius-sm/md/lg`, and the light/dark colour sets. What T-211 adds:

| Proposed token | Value | Why |
|---|---|---|
| `--bar-height` | 56 px | the workspace grid's first row |
| `--orbit-ring` | 10 % / 12 % foreground | hop rings, below every mark |
| `--edge-faint` | 18 % / 20 % foreground | the quiet Explore field |
| `--float-shadow` | two-layer | lifts chrome off the stage without a hard border |
| `--card-shadow` | two-layer | separates a card from the field it covers |

**Provenance is never colour alone** (ADR 0001 invariant 10). Every card states it four
ways: rail colour, rail **border style** (`solid` / `dashed` / `dotted`), badge glyph
(`◆` / `◇` / `✎`) and the badge word. It survives greyscale, and it survives the badge
being cropped.

**Kind hue is a small cue**, never a card fill: an 8 px swatch in the badge and the mark's
own colour on the stage.

The focused card is the centre by four means at once: size, a doubled border, a 1 px
accent ring plus accent glow, and — in light mode, where a glow reads as weaker — a 4 %
accent tint in its ground.

### Proposed constants, and what they replace

| Constant | Now | Proposed |
|---|---|---|
| `MAP_STAGE_PRIMARY_BOX` | 416 × 176 | 560 × 232 at `full` |
| `MAP_STAGE_CARD_BOX` | 320 × 296 | 320 × 148 — the card no longer holds a control |
| *(new)* hop-2 chip | — | 220 × 76 |
| `MAP_STAGE_CARD_BUDGET` | 4 | per-side and tier-derived; omissions still counted |
| `MAP_STAGE_PRIMARY_CHARS` | 200 | unchanged |
| `MAP_STAGE_NEIGHBOUR_CHARS` | 110 | unchanged |

Truncation is the existing `cutToBudget`, ported code-point-for-code-point: whitespace
collapsed, cut by code point (never by UTF-16 unit, which halves a surrogate pair), word
boundary preferred only at ≥ 60 % of the budget.

---

## 7. Semantic order vs visual order

CSS moves surfaces; the DOM does not follow them. This is the risk D-153 creates, and the
`ui-ux-pro-max` `ux` rule *Keyboard Navigation* names it: tab order must match visual order.

| DOM / tab order | Visual position |
|---|---|
| 1 `h1` + subtitle | visually hidden; the bar carries the name |
| 2 filters, counts | floating status, top end |
| 3 search rail | floating drawer, top start |
| 4 stage | the field itself |
| 5 outline | in the search drawer's panel list |
| 6 Quick Read | drawer at the inline end |
| 7 related list | inside Quick Read's drawer, below the relations |
| 8 legend | floating, bottom start |

Reading order is preserved: focus → its relations → the wider list. Nothing that floats
visually is reordered in the DOM to match; the visual placement follows the DOM, which is
the direction that keeps the keyboard route truthful.

---

## 8. Accessibility findings applied

Verified against the `ui-ux-pro-max` `ux` domain. Its `color` and `style` domains were
queried and **not** used: they return product palettes and presets, while `tokens.css`,
`KIND_FAMILY_COLOUR` (already Paul Tol's colourblind-safe qualitative set) and ADR 0006's
editorial direction are binding here and outrank any preset.

| Finding | Severity | How the composition answers it |
|---|---|---|
| **Focus Not Obscured (Minimum)**, WCAG 2.2 AA | High | The drawer's width is subtracted from the field **before** the centre is placed, so the focused card can never sit under it. Checked in the page, on both sides — see §10 |
| **Focus Not Obscured (Enhanced)**, AAA | Medium | Met at `full` and `stack`. Recorded as a target, not claimed as AA |
| **Keyboard Navigation** | High | §7 |
| Touch target ≥ 44 × 44 | Critical | Every control is `min-block-size: 2.75rem`, the rule `access.spec.ts` already asserts |
| Reduced motion | Medium | `prefers-reduced-motion: reduce` disables all animation and transition; the camera policy stays `motion.ts`'s |

---

## 9. What the references contributed

| Reference (per ADR 0006) | Taken | Deliberately not taken |
|---|---|---|
| Workflow reference | dark quiet field, compact cards, visible ports, labelled paths | its domain workflow semantics |
| Interaction-map reference | disciplined routes, sparse annotation, clear hierarchy | its step numbering and journey framing |
| Radial references (two) | a definite centre, rings, editorial composition | **any radar axis, cluster, importance score or magnitude** |

The rings encode `hops`, which the API returns. Nothing in either composition encodes a
quantity the records do not carry. There is no `size`, `weight`, `degree`, `importance`
or `cluster` field on `EntityRef` or `IndexedRelation`, and none is drawn.

---

## 10. Self-checks that run in the page

The Focus mockup measures its own acceptance clauses and writes them to
`window.__geometry`; the capture script fails on any console error, so a capture cannot be
produced while one is violated. It found three real defects during this work: a pill on top
of a card, a drawer covering the focused card in RTL, and cards under the focus bar at
1440×900.

- no two placed cards overlap
- no card is clipped by the stage edge **or by any floating chrome**
- the drawer does not cover the focused card, tested on both inline sides
- every relation pill found a seat touching no card and no other pill
- placed + omitted equals the neighbours returned

---

## 11. Content

Every record is real, from `output/library/graph.json` and
`output/pqlWNihgdjI/knowledge_units.json` — the AWS talk *From AI-Assisted to AI-Native*
(86 nodes, 118 edges, 69 units + 17 concepts).

Focus centre is `KU-000028`, degree 8: 6 incoming, 2 outgoing, 4 nodes at hop 2 — an
asymmetric fan-out on purpose, because a balanced one would hide the layout problem. The
neighbourhood includes `library:concepts:a4abbc1138ec`, which really carries
`source_id: null` and `confidence: null`, so the honest-null rendering — *not stated*, in
`--missing-fg` italic — is shown rather than described.

### Persian

Chrome strings are lifted **verbatim** from the `fa` catalogue in `catalog.ts`; they
already ship, and none is invented.

Twenty-four knowledge statements were translated **for this mockup only**, to exercise RTL
wrapping and truncation on realistic body copy. They live in `fa.js`, are labelled there,
and are **not** canonical: nothing is written to `output/`, and no knowledge unit gains a
translation. The API serves the extracted English.

That mixture is itself the honest depiction: a Persian UI around content the API returns in
English. It exposed a real bug — an untranslated English statement inside an RTL Map had
its truncation ellipsis reordered to the front of the line. Statements are therefore
rendered in a bidi isolate, which is what the production `Bidi` component exists for
(D-012). Identifiers stay LTR in `Mono`.

---

## 12. Regenerating

```bash
npx tsx web/scripts/mockup_layout.ts     # real forceAtlas2 -> layout.json
python3 docs/mockups/T-211/gen_data.py   # canonical records -> data.js
npx tsx web/scripts/capture_mockups.ts   # all ten captures
```

That writes `captures/` — the two compositions in dark, light and Persian, the honest-states
strip, and the 1440×900 and 390×844 breakpoints the browser gate already tests. The directory
is gitignored: it is a build product of the committed sources, not a source itself. A fresh
clone has no captures until the third command is run, which is the intended state.

Regeneration is deterministic. `layout.json` is committed rather than recomputed on every run,
so a change to the field is a reviewable diff instead of a silent reshuffle; re-run the first
command only when the graph or the layout constants actually change.

**The two baseline captures are the exception, and they are not reproducible from a clone.**
`capture_baseline.ts` photographs the *running* application, so it needs the API served, the
bundle built and a preview running — and it reads `output/`, which is gitignored and local to
whoever ingested the source. A clone with a different library, or none, cannot reproduce them:

```bash
../.venv/bin/python scripts/dev_api.py --project-root .. --port 8955
X2KNWLDG_API_BASE=http://127.0.0.1:8955 npm run build
X2KNWLDG_API_BASE=http://127.0.0.1:8955 npx vite preview --port 4199
npx tsx scripts/capture_baseline.ts
```

That is why the baseline is recorded as **numbers in §1** rather than only as pictures. The
numbers are the durable evidence — 1248 px column, 790 px stage top, 5795 px document — and
the script prints exactly those on every run, so the claim can be re-checked against a live
build even when the images are gone. The images themselves remain in the published review
artifact.

---

## 13. What `T-212` built, and the four places it departed

`T-212` implemented §2's workspace and §7's order. The §1 numbers were re-measured on the
running build at the same viewport by the same method, and they are the "after" the baseline
exists to be compared against:

| Measured at 2852×1688 | Before | After |
|---|---|---|
| Route content column | 1248 px | **2852 px** — there is no column |
| Stage top edge | 790 px | **56 px** — the app bar, and nothing else |
| Stage size, Explore | 1216 × 640 (38 % of the viewport) | **2852 × 1632** (97 %) |
| Stage size, Focus | 1216 × 640 | 2260 × 1632 — the field less the drawer |
| Document height, Explore | 1873 px | **1688 px — the viewport. It does not scroll** |
| Document height, Focus | **5795 px** | **1688 px** |
| Neighbour cards placed / omitted, Focus | 2 / 7 | **4 / 4** |

At 1440×900 the same loop needs no scroll either: the document is 900 px in both states. The
one number that moved the wrong way is the card count at that viewport — 1 placed and 8
counted, against 2 and 7 before — because the neighbourhood is framed by camera *ratio*, so
its marks are half as far apart on a field half as wide and the neighbours collide with the
focused card rather than with the chrome. Every one of the eight is counted and listed (R20),
and `T-213` replaces this placement entirely: SPEC §5 gives the `compact` tier a deterministic
two-cards-per-side orbit rather than cards pinned to ForceAtlas marks.

This file is a contract, so the four deliberate departures are recorded here rather than left
to be discovered. Each is also in D-192.

1. **The camera's controls share the inline-end rail with the drawer instead of floating
   under it.** §2 puts the zoom bottom-end and §4 gives the drawer the full height at the
   inline end; in the approved capture the drawer therefore paints *over* the zoom float,
   because `.drawer` carries `z-index: 5` and `.float` carries none. A reader who opens Quick
   Read cannot zoom the graph they are reading about — the same WCAG 2.2 AA *Focus Not
   Obscured* failure §8 cites, one surface over. The rail is a flex column with the controls
   last, so the position §2 states is kept and the drawer is about 60 px shorter.

2. **`html, body { overflow: hidden }` is scoped to the route.** Written as
   `html:has(.shell--workspace)`, because three routes share one document and the other two
   *are* documents: the Library and the Reader must scroll. The clause itself is unchanged.

3. **The outline is a panel inside the search drawer, so it precedes the stage.** §7 numbers
   it after the stage while placing it visually in that drawer's panel list, and those cannot
   both be true of one DOM. The visual column is the binding one — the table's own subject is
   that tab order follows visual order — and it agrees with D-129, which wants the account
   before the picture.

4. **The drawer's width comes out of the field only at the `full` tier.** §5 already says the
   `compact` tier keeps the drawer "closed to its trigger", and the browser gate measured why
   that boundary is arithmetic: subtract 560 px and its margins from a 1280 px viewport and
   the field is 688 px, the camera frames the focus in the middle of it, and the 416 px
   primary card needs 452 px of clear field on one side and has 344 px on either. No
   orientation fits, the card D-132 guarantees falls back to its preferred direction, and it
   hangs 5 px over the edge. Below 2000 px the drawer floats over the field instead, and the
   chrome-avoiding clause in `placeConstellation` is what keeps the card out from under it.

Two clauses of §5 and all of §6's constants are deliberately **not** implemented: the
`compact` and `stack` compositions and the new card boxes belong to `T-213` and `T-214`, which
own the orbit and the visual system. Below 48rem the route keeps the document composition it
already had and its tested touch journey, rather than shipping four floating surfaces stacked
on one another at 390 px.
