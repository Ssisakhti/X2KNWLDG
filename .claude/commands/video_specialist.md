Answer questions about ingested videos from canonical knowledge with source traceability.

## Source priority

1. Search `output/*/knowledge_units.json` first.
2. Follow typed edges in `relationships.json` and the cumulative `output/library/graph.json`.
3. Inspect `transcript.json` only for exact wording or missing detail.
4. Never answer from `report.md` alone.

Use `x2knwldg search "<query>" --video-id <id>` when useful.

## Rules

- Cite timestamp links for source-grounded answers.
- Label model synthesis as derived and list the source-unit IDs.
- Preserve exact numbers, units, populations, conditions, and caveats.
- If the canonical store and transcript do not contain the answer, say so clearly.
- For multi-video questions, preserve disagreements and scope instead of collapsing them.

