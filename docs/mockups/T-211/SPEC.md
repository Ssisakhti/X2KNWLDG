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
  `KIND_FAMILY`. Mark size scales with the viewport; the ratios do not. That last sentence
  took until `T-216` to be true of the shipped renderer, which scaled a mark by the *framing*
  instead — `markFieldScale` is the clause, and §17 is the decision.
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
| `--edge-faint` | 18 % / 20 % foreground | the quiet Explore field — no reader on a canvas, so it ships as `MAP_QUIET_EDGE_OPACITY` (§15's first departure, closed in §17) |
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
npm --prefix web run mockups:layout     # real forceAtlas2 -> layout.json
python3 docs/mockups/T-211/gen_data.py   # canonical records -> data.js
npm --prefix web run mockups:capture   # all ten captures
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
npm run mockups:baseline
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

---

## 14. What `T-213` built, and the five places it departed

`T-213` implemented §4's Directional Orbit and §5's three compositions. The numbers below
were read off the running build by `web/scripts/measure_orbit.ts`, at the same viewport and
by the same method as §13's, and they are what `T-215` has to hold or beat:

| Measured, focus `KU-000028` (8 neighbours returned) | `T-212` | `T-213` |
|---|---|---|
| Cards placed / counted at 2852×1688 | 4 / 4 | **7 / 1** |
| Cards placed / counted at 1440×900 | 1 / 8 | **2 / 6** |
| Cards clipped by the field | 0 | **0** |
| Card over card, or card under a floating control | 0 | **0** |
| Relation pills with no clear seat on their path | — | **0** |
| Document height at 2852×1688 | 1688 px | **1688 px** |

The five deliberate departures, recorded here rather than left to be discovered. Each is also
in D-193.

1. **The card boxes are larger than §6 proposes, because the browser laid them out larger.**
   §6 gives a neighbour 320 × 148; at 320 px wide Chrome laid the shipped card out at 186 px,
   and the reservation being smaller than the card is a fit test that passes while a relation
   pill is seated in space the policy believes is empty. The reserved heights are now upper
   bounds over what `measure_orbit.ts` reads back — 320 × 208 at `full`, 270 × 240 at
   `compact` — which is the discipline `T-209` established for `MAP_STAGE_CARD_BOX`. The
   mockup's own cards carried no `global_id` line and its measurement was of itself.

2. **The `compact` tier's boxes are smaller than the mockup drew at 1440.** §5 puts that
   tier's floor at 900 px, and half the centre card plus a gap plus a neighbour's card plus
   the field's inset has to fit in half of it. The mockup's 420 × 200 and 264 × 132 need
   1004 px, so at the tier's own minimum every card would have been refused and counted —
   honest and useless. 300 × 200 and 270 × 240 fit 900, and `orbitMinimumWidth` asserts it.

3. **The relation pill is as wide as its own words, not one fixed width.** §4 gives a hop-1
   edge `arm − primaryBox.width / 2` of clear run between the two cards it joins. One uniform
   260 px pill is wider than that run, and four of seven pills found no seat at all. The box
   is computed from the label's own code points and written onto the element, so the
   rectangle a seat was found for is the rectangle drawn.

4. **The vertical band is clamped by a search, not by an inset.** §4 says the band is
   "clamped so no card runs under floating chrome" and this is that clamp. An inset cannot
   do it: the search rail at the `full` tier is 424 px tall against the composition's 150 px
   inset, and the only adjustment a card has — pushing outward along its arm — moves it
   *towards* the field's inline edge, which on the incoming side is where that rail is. Three
   of six cards walked further under the surface they were escaping and were refused for
   leaving the field. Narrowing the band moves the whole side inwards instead.

5. **`stack` is the route's own document, and the floating chrome is bounded while focused.**
   §5's third tier asks for the focus card and then every relation as a row, all of them,
   none dropped — which is what the document composition below 900 px already is, in that
   order, with the direction and the hop count on each row. Moving the WebGL container in the
   DOM on a resize to put the strip elsewhere would risk the context loss D-147 exists to
   handle, and reordering it in CSS would break §7's binding rule that tab order follows
   visual order. Separately, §2 gives Focus different chrome from Explore — a focus bar
   rather than the search rail, the counts and the legend. Rather than build a second set of
   surfaces, the ones that exist are **bounded to a quarter of the field while focused**:
   they keep their headings, their numbers and their own scroll, so everything D-129 requires
   before the picture is still there and still reachable without a pointer. At 1440×900 the
   counts surface was 57 % of the field's height, standing where the outgoing side of the
   orbit is drawn.

---

## 15. What `T-214` built, and the two places it departed

`T-214` implemented §6's visual system over the composition `T-213` placed. It moved no card
and changed no coordinate: `measure_orbit.ts` reads the same 7 placed / 1 counted at
2852×1688 and 2 / 6 at 1440×900, with the same zeros for clipping, overlap, chrome and
unseated pills. What changed is what a reader can tell apart.

| Clause (§6, ADR 0006 clause 5) | How it is met |
|---|---|
| Provenance never colour alone | Four signals, unchanged and now asserted as a stylesheet rule: rail colour, rail **border style** (`solid`/`dashed`/`dotted`), badge glyph (`◆`/`◇`/`✎`) and the badge word |
| Kind hue is a small cue, never a card fill | `KindBadge` — an 8 px swatch from `KIND_FAMILY_COLOUR`, beside the record's own kind token, at every place the Map names a kind. A rule asserts no card is ever filled with it |
| The focused card is the centre by four means | Size (the tier's `primaryBox`), a doubled border, a 1 px accent ring with an accent glow behind it, and a 4 % accent ground tint in light mode only, where the glow reads as weaker |
| Type scale with an explicit hierarchy | Three card sizes carry three type sizes: `--text-md` for the statement being read, `--text-sm` for one being judged, `--text-xs` for a mark further out |
| Graph labels may not render under cards | A node the orbit has carded loses its canvas label, and an edge whose **both** endpoints are carded loses its relation label, because the card and the pill already carry them — in more text and with the cut marked. A neighbour the orbit only *counted* keeps its label, so every neighbour is still named |
| Nothing decorative implies a quantity | Asserted: no token keys a size, an opacity or a colour to a `confidence`, and `mapStyle` never reads that field at all |

The two deliberate departures. Each is also in D-194.

1. **`--edge-faint` is not implemented, because nothing can read it.** §6 proposes it for
   "the quiet Explore field", and Explore's edges are drawn by WebGL: a canvas cannot read a
   CSS custom property, which is the same constraint `mapStyle`'s comment on `labelColor`
   already records. The production equivalent exists and is `MAP_DIMMED_EDGE_OPACITY`, in the
   one style table, where a renderer can reach it. Adding the token as well would ship a
   number with no reader and two places to change it.

2. **The kind swatch is on the Map's surfaces, not the Library's and the Reader's.** The hue
   is `KIND_FAMILY_COLOUR`'s, the legend that explains it is the Map's, and a swatch on a
   Reader row would be a colour with no key on that screen. `EntityCard`, `SearchResults` and
   `ReaderView` keep the plain badge; they name the same kind in the same words.


---

## 16. What `T-215` built, and what the comparison shows

`T-215` is the gate, not a change to the composition: `git diff` over `web/src/` is empty and
no `output/` file was touched. It adds `browser/composition.ts` — the probe
`measure_orbit.ts` used to carry, moved so the script and the gate read one implementation —
`browser/visual.spec.ts`, sixteen scenarios that assert on it and photograph what they
asserted, and `scripts/review_sheet.ts`, which builds the page the two capture sets are
compared on.

### What each scenario is held to

Per scenario, from the seams `T-212`–`T-214` published rather than from a card count: the
tier the route says it drew; the direction the document is in; zero marks outside the field;
zero mark-over-mark; zero marks under a floating control; zero pills without a clear seat;
every pill horizontal; and the document exactly the viewport (the `stack` tier excepted — it
*is* a document, which is `T-213`'s fifth departure). With something focused it adds: the
centre is the selected entity; placed plus counted equals the neighbours the server returned,
which is also the number of rows in the list; every card's `hops` equals a breadth-first walk
of the served edges; every hop-1 card's side is the direction of its own relation *seen from
the focus*; that side is a place, mirrored under `rtl`; and the focused card is both the
largest card and the nearest to the middle of the field.

The entity walked is the mockups' own — `KU-000028` — whenever the served library holds it,
because two pictures of two different neighbourhoods cannot answer whether this build
reproduces *these* compositions. Over the committed seven-node fixtures the gate falls back to
the busiest entity the graph has: the clauses still hold, the recorded numbers cannot, and are
not asserted.

### The numbers, re-measured on the running build

| Focus `KU-000028`, 8 neighbours returned | `T-213`/`T-214` | `T-215` |
|---|---|---|
| Cards placed / counted at 2852×1688 | 7 / 1 | **7 / 1** |
| Cards placed / counted at 1440×900 | 2 / 6 | **2 / 6** |
| Cards placed / counted at 1280×720 | 1 / 7 | **1 / 7** |
| Clipped, overlapping, chrome-covered, unseated | 0 | **0** |
| Relation pills not horizontal | — | **0** |
| Document height at 2852×1688 / 1440×900 | 1688 / 900 | **1688 / 900** |

Held in dark, light and Persian: the placement reserves the tier's boxes rather than the
text's, so a mirrored composition places the same seven cards.

**Searching costs one card, and says so.** With results listed, the search rail grows from
237 px to 424 px, the orbit keeps its cards clear of the chrome, and the card that fitted
beside the collapsed rail is refused and counted — 6 placed and 2 counted at the review
viewport, with `no_room` going from 1 to 2. Nothing is dropped silently, which is the clause
that binds; what a reviewer should know is that reading and searching are two compositions.
The `focus-search` scenario holds that pair rather than the reading one.

### The one clause this gate cannot see

ADR 0006 clause 5 forbids a graph label under a card. In production that label is drawn by
WebGL into the single stage canvas: there is no DOM node for it, no per-label geometry to
read, and Sigma exposes no instance to ask. So the clause is asserted where it *is* readable
— `labelPolicy` hides a carded node's label and an edge's label when both endpoints are
carded, held by `labelPolicy.test.ts` and `visualSystem.test.ts` — and what the browser gate
asserts is the half with a rectangle: a relation pill is a label too, and a pill over a card
is the same defect with a DOM node to name it. Stated here rather than left as an implied
"all four clauses are in the browser".

### What the comparison shows

The geometry is green and the **Focus** composition reproduces the approved one closely:
the same sides, the same hop rings, the same ports, horizontal pills naming both ends, the
focused card unmistakably the centre. Three differences are visible in the pictures and are
recorded here for the acceptance decision rather than fixed, because `T-215` adds no
application surface.

1. **Explore's field is not quiet at the review viewport.** A node's size is stated in graph
   units and Sigma's default `itemSizesReference: "positions"` scales it with the camera
   (`zoomToSizeRatioFunction: Math.sqrt`), so framing the same 86-node graph into a 2852 px
   field draws every mark several times the diameter the approved composition shows. Marks
   touch and overlap, the label grid then has room for roughly forty labels where the
   reference has eight, and the topology the overview exists to show is harder to read at the
   review viewport than at 1440. The reference's quiet field is, in the shipped renderer, a
   function of viewport width.
2. **At the `compact` tier the floating surfaces are panels, not chips.** At 1440×900 the
   search rail is 420×219 and the counts/filters float 352×219, and the second stands at
   x=704 — the middle of an 1440 px field — with the graph behind it. SPEC §5 gives that tier
   a search "closed to its trigger", and the approved capture has a one-line search chip and a
   two-line counts chip in the corners. No card is placed under either (the placement refuses
   that), so this is a composition finding rather than a geometry one.
3. **Quick Read and the related list are present with nothing focused.** In Explore both
   panels are mounted and say "nothing focused", where the approved overview has an
   unobstructed field. That is a deliberate choice — a panel that disappears cannot say that
   nothing is selected — and is noted because it is a difference from the reference, not
   because it is wrong.

**These three are `T-216`.** The captures were not accepted as they stand (D-196): the three
differences above became a fifth child of `T-210`, with the sizing model behind the first of
them — Sigma's `itemSizesReference`, and the zoom rule that depends on it — decided there
rather than assumed here. `T-215`'s acceptance is taken up again against `T-216`'s captures,
and this gate is the instrument that judges them, unchanged. **§17 is what it closed, and
what is left over.**

### Regenerating the comparison

```bash
npm --prefix web run mockups:capture                     # the approved set
cd web && X2KNWLDG_BROWSER_PROJECT_ROOT=.. npx playwright test visual.spec.ts
npm --prefix web run mockups:review                        # the page they are compared on
```

The gate is pointed at the real library on purpose: the mockups compose `KU-000028` out of
the 86-node graph, and a capture of the committed fixtures would be a picture of a different
graph — green, and useless as a comparison. Both capture directories and the review page are
gitignored, for the reason §12 already gives.

---

## 17. What `T-216` built, and what is left over

`T-216` is the remediation the comparison in §16 produced (D-196): six clauses in a stated
order, one of them carrying a decision. **It moved no card.** The gate reads the same
7 placed / 1 counted at 2852×1688, 2 / 6 at 1440×900 and 1 / 7 at 1280×720, with every
geometry clause still zero — and it asserts one clause more than it did.

### R1 — a mark's size is a function of the field, and of nothing else

The decision D-196 left open, and neither half of it turned out the way D-196 assumed. Both
halves are mechanical facts about `scaleSize` in `sigma@4.0.0-beta.5`, which computes
`size / zoomToSizeRatioFunction(ratio)` and then, **only** under
`itemSizesReference: "positions"`, multiplies by `cameraRatio * graphToViewportRatio`:

1. **Clamping the ratio function could not have fixed this.** That function is handed the
   camera's ratio and nothing else, and the term that made a wider window draw bigger marks
   is the *framing* — pixels per graph unit — which sits outside it. No clamp on a function
   that cannot see the field can cancel the field. So the choice recorded as open was open
   in name only: `"screen"` is the one mechanism that removes the term.
2. **`"screen"` does not freeze size under zoom**, which is what D-196 expected it to do and
   why it expected D-122's zoom rule to retire. The division by
   `zoomToSizeRatioFunction` happens in *both* modes, so a mark still grows as
   `1 / sqrt(ratio)` as the camera comes in. The two modes differ by exactly one factor —
   the field's pixels per graph unit — and by nothing else.

So D-122's zoom rule survives, and what `T-216` does to it is re-express it (R2 below)
rather than delete it. And the viewport scale that `"screen"` leaves out is not missing: §3
already specifies it in words — *"Mark size scales with the viewport; the ratios do not"* —
so it moves into the one style table, where it can be read and tested:

| Constant | Value | What it is |
|---|---|---|
| `MAP_SIZE_SETTINGS.itemSizesReference` | `"screen"` | the decision: a size is pixels, with no framing term |
| `MAP_SIZE_SETTINGS.minEdgeThickness` | 0.75 | below the thinnest thickness the table declares |
| `MAP_FIELD_REFERENCE_WIDTH` | 1280 px | the field the mark sizes are stated at |
| `MAP_MARK_FIELD_SCALE` | 0.675 | the mockup's 1.35, halved: Sigma's `size` is a radius |
| `MAP_EDGE_FIELD_SCALE` | 0.62 | the mockup's own correction on `EDGE_VOCABULARY_MARK` |
| `MAP_EDGE_FIELD_THICKEN_WIDTH` | 1724 px | `max(1, MARK × 0.55)`, reduced to one threshold |

`minEdgeThickness` is a second finding rather than a tidy-up. Sigma's floor is 1.7 px, and
after `edgeFieldScale` the table's own thicknesses at the reference width are **1.36 px**
for a canonical edge and **0.87 px** for a library-synthetic one — so the default floor
would have clamped the thin one up into the thick one's neighbourhood and silently deleted
the vocabulary distinction `mapStyle.test.ts` asserts the *constants* preserve. The floor
is kept, below the table's smallest, because it still has a job: an edge on a camera zoomed
far out must not vanish.

What that draws, as arithmetic rather than as a picture — the approved capture's own
numbers, asserted in `mapStyle.test.ts`:

| Field width | Source circle | Derived diamond | Canonical edge | Library-synthetic edge |
|---|---|---|---|---|
| 1280 px | 12 px across | 15 px | 1.36 px | 0.87 px |
| 1440 px | 14 px | 17 px | 1.36 px | 0.87 px |
| 2852 px | 27 px | 33 px | 2.26 px | 1.44 px |

**One consequence outside the composition, recorded because it is a real cost.** A mark this
size is a smaller pointer target than a framing-scaled one, and the browser gate's own
mark-hunting sweep felt it first: `findMark` moves the pointer over a grid of the stage until
the route says what is under it, and over the committed **seven-node** fixtures — a tiny
extent framed into a whole field, so the marks used to be enormous — a 24 px grid of the
middle of the stage stopped hitting anything at all. The sweep's step and budget are now a
function of the size the table actually draws. The marks themselves are the approved
composition's own size, so this is the reference's target size rather than a new one, and the
pointer path remains an enhancement over a DOM path where every mark is also a row (ADR 0005
invariant 13) — but Sigma's `nodePickingPadding` is 0, so what a reader aims at is the mark
and nothing more.

### R2 — the label ration, re-measured and re-expressed

R1 was the root cause, so the ration was re-measured after it rather than tuned before it,
and what it needed was the **opposite** of what §16's picture suggested. With marks no longer
inflated by the framing, `labelRenderedSizeThreshold: 14` silenced the overview completely:
the largest mark on a 1440 px field is 8.3 px by `scaleSize`'s reckoning, so nothing could
claim an automatic label at rest at any viewport the tier table names.

The threshold is now **6**, and the number is derived rather than tried. It has to sit below
the *smallest* mark any field draws at rest — `NODE_PROVENANCE_MARK`'s 9, floored at
`MAP_MARK_FIELD_SCALE`, is 6.1 px — because `NODE_PROVENANCE_MARK` gives its four shapes
four different radii on purpose: each shape encloses a different area, and the radii are
what make the four read as the same weight (ADR 0005 invariant 15 — *the sizes are not a
ranking*). A threshold above the smallest of them would have silenced a **circle** while a
diamond in the same cell spoke, which turns a density rule into a statement about provenance
that no field makes. `labelPolicy.test.ts` asserts exactly that relation, against
`markFieldScale`, so the two cannot drift apart.

The rationing therefore moves entirely to Sigma's grid, which was always the other half of
D-122: `labelGridCellSize` is **560** (from 180), one automatic label per cell of the
viewport, biggest mark in the cell wins. "Zoom in and it speaks" is unchanged and is the
grid's own: the budget per cell is `ceil(labelDensity / ratio²)`, so one press of zoom-in
takes it from one to three while the viewport culls the cells that left the screen.

Measured on the running build over the real library, counted on the captures:

| | Approved | This build |
|---|---|---|
| Automatic labels at 2852×1688 | 8 over 86 marks | **10 over 86 marks** |
| Automatic labels at 1440×900 | 5 | **5** |

### R5 — the quiet Explore field, implemented where a renderer can reach it

§15 recorded `--edge-faint` as `T-214`'s one unimplemented clause: §6 proposes it for "the
quiet Explore field", Explore's edges are WebGL, and a canvas cannot read a custom property.
R5 closes it with `MAP_QUIET_EDGE_OPACITY` — **0.32** — in the one style table, and it is a
third level rather than a reuse of the second:

| An edge, in the state a reader meets it | Opacity |
|---|---|
| `normal`, with something focused — `MAP_DIMMED_EDGE_OPACITY` | 0.25 |
| `normal`, with nothing focused — `MAP_QUIET_EDGE_OPACITY` | 0.32 |
| on the active path — `EDGE_INTERACTION.selected` | 1 |

The approved capture draws its edges at 20 % white on the dark ground and 18 % black on the
light one, which is about this weight; unlike a grey line, a provenance hue at this opacity
still says which of the three provenances the relation has, so nothing that ADR 0005
invariant 9 requires is traded for the quiet. **Marks are deliberately not quieted with
them**: ADR 0006 clause 3 has marks and structure dominating with text on demand, so
quieting both would produce a grey picture rather than a quiet one.

### R3 — the `compact` tier's chips

Three surfaces, and each of the three is the finding §16 stated rather than a redesign:

- **The search rail is closed to its trigger below the `full` tier.** It used to decide that
  for itself as `focus === null`; the route decides it now, because SPEC §5 gives that tier a
  search "closed to its trigger" and only the route measures the field. An *unmeasured* field
  counts as wide — `orbitTier(0)` is `stack`, and a rail that mounted closed on every first
  paint would put D-130's own opening step behind a click at every viewport.
- **The filters fold to their trigger**, at every tier: SPEC §2 gives Explore "counts
  top-end" and no filter controls on the stage at all, and both approved Explore captures
  draw that corner as a two-line chip. A disclosure and not a `max-block-size`, because a
  folded panel here states what it holds — the summary says how many filters are applied, so
  the one thing a reader must not lose is on screen either way.
- **The account folds to its two headline numbers.** §16's finding was that this surface "is
  not a disclosure at all"; it is one now, its summary reads *86 nodes · 118 edges*, and the
  five-row account is one press away. D-129 is intact and this is where to check it rather
  than take it on trust: the surface still precedes the stage, the counts a test or a screen
  reader reads are attributes on the **section** — the part a folded disclosure never hides —
  and it opens itself whenever the picture is not being drawn, which is the case D-129 exists
  for.

That took the counts float from 261 px to 139 px at 1440×900 and moved no card.

### R4 — Explore mounts no drawer

The judgement D-196 asked for either way, recorded: **it goes.** `T-212` kept both panels
mounted on the argument that a panel which disappears cannot say that nothing is selected,
and three things outweigh it. ADR 0006 clause 4 allows one primary drawer to open *on
demand*; SPEC §2 gives Explore four surfaces and none of them is a drawer, and both approved
Explore captures leave that corner empty; and the sentence was never this drawer's only home
— `MapSearchRail`'s focus row says *"Nothing is focused. Choose a result to focus it."* on
the one surface SPEC §2 does give Explore, which is also the step D-130's journey is on while
nothing is selected. What settled it is the share R6 made the gate measure: two collapsed
panels saying "nothing focused" are 4.5 % of an 844 px field, and the approved `compact`
composition spends 10.3 % on all of its chrome together.

### R6 — the clause the gate gained, and the re-run

`browser/composition.ts` reports one number more: `chromeShare`, the union of the floating
chrome's rectangles clipped to the field, over the field's area. A **union**, because two
surfaces that overlap cover one region once and a sum would report more than the whole field.
`coveredShare` is that arithmetic, and `capture_mockups.ts` calls the same function over the
approved mockups' own `.float` and `.drawer` surfaces — so the bound the gate holds this
build to is read off the reference by the instrument that measures the build, and prints
beside every reference capture it writes.

| Tier | Approved Explore | Approved Focus | This build, worst | Bound asserted |
|---|---|---|---|---|
| `full` (2852×1688) | 2.7 % | 19.8 % | 11.9 % | **20 %** |
| `compact` (1440×900) | 10.3 % | 6.4 % | 27.3 % | **30 %** |
| `stack` (390×844) | — | 8.8 % | 0 % | **10 %** |

### The differences that remain, measured

Recorded here for the acceptance rather than fixed, on the same terms §16's three were.
Items 1–4 are `T-216`'s; items 5 and 6 are D-203's, and both are consequences of closing
audit findings rather than new choices about the composition.

1. **The `compact` bound is a ratchet, not the reference's own share.** This build spends
   22.7 % of a 1440×900 field on chrome in Focus and 27.3 % of a 1280×720 one, against the
   reference's 10.3 %, and the gap is not slack: at that tier the drawer floats *over* the
   field instead of taking a slice out of it, and the chrome's rectangles are what
   `placeOrbit` refuses cards against — so the share and the card counts are one number seen
   twice. Measured, not assumed: bounding those surfaces to 14.4 % of the field placed
   **three** cards at 1440×900 where §14 records two. `T-216` requires the recorded numbers
   not to change, so the trade is stated instead of taken: **the reference's 10.3 % costs the
   2 / 6 this gate holds.**
2. **Explore's search float is not the reference's one-line chip.** 420×237 at 1440×900
   against 420×70, because it carries two things the mockup does not draw at all: the
   sentence that says the marks are one view of a list, and the outline's own trigger, which
   SPEC §7 places in this drawer's panel list. Both are content rather than decoration.
3. **Ten automatic labels at the review viewport where the reference draws eight**, and two
   of the ten sit close enough to read as a pair. The mockup rejects a label that would land
   near another or on a mark (§3); production has Sigma's grid and no second overlap test,
   and adding one would be a second label policy beside `labelPolicy.ts`.
4. **In Focus the unrelated topology is drawn at the camera's framing, not the graph's.**
   D-146 frames the camera on the focus, so the background marks are larger and softer than
   the reference's, which draws the whole graph small. Unchanged by `T-216` and half the size
   it was before it: the framing is a zoom, and a zoom is the one thing that is still allowed
   to change a mark's size.

5. **The focused card is 260 px tall at `compact`, where it drew 192 px.** D-203 enforced
   the reservation `placeOrbit` computes — `MapOrbit` wrote only each card's *width* onto the
   element, so the heights were upper bounds nothing occupied and the placement's whole
   no-overlap guarantee was over boxes no browser had laid out. Enforcing them exposed that
   the `compact` tier's own geometry contradicted §6: `primaryBox` was 300×200 = 60,000 and
   `cardBox` 270×240 = 64,800, so the focused card became the **smaller** of the two, and
   size is the first of the four means §6 gives for saying which card the reader asked for.
   The primary's box was the wrong one — it carries `MAP_STAGE_PRIMARY_CHARS` (200) against a
   neighbour's 110 in a box 11 % wider, and had 8 px of slack over its measured 192 where the
   neighbour's had 34 — so it is 300×260 now. Measured on the real 86-node library at
   1440×900 and 1280×720; **the recorded card counts are unchanged**, and the gate confirms
   them with `X2KNWLDG_BROWSER_REQUIRE_RECORDED=1` over that library. What changed in the
   picture is one card's height at two viewports.
6. **At the `stack` tier the field begins 632 px down the document.** Measured at 390×844 on
   the real library: a 129 px app bar — two rows since the wrap that stopped every route
   scrolling sideways on a phone — then the search float at 275 px and the counts at 168 px,
   above a 360 px stage. SPEC §5's content clause **is** met and is now asserted: no orbit,
   the focus card, and every relation as a row with its direction and hop count, none dropped
   (`MapView.test.tsx`). What §5 does not specify is the *order* of the surrounding surfaces,
   and D-203 improved it only as far as one unambiguous move allowed — search now precedes the
   counts, which is both the reading order and the tab order, and D-129 still holds because
   the counts still precede the stage. Putting the field first would either break D-129 or put
   visual order and tab order back into conflict, which is the defect that move fixed. So the
   number is recorded for a person to accept or refuse rather than traded silently.

### Regenerating

Unchanged from §16's three commands. `capture_mockups.ts` now prints the field and the
chrome share beside each reference capture, which is where the bounds in the table above
come from.

**The captures in `docs/mockups/T-215/captures/` are regenerable output and are gitignored**
(the `.gitignore` note beside them says why: the sources are committed and one run's render
is not). They are therefore *not* the pictures accepted on 2026-09-03 under D-202 any more —
D-203 re-ran the gate over them, so they now show the contrast repair, item 5's card height
and the corrected camera framing. Re-accepting them is the acceptance step D-202 was, and it
is a person's.
