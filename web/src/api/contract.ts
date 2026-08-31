/**
 * The one place `web/` reaches outside itself for API types.
 *
 * `schemas/api/v1/types.d.ts` is generated from the frozen contract by
 * `tools/generate_api_types.py` and committed (D-029). Application code imports
 * from *here* rather than reaching up the tree itself, so if the contract moves,
 * one line changes and `tests/test_ui_scaffold.py` says so before CI does.
 *
 * `export type *` is fully erased, so no bundler ever has to resolve the path
 * above — only `tsc` does, and `web/tsconfig.json` also lists the declarations
 * as a root file with `skipLibCheck: false`. That is what makes
 * `npm run typecheck` prove the generated file is valid TypeScript (risk R17).
 *
 * Never hand-edit the generated file. Regenerate it:
 *     python tools/generate_api_types.py
 */
export type * from "../../../schemas/api/v1/types";
