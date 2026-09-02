# ADR 0006 — Separate Explore and Focus compositions for Map visual quality

- **Status:** Accepted
- **Date:** 2026-09-03
- **Decision ledger:** D-150 … D-154 (`KNOWLEDGE_CANVAS_PLAN.md` §19 and
  `PROJECT_MANAGEMENT.md` §6)
- **Extends:** [ADR 0005](0005-knowledge-map-client.md)
- **Supersedes:** none
- **Superseded by:** none

## Context

Phase 2 is functionally complete and its real-browser gate passes. The resulting Map preserves
truth, provenance, selection identity, keyboard access and the Search → Focus → Quick Read
journey. A visual review against the four user-approved references nevertheless rejected the
screen as a product experience.

The problem is compositional, not cosmetic. The current page places controls and status in
normal document flow, so the stage begins far below the route header. The stage then asks one
ForceAtlas composition to be both an overview and a reading surface. Large HTML cards follow
graph coordinates while raw labels remain underneath them; cards, labels and edges compete,
the selected item is not the obvious visual centre, and the next useful item cannot be judged
at a glance. A palette or spacing pass alone cannot repair those relationships.

The references are used for their transferable ideas rather than copied literally:

- the workflow reference contributes a dark, quiet field, compact cards, ports and labelled
  paths;
- the interaction-map reference contributes disciplined routes, sparse annotation and clear
  hierarchy;
- the radial references contribute a definite centre, rings and an editorial composition;
- none of them authorises a fabricated metric, cluster, importance score or quantitative
  radial axis.

## Decision

1. **Insert a visual-quality phase before Canvas work.** Phase 2 remains complete as a
   functional and accessibility milestone. Phase 2.1, epic `T-210`, is a release-quality
   correction and blocks Phase 3 until its own visual gate passes. *(D-150)*
2. **Design before implementation.** `T-211` produces high-fidelity Explore and Focus
   screenshots at the current review viewport, with light/dark and English/Persian behaviour
   stated. No production UI implementation starts until the user approves both compositions.
   *(D-151)*
3. **Give Explore and Focus different compositions over the same graph state.** Explore is a
   quiet, full-graph overview with labels revealed by zoom, hover or selection. Focus is a
   **Directional Orbit**: the selected Knowledge Card is the centre, incoming relations are
   arranged to the left, outgoing relations to the right, and actual hop count determines
   distance from the centre. Active relations have horizontal text pills and visible ports;
   unrelated structure recedes as context. *(D-152)*
4. **Make the Map a viewport workspace.** The graph occupies the usable route viewport.
   Search, filters, status, legend, the semantic related list and Quick Read become compact
   floating controls or bounded drawers rather than sections that push the stage down the
   document. Search → Focus → Quick Read remains usable without page scrolling on the review
   viewport. DOM order and keyboard access remain truthful even when CSS places a surface as
   an overlay. *(D-153)*
5. **Adopt an editorial visual system and a screenshot gate.** Use a neutral charcoal field,
   neutral readable cards, one strong active accent, type scale and spacing with an explicit
   hierarchy, and provenance encoded by shape/border/badge as well as colour. Cards may not be
   clipped or overlap; graph labels may not render under cards; active relation labels stay
   horizontal. `T-215` compares real browser captures with the approved mockups at actual
   viewports in dark/light, English/Persian and reduced-motion modes. *(D-154)*

The Directional Orbit is presentation state only. It consumes the existing `GraphSnapshot`,
`mapLink`, selection, neighbourhood and card formatter; it does not create another graph
store, identity, endpoint or canonical field. Returning to Explore deterministically restores
the overview presentation without changing the selected entity or URL semantics.

## Rejected alternatives

### Keep ForceAtlas fixed and adjust only colour, spacing and shadows

Rejected because the primary failure is hierarchy and spatial composition. The selected card,
neighbour cards and overview labels would still compete in one coordinate system.

### Turn every graph node into an HTML card

Rejected because it recreates a heavy node renderer at graph scale, obscures topology and
reopens R20. Explore stays WebGL-first; richer cards are bounded to the Focus composition and
semantic drawers.

### Put a large inspector permanently beside the graph

Rejected because it reduces the stage before the user asks to read and leaves multiple panels
competing for attention. One primary drawer may open on demand over the workspace.

### Copy the radial references as a radar or cluster chart

Rejected because the project has no defensible magnitude, importance or cluster value for
those axes. Only direction, hop, relation vocabulary, provenance, source and identity may
determine the composition.

## Consequences

- The existing functional Phase 2 work and its tests remain valid; visual acceptance is a new
  gate rather than a rewritten history.
- The Focus view may position a bounded presentation of the neighbourhood independently of
  ForceAtlas while retaining the same records and selection identity.
- Some current on-stage placement code may become Explore-only or be retired after the new
  composition is proven. That decision belongs to implementation after `T-211`, not to the
  mockup task.
- Visual QA becomes a release criterion: a green component or browser suite is necessary but
  no longer sufficient for the Map.
- Phase 3 cannot begin until `T-210` is complete.

## Validation

The gate requires approved Explore and Focus mockups first, then real-browser captures proving:

- the focused card is the unmistakable centre;
- incoming, outgoing and hop distance remain truthful;
- no card or important text is clipped, and no two cards overlap;
- labels and edges do not run through readable card content;
- unrelated structure does not compete with the active reading path;
- Search, Focus and Quick Read work without document scrolling at the review viewport;
- the same hierarchy survives dark/light, English/Persian, keyboard and reduced motion;
- the existing semantic DOM path, honest states, URL history and WebGL lifecycle still pass.
