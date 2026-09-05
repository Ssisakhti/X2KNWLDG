# X2KNWLDG Agent Workflow

This workflow is vendor-neutral. ChatGPT/Codex, Claude, or any MCP-capable agent must use the same canonical files and validators.

**Two source types are implemented.** Sections 1–5 are the **YouTube** path. The
**Twitter/X** path follows and uses a different acquisition step and citation unit,
not a second pipeline: `apply-bundle`, `validate`, and `finalize` dispatch on the
source type declared by the run (D-240, D-243). Medium/articles, books, PDFs/EPUBs,
and arbitrary web pages are roadmap items only. Do not ingest them until they have a
capture contract, extraction rules, an adapter, a row in `artifacts.MEDIUM_PROFILES`,
fixtures, and validators.

## Permanent output-language policy

This policy applies to every model pass, supported source type, report, graph label,
and vault note. It is part of the canonical workflow, not a per-run preference:

- Write `content`, `normalized_statement`, summaries, analysis, `derivation_note`, and
  human-readable coverage notes in **Persian**.
- Express technical terms in Persian and include the English term in parentheses when
  it materially improves precision or recognition. Do not add an English equivalent
  mechanically when it adds no value.
- Preserve every `evidence_excerpt` exactly in the source language. Never translate,
  normalize, or rewrite evidence.
- Preserve source titles and acquisition metadata in their original form. Do not
  translate a title, author/channel name, URL, language tag, or other source fact.
- Keep schema keys, IDs, enum values, relationship types, omission codes, and status
  values in their canonical machine-readable form. The Persian rule governs narrative
  knowledge, not the wire format.

**What a validator checks, and what it does not.** The policy applies to every field listed
above; the validators reach two of them. `validators._narrative_script_error` refuses text
containing no Perso-Arabic character at all, and it has exactly two call sites: a source
brief's statement `content`, in `validate_source_knowledge`, and a source relation's
`rationale`, in `validate_source_relations`. Everything else — a knowledge unit's `content`
and `normalized_statement`, a `derivation_note`, an omission's `note`, every human-readable
coverage note — is policy that no exit code enforces. That is a statement about the guards,
not a licence: an English extraction is a policy violation whether or not a validator
notices, and the primary extraction output is precisely where nothing does.

Even where it runs, it is a **script** check and not a language check. Text with no
Perso-Arabic character cannot be the Persian this policy requires, and that is the whole of
what a refusal proves — it says nothing about whether Perso-Arabic text is good Persian, and
a check that claimed otherwise would be inventing a verdict. Mixed text passes, which it
must: an English technical term in parentheses is the spelling this policy asks for.

## 1. Acquire the transcript

Preferred order:

1. Timestamped English captions when YouTube exposes them. `process` requests `en`
   by default, including YouTube's translated automatic track when that is the English
   track the service exposes. Pass one or more `--preferred-language` flags to replace
   this default deliberately. Never fall back silently to an unrequested language.
2. User-provided `VTT`, `SRT`, or timestamped `JSON`.
3. Timestamped `TXT/MD` using `[HH:MM:SS - HH:MM:SS]` headers.

Whisper and WhisperX are disabled. Never silently fall back to audio transcription.

Run either:

```bash
x2knwldg process "<youtube-url>"
x2knwldg import-transcript "<file>" --video-id "<id>" --video-url "<url>"
```

If native captions are unavailable, `process` creates `inbox/<video-id>/README.md` and exits `5` (`TRANSCRIPT_REQUIRED`). Ask the user to put a timestamped transcript there.

## 2. Inspect canonical inputs

Use only these files as extraction inputs:

- `output/<video-id>/metadata.json`
- `output/<video-id>/transcript.json`
- `output/<video-id>/segments.json`

Some captions in `transcript.json` carry `"non_speech": true` with `"text": ""` — a cue
like `[music]` whose text cleaned away. They keep their timing on purpose, because dropping
them shortens the run's reported duration and the coverage windows with it. Treat them as
data, not as a gap: never quote one, never extract from one, and never leave one out when
counting captions or computing a duration.

The file under `raw/` is immutable evidence. Never edit it.

## 3. Run the model passes

Follow the prompt files in this order:

