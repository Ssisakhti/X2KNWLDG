# T-255 — Source Explore and Source Focus, for approval

**Status: awaiting approval.** Nothing in `web/src/` changed. These pages are a proposal
drawn from the two served source-graph reads, and the decision they are asking for is
whether `T-256` may build this.

Everything here is regenerable from a clone:

```
.venv/bin/python docs/mockups/T-255/gen_data.py     # data.js + layout_input.json
npm --prefix web run mockups:source-layout          # layout.json, production path
npm --prefix web run mockups:source-capture         # captures/, 20 pictures
```

The captures are **gitignored and regenerated** — `.gitignore` already covers
`docs/mockups/*/captures/`. The sources are committed, so a clone reproduces the pictures
rather than trusting a stored PNG.

---

## 1. The decision this task had to make first, and what settled it

The task row asks for "dense/mixed relationships". Claiming it measured that **no committed
data can produce them**:

| Corpus | Sources | Relationships |
|---|---:|---:|
| `tests/source_map_corpus.py` (the `T-254` corpus) | 4 | **1** |
| `source_relations.json` / `.bounded.json` / `.empty.json` | — | 1 / 1 / 0 |
| This machine's `output/` | 1 | 0 |
| **Real discovery over every committed fixture run** | 10 | **3 pairs** |

The last row is the one that closed the question. `candidates.discover` over the ten distinct
sources in `tests/fixtures/runs/` and `tests/fixtures/twitter-runs/` proposes **three unordered
pairs, all `youtube:fixture-*` to `youtube:fixture-*`, through a single shared canonical
concept — and no cross-medium pair at all.** Every committed Twitter run emits `quote` and
`synthesis` units rather than concept kinds, which `tests/source_corpus.py` explains is
deliberate and must not be edited away: inventing analytical claims about real posts "would put
words in real authors' mouths in a file that is committed forever".

So the dense picture is drawn from **openly-labelled synthetic relationships**, and the split
between what is real and what is written is exact:

