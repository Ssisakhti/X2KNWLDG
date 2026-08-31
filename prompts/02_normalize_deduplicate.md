# Pass 2 — Normalize and deduplicate

Input: all source-grounded units produced for one video.

Tasks:

1. Normalize wording without changing meaning, strength, scope, attribution, or causal direction.
2. Merge true duplicates across overlapping segments.
3. Preserve every occurrence under `source_occurrences` when repeated.
4. Preserve repeated emphasis with `recurrence_count`.
5. Keep related-but-distinct claims separate.
6. Keep separate experiments, populations, baselines, and statistics separate.
7. Give final stable IDs in transcript order.

Return JSON only: `{ "units": [...] }`.

