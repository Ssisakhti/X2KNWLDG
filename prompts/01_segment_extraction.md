# Pass 1 — Source-grounded segment extraction

Input: one object from `segments.json`, video metadata, and the canonical knowledge-unit schema.

Extract every meaningful knowledge unit. Do not optimize for novelty, brevity, or a fixed count. Preserve boring-but-important details, qualifiers, scope, limitations, numbers, units, examples, disagreements, uncertainty, and causal direction.

Rules:

- This pass creates `source` units only.
- Do not infer beyond the supplied transcript.
- Keep distinct claims and experiments separate.
- Every unit must use an exact source span within this segment.
- `evidence_excerpt` must be copied from the transcript; never invent a quote.
- Use `evidence_status: unsupported_in_video` when an asserted claim has no support in the segment or adjacent supplied context.
- Return JSON only: `{ "units": [...] }`.

Required unit fields:

```json
{
  "id": "KU-000001",
  "kind": "claim",
  "source_class": "source",
  "content": "...",
  "normalized_statement": "...",
  "importance": "high",
  "confidence": 0.95,
  "source": {
    "video_id": "...",
    "segment_id": "seg_0001",
    "start_sec": 12.3,
    "end_sec": 28.1,
    "evidence_excerpt": "..."
  },
  "attribution": {
    "speaker": null,
    "attribution_type": "direct"
  }
}
```

