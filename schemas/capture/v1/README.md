# Twitter/X capture model v1

The **acquisition** contract: one public X post, or one same-author self-thread,
normalized away from every provider's response shape. Delivered by `T-223`.

| File | Describes |
|---|---|
| `twitter_capture.schema.json` | One capture — provenance, raw evidence, items, order, completeness, coverage |

Draft **JSON Schema 2020-12**. The `$id` is
`https://x2knwldg.local/schemas/capture/v1/twitter_capture.schema.json`.

## Where this sits, and what it deliberately does not touch

This is a **pipeline** contract, upstream of extraction. It is not part of the
derived index model in [`schemas/v1/`](../../v1/README.md), and it does not
reference it — the dependency would run backwards, since the index layer is
derived *from* captures and is explicitly documented as describing "nothing that
the pipeline writes". The schema is therefore self-contained: every primitive it
needs is in its own `$defs`, even where `schemas/v1/common.schema.json` has a
near-twin.

Extraction and the UI consume this record. Neither ever sees a provider
response (ADR 0007 decision 7).

## Versioning

Same doctrine as the index model: **the version is the directory**.

- Additive optional field, or a pattern widened to accept strictly more → edit
  in place.
- New required field, removed field, narrowed type, changed meaning → create
  `schemas/capture/v2/` and leave `v1` untouched.

Two patterns here are deliberately narrow so they can be widened rather than
versioned later: post ids are `^[0-9]{1,25}$`, and `lang` accepts BCP-47 plus
the handful of X-specific codes observed.

## Why the constraints are shaped this way

Frozen on measurement, not on documentation. The
[`T-222` spike report](../../../docs/spikes/T-222/REPORT.md) records four places
where the candidate tool's own field table disagreed with what it actually
returned, which is why nothing here was taken from a provider's docs.

Every constraint exists to make one specific dishonest record **unrepresentable**
rather than merely discouraged. The pointed ones:

| Constraint | The lie it prevents |
|---|---|
| Ids are strings matching `^[0-9]{1,25}$` | `2094037638856454625` exceeds a double's exact-integer range, so numeric handling corrupts it silently |
| `tier` is `0` or `1` only | Tier 2 is session cookies, excluded by ADR 0007 decision 6. A session-derived capture cannot be expressed |
| `text.form` is `const: "authored"` | Spans are offsets into the canonical text (D-211). A rendered form would shift every offset in a stored corpus |
| `completeness.downward.status` has no `complete` | No credential-free route enumerates descendants. A 250-post author archive held 3 of 10 members of a real thread |
| `anchor.terminal_claim` has no `observed` | Nothing proves an anchor is a thread's last post. It is the user's assertion, recorded as one (D-206) |
| `media`/`edits` require `minItems: 1`; `poll`/`article` require `minProperties: 1` | `[]` and `{}` would claim absence *was observed*, which a truncating surface cannot support |
| `metrics` requires `observed_at` | A bare count invites comparison across time as though it were a property of the post |
| `sha256_raw` beside `sha256_sanitized` | A redacted body passed off as the original bytes |
| `availability.reason` normally `not_determinable_at_this_tier` | Deleted, suspended and protected are one message below Tier 2. The specific reasons are listed but unreachable, which is the point |
| `additionalProperties: false` on every node but two | A provider's response shape leaking into extraction or the UI. The two open nodes are `post.poll` and `post.article`, each `type: object` with `minProperties: 1` and no key list, because no measured route produces one and inventing a shape for an unobserved feature would be worse than leaving it open. They are also, exactly, the two places a provider blob could ride through — so "throughout" was the one word this row could not afford, and it stood while both were open |
| `network.via_tunnel` | D-209: the qualified path runs over an always-on tunnel. Recorded so a reachability failure is not misread as provider drift |

## What the schema cannot enforce

JSON Schema compares no two fields, so these live in
[`tests/test_twitter_capture.py`](../../../tests/test_twitter_capture.py), the
same division the extraction bundle uses for its window bounds:

- `PASS` while an expected item is unaccounted for.
- Entity spans re-slicing to their own text — the guard on the **codepoint**
  index basis, which was proven against astral emoji.
- Thread order being root-first and parent-consistent.
- Raw evidence digests recomputing from the preserved bytes.
- An unavailable post carrying an author, timestamp or text it never observed.
