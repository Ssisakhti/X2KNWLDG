# 0008 — Add a source-level knowledge map above the KU graph

**Status:** Accepted  
**Date:** 2026-09-05  
**Decision ledger:** D-244–D-250  
**Supersedes:** nothing

## Context

The current Knowledge Map is useful for inspecting concepts and atomic knowledge units, but it
does not answer a broader question: how does one whole source relate to another? A video about
harness engineering and a multi-post critique of that video should be separately readable
nodes connected by qualified relationships.

Treating a source as a large KU would erase an important distinction. A source is acquired
evidence with identity, status and artifacts; a readable source-level account is derived from
many KUs; a cross-source relationship is an aggregation whose truth depends on specific KU
pairs. The current library graph emits KU/concept nodes, even though the generic entity
contract already reserves `entity_type = source`.

The design must also admit long-form sources without turning every book chapter into global
graph clutter or claiming support for book ingestion before it exists.

## Decision

1. Add `Sources` as a distinct, addressable mode of the existing Map before Canvas work. The
   existing `Knowledge` mode and its contracts remain unchanged.
2. Emit one source entity per acquired run. A source node is not a KU, and chapters/items/KUs
   stay below it.
3. Add a gated per-run derived `source_knowledge.json`. Every Persian narrative statement
   names supporting KUs and cannot claim a status stronger than its source run.
4. Add a separate, versioned `SourceRelation` record and vocabulary. Every automatic relation
   is derived and contains direction, scope, Persian rationale, supporting KU pairs and input
   digests. Similarity creates candidates, not relationships; chronology or overlap cannot
   establish influence or response.
5. Store accepted cross-source synthesis canonically under `output/synthesis/` and rebuild the
   library/index projection from it. Raw evidence and user workspace state remain separate.
6. Reuse Sigma and the approved Directional Orbit. Only the selected source becomes a rich
   readable HTML card; neighbours stay compact and every returned relationship is available
   in the semantic DOM companion. React Flow remains the Canvas renderer.
7. Model a book as one source node. Its captured parts/chapters form Reader drill-down, not
   Source Map nodes. This decision does not implement or advertise book ingestion.
8. Add dedicated read-only source-graph endpoints and repository methods rather than changing
   the existing KU graph payload.

The executable contract is [SOURCE_MAP_SPEC.md](../SOURCE_MAP_SPEC.md).

## Consequences

- Users can read the knowledge extracted from a selected source without losing graph context.
- Cross-source claims remain inspectable down to exact evidence rather than presenting a
  coarse whole-document verdict.
- Source density scales with acquired sources, not chapters or KUs.
- The model requires two new canonical derived record families and corresponding gates,
  validators, fixtures and staleness handling.
- Automatic comparison must be retrieval-bounded; an all-pairs scan is prohibited.
- The UI gains one Map mode but no new top-level product surface or renderer.
- Books can join later through an adapter without changing the global graph abstraction.

## Rejected alternatives

### Make each source a large KU

Rejected because it conflates evidence identity with synthesis, weakens provenance, and makes
whole-source relationships appear stronger than their supporting passages.

### Put source nodes into the existing KU graph without a distinct mode

Rejected because source, concept and KU scales compete visually and semantically. A mode keeps
the abstraction explicit while preserving shared navigation and identity.

### Render every source as a rich React Flow node

Rejected because the Source Map is an automatic global graph, not an editable flow. Rich nodes
at global density create layout and accessibility problems; one selected overlay satisfies the
reading requirement while Sigma retains topology.

### Treat semantic similarity as an edge

Rejected because retrieval similarity is a candidate signal, not evidence of support,
critique, response or influence.

### Make chapters first-class global nodes

Rejected because long books would dominate the graph. Preserved internal structure belongs in
Reader drill-down and can still lead to KUs and exact evidence.

