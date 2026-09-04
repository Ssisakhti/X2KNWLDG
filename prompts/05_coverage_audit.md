# Pass 5 — Coverage audit and repair

Input: one coverage window, its caption text, and all knowledge units mapped to that time span.

Audit semantic coverage. Account for every meaningful item in the window.

Write every human-readable coverage note, explanation, missing-unit candidate, summary,
and analysis in Persian. Use Persian technical terms with the English term in parentheses
when useful. Keep controlled omission labels, statuses, IDs, and schema keys in their
canonical machine-readable form. Never translate an evidence excerpt or source metadata.

- If meaningful content is represented, mark the window `covered`.
- If meaningful content is missing, mark it `uncovered` and return missing source-unit candidates.
- If content is intentionally omitted, use only an allowed omission label from `src/x2knwldg/constants.py`.
- `other_explained` requires a note.
- Never classify a meaningful caveat, limitation, number, example, disagreement, or process step as filler.
- Never claim `PASS` while any important item is unresolved.
- A window holding only `non_speech` captions (`"text": ""`) has no speech to cover. Mark it `omitted` with `other_explained` and a note saying the span carries no speech — there is no silence-specific omission reason in `constants.py`. Do not mark it `uncovered`, and do not invent units to fill it. Such windows are in the set on purpose: dropping their captions is what once shrank a 600-second video to an audited 5 seconds.

## Repair loop — hard cap of three attempts

This pass is the loop. Repair is bounded, and the bound is counted here:

1. Create the missing source-grounded units for the uncovered windows.
2. Normalize and deduplicate again (pass 2).
3. Re-audit **only the affected windows**.
4. **Stop after three total audit attempts.** The initial audit is attempt 1, so at most two
   repair rounds follow it. Counting is per run, across the whole transcript — not per window.
5. If important content is still unresolved at the cap, report `PARTIAL`. Never a fourth attempt,
   and never `PASS`.

Record what stayed uncovered and why; an unresolved window with a stated reason is an honest
`PARTIAL`, and a silent one is not.

**Report the count. `audit_attempts` is a required field of the coverage object** — an integer
from 1 to 3 in the bundle you hand to `apply-bundle`, and it must be the number of audits you
actually ran, not the number you wish you had needed. The validator rejects a coverage document
that omits it, that reports more than the cap, or that claims `PASS` on zero attempts. Zero is
reserved for the never-audited coverage document the pipeline scaffolds at import; if you are
running this pass, your answer is at least 1.

(The cap is `MAX_AUDIT_ATTEMPTS` in `src/x2knwldg/constants.py`, and is also stated in
`WORKFLOW.md` §4, `CLAUDE.md`, and the MCP server's workflow description. If they ever
disagree, `WORKFLOW.md` is the source of truth.)

## Output

After repairs, return a complete coverage object with contiguous windows spanning the entire transcript. Overall `PASS` requires every window to be covered or explicitly accounted for and zero unresolved important items.

Each entry of a window's `omitted_items` is an object with **these key names** (D-092 — they were
stated nowhere this prompt sends you, and `apply-bundle` rejects an entry that uses others):

```json
{
  "type": "sponsor",
  "note": "بخش معرفی حامی مالی است و محتوای دانشی قابل استخراجی ندارد."
}
```

- `type` — one of the omission labels in `src/x2knwldg/constants.py` (`OMISSION_REASONS`). Not
  `reason`, not `category`: `apply-bundle` reads `type`, and anything else is rejected as
  `invalid_omission_reason` naming `null`.
- `note` — free text. **Required when `type` is `other_explained`**, and rejected as
  `missing_other_explanation` without it. Write one for every omission anyway: the note is what
  makes an omission auditable rather than merely declared.
