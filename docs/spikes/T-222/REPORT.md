# `T-222` — acquisition qualification report

- **Task:** `T-222`, Phase 2.2 (`T-220`), the first executable task after
  [ADR 0007](../../adr/0007-twitter-acquisition-boundary.md)
- **Measured:** 2026-09-03, from the user's own machine and network (Iran),
  `darwin/arm64`
- **Provider under test:** [`tamnd/x-cli`](https://github.com/tamnd/x-cli)
  **v0.5.0**, AGPL-3.0 — `x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z)`
- **Credentials used:** none. No X session, cookie, password, browser profile
  or account. `x auth import` was never run
- **Machine-readable results:** [`results.json`](results.json) · fixtures in
  [`fixtures/`](fixtures/) · reproduce with [`qualify.py`](qualify.py)

---

## 1. Verdict

**GO, with one scope correction that needs a decision.**

A no-payment, credential-free path works from this environment and is good
enough to build Phase 2.2 on. Every Tier 0 surface answered; 48 matrix cells
were measured with **zero `FAIL`**.

But the phase MVP as written in `PROJECT_MANAGEMENT.md` §5 is *"public single
posts and provable same-author self-threads"*, and that second half does not
hold unconditionally:

| MVP half | Result |
|---|---|
| Public single posts | **Qualified.** Three independent routes, no credential |
| Same-author self-threads | **Qualified only from a deep anchor.** A thread anchored at its **root** cannot be completed by any credential-free route |

A self-thread is provably whole when the anchor is its **last** post: the parent
chain walks upward to a root and terminates there. Anchored at the **root**,
descendants cannot be enumerated at all — so the honest coverage for that input
is `PARTIAL`, by construction and forever, not as a defect to fix later.

**This is the finding that justified the task.** Had `T-223` frozen a capture
contract from the candidates' documentation, it would have encoded a thread
capability that does not exist credential-free, and the pipeline would have
reported whole threads while silently dropping 70% of their posts (§4).

## 2. The environment answers

`x doctor`, Tier 0, no guest token, from Iran — every credential-free surface
reachable, no proxy, no VPN, no payment:

| # | Surface | Host | Status | Latency |
|---|---|---|---|---|
| s1 | syndication tweet | `cdn.syndication.twimg.com` | `ok` | 1652 ms |
| s2 | syndication timeline | `syndication.twitter.com` | `ok` | 1659 ms |
| s3 | oembed | `publish.x.com` | `ok` | 1135 ms |
| s4 | guest graphql | `x.com/i/api/graphql` | `ok` (with `--guest`) | 2971 ms |
| s5 | app-only v1.1 | `api.x.com/1.1` | `ok` | 953 ms |
| s6 | media cdn | `pbs.twimg.com` | `ok` | 1526 ms |
| s7 | session graphql | — | `skip` — no session, by design | — |
| s8 | x.com html | `x.com` | `ok` | 3884 ms |

Median end-to-end latency per route, across the matrix: oEmbed 808 ms,
FxTwitter 847 ms, x-cli guest 1861 ms, x-cli Tier 0 3130 ms.

**Budgets observed**, which bound any future design: syndication tweet — none
observed; syndication profile — **30 / 15 min**; guest GraphQL — **500 / 15
min**; app-only v1.1 — 75 / 15 min.

## 3. Capability matrix

`PASS` means the route answered *and* carried every field the case needs.
`PARTIAL` means it answered but something the case requires was missing —
never rounded up.

| Case | x-cli Tier 0 | x-cli Tier 1 (guest) | FxTwitter | oEmbed |
|---|---|---|---|---|
| Single post, English | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Single post, Persian/RTL | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Self-thread, root anchor | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Self-thread, middle anchor | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Self-thread, last anchor | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Quote post | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Long / note post (521 chars) | **`PARTIAL`** | `PASS` | `PASS` | `PARTIAL` |
| Photo with alt text | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Video, Persian | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Animated GIF | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Unavailable post | `PASS` | `PASS` | `PASS` | `PASS` |
| Malformed reference | `PASS` | `PASS` | **`PARTIAL`** | `PASS` |

Totals — Tier 0: 11 `PASS` / 1 `PARTIAL`. Guest: **12 `PASS` / 0 `PARTIAL`**.
FxTwitter: 11 / 1. oEmbed: 2 `PASS` / 10 `PARTIAL`. No `FAIL` anywhere.

The rows a matrix like this exists to catch are the two bold cells, and §4–§6
are about them.

## 4. Threads: request success is not completeness

Measured on a real 10-post `@NASA` self-thread, at Tier 0, with the two
directions scored **separately**:

| Anchor | Upward walk (anchor → root) | Downward reach (whole thread from the author archive) |
|---|---|---|
| Root | `PASS` — 1 post, root has no parent | `PARTIAL` — 3 of 10 |
| Middle | `PASS` — 8 posts to root, one author | `PARTIAL` — 3 of 10 |
| Last | `PASS` — **10 posts to root, one author** | `PARTIAL` — 3 of 10 |

**Upward is provable.** Following `reply_to` terminates at a post whose parent
is `null`; every hop resolved, and every hop was by the same author. That
termination *is* the completeness proof, and it needs no credential — Tier 0
returns a reply's parent.

**Downward is not, and cannot be faked.** A 250-post guest-tier archive read of
`@NASA` contained **3 of the 10** members. The seven absent posts are exactly
the ones a naive implementation would drop while reporting success. Two
independent reasons, both structural:

- `x thread` and `x replies` return **only the anchor** at every credential-free
  tier — `n=1` on a post with 11,337 replies, confirmed against three surfaces
  (`--tier 0`, `--tier web`, `--tier syndication`) and on a second thread with
  18,011 replies. `x routes` puts the whole reply tree at **Tier 2 (session
  cookies)**, which ADR 0007 excludes.
- X's `UserTweets` archive omits replies, and thread continuations *are*
  replies. `x routes` advertises "the full archive, paged" at Tier 1; measured,
  it returned a ranked selection spanning 2018–2026 rather than time order.

So the acquisition rule for `T-223` is: **a self-thread is complete only when
its anchor is its deepest post.** Anything else is `PARTIAL` with the reason
named. Post order is derived from the parent chain, never from arrival order.

## 5. Tier 0 truncates long posts, and does not say so

The sharpest single-post finding, on a real 521-character note post:

| Route | Characters | Announces truncation? |
|---|---|---|
| x-cli Tier 0 (syndication) | **304** | **No** |
| x-cli Tier 1 (guest) | 521 | n/a — complete |
| FxTwitter | 521 | yes — `is_note_tweet: true` |

Tier 0 returned 58% of the text, ending in a `t.co` link, and carried **no
field** signalling that anything was cut — no `is_note_tweet`, no `truncated`,
no `note_tweet`. A trailing `t.co` link cannot be used to detect it either,
because ordinary complete posts end that way too.

This is the one place where the most conservative route is the *least* honest,
and it is why the recommendation below is not "Tier 0 for everything".

## 6. Failure semantics are clean and distinguishable

x-cli exits are deterministic and specific, which is what `T-224` needs:

| Exit | Meaning | Message |
|---|---|---|
| `0` | success | — |
| `1` | not a reference; refused **offline**, no request sent | `Not a tweet id or status URL: "not-a-ref"` |
| `5` | rate limited | names the surface *and* the reset time: `Rate limited by X on graphql.UserTweets; the window resets at 20:33:34` |
| `6` | unavailable | `Tweet not found: … (deleted, suspended, or protected)` |
| `8` | timeout | `The request timed out: raise --timeout` |

Two consequences worth carrying into the contract:

- **Unavailability has no distinguishable reason.** Deleted, suspended and
  protected collapse into one message; `x routes` puts distinguishable errors at
  Tier 2. The canonical capture must therefore record *"unavailable, reason not
  determinable at this tier"* and must never guess which it was.
- **`--dry-run` still performs the request.** It printed live records for
  `x discover`. Do not rely on it as a no-network mode.

Third-party failure modes are less clean. FxTwitter answers a malformed
reference with **HTTP 200 and an HTML body**, so any consumer that treats
`200` as success sees success where there is no record; it must inspect the
`code`/`tweet` fields. It refuses a well-formed unavailable id properly, with
`404` and `{"code":404,"message":"NOT_FOUND","tweet":null}`. oEmbed answers an
unavailable post with `404` and an **HTML error page**, not JSON. And
`publish.twitter.com/oembed` **301-redirects** to `publish.x.com`, so the
reviewed origin must be the latter and the redirect must not be followed blindly.

## 7. The tool's own documentation disagrees with the tool

`x fields tweet` declares which surface fills which field. Measured against
real posts at Tier 0, it is wrong in four places — in both directions. This is
the strongest argument for freezing `T-223` on observation:

| Field | `x fields tweet` says | Measured at Tier 0 |
|---|---|---|
| `media` | surfaces 2, 4, 8 — not 1 | **present** via surface 1, with variants, dimensions and duration |
| `quoted` | no surface, any tier | **present**, with the quoted post's id, author and text |
| `alt_text` | not listed at all | **present** — 62 of 108 media objects carried author-written alt text |
| `replies` (the tree) | Tier 0 via surface 8, "three of them" | **empty** — `[]` and `No results.` |

`conversation_id` is the reverse case and matters for design: `fields` puts it
on surfaces 2 and 4, and Tier 0 single-post reads indeed return `null` for it.
A Tier 0 capture can therefore walk a thread by parent links but cannot name
the conversation it belongs to.

## 8. Privacy and licence boundary

Audited after the run, with the guest tier exercised:

- **Nothing credential-shaped is persisted.** `~/.local/share/x/` holds
  `limits.json`, `guest.json` and an HTTP cache. `guest.json` contains exactly
  two keys — `guest_token` (a 19-digit anonymous value X mints on request, tied
  to no account) and `minted_at`. A grep for `cookie|auth_token|ct0|bearer|
  password|session` across the data and config directories produced one hit:
  `"session_id":""`, an empty field inside X's own embed payload.
- **The fixtures are clean.** All 48 were redacted and then re-scanned; the
  scan passes. The only request material found was the syndication `token`
  parameter, stripped from ten fixtures — and the first version of that
  stripper missed it, which is recorded in [`README.md`](README.md) because it
  is the kind of near-miss `T-223`'s validators should assume.
- **The HTTP cache holds post content** under `~/.local/share/x/cache`
  (1.5 MB after this run), outside the project. `--no-cache` bypasses it and
  `x cache clear` empties it; the harness always passes `--no-cache`.
- **Licence:** AGPL-3.0. It stays a separately installed, pinned binary
  invoked as a subprocess, per ADR 0007 and `T-224`. Nothing is vendored, and
  the Python core keeps zero dependencies. Pinned artefacts:
  `x_0.5.0_darwin_arm64.tar.gz` SHA-256
  `6de9cde491c10aa9455f37e73beaba9b469e58de93940ba8db1aeca2ee77a705`
  (verified against the release `checksums.txt`), extracted binary SHA-256
  `6cb6b7f9b5fdb2366f113919423e87b4ddf9d41ce10bfc65b43614bed9987c97`.

**Maintenance risk, stated plainly:** the repository was created 2026-06-13 and
last pushed 2026-07-29 — roughly five weeks stale at measurement, 15 stars, one
author. It is qualified as a *tool we invoke and can replace*, never as a
library we depend on.

## 9. What could not be qualified

Recorded as `NOT_SUPPORTED` for this phase, with the reason and the kind of
evidence separated, because "proven absent" and "no fixture found" are not the
same claim:

| Case | Verdict | Evidence |
|---|---|---|
| Poll | `NOT_SUPPORTED` | No public poll found in 610 credential-free posts across seven accounts. `x fields tweet` declares `poll` with **no surface at any tier**, and `x poll` exits `1`. Absence is structural, but no fixture proves it |
| Edited post | `NOT_SUPPORTED` | Same scan, no instance. `fields` declares `edits` with no surface at any tier |
| X Article | `NOT_SUPPORTED` | The tool models only `tweet` and `user` record kinds. No Article representation exists to test |
| Protected / suspended, as distinct from deleted | `NOT_SUPPORTED` | Proven: Tier 0 collapses all three into one message (§6) |
| Reply by another author | not measured | No cross-author reply appeared in the archives read; every reply observed was a self-reply. Out of MVP scope anyway |
| Provider outage | `PASS` | An unresolvable host yields a transport error and no record; x-cli exits `8` on timeout |

Search is Tier 2, which is why polls and edits could not be hunted directly.
`T-227` must treat all four as absent-unless-represented, never as fields to
guess.

## 10. Recommendation

**Default:** x-cli v0.5.0 at **Tier 1 (guest)** for the capture read. It is the
only route that passed every MVP cell, it sends nothing to a third party, and
Tier 0 is disqualified as a sole default by the silent truncation in §5.

**A decision is needed on this, because Tier 1 is an escalation from Tier 0**
and ADR 0007 said to test unauthenticated first. What a guest token is: an
anonymous value X mints on request, tied to no account, stored as
`guest_token` + `minted_at`, with a 500/15-min budget. It is not a credential,
a session or an account, so it sits inside the ADR's exclusions — but it is
minted material, and the ADR did not name it. §11 puts this to the user.

**Fallback order:**

1. **x-cli Tier 0** — no token at all. Correct for short single posts and for
   the thread parent-walk, which is where it is strongest. Never for a post
   that might be long, unless a Tier 1 or FxTwitter read confirms the length.
2. **FxTwitter**, explicit opt-in per ADR 0007 §3 (`T-225`). It agreed with the
   guest tier on **every** MVP cell including the full 521-character text, so it
   is a real cross-check rather than a second guess — at the cost of disclosing
   the post id. Reviewed origin `api.fxtwitter.com`; treat `200` as meaningless
   without a `tweet` object.
3. **Official oEmbed**, corroboration only (`T-225`). It confirms author, text
   and RTL direction — `dir="rtl"`, `lang="fa"` came through correctly on the
   Persian case — and nothing else. It cannot carry timestamps, media, parents
   or quotes, and can never raise completeness. Origin `publish.x.com`.

**`T-226` (passive Firefox capture) is promoted from optional to required** for
any thread the user anchors at its root. It is the only remaining credential-free
way to observe descendants, because a browsing session loads the conversation
that no public surface will enumerate. If the user accepts the "anchor at the
last post" contract instead, `T-226` can stay optional — that is the §11 choice.

## 11. What this puts to the user

1. **Self-thread ingestion contract.** Either (a) the product asks for the
   **last** post of a thread and reports `PASS`, or (b) it accepts a root
   anchor and reports `PARTIAL` with the descendants named as unresolved, or
   (c) `T-226` is brought forward to close the gap. This changes the MVP
   sentence in `PROJECT_MANAGEMENT.md` §5 either way.
2. **Tier 1 (guest) as the default read.** §10 states exactly what it is and
   what it stores. Tier 0 alone cannot represent long posts honestly.
3. **Confirm the pin.** v0.5.0, AGPL-3.0, invoked as an external binary, with
   the two digests in §8 recorded as the qualified artefacts.

## 12. What `T-223` must encode

Carried forward as contract requirements, each traceable to a measurement above:

- Post, conversation, user and media ids stay **strings** (`20` and
  `2094037638856454625` both appear).
- A capture records the **tier and surface** that filled each field, because
  the same field arrives complete or truncated depending on it (§5).
- **Completeness is a separate field from request success**, with direction:
  `upward_complete` provable, `downward_complete` not (§4).
- Thread order comes from **parent links**, never arrival order (§4).
- `conversation_id` is **absent at Tier 0** and must be optional (§7).
- Unavailability records *"reason not determinable at this tier"* (§6).
- Poll, edits, Article and reply-settings are **absent, not empty** (§9).
- A quoted post is a **separate cited source**, and its id and author are
  available at Tier 0 (§7).
- `alt_text` is real and worth carrying — 62 of 108 media objects had it (§7).
- Raw evidence keeps its **pre-sanitization digest** alongside the sanitized
  one, and sanitization records what it removed (§8).

No production integration was written in this task, as `T-222` requires.