1. `prompts/01_segment_extraction.md`
2. `prompts/02_normalize_deduplicate.md`
3. `prompts/03_relationships.md`
4. `prompts/04_derived_synthesis.md`
5. `prompts/05_coverage_audit.md`

Do not summarize before these passes finish. Store intermediate results under `output/<video-id>/work/`.

## 4. Coverage repair

When the coverage audit finds missing meaningful content:

1. Create the missing source-grounded units.
2. Normalize and deduplicate again.
3. Re-audit only the affected windows.
4. Stop after three total audit attempts. `MAX_AUDIT_ATTEMPTS` in `src/x2knwldg/constants.py` is the number, and the coverage document must report how many it took: `audit_attempts` is **required**, an integer, and never above the cap. The validator accepts `0` only while the document does not claim `PASS`, which is the honest state of a scaffolded, never-audited run.
5. If important content remains unresolved, use `PARTIAL`, never `PASS`.

A window's audit is checked against the window (D-164), so three rules bind:

- `window_size_sec` is required whenever coverage claims `PASS`, and **no window
  may be wider than it**. Subdividing a scaffolded window is fine — auditing at a
  finer granularity is honest work. Merging windows is not.
- A `covered` window must name at least one `source` knowledge unit whose
  evidence **overlaps that window's own span**, or account for what it left out
  in `omitted_items`. A `derived` unit carries no timing and can never anchor a
  window.
- `summary` is **optional in the bundle**, and derived from the windows wherever
  it appears. `apply-bundle` recomputes it —
  `artifacts._carry_coverage_scaffold_forward` replaces whatever the bundle
  stated, and the Twitter path does the same — so there is nothing to gain by
  writing one. Outside the gate the rule is stricter rather than absent: a
  `coverage.json` edited by hand into disagreement with its own windows is
  `coverage_summary_disagrees_with_windows` from `validate`, compared field by
  field, not a silent correction (D-164). Omit it.

## 5. Apply and finalize

Assemble `extraction_bundle.json` using `schemas/extraction_bundle.schema.json`. It has
three **required** keys and one **optional** one, and the schema sets
`additionalProperties: false`, so no other top-level key is accepted. All four are listed
here: this table used to omit `extraction_metadata` while saying "exactly three… no other
top-level key is accepted", so an agent following it silently dropped the provenance record
the pipeline does consume (D-189).

The schema describes **both** implemented media and branches between them on the coverage
document it is handed — `windows` for the run below, `items` for §T5 — because a bundle
carries no `source_type` of its own. Validating against it is optional and always has been:
`jsonschema` is a `dev` extra and the package applies no JSON Schema at runtime, so
`apply-bundle` is the gate that decides, and the schema is what an agent can check itself
against beforehand.

| Bundle key | Required | Comes from | Note |
|---|---|---|---|
| `knowledge_units` | yes | passes 1, 2 and 4 | The **bundle** key is `knowledge_units`. The canonical `knowledge_units.json` file writes the same list under `units`; do not carry that spelling into the bundle (D-073) |
| `relationships` | yes | pass 3 | Required, and refused when missing or misspelled — it used to default silently to `[]` and wipe every relationship the run had (D-169) |
| `coverage` | yes | pass 5 | `audit_attempts` is required; `0` is the honest never-audited state and may not accompany a `PASS` (§4.4). See the three window rules in §4 |
| `extraction_metadata` | no | the run itself | An object describing what produced the extraction. `apply-bundle` copies it into `metadata.extraction`; a non-object is refused rather than dropped (D-169). All three committed fixtures carry one |

Then run:

```bash
x2knwldg apply-bundle output/<video-id> extraction_bundle.json
x2knwldg validate output/<video-id>
x2knwldg finalize output/<video-id>
```

Three commands, and `validate` is the middle one because `CLAUDE.md` and `AGENTS.md` both
require validation **before finalization** and before any claim of success. This block
listed two for long enough that §T5 pointed back at it saying "the same three commands" —
`README.md` and §T5 were right and this was the one out of step.

