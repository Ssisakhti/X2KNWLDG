# `web/` — the Knowledge Canvas frontend

Scaffolded by `T-008`. **Track C (`T-109`–`T-114`) owns everything in here from now on.**

What `T-008` deliberately did *not* do: install Vite, React, a router, or design
tokens. `T-109` chooses those, and handing it a scaffold it did not choose is the
same mistake `D-029` avoided on the Python side. What is here is the minimum that
makes the frozen contract compile — nothing more.

| File | Holds |
|---|---|
| `package.json` | `typescript` as the only dependency, and the `typecheck` script CI runs |
| `tsconfig.json` | `strict`, `noEmit`, and `skipLibCheck: false` — see below |
| `src/api/contract.ts` | The single re-export of the generated API types |

## The API types

The frontend's types are **generated** from
[`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md) into a committed
`schemas/api/v1/types.d.ts` (D-029). Import them from `src/api/contract.ts`:

```ts
import type { Source, SearchResponse, Endpoints } from "./api/contract";
```

Never hand-edit the generated file, and never reach up the tree from application
code — `contract.ts` is the one place that path lives. Regenerate with:

```bash
python tools/generate_api_types.py          # rewrite
python tools/generate_api_types.py --check  # fail if stale
```

`tests/test_api_types.py` fails if the committed file drifts from the generator.

## Why `skipLibCheck` is `false`

TypeScript's default is to skip `.d.ts` files, which would skip the only file in
this project that CI is here to check. With it off — and with the declarations
listed as a root file in `include` — `npm run typecheck` type-checks the
generated contract itself. That is the whole of risk **R17**: until `T-008` there
was no Node in CI, so nothing proved the generated text compiled.

If `skipLibCheck` is ever turned on, R17 reopens silently.

## Commands

```bash
cd web
npm ci             # reproducible install from package-lock.json
npm run typecheck  # tsc --noEmit — the check CI runs
```

`node_modules/`, `.vite/`, and `*.tsbuildinfo` are ignored at the repository
root; `package-lock.json` is committed so `npm ci` and CI agree.

## Boundaries this directory inherits

From [ADR 0001](../docs/adr/0001-local-web-ui.md) — these are not style
preferences:

- `output/<id>/raw/` is never written. The UI reads canonical files only.
- Run status comes from `validation.json` and `coverage.json` alone. Never
  recompute it, never coerce `PARTIAL`/`FAIL` toward `PASS`.
- Never render an invented timestamp, quote, evidence excerpt, confidence, or
  coverage value. A missing value is missing.
- Provenance (`source` / `derived` / `user`) is never signalled by colour alone —
  icon, label, or line style must also distinguish it (invariant 10).
- English is the default UI language, and `dir` switching plus logical CSS
  properties belong in the first component, not a retrofit (D-012, `T-110`).
