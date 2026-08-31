# Pass 4 — Derived synthesis

Input: validated source units and typed relationships.

Using only those inputs, derive useful implications, generalized rules, mental models, diagnostic models, hypotheses, syntheses, and actionable experiments.

Rules:

- Every item must have `source_class: derived`.
- Every item must list valid source-unit IDs under `derived_from`.
- Every item must include a concise `derivation_note`.
- Never phrase derived content as if the speaker explicitly said it.
- Preserve uncertainty and scope conditions.

Return JSON only: `{ "units": [...] }`.

