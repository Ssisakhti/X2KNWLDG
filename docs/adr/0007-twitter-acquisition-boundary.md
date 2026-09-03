# ADR 0007 — Qualify local Twitter/X acquisition before integration

- **Status:** Accepted
- **Date:** 2026-09-03
- **Decision ledger:** D-204 (`KNOWLEDGE_CANVAS_PLAN.md` §19 and
  `PROJECT_MANAGEMENT.md` §6)
- **Supersedes:** none
- **Superseded by:** none

## Context

Twitter/X is the next requested source, before Canvas. The user cannot currently pay for the
official API and is operating from Iran. The project therefore needs a useful public-content
path without asking the user to evade payment, sanctions, account controls or access controls.
No candidate can be treated as dependable from documentation alone: X changes its public web
surface, unofficial services may disappear, and behaviour can differ by region and account
state.

The local `Treasury` project proved one useful pattern: Firefox can expose responses that the
user's ordinary browsing session has already received. It also contains patterns that this
project must not inherit as a product default: session material, account pools, automated
interaction and anti-detection behaviour would enlarge the security, maintenance and account
risk beyond what a personal knowledge importer needs.

Research on 2026-09-03 found four relevant acquisition surfaces:

- `x-cli` reads public X web surfaces locally, emits structured JSON/JSONL and does not send
  the requested post to a third-party service. It is the best primary candidate, but it is a
  young AGPL-3.0 project and its unauthenticated thread view is limited to what the public
  status page exposes.
- FxTwitter/FxEmbed exposes structured post, thread and conversation endpoints, including
  tombstones and rich post types, but a request discloses the requested post identifier and
  ordinary network metadata to a third party and the service can change or disappear.
- X's official oEmbed endpoint is free, requires no authentication and is documented as not
  rate-limited. It returns embed HTML for one public post; it is useful corroboration, not a
  complete thread or extraction source.
- Passive Firefox capture can import X GraphQL responses already received during an ordinary,
  user-driven browsing session. It can be local and credential-free if designed narrowly,
  but an observed response is not evidence that the whole conversation was loaded.

X's Terms of Service prohibit scraping or crawling without prior written consent. None of the
unofficial paths is represented as approved by X, and this ADR is an engineering boundary,
not a legal conclusion.

## Decision

1. Insert Phase 2.2, epic `T-220`, before Canvas. Its first executable task is a measured
   acquisition spike from the user's real Iran environment; Canvas remains technically ready
   but is deliberately deferred.
2. Treat `x-cli` as the **primary candidate, not yet a dependency**. Qualify a pinned version
   against the fixture matrix in `T-222`, record its licence and version, preserve its raw
   output and failures, and decide whether to invoke it as an external tool or reimplement a
   narrow compatible acquisition seam only after the measurements exist.
3. Allow FxTwitter/FxEmbed only as an **explicit opt-in fallback**. The UI/CLI must disclose
   that the post id and ordinary request metadata leave the machine. Use a fixed reviewed
   origin, reject redirects to unapproved origins, send no X cookie or credential, and save
   the returned bytes, acquisition time, provider version when available, and SHA-256.
4. Use official X oEmbed only as a single-post anchor/corroboration check. Its success cannot
   prove thread completeness, and its HTML is never trusted as executable application UI.
5. Design Firefox fallback as **passive capture only**: user-initiated, observing responses
   already loaded by normal browsing. It sends no extra X request, auto-scrolls or clicks
   nothing, exports no browser profile or session, and stores no cookie, password or token.
   Observed-only capture is `PARTIAL` unless completeness is independently proven.
6. Exclude Treasury/twscrape-style account pools, passwords, cookie jars, multi-account
   rotation, proxy rotation, automated browser interaction and stealth/anti-detection from
   this phase. Reconsidering any of them requires a new decision and explicit user approval.
7. Normalize every accepted provider into one provider-neutral canonical Twitter capture.
   External ids remain strings; the raw response is immutable evidence; hashes, provider,
   provider version, acquisition time and failure/omission reasons are recorded. Provider
   success is not completeness. Coverage remains honestly `PASS`, `PARTIAL` or `FAIL`.
