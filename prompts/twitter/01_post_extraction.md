# Pass 1 (Twitter) — Source-grounded post extraction

Input: one **item** from a `schemas/capture/v1/` capture, the run's
`metadata.json`, and the canonical knowledge-unit schema.

A post is the segment. There is no `segments.json` for a Twitter run and no time
range to cite: the capture's `items` array *is* the segmentation, in root-first
order, and it is sealed.

Extract every meaningful knowledge unit. Do not optimize for novelty, brevity,
or a fixed count. Preserve boring-but-important details, qualifiers, scope,
limitations, numbers, units, examples, disagreements, uncertainty, and causal
direction.

Rules:

- This pass creates `source` units only.
- Do not infer beyond this item's `text.canonical` and the adjacent items
  supplied as context.
- Every unit cites **one post id and one codepoint span** into that post's
  `text.canonical`, plus the excerpt.
- `evidence_excerpt` must equal `text.canonical[start_char:end_char]`
  **exactly** — byte for byte, character for character. Not a paraphrase, not a
  trimmed version, not a normalized one. The validator compares them verbatim.
- `start_char`/`end_char` are **codepoint** offsets, which is what Python string
  indexing natively is. They are not UTF-16 code units: a post containing an
  emoji outside the BMP will slice wrongly under that reading, and D-211
  settled the basis against exactly such a post.
- **Never normalize an excerpt.** Persian text is made of ZWNJ (`U+200C`),
  Persian digits and sometimes NBSP; stripping them produces an excerpt that is
  not its own span and the unit is refused.
- `text.canonical` is the **authored** form, with `t.co` links intact (D-211).
  Do not substitute an expanded URL into an excerpt, and do not treat a `t.co`
  link as if you know where it points unless the item's `text.entities` carries
  the `expanded` value.
- **Never follow a link.** Not a `t.co` link, not an expanded URL, not a quoted
  post. Linked pages are not fetched at any point in this pipeline.
- A post whose `availability.state` is `unavailable` carries no text. Produce
  **no units** from it. It is accounted for as an omission with reason
  `source_unavailable`, which the pipeline states for you.
- A post whose `text.completeness.status` is `known_truncated` has had part of
  its text withheld by the acquiring surface. Extract from what is there and do
  not speculate about the rest; the gap is already recorded as an unresolved
  item.
- `text.completeness.status: unverified` is the **normal** state of a
  single-route read, not a defect and not a reason to hedge every unit.
- A **quote** is a separate cited source (ADR 0007 decision 8), recorded in
  `metadata.external_references`. You may state that this post quotes it. You
  may not state what the quoted post says: its content is not in this run.
- **Metrics are not knowledge.** Like counts and impressions are absent from the
  capture on purpose. Never state one, and never infer reach, popularity or
  consensus from anything.
- Return JSON only: `{ "knowledge_units": [...] }`.

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
    "post_id": "1795393908886712425",
    "start_char": 0,
    "end_char": 22,
    "evidence_excerpt": "..."
  },
  "attribution": {
    "speaker": "<author username of the cited post>",
    "attribution_type": "direct"
  }
}
```

Note what is **not** in `source`: there is no run id. YouTube's `video_id`
guards against a bundle applied to the wrong run; here the guard is stronger and
automatic — the `post_id` has to be an item of this run's capture, which an id
copied from elsewhere cannot satisfy.
