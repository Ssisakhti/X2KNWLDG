/**
 * Ambient declarations for the non-TypeScript modules the bundler resolves.
 *
 * Declared here rather than by pulling in a bundler's own ambient types: the
 * type-check program runs with `skipLibCheck: false` so that the generated
 * contract declarations are genuinely checked (risk R17), and every ambient
 * package added to it is checked too. Three lines cost less than that.
 */

declare module "*.css" {
  const url: string;
  export default url;
}

declare module "*.css?raw" {
  const content: string;
  export default content;
}

/**
 * The one bundler API a test reaches for, declared for the same reason as the
 * two above rather than by adding an ambient package.
 *
 * `src/styles/logical.test.ts` needs to read *every* component's source to
 * check D-012 over inline styles, and the whole point of that guard is that a
 * component nobody listed is still checked — so a glob is the mechanism and an
 * explicit list would be the defect. Narrowed to the eager, raw-string form it
 * uses; anything else stays unavailable.
 */
interface ImportMeta {
  glob(
    pattern: string,
    options: { query: "?raw"; import: "default"; eager: true },
  ): Record<string, string>;
}
