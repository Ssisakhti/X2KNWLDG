# Pass 6 — Source knowledge (the readable brief)

Runs **after** `apply-bundle`, not before it. This pass reads the run's canonical
extraction — `knowledge_units.json`, `relationships.json`, `coverage.json` — and its
standing verdict in `validation.json`, and writes one readable account of the whole
source. A brief produced before those files are canonical is a brief about a draft.

The same pass for every supported medium. A thesis, some points, the units they rest
on and three digests are not statements about video or posts, so there is no
`prompts/twitter/06_...`; run this one over a YouTube run and over an X run alike.

Input: the four canonical files above. Nothing else — not the transcript, not the
capture, not `raw/`.

## What this is, and what it is not

It is **derived knowledge**, exactly like a pass-4 synthesis unit: a reader's account
of the source, not evidence from it. So:

- Every statement names the knowledge units it rests on, in `based_on`, and the list is
  never empty. A statement with no support is an assertion the source never made.
- **Never copy an `evidence_excerpt` into this document.** Excerpts live in the units,
  in the source language, byte for byte. A copy here is evidence that has been through
  a paraphrase nobody can see — and the apply gate refuses the document outright,
  because the schema admits no such field.
- Never quote the speaker or the author as if this were their wording.

## Rules

- Write `content` in **Persian** — the thesis, every key point and every limitation.
  Use Persian technical terminology and add the English term in parentheses when it
  materially improves precision or recognition. Do not add an English equivalent
  mechanically when it adds no value.
- `status` is **copied from `validation.json`**, never decided here. It may be the
  run's own status or a more cautious one; it may never be stronger. A brief over a
  `PARTIAL` run is `PARTIAL`, and it reads like an account of an incomplete source
  rather than a complete one.
- `key_points` holds at least one point, in the order a reader should meet them.
- `limitations_or_tensions` may be `[]`. An empty list is a claim — "none recorded" —
  and it is allowed; omitting the key is not.
- Point ids are `SP-001`, `SP-002`, … and are unique within their list.
- `based_on` names unit ids **this run holds**. A plausible-looking id the run does not
  have is the one failure that would otherwise look checkable and not be.

## `generated_from`

Three SHA-256 digests of the canonical inputs, so a later reader can tell a current
brief from one describing a run that has since changed. **Compute them; do not write a
plausible hex string.** The apply gate recomputes all three and refuses any that
disagrees, so an invented digest fails and a guessed one cannot pass:

```bash
python -c "import json;from pathlib import Path;from x2knwldg.synthesis import canonical_input_digests;print(json.dumps(canonical_input_digests(Path('output/<run-id>')),indent=2))"
```

They are not filled in for you on purpose. If the gate stamped the current digests
itself, a brief generated against yesterday's units would be filed as though it
described today's, and the staleness the field exists to expose would be exactly what
it hid.

## Output

Return JSON only:

```json
{
  "schema_version": "1.0",
  "source_id": "youtube:pqlWNihgdjI",
  "status": "PASS",
  "thesis": {
    "content": "روایت فارسیِ فشرده از مدعای محوری منبع.",
    "based_on": ["KU-000001", "KU-000014"]
  },
  "key_points": [
    {
      "id": "SP-001",
      "content": "نکتهٔ اصلی به فارسی.",
      "based_on": ["KU-000004", "KU-000009"]
    }
  ],
  "limitations_or_tensions": [],
  "generated_from": {
    "knowledge_units_sha256": "...",
    "relationships_sha256": "...",
    "coverage_sha256": "..."
  }
}
```

`generated_at` is the one optional key. Every other top-level key is required, and no
other is accepted — the contract is
`schemas/synthesis/v1/source_knowledge.schema.json`.

## Applying it

```bash
x2knwldg apply-source-knowledge output/<run-id> source_knowledge.json
```

A **gate**: a brief that fails validation is refused rather than written, so
`source_knowledge.json` cannot reach the disk in a state its own validators reject. The
command's exit code is the **run's** standing verdict, not the brief's — writing an
account of a run does not re-grade it, so a brief over a `PARTIAL` run still exits `3`.
