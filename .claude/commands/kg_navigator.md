Navigate the cumulative X2KNWLDG knowledge graph.

1. Rebuild with `x2knwldg rebuild-library` when videos changed.
2. Read `output/library/graph.json`, `concepts.json`, and `videos.json`.
3. Use globally namespaced IDs in the form `<video-id>:<knowledge-unit-id>`.
4. Keep source and derived edges distinguishable.
5. Never invent a relation; return to the source knowledge unit and transcript evidence when needed.
6. Preserve cross-video contradictions rather than choosing a winner without a separate fact-checking pass.

