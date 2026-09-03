/**
 * The frontend lint gate (D-203).
 *
 * There was no ESLint anywhere: no config, no dependency, no script, no CI
 * step — and nine `// eslint-disable-next-line react-hooks/exhaustive-deps`
 * comments across `web/src`. Every one of those suppressed nothing, because
 * nothing ran; and the rule they name is the one rule this code repeatedly
 * needed to silence, which makes it the last rule that should have been
 * unchecked. Exactly the asymmetry D-114 created the Python lint job to fix,
 * mirrored on the other half of the repository.
 *
 * **Deliberately narrow.** This is not a style gate: `tsc --strict` with
 * `noUnusedLocals`, `noUnusedParameters` and `noUncheckedIndexedAccess`
 * already covers what a type checker can, and a second opinion about
 * formatting would be noise. What it adds is the class of rule a type checker
 * cannot express — the hooks rules, and the handful of correctness rules about
 * things that are legal TypeScript and always a mistake.
 *
 * `react-hooks/exhaustive-deps` is a **warning**, and that is the honest
 * setting for this codebase rather than a way of avoiding the work: nine of
 * its suppressions are load-bearing and documented at the site, because a
 * graph mutated in place (D-118) and a snapshot identified by a revision
 * (D-128) are dependencies the rule cannot see. What matters is that the rule
 * runs, so a *new* incomplete dependency list is reported instead of being
 * invisible — and that a suppression that stops being needed shows up as a
 * useless directive, which `reportUnusedDisableDirectives` makes an error.
 */

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // `dist/` is build output and `node_modules/` is not ours. The browser
    // gate and the capture scripts are linted: they are the code that produces
    // the acceptance evidence, and D-156's lesson is that the files nothing
    // checks are the ones that rot.
    ignores: ["dist/**", "node_modules/**", "test-results/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    linterOptions: {
      // A directive that suppresses nothing is a claim about the code that is
      // no longer true. Nine of them survived here because nothing ran.
      reportUnusedDisableDirectives: "error",
    },
    rules: {
      // The two rules a type checker cannot express, and the reason this gate
      // exists at all.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // `tsc` owns unused locals and parameters; a second reporter for them is
      // two voices saying one thing.
      "@typescript-eslint/no-unused-vars": "off",
      "no-unused-vars": "off",

      // Legal TypeScript, always a mistake.
      "no-console": ["error", { allow: ["error", "warn"] }],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-constant-binary-expression": "error",
      "no-self-compare": "error",
      "no-unmodified-loop-condition": "error",
      "require-atomic-updates": "off",

      // `any` is checked by `tsc --strict`; the explicit-any rule fires on the
      // deliberate `unknown`-adjacent boundaries this codebase documents.
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    // A test may say anything to the console and may hold a non-null
    // assertion: both are how a fixture states what it assumes.
    files: ["**/*.test.{ts,tsx}", "src/test/**", "browser/**"],
    rules: {
      "no-console": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
  {
    // A capture or measurement script's *output* is its whole product: these
    // are run by hand and by the gate to produce the acceptance evidence, and
    // printing it is the job. They are still linted for everything else, which
    // is the half D-156 was about.
    files: ["scripts/**/*.ts"],
    rules: { "no-console": "off" },
  },
  {
    // `vite.config.ts` declares vitest's config types with a triple-slash
    // reference on purpose: `tsconfig.json` sets `types: []` so that
    // `skipLibCheck: false` genuinely checks the generated contract
    // declarations (risk R17, `src/env.d.ts`), and an `import` of the same
    // types would pull the ambient package back in.
    files: ["vite.config.ts"],
    rules: { "@typescript-eslint/triple-slash-reference": "off" },
  },
);
