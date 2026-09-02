# Pass 4 — Derived synthesis

Input: validated source units and typed relationships.

Using only those inputs, derive useful implications, generalized rules, mental models, diagnostic models, hypotheses, syntheses, and actionable experiments.

Rules:

- Every item must have `source_class: derived`.
- Every item must list valid source-unit IDs under `derived_from`.
- Every item must include a concise `derivation_note`.
- Never phrase derived content as if the speaker explicitly said it.
- Preserve uncertainty and scope conditions.

Return JSON only: `{ "knowledge_units": [...] }`.

Required unit fields (D-110 — this pass stated only the three obligations above and
omitted the four the bundle schema *requires*, so a model reading pass 4 alone emitted
units `apply-bundle` rejects). `kind` must be one of the derived kinds in
`src/x2knwldg/constants.py` (`DERIVED_KINDS`): a derived unit declaring a source kind is
refused as `kind_source_class_mismatch`.

```json
{
  "id": "KU-D-0001",
  "kind": "synthesis",
  "source_class": "derived",
  "content": "...",
  "confidence": 0.7,
  "derived_from": ["KU-000001", "KU-000002"],
  "derivation_note": "Why these units support this, in one sentence."
}
```

A derived unit carries **no** `source` block: it cites units, not the transcript. Adding one
is how a synthesis comes to look like a quotation.

