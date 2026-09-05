# Pass 7 — Cross-source relations

Runs over **two whole sources at a time**, after each has a validated extraction. It
produces `output/synthesis/source_relations.json`: qualified, directional relationships
between sources, each resting on named knowledge-unit pairs.

The same pass for every supported medium, and the interesting case is the cross-medium
one — a thread that critiques a video is the shape this exists for.

## Do not start from the sources

Start from the candidate list:

```bash
x2knwldg source-candidates --output output
```

That command is deterministic and bounded. It reports which ordered pairs are worth
comparing and **why** — a resolved explicit reference, a shared canonical concept — plus
`considered`, `omitted`, `bound` and `pairs_in_corpus`.

**Compare only the pairs it lists.** A relation for a pair it did not propose is refused
by the apply gate, which re-runs discovery and checks. That is not bureaucracy: comparing
every pair is quadratic in the corpus and each comparison is a pass over two whole unit
sets, so an unbounded walk is the failure risk R28 names.

Copy `considered`, `omitted`, `bound` and `pairs_in_corpus` into the document's
`candidates` block **verbatim**. The gate recomputes them, so a number that flatters the
run fails rather than passing.

## A candidate is not a relationship

This is the rule the whole pass turns on.

- A **shared concept** means the two sources talk about the same thing. It does not mean
  one supports, critiques, extends or responds to the other. Two sources can share every
  concept in a field and stand in no relation at all.
- **Chronology is not influence.** That one source is older does not make the newer one a
  response to it.
- **Similarity is not agreement.** Retrieval put the pair in front of you; that is all it
  did, and no number from discovery may reach the record.

Emitting **no relation** is a correct and common outcome. It is not a failed pass, and
the candidate counts are what make an empty result readable.

## What a relation must carry

```json
{
  "id": "SR-…",
  "from_source_id": "twitter:1795393908886712425",
  "to_source_id": "youtube:pqlWNihgdjI",
  "relation_type": "critiques",
  "scope": "partial",
  "provenance_class": "derived",
  "rationale": "این رشته‌توییت سه ادعای مشخص ویدیو را نقد می‌کند.",
  "basis": [
    { "from_ku_id": "KU-000006", "to_ku_id": "KU-000021", "relation_type": "contradicts" }
  ],
  "generated_from": {
    "from_run_digest": "…",
    "to_run_digest": "…"
  }
}
```

**`relation_type`** is one of exactly eight, and they are **not** the knowledge-unit
relation types: `explicitly_references`, `responds_to`, `critiques`, `supports`,
`contradicts`, `extends`, `applies`, `overlaps_with`. A unit-level type such as `causes`
is refused here — `supports` at unit level is a claim about two sentences, and at source
level it is an aggregation over many.

**`scope`** is `partial` or `broad`. It qualifies how much of the two sources the basis
supports. It is not a percentage and there is no third value.

**`basis`** is the whole point. Each entry names one unit of the **from** source, one unit
of the **to** source, and how they relate at unit level. Both endpoints' runs use ids like
`KU-000001`, so a unit id that looks right can still belong to the wrong source — the gate
checks ownership, and that check is the reason the relation is inspectable at all.

**Keep contrary grounds.** If three pairs agree and one disagrees, list all four and say
so in the rationale, or emit a narrower relation, or emit two. Never drop the one that
disagrees to make the relation read cleanly. A relation whose grounds *all* point the
other way — a `supports` resting entirely on `contradicts` pairs — is refused as an
inversion.

**`rationale`** is Persian, under the permanent output-language policy, and may not claim
more than `scope` and `basis` carry. Use Persian technical terminology, adding the English
term in parentheses where it materially improves precision.

**There is no `confidence` field**, and adding one is refused. No number here was measured.

## `explicitly_references` needs corroboration

Claim it only when the from-source's canonical artifacts actually record the reference —
today that means a capture's `external_references` naming an id the to-source holds. The
gate checks this against discovery and refuses an uncorroborated claim. A source that
merely discusses the same subject *references nothing*.

It is still `derived` provenance, like every other automatic relation: the cited link may
be source-grounded, but promoting it into a source-to-source relationship is an
aggregation the sources themselves never made.

## The id and the digests

`id` is a digest of four fields — the two endpoints in order, the type and the scope — and
the gate recomputes it. Compute it rather than inventing one:

```bash
python -c "from x2knwldg.ids import source_relation_id;print(source_relation_id('<from>','<to>','<type>','<scope>'))"
```

Two relations between the same pair are allowed when their type or scope differs; they get
different ids by construction. Basis and rationale are **not** part of the id, so a later
pass that finds a fourth ground updates this record rather than minting a second.

`generated_from` records each endpoint's run digest, so a conclusion about two runs that
have since changed is detectable rather than silently trusted:

```bash
python -c "from pathlib import Path;from x2knwldg.synthesis import run_digest;print(run_digest(Path('output/<run-id>')))"
```

## Output and applying

Return JSON only:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-01-01T00:00:00+00:00",
  "candidates": { "considered": 2, "omitted": 0, "bound": 25, "pairs_in_corpus": 2 },
  "relations": []
}
```

```bash
x2knwldg apply-source-relations source_relations.json --output output
```

A **gate**: endpoints, ids, basis ownership, direction, corroboration, digests and the
candidate counts are all checked before anything is written, and the previous synthesis is
left exactly as it was if any of them fails. The contract is
`schemas/synthesis/v1/source_relations.schema.json`.
