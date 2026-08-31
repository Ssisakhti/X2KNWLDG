# ADR 0003 — Externally supplied identifiers are rejected, never rewritten

- **Status:** Accepted
- **Date:** 2026-08-31
- **Decision ledger:** D-020, with D-030 for how the refusal is rendered over HTTP
  (`KNOWLEDGE_CANVAS_PLAN.md` §19). No new `D-0xx` is minted: D-020 already *is* this
  decision, and a second row for the same fact is the drift D-026 warns about. What this
  ADR adds is the reasoning, the prohibition, and the correction of a contradicting
  instruction.
- **Supersedes:** [ADR 0001](0001-local-web-ui.md) **invariant 8 only.** ADR 0001 stays
  `Accepted`; nothing else in it is affected.
- **Superseded by:** none

## Context

[ADR 0001](0001-local-web-ui.md) invariant 8 told the implementer of `T-108`
("path-traversal hardening") that *"every source id arriving over HTTP goes through
`pipeline._safe_identifier`"*, and that `query.py` and `mcp_server.py` *"have no such
guard"*.

Every clause of that is now wrong, and the middle one was wrong when it was written.

1. **It names the wrong function for the job.** `_safe_identifier` guards the *creating*
   side — it decides whether a run may be filed at an id. At the time invariant 8 was
   written it did so by rewriting: `../other` became `_other`. Pointed at a **lookup**,
   that is precisely the wrong shape. A lookup that rewrites hands the caller a different
   run than the one asked for and reports no traversal at all. D-020 exists to draw that
   line, and ADR 0001 invariant 8 crossed it in the one document `T-108`'s implementer
   would read first.

   Naming a function is the weaker half of the rule anyway. What a boundary needs is a
   *behaviour* — refuse, and prove the resolved path stays under the root — and the
   invariant asserted a function instead. This ADR states the behaviour, so it stays true
   when either function's internals change.
2. **The guard it says is missing exists.** Verified 2026-08-31 by reading the code:
   `query.search_knowledge` resolves a caller-supplied `video_id` through
   `pipeline.resolve_run_dir`, and `mcp_server._run_dir` — the single funnel every MCP
   tool argument naming a run passes through — does the same. `artifacts._checked_video_id`
   applies `ids.is_id_part` to a run's *own* declared id before it becomes a filename.
   Risk R14 is recorded as mitigated on exactly this basis, with traversal cases in
   `tests/test_core_pipeline.py::RunLookupTests`. An implementer told those call sites are
   unguarded and must not be copied would avoid the one pattern that is right.
3. **Its line citation had rotted.** It cited `pipeline.py:42`; by the commit where this was
   audited (`441fe9f`) that line was blank and `_safe_identifier` had moved well down the
   file. A reader who followed the citation found nothing and had no way to tell whether the
   function or the number was wrong. See the note on citations at the end.

The cost of leaving this in place is not hypothetical. `T-108` is `S`-flagged, single-owner,
and its whole subject is this check. An agent that follows its own ADR would reopen the
hole the ADR exists to close, and would have a written justification for doing so.

`docs/adr/README.md` states the project's rule for this situation: *"An accepted ADR is
never edited to change its decision. Write a new ADR that supersedes it and update the old
file's status line only."* This ADR is that.

## Decision

1. **Every identifier that arrives from outside the process is resolved by
   `pipeline.resolve_run_dir`, which refuses an unsafe id.** "Outside the process" means an
   HTTP path parameter or query value (`T-108` and every route of `T-105`–`T-107`), an MCP
   tool argument, a CLI argument naming an existing run, and any id read back out of a file
   the pipeline did not write in this process. The refusal is the point: the caller is told
   the id is unusable, and nothing is read.
2. **No sanitiser stands in for that check.** No code path may make an externally supplied
   id safe by *transforming* it — not `_safe_identifier`, not a `replace`, not a `strip`,
   not a regex substitution, not `os.path.basename`. A transformation converts "this
   request is invalid" into "this request was about something else", which is the failure
   mode, not a mitigation. This is a rule about behaviour, not about any one function's
   current implementation: a sanitiser that is later hardened into a rejector is still not
   the boundary check, because the boundary needs a resolver that also proves containment
   under the output root.
3. **The lookup rule has one implementation.** `resolve_run_dir` is it, and it delegates
   the identifier grammar to `ids.is_id_part` (D-017, D-018) rather than restating it.
   Adding a second way to resolve a run is a change to this ADR first.
4. **A refused id is reported as refused.** Over HTTP that is `400 invalid_id` (D-030),
   never `404`, and never an empty result. A well-formed id naming nothing is the `404`;
   conflating the two hides an attack behind an ordinary answer.
5. **`_safe_identifier` keeps exactly one job: guarding the id a run is *created* at**
   (`process`, `import_transcript`). It is not exported to the API, the repository, or the
   server, and no route may import it. Whether it refuses or transforms is that side's
   business; either way it is not the boundary check, because it resolves nothing.
