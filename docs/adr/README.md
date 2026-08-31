# Architecture Decision Records

This directory holds the architecture decisions for X2KNWLDG, one file per decision.

An ADR captures a decision that is **expensive to reverse** — something that shapes data contracts, storage boundaries, dependency surface, or the module layout. Routine implementation choices do not need one.

## Relationship to the other documents

There are three decision surfaces; they are not redundant.

| Where | Holds | Granularity |
|---|---|---|
| `docs/adr/` | The reasoning: context, alternatives, consequences | One file per decision |
| [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) §19 | The decision *ledger* — `D-0xx` IDs, one row each | One line per decision |
| [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) §6 | Decisions added after the plan was written, staged for §19 | One line per decision |

**Rule:** the §19 table stays the canonical index of *what* was decided. An ADR explains *why* and records what was rejected. When an ADR covers one or more `D-0xx` rows, it lists them under `Decision ledger` in its header, and the §19 rows point back at the ADR file.

## Language

ADRs are written in **English**, like all project documentation (D-014). Persian is reserved for the application UI and for knowledge content extracted for the user.

## Naming and numbering

```
docs/adr/NNNN-kebab-case-title.md
```

- `NNNN` is a zero-padded, monotonically increasing integer. Never reuse or renumber.
- `0000-template.md` is the template and is not a decision.

## Status values

| Status | Meaning |
|---|---|
| `Proposed` | Written, not yet agreed |
| `Accepted` | In force; build to it |
| `Superseded by NNNN` | Replaced. The file stays; it is history |
| `Deprecated` | No longer applies, with no direct replacement |

An accepted ADR is **never edited to change its decision**. Write a new ADR that supersedes it and update the old file's status line only. Correcting a typo or a stale fact is fine; reversing the decision in place is not.

## Writing one

1. Copy `0000-template.md` to the next number.
2. Keep it short. Context and consequences carry the value; the decision itself is usually a few lines.
3. State the alternatives you rejected and why — that is the part future sessions cannot reconstruct.
4. Add the `D-0xx` row(s) to §19 of the canvas plan, referencing the ADR.
5. Do not restate architecture that already lives in the canvas plan; link to the section instead.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-local-web-ui.md) | Local-first web layer for the Knowledge Canvas | Accepted |
