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
