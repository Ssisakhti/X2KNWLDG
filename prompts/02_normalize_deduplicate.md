# Pass 2 — Normalize and deduplicate

Input: all source-grounded units produced for one video.

Tasks:

1. Normalize wording in Persian without changing meaning, strength, scope, attribution, or
   causal direction. Use Persian technical terms and add the English term in parentheses when
   it materially improves precision or recognition.
2. Merge true duplicates across overlapping segments.
3. Preserve every occurrence under `source_occurrences` when repeated.
4. Preserve repeated emphasis with `recurrence_count`.
5. Keep related-but-distinct claims separate.
6. Keep separate experiments, populations, baselines, and statistics separate.
7. Give final stable IDs in transcript order.

Keep every `evidence_excerpt` verbatim in its source language and keep source titles and
metadata in their original form. Do not translate schema keys, enum values, IDs, relation
types, omission codes, or status values.

Return JSON only: `{ "knowledge_units": [...] }`.
