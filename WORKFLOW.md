# X2KNWLDG Agent Workflow

This workflow is vendor-neutral. ChatGPT/Codex, Claude, or any MCP-capable agent must use the same canonical files and validators.

**Two media.** Sections 1–5 are the **YouTube** path. The **Twitter/X** path is below them, and it is a different first step and a different citation unit rather than a different pipeline: `apply-bundle`, `validate` and `finalize` are the same commands and dispatch on what the run declares (D-240, D-243). A third and fourth medium — articles, then books, then web pages (D-234) — add a section here and a row to `artifacts.MEDIUM_PROFILES`, not a second workflow.

## 1. Acquire the transcript

Preferred order:

1. Native YouTube captions with timestamps.
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
- `summary` is derived from the windows and is recomputed on apply. Do not
  hand-write it.

## 5. Apply and finalize

Assemble `extraction_bundle.json` using `schemas/extraction_bundle.schema.json`. It has
three **required** keys and one **optional** one, and the schema sets
`additionalProperties: false`, so no other top-level key is accepted. All four are listed
here: this table used to omit `extraction_metadata` while saying "exactly three… no other
top-level key is accepted", so an agent following it silently dropped the provenance record
the pipeline does consume (D-189).

| Bundle key | Required | Comes from | Note |
|---|---|---|---|
| `knowledge_units` | yes | passes 1, 2 and 4 | The **bundle** key is `knowledge_units`. The canonical `knowledge_units.json` file writes the same list under `units`; do not carry that spelling into the bundle (D-073) |
| `relationships` | yes | pass 3 | Required, and refused when missing or misspelled — it used to default silently to `[]` and wipe every relationship the run had (D-169) |
| `coverage` | yes | pass 5 | `audit_attempts` is required; `0` is the honest never-audited state and may not accompany a `PASS` (§4.4). See the three window rules in §4 |
| `extraction_metadata` | no | the run itself | An object describing what produced the extraction. `apply-bundle` copies it into `metadata.extraction`; a non-object is refused rather than dropped (D-169). All three committed fixtures carry one |

Then run:

```bash
x2knwldg apply-bundle output/<video-id> extraction_bundle.json
x2knwldg finalize output/<video-id>
```

Completion may be claimed only when validation and coverage both report `PASS` — which is
exactly **exit code `0`**. `PARTIAL` exits `3` and `FAIL` exits `4`: both are real results to
report, and neither is completion. The full table is in
[`README.md` § Exit codes](README.md#exit-codes), and `x2knwldg --help` prints it.

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
1. prompts/twitter/01_item_extraction.md
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

The bundle is the same shape as §5, with one difference: `coverage` carries `items`
rather than `windows`. Then the same three commands:

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
the post id and normal network metadata leave the machine. Provider bytes are sanitized
and then **scanned** for credential material before being written, in that order, because
a redactor is not evidence that redaction worked. No provider name, version or binary
digest reaches an index record or the read surfaces (D-238) — the acquisition record lives
in `capture.json`, which anyone can open.

## T7. Troubleshooting

| Exit | What happened | What to do |
|---|---|---|
| `7` `PROVIDER_UNAVAILABLE` | The pinned binary is missing, or the binary at that path is not the pinned build. **Nothing ran** | Install the pinned build, or pass `--xcli <path>`. Never work around it by relaxing the pin |
| `8` `PROVIDER_UNREACHABLE` | The read could not be completed and **nothing was learned** — tunnel down, timeout, or rate limit | Wait and retry. The stderr envelope says which, so the wait can be the right length |
| `9` `PROVIDER_DRIFT` | The provider answered and the answer was unusable | Do not retry in a loop. The provider's output shape moved; that is a code change, not a network event. Never reported for a network failure |
| `4` `FAIL` + `evidence` | A file under `raw/` no longer matches its recorded digest | The run is refused and cannot be finalized. Re-acquire into a fresh run directory; do not edit evidence to make a digest match |
| `3` `PARTIAL` | Honestly incomplete — a root-anchored thread, an unavailable item, or an unaudited run | A real deliverable. Report it as `PARTIAL`; never as completion |
| `1` `ERROR` on `apply-bundle` | The gate refused the bundle | Read the named errors, fix the extraction, re-apply. The run on disk was not changed |

## T8. Steps a person still has to do

These cannot be asserted from a test machine and are not claimed as done by CI:

1. Install the pinned `x-cli` build on the target machine and confirm `capture` reports
   its digest matches — the pin is verified at every invocation, so a wrong build exits
   `7` rather than producing a capture.
2. Bring up the tunnel, and state it with `--via-tunnel`.
3. Walk one **real public** post and one **real public** Persian self-thread from their
   last posts, end to end, and confirm exit `0` at each step and a vault note at the end.
4. Confirm `output/<post-id>/raw/` is byte-identical before and after the rest of the
   journey.

The committed fixtures rehearse all of this offline, including every failure above; what
they cannot rehearse is the network and the pin on real hardware.
