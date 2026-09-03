# `T-222` — acquisition qualification report

- **Task:** `T-222`, Phase 2.2 (`T-220`), the first executable task after
  [ADR 0007](../../adr/0007-twitter-acquisition-boundary.md)
- **Measured:** 2026-09-03, on the user's own machine, `darwin/arm64`, through
  the always-on tunnel that is part of that environment — see §0
- **Provider under test:** [`tamnd/x-cli`](https://github.com/tamnd/x-cli)
  **v0.5.0**, AGPL-3.0 — `x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z)`
- **Credentials used:** none. No X session, cookie, password, browser profile
  or account. `x auth import` was never run
- **Machine-readable results:** [`results.json`](results.json) · fixtures in
  [`fixtures/`](fixtures/) · reproduce with [`qualify.py`](qualify.py)

---

## 0. Correction of record — the environment is the tunnel, not a bare Iranian egress

**Found after the matrix was committed, and it limits what §2 may be read to
mean.** The premise of `T-222`, in ADR 0007 and in the task row, is qualification
*from the user's real Iran environment*. That premise was assumed from the
user's stated location and never verified. It is wrong:

| Check | Result |
|---|---|
| `ipinfo.io` | `country: US`, `region: New York`, `org: AS208226 Ouiheberg SARL` |
| `cloudflare.com/cdn-cgi/trace` (independent) | `ip=50.117.3.112`, `loc=US`, `colo=EWR` |
| Shell proxy variables | none set |
| macOS system proxy | `HTTPEnable: 0`, `HTTPSEnable: 0`, `SOCKSEnable: 0` |
| Tunnel interfaces | **`utun4` active**, `10.141.112.250 --> 10.141.0.1` |

So the traffic left through an active tunnel presenting a US egress, not from an
Iranian one — invisible to both proxy checks, which is why it was missed.

**What this does not affect.** Every capability finding is a property of X's
surfaces and of the tool, not of geography, and stands as measured: the Tier 0
truncation ceiling (§5), thread enumerability in both directions (§4), the field
shapes and the four disagreements with the tool's own table (§7), exit-code
semantics (§6), and the privacy and licence audit (§8).

**What this scopes.** §2 shows the surfaces answering *through this tunnel*. It
is not evidence that `cdn.syndication.twimg.com`, `x.com/i/api/graphql`,
`publish.x.com` or `api.fxtwitter.com` answer from a bare Iranian egress, and no
claim here should be read that way. Since the tunnel is always on, that is the
environment the phase targets — but it is a dependency, and the phase must say
so.

**Resolved by the user on 2026-09-03: the tunnel is always on, so it is part of
the real environment.** The measurements therefore do describe the target
environment, and `T-222`'s environment half is met — with the tunnel named as a
dependency of the phase rather than left implicit. Two consequences were then
measured rather than assumed:

- **The egress is stable.** `50.117.3.112` / `colo=EWR` on three consecutive
  samples. It does not rotate, so per-IP budgets and latency are reproducible.
- **The shared-budget worry does not hold.** The consumption recorded in
  `limits.json` matches this session's own request count — 486 of 500
  `TweetResultByRestId` and 19 of 50 `UserTweets` remaining — so the budgets
  behave as a dedicated egress rather than one shared with strangers. The
  latency figures in §2 are the tunnel's, which is the correct number for this
  environment.

What remains is a **named dependency, not an open question**: X is reached
through a tunnel, so `T-223`/`T-224` must distinguish "the tunnel is down" from
"the provider changed" — otherwise a routine network drop reads as provider
drift and can discard a capture that was fine.

One wording point is left for the user. ADR 0007 says no *payment or regional
restriction* is to be circumvented, in a sentence written about not evading the
paid API. The accepted path routes around a state-level block on the user's own
traffic, which is a different thing from evading X's access controls or its
payment. The phrasing deserves one clarifying line so the record does not read
as self-contradictory. Recorded as **D-209**, resolved.

## 1. Verdict

**GO, with one scope correction that needs a decision.**

A no-payment, credential-free path works from this machine and is good enough to
build Phase 2.2 on. §0 records what "the environment" means here: the user's
always-on tunnel, now a named dependency of the phase rather than an assumption. Every Tier 0 surface answered; 52 matrix cells
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

`x doctor`, Tier 0, no guest token — every credential-free surface reachable
**through the egress described in §0**, without payment:

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

**Budgets observed**, which bound any future design. The guest tier is **metered
per operation, not per tier**, and the first version of this report flattened it
to a single "500 / 15 min" — a 10x overstatement of the scarcest one. Read back
from `~/.local/share/x/limits.json` after the run:

| Operation / surface | Limit per 15 min |
|---|---|
| syndication tweet (s1) | none observed |
| syndication profile (s2) | 30 |
| oembed (s3) | none observed |
| guest `TweetResultByRestId` — one post | **500** |
| guest `UserByScreenName` — one user | 150 |
| guest `UserTweets` — the author archive | **50** |
| app-only v1.1 (s5) | 75 |

This lands well for the recommended design and badly for the one it rejects. A
single-post capture and a parent-walk spend `TweetResultByRestId` at 500 per
window, or the unmetered syndication surface at Tier 0 — comfortable. The
author-archive read costs the **50** budget, and a deep read pages, so it burns
several at a time. The archive was already only `PARTIAL` evidence for
descendants (§4); it is also the scarcest call available, which is a second
reason not to build thread discovery on it.

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
| Long / note post (**2967 chars**) | **`PARTIAL`** | `PASS` | `PASS` | `PARTIAL` |
| Photo with alt text | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Video, Persian | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Animated GIF | `PASS` | `PASS` | `PASS` | `PARTIAL` |
| Unavailable post | `PASS` | `PASS` | `PASS` | `PASS` |
| Malformed reference | `PASS` | `PASS` | **`PARTIAL`** | `PASS` |

Totals — Tier 0: 11 `PASS` / 2 `PARTIAL`. Guest: **13 `PASS` / 0 `PARTIAL`**.
FxTwitter: 12 / 1. oEmbed: 2 `PASS` / 11 `PARTIAL`. No `FAIL` anywhere.

The rows a matrix like this exists to catch are the bold cells, and §4–§6
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

The sharpest single-post finding, measured on two real note posts:

| Route | 521-char post | 2967-char post | Announces truncation? |
|---|---|---|---|
| x-cli Tier 0 (syndication) | **304** | **280** | **No** |
| x-cli Tier 1 (guest) | 521 | 2967 | n/a — complete |
| FxTwitter | 521 | 2967 | yes — `is_note_tweet: true` |

Tier 0 carries **no field** signalling that anything was cut — no `is_note_tweet`,
no `truncated`, no `note_tweet`. On the longer post it returned **280 characters
of 2967 — 9% of the content** — cut mid-sentence at the classic tweet limit
("…2027 will be the warmest year in recorded"), with no ellipsis and no error.

The 521-char case alone would have understated this badly: 304 of 521 looks like
a margin problem, and its tail happened to end in a `t.co` link, which invites
exactly the wrong heuristic. It is not a margin problem and the link is not a
marker — Tier 0 returns the first 280 characters and stops. A consumer cannot
detect the loss from the response, because a complete short post is
indistinguishable from a truncated long one.

**This is the one place where the most conservative route is the least honest**,
and it is why the recommendation below is not "Tier 0 for everything". It is also
the strongest argument for keeping a second route: Tier 1 and FxTwitter agreed
character-for-character at 521 and 2967, so cross-route agreement is a real
verification mechanism where no in-band completeness signal exists.

**With one correction that §5a makes.** All three long-post samples happened to
be link-free prose, and "agreed character-for-character" does not generalize:
where a post contains a link the two routes disagree *by design*, because x-cli
preserves the authored `t.co` form while FxTwitter expands links and strips a
trailing media one. A truncation check that compares raw text would therefore
fire on almost every post carrying media or a URL. It has to compare
URL-normalized text.

The ceiling was probed once further, outside the matrix, on a 3659-character
post: Tier 0 returned **276 characters**, Tier 1 and FxTwitter both returned all
3659, and the two agreed exactly again. So Tier 1 is intact to at least 3659
characters. That is a **measured floor on its capacity, not a proof of it** —
X's note posts run to far greater lengths than anything located here without
search, so a higher ceiling may exist and has not been ruled out. `T-223` should
therefore treat text completeness as corroborated, never as asserted (§12).

## 5a. Persian text survives; the routes disagree about links

Measured by [`fidelity.py`](fidelity.py) into [`fidelity.json`](fidelity.json),
across four Persian posts from three accounts. This exists because a source claim
cites a post id **plus an exact text span**: if two routes disagree about the
characters, a span recorded from one silently misresolves against the other.

**The reassuring half. No Persian codepoint was damaged by any route.** ZWNJ
(`U+200C`), Persian ye (`U+06CC`), Persian keheh (`U+06A9`) and Persian digits
(`U+06F0`–`U+06F9`) came back identical from Tier 1 and FxTwitter in every case.
ZWNJ is not a corner case here — it appeared in **53 of 60** posts sampled from
one Persian account alone, so silent folding would have corrupted most of the
corpus. `cases_with_real_codepoint_damage` is empty.

**The half that changes the design. The routes represent links differently.**

| Case | Tier 0 | Tier 1 | FxTwitter | Raw equal? | Equal after URL normalization? |
|---|---|---|---|---|---|
| Persian prose, ZWNJ + Persian digits | **273** | 418 | 418 | yes | yes |
| Persian post ending in a media link | 285 | 285 | 261 | **no** | yes |
| Persian post with an expandable link | 60 | 60 | 77 | **no** | yes |
| Second Persian source | 142 | 142 | 135 | **no** | yes |

Three of four disagree raw, and all four agree once URLs are normalized away:

- **x-cli preserves the authored form** — `https://t.co/WlXNDbE5I2`.
- **FxTwitter expands a non-media link** — the same post's `t.co` becomes
  `https://x.com/i/broadcasts/1OGwbnpYmVLKB`, which is *longer* than the original.
- **FxTwitter strips a trailing media link entirely**, exposing the media in a
  separate field instead.

One apparent codepoint disagreement turned out to be an artifact of exactly this:
the `ascii_digits` class vanished from FxTwitter's inventory for one post because
the digits lived inside the stripped `t.co` slug. The script now compares
inventories on URL-normalized text and reports the artifact separately, because
"the routes disagree about characters" and "one route dropped a URL" are not the
same finding and must not be logged as though they were.

**And a fourth truncation instance, in Persian.** Tier 0 returned **273 of 418**
characters of the link-free Persian post — a post nowhere near the 2967-character
extreme of §5. Silent truncation is not an exotic long-post problem; it reaches
ordinary Persian news posts.

**What this obliges `T-223` to decide.** One canonical text form, because the
offsets of every stored span depend on it. On this evidence the authored `t.co`
form is the better canonical choice — it is what the author wrote, it is what
raw evidence contains, and expansion is a lossy, provider-specific opinion that
can change without the post changing. Expanded targets belong in text entities
beside the span, not inside it.

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
- **The fixtures are clean.** All 52 were redacted and then re-scanned; the
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

**Accepted by the user on 2026-09-03 (D-207).** It needed ratifying because
Tier 1 is an escalation from Tier 0 and ADR 0007 said to test unauthenticated
first. What a guest token is: an
anonymous value X mints on request, tied to no account, stored as
`guest_token` + `minted_at`, metered per operation (500 for a single post, 50 for an archive read). It is not a credential,
a session or an account, so it sits inside the ADR's exclusions — but it is
minted material, and the ADR did not name it. §11 records the answer.

**Fallback order:**

1. **x-cli Tier 0** — no token at all. Correct for short single posts and for
   the thread parent-walk, which is where it is strongest. Never for a post
   that might be long, unless a Tier 1 or FxTwitter read confirms the length.
2. **FxTwitter**, explicit opt-in per ADR 0007 §3 (`T-225`). It agreed with the
   guest tier on **every** MVP cell, and character-for-character on link-free
   prose at 521, 2967 and 3659 — with the URL caveat in §5a — so it
   is a real cross-check rather than a second guess — at the cost of disclosing
   the post id. Reviewed origin `api.fxtwitter.com`; treat `200` as meaningless
   without a `tweet` object.
3. **Official oEmbed**, corroboration only (`T-225`). It confirms author, text
   and RTL direction — `dir="rtl"`, `lang="fa"` came through correctly on the
   Persian case — and nothing else. It cannot carry timestamps, media, parents
   or quotes, and can never raise completeness. Origin `publish.x.com`.

**`T-226` (passive Firefox capture) stays optional.** The user chose the
"anchor at the last post" contract instead (D-206), so the descendant gap is
closed by asking rather than by browsing. That is the better trade on the
evidence available: `T-226` is untested here, and it plausibly inherits the same
unprovability — an observed subset is `PARTIAL` unless completeness is
independently proven, and "the browser loaded to the end" is not a proof.

## 11. What this put to the user, and what he decided

Answered on 2026-09-03. Recorded as D-206 and D-207 in
[`PROJECT_MANAGEMENT.md`](../../PROJECT_MANAGEMENT.md) §6.

1. **Self-thread ingestion contract (D-206) — decided: ask for the last post.**
   Ingestion asks for the thread's final post, walks upward to the root and
   reports `PASS`; a root anchor warns and asks for the last post rather than
   being accepted quietly. Completeness is recorded as *"complete to root from a
   user-asserted terminal anchor"*, never as an observed fact. This keeps `PASS`
   meaningful instead of making `PARTIAL` the normal state — and it leaves one
   permanent, explicit residual risk: the terminal anchor is a human judgement
   the system cannot verify, so a thread continued later will be silently short.
   `T-226` was **not** promoted, which is well judged: it is untested and
   probably inherits the same wall, "I scrolled to the end" being no more
   provable than "this is the last post".
2. **Tier 1 (guest) as the default read (D-207) — decided: yes.** Tier 0 remains
   the fallback for short single posts and for the parent-walk, where it is
   unmetered and at its strongest. Tier 0 alone cannot represent long posts
   honestly (§5).
3. **The pin (D-208) — still open.** v0.5.0, AGPL-3.0, external binary, the two
   digests in §8.

**And one item this report did not originally raise.** ADR 0007's "no payment or
regional restriction is to be circumvented" was written about not evading the
paid API; the accepted path routes around a state-level block on the user's own
traffic, which is a different thing. §0 explains why one clarifying line is
worth adding so the record does not read as self-contradictory. Also open.

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
- **One canonical text form, and it is the authored one.** Spans are offsets
  into it, so the choice is load-bearing. Store expanded link targets as
  entities beside the span, never substituted into it (§5a).
- **Any cross-route text comparison normalizes URLs first.** Raw comparison
  disagrees on three of four Persian posts purely over link representation, so a
  raw check would fire on almost every post with media or a URL (§5a).
- **Persian codepoints need no special handling but do need a guard.** Nothing
  damaged ZWNJ, Persian ye, keheh or Persian digits, and a regression test
  should keep it that way (§5a).
- **Text completeness has no in-band signal**, so it is not assertable from one
  route. A capture records the surface that supplied the text and, where a
  second route was read, whether the two agreed. Tier 1 and FxTwitter matched
  character-for-character at 521 and 2967 (§5); that agreement is the only
  available check, and it is corroboration, not proof.
- **A terminal anchor is an assertion, not an observation.** The parent walk
  proves a chain is whole *from its anchor to the root*; nothing credential-free
  proves the anchor is the thread's last post. If the product asks the user for
  the last post, the capture must record completeness as *"complete to root from
  a user-asserted terminal anchor"* and never as an observed fact (§4).

No production integration was written in this task, as `T-222` requires.
