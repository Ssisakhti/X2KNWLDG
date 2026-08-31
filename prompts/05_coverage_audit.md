# Pass 5 — Coverage audit and repair

Input: one coverage window, its caption text, and all knowledge units mapped to that time span.

Audit semantic coverage. Account for every meaningful item in the window.

- If meaningful content is represented, mark the window `covered`.
- If meaningful content is missing, mark it `uncovered` and return missing source-unit candidates.
- If content is intentionally omitted, use only an allowed omission label from `src/x2knwldg/constants.py`.
- `other_explained` requires a note.
- Never classify a meaningful caveat, limitation, number, example, disagreement, or process step as filler.
- Never claim `PASS` while any important item is unresolved.

After repairs, return a complete coverage object with contiguous windows spanning the entire transcript. Overall `PASS` requires every window to be covered or explicitly accounted for and zero unresolved important items.