8. The Phase 2.2 MVP is public single posts and same-author self-threads that the chosen path
   can actually prove. Replies by other accounts, private/bookmarked/account-only material,
   engagement scraping and recursive fetching of linked pages are out of scope. Quotes are
   separate cited sources; media are metadata/URLs/alt text unless a later approved task adds
   binary preservation. Edited, deleted, withheld and unavailable posts must be represented
   explicitly rather than silently omitted.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Official paid X API as the required path | The user cannot currently pay; making it mandatory would make the phase unusable. No payment or regional restriction is to be circumvented. |
| Adopt `x-cli` immediately | Its current behaviour, regional reach, completeness, maintenance risk and AGPL boundary must be measured before it enters the product or build. |
| FxTwitter as the silent/default provider | It transfers requested post ids to a third party, adds availability risk, and cannot be assumed to satisfy X policy. It remains explicit opt-in fallback. |
| Treasury or twscrape as the default | Their account/session and rotation patterns create unnecessary credential, account-ban and maintenance risk for this product. Treasury remains research input, not an implementation to transplant. |
| Fully automated Firefox scraping | Automation and evasion broaden risk and make completeness brittle. The approved browser path only imports responses the user already loaded. |
| HTML scraping as the canonical model | Page markup is presentation and changes independently of the knowledge contract. Providers must end at a source-neutral capture boundary. |

## Consequences

**Positive**

- The likely best no-payment path is tested where it must work before the codebase depends on
  it.
- Credentials and browser sessions stay outside canonical data and outside normal operation.
- A provider can fail or be replaced without rewriting extraction, indexing or the UI.
- Partial conversations and unavailable posts remain visible facts instead of false success.

**Negative / accepted costs**

- Twitter implementation does not start until the qualification spike produces evidence.
- Supporting more than one acquisition route adds fixtures and failure states.
- The useful no-payment routes are unofficial or incomplete and may break when X changes.
- FxTwitter opt-in leaks the requested post id and request metadata to its operator.

**Neutral**

- This ADR does not conclude that an unofficial route complies with X's terms.
- It does not add a runtime dependency, provider command, schema or browser extension by
  itself; those belong to `T-222` and later tasks.
- `WORKFLOW.md` continues to describe the implemented YouTube workflow until Phase 2.2 ships
  and its validators exist.

## Invariants this decision must preserve

- No X password, cookie, bearer token, browser profile or session export enters `output/`,
  logs, fixtures, configuration committed to git, or error messages.
- No provider may turn absence, an unloaded reply, a tombstone or an outage into `PASS`.
- Raw acquired bytes are immutable and their recorded digest is verified before success.
- Extraction and UI consume the canonical capture, never a provider-specific response.
- Public identifiers remain strings; JavaScript number coercion must never touch an X id.
- A new external service or credential-bearing path requires explicit user approval.
- The zero-dependency core remains intact; optional tools are loaded only in their dispatch
  branch and are absent from a core installation.

## References

- `x-cli`: <https://github.com/tamnd/x-cli>
- `x-cli` reading guide: <https://x-cli.tamnd.com/guides/reading-tweets/>
- `x-cli` account tiers: <https://x-cli.tamnd.com/guides/your-account/>
- FxTwitter API: <https://docs.fxembed.com/api/introduction/>
- FxTwitter thread endpoint: <https://docs.fxembed.com/api/twitter/operations/2threadid/>
- FxTwitter conversation endpoint: <https://docs.fxembed.com/api/twitter/operations/2conversationid/>
- X oEmbed: <https://docs.x.com/x-for-websites/oembed-api>
- X ids: <https://docs.x.com/fundamentals/x-ids>
- X Terms of Service: <https://x.com/en/tos>
- `twscrape`: <https://github.com/vladkens/twscrape>
- `xTap` passive-capture reference: <https://github.com/mkubicek/xTap>
