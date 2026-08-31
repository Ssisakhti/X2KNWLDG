# Pass 3 — Typed relationships

Input: validated, deduplicated source-grounded units.

Create directed edges only when supported by the units. Use only the allowed relation types in `src/x2knwldg/constants.py`. Edges must reference knowledge-unit IDs, not free text.

For inferred edges, set `source_class` to `derived`. Never reverse a causal direction. Do not create vague `related_to` edges when a more precise relation is supported.

Return JSON only:

```json
{
  "relationships": [
    {
      "from": "KU-000001",
      "relation": "supports",
      "to": "KU-000002",
      "confidence": 0.92,
      "source_class": "derived"
    }
  ]
}
```