6. **`/api/media` is a path check, not an id check.** The record already carries the path;
   it was made project-relative by `adapters.project_relative`, which refuses a path
   outside the project root (R15). Serving it re-checks containment under the root it
   resolves against. It never rebuilds a path from a client-supplied string.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Edit ADR 0001 invariant 8 in place | The README forbids reversing a decision in place, and for a reason that applies here exactly: a future session reading ADR 0001 would find no trace that the rule ever said otherwise, and no reason recorded for the change. Fixing the two stale *facts* in that line is allowed and has been done; replacing its *rule* silently is not |
| Mark ADR 0001 `Superseded by 0003` | Twelve decisions and nine other invariants in it are in force and unaffected. Retiring the whole file to correct one line would strand them |
| Mint a new `D-0xx` for this | It would be a second ledger row saying what D-020 says. §19 is the canonical index of *what* was decided; the ADR carries *why*. Two rows for one decision is how they come to disagree |
| Harden the creating-side check into a rejector and keep invariant 8's wording | Worth doing on its own merits — the two sides should agree about which ids exist — but it does not rescue the invariant. A grammar check is not a boundary check: refusing a badly-formed id is not the same as proving the *resolved* path still sits under the output root, and only the second closes a traversal. `resolve_run_dir` is both, which is why the rule names it |
| Rely on the web framework to normalise the path | A framework normalises *its* routing path. The value that reaches the handler is a decoded string that the handler then joins onto a filesystem root, and encodings, Unicode normalisation, and symlinks all survive that. The check belongs where the join happens |
| Leave it to `T-108` to notice the contradiction | `T-108` is a single-owner task whose entire subject is this check, running while three other tracks are in flight. A correct outcome that depends on an agent disbelieving its own ADR is not a control |

## Consequences

**Positive**

- `T-108` has one instruction, and every document it might reach — this ADR, ADR 0001
  invariant 8, D-020, D-030, R14, `schemas/api/v1/README.md`, and the §10 reuse table —
  now says the same thing.
- The existing `query.py` and `mcp_server.py` call sites become the reference pattern
  rather than a warning, so `T-108` copies working code instead of writing a fourth rule.
- The rule survives the sanitiser changing. It is stated over behaviour at a boundary, not
  over the internals of `_safe_identifier`.
- D-030's `400 invalid_id` gets a decision behind it rather than only a taxonomy row.

**Negative / accepted costs**

- A caller that previously got *some* run back for a malformed id now gets an error. That
  is the intended change, and no such caller should exist.
- One more file in the reading path for `T-108`. Mitigated by the task row naming it.

**Neutral**

- No code changes because of this ADR. It records the rule the code already follows and
  removes the document that disagreed with it.

## Invariants this decision must preserve

1. **`resolve_run_dir` is the only run lookup.** A second implementation is a contract
   change, not a local convenience.
2. **A rewriting sanitiser never touches an externally supplied id.** Creation-time id
   minting is the only place a transformation is legitimate, and its result is the new
   run's own id.
3. **A refusal is visible.** Refused, reported, nothing read. Never a fallback, never a
   default run, never an empty page standing in for an error.
4. **Grammar lives in `ids.py`.** `is_id_part` is the single definition of what may be one
   segment of an identifier (D-017, D-018); no caller re-derives it with its own regex.
5. **Containment is re-checked after resolution.** Grammar alone is not sufficient: the
   resolved path must still be proven to sit under the root it was resolved against.
6. **`T-115` owns the proof.** Path-traversal tests are part of that task; a route added
   without one is not done.

## References

- [ADR 0001](0001-local-web-ui.md) — invariant 8, superseded here
- [ADR 0002](0002-index-repository-seam.md) — invariant 1: `/api/media` streams a record's
  own path through a single safety check
- [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) §15 API rules, §19 (D-017,
  D-018, D-020, D-030)
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) §5 (`T-108`), §6 (D-020), §9 (R14),
  §10 (reuse table)
- [`schemas/api/v1/README.md`](../../schemas/api/v1/README.md) — "An id is resolved, never
  sanitised"
- `src/x2knwldg/pipeline.py` — `resolve_run_dir`, `_safe_identifier`
- `src/x2knwldg/ids.py` — `is_id_part`, `validate_id_part`, `ID_PART_PATTERN`
- `src/x2knwldg/query.py` — `search_knowledge`; `src/x2knwldg/mcp_server.py` — `_run_dir`
- `tests/test_core_pipeline.py::RunLookupTests` — the traversal cases

## A note on citations in this file

This ADR cites **symbol names, not line numbers**. ADR 0001 invariant 8 pointed at
`pipeline.py:42` and, by the time anyone read it, that was a blank line — the fact was
stale before the rule was. A symbol name survives every edit that does not rename or delete
the thing being cited, and when it *is* renamed, a grep finds nothing and the reader knows
the citation is stale instead of being sent to the wrong line with full confidence.