Completion may be claimed only when validation and coverage both report `PASS` — which is
exactly **exit code `0`**. `PARTIAL` exits `3` and `FAIL` exits `4`: both are real results to
report, and neither is completion. The full table is in
[`README.md` § Exit codes](README.md#exit-codes), and `x2knwldg --help` prints it.

Three commands operate over the whole project rather than one run, and none of them belongs
to a pass above: `x2knwldg status` lists every local run and its standing verdict,
`x2knwldg search "<query>"` searches canonical knowledge first and then exact captions, and
`x2knwldg rebuild-library` rebuilds the cumulative graph and concept registry. Every
subcommand and flag is in [`README.md` § Command reference](README.md#command-reference);
these three were reachable from the CLI and named in no document at all.

---

# Twitter/X posts and self-threads

Everything above is the YouTube path and is unchanged. This medium reaches the same
end — a validated run, a `graph.json`, a `report.md`, a vault note and a place in the
library — through the same commands, because the pipeline dispatches on what a run
declares rather than branching per medium (D-240). What differs is the first step and
what a claim cites.

## T1. Acquire the post

```bash
x2knwldg capture "<post-id-or-url>" --via-tunnel --output output
x2knwldg capture "<last-post-id>" --thread --via-tunnel --output output
```

**Ask for the thread's LAST post, not its first.** A self-thread is provably complete
only upward: following `reply_to` terminates at a parent-less root and every hop is
checkable. Downward is not available on any credential-free route — `x thread` and
`x replies` return the anchor alone — so an ingestion anchored at the root would report
success while dropping most of the thread. Anchoring at the root is therefore a warning
and a `PARTIAL`, never a silent success (D-206). Completeness is recorded as *"complete
to root from a user-asserted terminal anchor"*: the system cannot verify that the post
you named is the last one, so a thread continued later will be short and nothing will
say so.

`--via-tunnel` / `--no-tunnel` is not a preference and has no default. The capture
records what was stated, so the operator states it; `X2KNWLDG_VIA_TUNNEL=1/0` works too.

`capture` leaves an initialized **run**, not just a file: `capture.json`, the preserved
provider bytes under `raw/`, a `metadata.json` and an item-based `coverage.json`
scaffolded to `PARTIAL` with `coverage_not_audited` against every item. That last part
is the honest state of a run nothing has extracted yet, and it is why `capture`
reporting `PASS` for its *coverage* still leaves the run at `PARTIAL`.

Re-running `capture` for a post that already has one **refuses**. Raw evidence and
captures are never overwritten — not by a retry, not by a provider that has since
changed its output, not by a dropped tunnel.

## T2. Inspect canonical inputs

Use only these as extraction inputs:

- `output/<post-id>/metadata.json`
- `output/<post-id>/capture.json`

There is no `transcript.json` and no `segments.json`, and that is not a gap: **a post is
the segment**, so no segmentation step exists and none should be invented. Everything
under `raw/` is immutable evidence. Never edit it — `validate` recomputes its digest and
re-derives the item set from those bytes, so an edited file is a `FAIL`.

The canonical text is `items[].text.canonical`, the **authored** form (D-211): `t.co`
links as written, Persian digits, ZWNJ and NBSP all preserved. Do not normalize it, and
do not expand a `t.co` link — the expansion is not in the text and pairing the two is
not safe on this route (D-218).

## T3. Run the model passes

```
1. prompts/twitter/01_post_extraction.md
2. prompts/02_normalize_deduplicate.md
3. prompts/03_relationships.md
4. prompts/04_derived_synthesis.md
5. prompts/twitter/05_item_coverage_audit.md
```

Two of the five are replaced because they do not survive the change of medium; the other
three do and are reused as they are. Store intermediate results under
`output/<post-id>/work/`.

A source claim cites a **post id and an exact character span**, and the excerpt must be
`text.canonical[start_char:end_char]` **verbatim** — compared byte for byte, not
normalized, because normalizing would discard the joiners a Persian post is made of.
There are no seconds anywhere in this medium: a claim that carries `start_sec` is a
claim in the wrong shape.

## T4. Coverage repair

The same rules and the same three-attempt cap as §4 — they are shared code, not a second
implementation — over **items** rather than time windows. A `covered` item names at least
one `source` unit whose span falls inside that item's own text, or accounts for what it
left out. `PASS` is impossible while any expected item is unaccounted for, and impossible
again over a capture that is not itself `PASS`.

## T5. Apply and finalize

The bundle is the same shape as §5 — same three required keys, same optional
`extraction_metadata`, same refusal of anything else — and differs in **three** places,
all of them consequences of the citation unit rather than three separate rules:

| Where | YouTube (§5) | Here |
|---|---|---|
| `coverage` | `windows`, a walk along a timeline | `items`, a set comparison over the posts the capture included |
| `coverage.basis` | absent | `items`, and imposed from the capture rather than accepted from the bundle |
| a source unit's `source` | `video_id`, `segment_id`, `start_sec`, `end_sec`, `evidence_excerpt` | `post_id`, `start_char`, `end_char`, `evidence_excerpt` |

`window_size_sec` has no counterpart and no entry has a span. This section said "one
difference" while the published schema encoded all three as YouTube-only requirements, so
a bundle the gate accepts was refused by the schema `mcp_server.extraction_schema_resource`
serves as the contract — five refusals for a single post, 41 for a ten-post thread. The
schema now branches; the difference is still worth reading here first.

Then the same three commands:

```bash
x2knwldg apply-bundle output/<post-id> extraction_bundle.json
x2knwldg validate output/<post-id>
x2knwldg finalize output/<post-id>
```

`apply-bundle` is a **gate**: a bundle that fails validation is refused rather than
written, so a run cannot reach the disk in a state its own validators reject. `finalize`
refuses a `FAIL` run before its first write and finalizes a `PARTIAL` one. It writes
`vault/posts/<anchor>.md` with `type: post` frontmatter, and each claim's provenance line
cites the post it came from — not the anchor — as
`[post <id>, characters n–m](https://x.com/i/status/<id>)`.

For both supported source types, the generated `vault/` tree is Obsidian-compatible
plain Markdown: YAML frontmatter, stable note filenames, and wikilinks connect source,
derived, and relationship notes. This is a file-format output, not an Obsidian plugin
or a synchronization step; do not write into a separate user vault without an explicit
request.

## T6. What this medium can and cannot do

Every row was measured on the target environment, not read off a capability table the
provider advertises — its own `x fields tweet` disagreed with measurement in four places.

<!-- twitter-capability-table -->

| Route / capability | Status | What it means |
|---|---|---|
| `xcli_guest` (pinned local `x-cli`; the registry carries tiers 0 and 1, and **tier 1 `guest` is the default and the qualified read**) | **supported, default and only** | The one measured no-payment path. Verified live on the target machine on 2026-09-04, on the `guest` tier: a single post, a Persian post, a ten-post self-thread walked from its last post, and an unavailable id — then again end to end to a vault note (`T-229`). `--via-tunnel` records what the operator **stated**; whether a tunnel carried the request is never measured, which is why the capture stores the statement rather than an inference (D-209) |
| Single public post | **supported** | Canonical text, author, timestamp, language, mention spans |
| Self-thread from its last post | **supported** | Walked upward to a parent-less root, every hop resolved and single-author |
| Self-thread from its root | **`PARTIAL` with a warning** | Downward traversal does not exist on any credential-free route (D-206) |
| Persian / RTL text | **supported** | Authored form preserved byte for byte, joiners included |
| Quote posts | **supported** | The quoting post's own text; the quoted post is a reference, not an ingestion |
| Deleted / protected post (tombstone) | **`FAIL`, named** | The capture states it and the run cannot pass. Nothing is fabricated to fill the gap |
| Edited posts | **representable, never observed** | The contract can carry `edits`; no measured route produces one, so the handling is pinned by a fixture rather than by data (D-222) |
| Mention spans | **supported** | Recorded only for an unambiguous single occurrence |
| URL spans | **not supported on this route** | The provider returns *expanded* URLs that appear nowhere in the authored text, so a span's target would be a guess (D-218). A claim about a link cites the `t.co` text as authored |
| Text completeness | **`unverified`, always** | One route, and no in-band signal for truncation on any measured route. Never reported as `corroborated` |
| Whole reply trees, other authors' replies | **unsupported** | Tier 2. Out of scope for this phase |
| Follower/engagement counts, timelines, search | **unsupported** | Not acquired and not represented |
| FxTwitter / FxEmbed opt-in fallback | **not implemented** (`T-225`) | Would be explicit opt-in only, and would add URL spans and raise completeness to `corroborated`. Nothing is sent to it today |
| Official X oEmbed corroboration | **not implemented** (`T-225`) | Would be corroborative only and could never raise completeness |
| Firefox passive capture / import | **not implemented** (`T-226`) | Would be credential-free and passive. Not selected for this phase (D-243) |

<!-- /twitter-capability-table -->

**Privacy and what leaves the machine.** The default path makes exactly one kind of
outbound request: the pinned local `x-cli` binary reading `x.com` over the operator's own
tunnel. No credential, cookie, token or browser profile is read, stored or sent; no
account pool and no evasion logic exists here, by decision ([ADR
0007](docs/adr/0007-twitter-acquisition-boundary.md)). Nothing is sent to any third-party
mirror — FxTwitter is not implemented and would be opt-in with a visible statement that
the post id and normal network metadata leave the machine. Provider bytes are checked for
credential material **inside the post's own text first** — a hit there is a refusal with
nothing written, because a post whose authored text contains something like `ct0=` cannot
be both redacted on disk and preserved byte for byte in `capture.json`, and silently
redacting it produced a run that could never validate and a diagnosis that blamed the
operator's evidence. Only then are the envelope's bytes sanitized and **scanned** again
before being written, in that order, because a redactor is not evidence that redaction
worked. `capture.json` itself is never redacted: `items[].text.canonical` is preserved
exactly, and the refusal above is what makes that safe. No provider name, version or binary
digest reaches an index record or the read surfaces (D-238) — the acquisition record lives
in `capture.json`, which anyone can open.

## T7. Troubleshooting

| Exit | What happened | What to do |
|---|---|---|
| `1` | `AcquisitionError: … authored text …` — the provider's answer carries credential-shaped text **inside a post**, so it can be preserved or redacted but not both | A statement about the provider's answer, not about your run. Nothing was written. Re-read the post; if its author really wrote a token, the post cannot be captured under this rule |
| `7` `PROVIDER_UNAVAILABLE` | The pinned binary is missing, or the binary at that path is not the pinned build. **Nothing ran** | Install the pinned build, or pass `--xcli <path>`. Never work around it by relaxing the pin |
| `8` `PROVIDER_UNREACHABLE` | The read could not be completed and **nothing was learned** — tunnel down, timeout, or rate limit | Wait and retry. The stderr envelope says which, so the wait can be the right length |
| `9` `PROVIDER_DRIFT` | The provider answered and the answer was unusable | Do not retry in a loop. The provider's output shape moved; that is a code change, not a network event. Never reported for a network failure |
| `4` `FAIL` + `evidence` | A file under `raw/` no longer matches its recorded digest | The run is refused and cannot be finalized. Re-acquire into a fresh run directory; do not edit evidence to make a digest match |
| `3` `PARTIAL` | Honestly incomplete — a root-anchored thread, an unavailable item, or an unaudited run | A real deliverable. Report it as `PARTIAL`; never as completion |
| `1` `ERROR` on `apply-bundle` | The gate refused the bundle | Read the named errors, fix the extraction, re-apply. The run on disk was not changed |

## T8. Operational prerequisites and verification boundary

The end-to-end phase gate was completed on the target machine on 2026-09-04 with a real
public Persian post and a real ten-post self-thread anchored at its last post. Both were
captured, applied, validated, finalized into vault notes, and merged into one library;
the commands exited `0` and preserved every `raw/` file byte for byte. Committed fixtures
rehearse the same path and its failure states offline.

That historical verification does not remove the prerequisites for a new capture:

1. Install the pinned `x-cli` build and let `capture` verify its digest at every
   invocation. A missing or mismatched build exits `7` before acquisition.
2. Make the required network route available and state it truthfully with
   `--via-tunnel` or `--no-tunnel`; the program records the statement but cannot measure
   the route.
3. Use only public content you have the right to preserve and process.
4. Treat each new network acquisition as a new observation. CI proves the local
   contracts and fixtures, not current X availability or unchanged provider behaviour.

---

# Source synthesis, across a whole project

Everything above produces **one run**. This stage is about a project that holds several,
and it is the only part of this workflow that is not per-source: it produces a readable
account of one source, and qualified relationships *between* sources. `T-257` added it
here, and the ordering rule §8.9 states is why it was not here sooner — no task in
Phase 2.3 documents a step in this file until there is behaviour, a validator **and** a
surface that renders it. All three now exist, so the sequence is numbered rather than
described only in `README.md`.

Both steps are **optional**, both are gates, and both are derived knowledge rather than
evidence. Neither re-grades a run: writing an account of a run does not change its verdict,
so a brief over a `PARTIAL` run still exits `3`.

## S1. A readable brief for one source

Run after `apply-bundle` has written the run's knowledge, relationships and coverage —
those three files are what the brief is derived from and what its digests are taken over.

```bash
# run prompts/06_source_knowledge.md over the run's canonical files
x2knwldg apply-source-knowledge output/<run-id> source_knowledge.json
```

The document is a thesis, its key points and any limitations or tensions, in Persian, with
**every statement naming the knowledge units it rests on**. The contract is
`schemas/synthesis/v1/`, and the command refuses rather than writes when the brief names a
unit the run does not hold, claims a status stronger than the run's own, or records input
digests that no longer match the files. A refused brief leaves the run byte-identical; an
accepted one changes exactly one file and does not restamp `extracted_at`.

No evidence excerpt may appear in a brief, and none can: the contract has no field for one.
A brief is an account *of* extracted knowledge, and quoting a source inside it would put
unverifiable text where the run's own timed evidence belongs.

A run with no brief is in the `unavailable` state, which is normal and possibly permanent
rather than a shortfall. A run whose canonical files change afterwards makes its brief
`stale`, and the brief is still carried with the state saying so.

## S2. Relationships between whole sources

Run once two or more sources have validated extractions.

```bash
x2knwldg source-candidates --output output
# run prompts/07_source_relations.md over the pairs it lists
x2knwldg apply-source-relations source_relations.json --output output
```

`source-candidates` is deterministic and **bounded**: it proposes a pair only where
something specific points at it — a reference one source's artifacts actually record, or a
canonical concept both contribute to — and it reports what it considered, what the bound
left out, and how many ordered pairs existed at all. Comparing every pair is quadratic in
the corpus and each comparison is a pass over two whole knowledge-unit sets, so the bound
is the point rather than a limitation to work around.

`apply-source-relations` is the gate and it does not take the pass's word for the bound: it
**re-runs discovery** and refuses a relation for a pair nothing proposed, along with counts
that disagree with a fresh run. It also refuses a basis unit belonging to the other
endpoint, an `explicitly_references` claim the corpus cannot corroborate, a relation whose
grounds all contradict its direction, a rationale that is not Persian, and any invented
confidence — there is no field for one, and no score, rank or similarity is representable.
Accepted records are written atomically to `output/synthesis/source_relations.json`.

**Emitting no relation is a normal outcome, not a failure.** Two sources can share every
concept in a field and stand in no relation at all. The candidate counts are what make an
empty result readable, and a report that names the retrieval route it did not implement is
telling the truth rather than producing nothing silently.

## S3. Where this is read

Both documents are rendered by the **Source Map**, at `#/map?of=sources` in the local UI
that `x2knwldg ui` serves: one mark per acquired source, a readable brief for the selected one with
its supporting knowledge-unit ids beside every statement, and each returned relationship as
a row that expands into the unit pairs it rests on, each linking into that endpoint's own
Reader. Nothing there is drawn from anything a record does not carry — no ranking, no
weighting by basis count, and no claim that a relationship is still current, because the
v1 shapes carry no per-relation staleness.

The whole reading path is DOM: a browser with no WebGL2 loses the picture and keeps the
brief, the relationships and the grounds.

---

# Unsupported source types

Do not treat architectural readiness as ingestion support. Medium articles, generic web
pages, books, PDF, and EPUB have no implemented acquisition command, canonical capture
contract, prompt pair, adapter, or medium profile in this release. If a user requests one,
report that boundary rather than converting the content into a fake YouTube transcript or
an unversioned post capture. Implementing a source requires the complete vertical slice
listed at the top of this file and cross-source coexistence tests before this workflow may
name it as supported.