* **Real** — all ten source nodes (committed fixture runs, real titles, real ids, real media),
  the three gated Persian briefs, the one gated relationship, every relationship id (through
  `ids.source_relation_id`), every endpoint digest (through `candidates.discover`'s own report),
  and every basis knowledge-unit id (read from the run that claims it).
* **Written** — thirteen editorial judgements ("this source critiques that one") and their
  Persian rationales.

The pages disclose this on their face: a dashed **Synthetic relationships** panel on Explore, a
`written` chip on every synthetic pill and companion row, and a `gated` chip on the one that is
not. `gen_data.py` writes nothing outside `docs/mockups/T-255/`.

**The served pictures are separate and are first in the capture list.** `explore-served-*` and
`focus-served-dark` are four nodes and one relationship, entirely real. If the dense pictures
are read as what the product has today, that reading is wrong and these two are the correction.

---

## 2. What the Source Map draws, and what it refuses to

A source node is not a knowledge unit, so two of the Knowledge Map's channels are given up and
two are added. Every added channel is drawn twice — never colour alone (ADR 0001 invariant 10).

| Attribute | Channel | Why |
|---|---|---|
| Provenance | circle + `◆` + word | Every source node is `provenance_class: "source"`; the shape stays what the Knowledge Map already means by it |
| Medium | hue + glyph (`▶` / `✦`) + word | `youtube` / `twitter`, legended |
| Brief state | fill + word | filled = `available`, filled with a dashed halo = `stale`, hollow = `unavailable` |
| Relationship direction | arrowhead | read from the relation's own ends |
| Relationship scope | dash + word | `partial` dashed, `broad` solid. Two values, no third, no percentage |
| Run status | **card badge only, never a mark** | A status is a fact about a run. On the field it would be read as a quality ranking of the source |
| Confidence, score, rank | **nothing** | A relationship carries none (D-247) |
| Freshness | **nothing** | The v1 shapes carry no per-relation staleness (D-274) |

**Every mark is the same size and every edge the same weight.** This is the load-bearing
refusal. `basis_total` is a count, and weighting an edge by it would draw a ranking the records
do not contain. The legend says so in the picture, and the Focus drawer says it again under
*What this Map will not tell you*.

The `kind` hue palette is **absent**, not reused: a source node's `kind` is `null` in every body.

---

## 3. Explore

One circle per acquired source, laid out through the production path — `seedPosition` plus
`forceAtlas2` with `inferSettings` at `MAP_LAYOUT_ITERATIONS`, which is what `MapSession.relax()`
runs. `web/scripts/source_mockup_layout.ts` reads `layout_input.json` rather than
`output/library/graph.json`, so the field reproduces in a clone.

**Counts are stated separately**, because the response states them separately: sources returned,
relationships returned, relationships omitted, sources in the index. An omitted relationship is
one the bound cut *or* one naming a source the index does not hold, and the panel says which
those two are rather than collapsing them.

**An edge whose other end is not on this page is not drawn to an invented mark.** It is counted
and named. The mark arrives with the next page; a phantom would assert a node the client has no
record of.

### Two label rules from T-211, and only one of them survived

* The **grid-cell ration** did not. `labelGridCellSize` rations labels on an 86-node knowledge
  field; over ten sources it refused three labels there was room for. A source's title is the
  one thing its mark cannot say, so every source is a label candidate. Measured: 7 of 10 labelled
  with the ration, **10 of 10** without it.
* The **overlap rule** did, in all three halves: a label may sit on no other label, on no mark,
  and under no floating control. Two seats are tried, below the mark and then above it. What
  still cannot be placed is counted in the panel, never dropped in silence.

### The field is what the chrome leaves

The first draft laid the graph over the whole stage and put a source — the one with no
relationships, which forceAtlas2 flings furthest — **underneath the legend**. `placeOrbit` refuses
a card against the floating chrome rather than against the stage edge, and a field is owed the
same rule. The field is now the largest rectangle no control overlaps, inset further by half a
label width on each side, because *a mark may not land where its own label cannot be drawn* —
without that, the two extreme sources in every layout lost their titles to the stage edge.

---

## 4. Focus — a Directional Orbit around one source

The composition is `T-211`'s, inherited whole: incoming on the side reading starts from,
outgoing opposite, direction read from the focus's own end, the drawer's width subtracted from
the field *before* the centre is centred so the focused card can never be covered
(WCAG 2.2 AA *Focus Not Obscured*).

What is new is the card. One **readable source card** carries the title, the medium, the brief
state, the run status, and the brief itself — thesis, key points, limitations — with **every
narrative element showing the knowledge-unit ids it rests on**, as `KU-…` chips. That is the
phase's acceptance clause drawn rather than described.

The drawer carries one relationship's **basis**: the Persian rationale, every
`from_ku_id → to_ku_id (relation_type)` pair, and `basis_returned` of `basis_total` — both,
always, because a body carrying only the second presents a truncation as the whole basis. Under
it, the **semantic companion list** of every returned relationship with its direction, scope,
basis count and `written`/`gated` mark, so every returned relationship stays text-accessible
whether or not the stage had room for it.

### Three geometry findings, each caught by measurement rather than by looking

1. **The arm must clear the primary card, not merely be a scaled constant.** T-211's arm is
   `(compact ? 250 : 400) * scale`, which works for a knowledge card because a KU card is
   narrower than the arm at every tier. A source card carries a brief and is 440–660 px wide, and
   at the `compact` tier the scaled arm lands **56 px inside the primary's own box** — every
   neighbour was seated on top of the focused card. The arm is now
   `max(scaled, PRIMARY.width / 2 + 32)`. A port inside the card it leaves is a geometric
   impossibility, so it is stated as one.
2. **A pill's seat must be searched against drawn rectangles, not reserved ones.** D-203 settled
   this for the Knowledge Map — 63 of 86 cards lay out taller than their reservation — and a
   source card varies more, because a brief is one to three sections. Against reservations, a
   relation pill sat on a side label at two tiers and on a neighbour card at one. The obstacle
   set is now read from the DOM.
3. **Where a pill lives is part of the composition.** At `full` it rides its own edge. At
   `compact` there is no clear run to ride — short arms, close cards — and the honest answer is
   not a smaller pill: the pill moves into the neighbour card's head and the edge carries
   direction alone. Three compositions, not one scaled three ways.

---

## 5. Honest states

`states.html` draws twelve, each labelled with the machine-readable state it is drawn from:
`available` at `PASS` and at `PARTIAL`; `stale` carried with its reason; `unavailable` with
`no source_knowledge.json`; a truncated graph page with its four counts and its off-page
endpoint; a bounded neighbourhood; a source with no relationships at all; a well-formed id the
index does not hold (`404`); the two omission causes; **no WebGL2**; an empty index; and the
refusals themselves.

The no-WebGL row is the one that matters most here, and its text is the Knowledge Map's shipped
string verbatim: the Source Map's whole reading path — brief, relationships, basis — is DOM, so
none of it depends on the drawing.

---

## 6. Language

The output-language policy governs the **records**, not the chrome, and the mockups draw the
consequence: a brief's narrative is Persian in the canonical document, so **it is Persian in both
locales**. The English UI shows English chrome around a Persian brief. That is not a gap in the
mockup.

`i18n.js` keeps the two piles apart. `SHIPPED` is lifted verbatim from `web/src/i18n/catalog.ts`
in both locales. `PROPOSED` is **54 new keys with no home in the catalogue**, beside the 29 lifted verbatim,, because nothing
renders the Source Map yet; `T-256` must add them before it can render anything.

Persian was measured rather than assumed: `focus-rtl-label` focuses `twitter:2027781710667010262`,
a real committed run whose title is Persian with a ZWNJ, and the dense field carries two
Persian-labelled sources beside Latin ids in every capture.

---

## 7. Measured geometry

Read off the captures by the instrument that measures the build — `browser/composition.ts`'s own
`coveredShare` — on 2026-09-05.

| Capture | Viewport | Field | Chrome share | Composition |
|---|---|---|---:|---|
| `explore-served-dark` | 2852×1688 | 2444×1145 | 3.3 % | 4 nodes, 1 edge, **4 of 4** labelled |
| `explore-dense-dark` | 2852×1688 | 2444×1017 | 4.7 % | 10 nodes, 14 edges, **10 of 10** labelled |
| `explore-dense-fa` | 2852×1688 | 2444×1017 | 4.5 % | identical composition, mirrored |
| `explore-dense-1440` | 1440×900 | 1186×501 | 8.8 % | 8 labelled, **2 counted** |
| `focus-dense-dark` | 2852×1688 | 2852×1632 | 19.8 % | `full`: 7 cards, 6 pills, 3 in / 3 out, 0 omitted |
| `focus-dense-fa` | 2852×1688 | 2852×1632 | 19.7 % | same numbers, mirrored |
| `focus-dense-1440` | 1440×900 | 1440×844 | 4.8 % | `compact`: 5 cards, **2 omitted and counted** |
| `focus-dense-390` | 390×844 | 390×788 | 8.8 % | `stack`: no orbit, **6 omitted and counted**, all in the list |
| `focus-bound` | 2852×1688 | 2852×1632 | 20.6 % | `truncated: true`, 2 in / 1 out |
| `focus-served-dark` | 2852×1688 | 2852×1632 | 19.8 % | 2 cards, 1 pill — what the API answers today |

**Every geometry clause is zero in every capture**: no two drawn surfaces over the same pixels,
nothing clipped by the field, nothing under a floating control, no pill without a clear seat, and
`placed + omitted === returned` at every tier. The capture script refuses a picture while any of
them is violated, which is how three of the four defects above were found.

### The chrome share, and one number to look at

At the `full` tier Focus measures 19.8 %, against T-211's approved **19.8 %** at the same
viewport — the drawer is the same width and the same shape, and the agreement is worth stating
because it was not aimed at. Explore measures 3.3–4.7 % against the approved **2.7 %**, so this
field's chrome is up to two points heavier than the Knowledge Map's: the counts panel carries
four numbers where the Knowledge Map's carries two, and the dense field adds the disclosure. The
one that moved is `explore-dense-1440`: un-folded, the legend and the
disclosure took **19.2 %** of a 1440×900 field and left the graph 299 px of height. At the
`compact` tier both now fold to their triggers, which is SPEC §5's rule for that tier arriving as
a measurement rather than as a style — 8.8 %, and 501 px of field.

---

## 8. Differences from the approved T-211 set, stated rather than fixed

1. **The forceAtlas2 field is uneven, and deliberately not corrected.** The source with no
   relationships is flung far from the other nine, which compresses them into roughly half the
   field. That is what the production layout does with a disconnected node, and faking a
   friendlier layout would make the mockup an argument about a picture the Map never draws. It
   is the first thing to look at and refuse if it is not acceptable.
2. **Explore's chrome is lighter than T-211's** because there are no kind filters and no
   attribute rows to carry — the legend is medium, brief state and scope, and nothing else.
3. **No hop-2 ring.** The neighbourhood endpoint takes a `limit` and **no `depth`** (D-272), so
   there is exactly one ring to draw. The chip tier T-211 built for hop 2 is unused here.
4. **`T-211`'s own generator no longer runs on this machine** — it reads a run that has left
   `output/`. T-255's reads committed fixtures only, which is why its pictures reproduce in a
   clone. Worth fixing for T-211 separately; not fixed here, because editing that directory
   would move the approved Phase 2.1 captures.

---

## 9. What is being asked

1. Do these two compositions read as one product with the Knowledge Map?
2. Is the synthetic-relationship disclosure sufficient, or should the dense pictures be dropped
   in favour of the four-node served field alone?
3. Is the uneven forceAtlas2 field acceptable as an honest picture of the production layout?
4. Are the 54 proposed strings the right vocabulary for `T-256` to add to `catalog.ts`?

Approval is what unblocks `T-256`. Until then no production UI changes — that ordering is
ADR 0006 clause 2, restated for this phase as D-250.
