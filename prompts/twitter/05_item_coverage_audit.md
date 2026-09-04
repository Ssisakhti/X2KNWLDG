# Pass 5 (Twitter) — Item coverage audit and repair

Input: one **coverage item** from `coverage.json`, its post's `text.canonical`,
and every knowledge unit citing that post.

Coverage is item-based, not time-based. There are no windows, no timeline and no
gap to walk: the capture *enumerates* which posts it included, so the audit is a
set comparison and it is exact. Every included post is covered, omitted with a
reason, or unresolved.

Write every human-readable coverage note, explanation, missing-unit candidate, summary,
and analysis in Persian. Use Persian technical terms with the English term in parentheses
when useful. Keep controlled omission labels, statuses, IDs, and schema keys in their
canonical machine-readable form. Never translate an evidence excerpt or source metadata.

- If the post's meaningful content is represented, mark the entry `covered`.
- If meaningful content is missing, mark it `uncovered` and return the missing
  source-unit candidates.
- If content is intentionally omitted, use only an allowed omission reason from
  `src/x2knwldg/constants.py`.
- `other_explained` requires a note.
- A unit may only be named under the entry for **the post it cites**. A claim
  about post A listed under post B leaves B looking covered with no evidence of
  its own, and is refused.
- Never claim `PASS` while any item is unresolved.

Three states the pipeline sets for you. Do not overwrite them:

- **`omitted` with `source_unavailable`** — the post was never observed, so
  there is no text to audit. Produce no units for it and do not mark it
  `covered`.
- **`unresolved` with `capture_text_truncated`** — part of the post's text was
  withheld by the acquiring surface. Audit what is there; the gap stays
  unresolved because a corroborating route can close it, and it holds the run
  off `PASS`.
- **`excluded_items`** — a third-party parent, or descendants no credential-free
  route can enumerate. These were never candidates. They are named with the
  capture's own reason and are not audit entries: do not add coverage for them,
  and do not count them as covered or omitted.

## `PASS` is impossible while the capture is not whole

A run is never more complete than the evidence under it. If the capture's own
`coverage.status` is `PARTIAL` or `FAIL`, the audit may still be complete over
what was captured — mark the entries honestly — but the coverage document stays
`PARTIAL`. The audit being complete and the capture being complete are different
claims, and the validator will refuse a coverage `PASS` over an incomplete
capture.

## Repair loop — hard cap of three attempts

Identical to `prompts/05_coverage_audit.md`, because the cap is a rule about the
workflow and not about what a coverage entry is:

1. Create the missing source-grounded units for the uncovered items.
2. Normalize and deduplicate again (`prompts/02_normalize_deduplicate.md`).
3. Re-audit **only the affected items**.
4. **Stop after three total audit attempts.** The initial audit is attempt 1, so
   at most two repair rounds follow it. Counting is per run.
5. If important content is still unresolved at the cap, report `PARTIAL`. Never
   a fourth attempt, and never `PASS`.

**Report the count. `audit_attempts` is a required field** — a document that
will not say how many audits it took cannot be checked against the cap, and an
unverifiable claim is a failure.
