/**
 * A small Markdown parser that produces *data*, never HTML.
 *
 * Canvas plan §14 requires untrusted raw HTML and Markdown to be sanitised.
 * The cheapest correct sanitiser is not to have an HTML path at all: this
 * parser emits a node tree, the renderer hands every leaf to React as text,
 * and no code in this project passes report bytes to `innerHTML`. Raw HTML in
 * a report therefore renders as the characters the author wrote, which is both
 * safe and honest.
 *
 * It is deliberately small. It covers what `report.md` actually contains --
 * headings, lists, emphasis, inline code, fenced code, block quotes, links --
 * and renders anything else as the text it is, rather than guessing.
 */

export type Inline =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] }
  | { type: "break" };

export type Block =
  | { type: "heading"; level: number; children: Inline[] }
  | { type: "paragraph"; children: Inline[] }
  | { type: "code"; text: string; language: string | null }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "quote"; children: Inline[] }
  | { type: "rule" };

/** Schemes a link may be rendered as clickable with. Everything else stays text. */
const SAFE_SCHEMES = ["http:", "https:", "mailto:"];

export function isSafeHref(href: string): boolean {
  try {
    return SAFE_SCHEMES.includes(new URL(href).protocol);
  } catch {
    return false;
  }
}

// D-106: the link arm was `\([^)\s]+\)`, which stops at the *first* `)` — so
// a Wikipedia-style URL (`.../wiki/Ruby_(programming_language)`) was cut at
// the inner paren, and both the label and the href came out wrong: the link
// pointed somewhere real and different, which is worse than not linking. One
// level of balanced parens is what CommonMark allows without escaping and is
// what real URLs use.
const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]*\]\((?:[^()\s]|\([^()\s]*\))*\))/;

export function parseInline(text: string): Inline[] {
  const nodes: Inline[] = [];
  let rest = text;
  while (rest !== "") {
    const match = INLINE.exec(rest);
    if (match === null || match.index === undefined) {
      nodes.push({ type: "text", text: rest });
      break;
    }
    if (match.index > 0) nodes.push({ type: "text", text: rest.slice(0, match.index) });
    const token = match[0];
    if (token.startsWith("`")) {
      nodes.push({ type: "code", text: token.slice(1, -1) });
    } else if (token.startsWith("**")) {
      nodes.push({ type: "strong", children: parseInline(token.slice(2, -2)) });
    } else if (token.startsWith("*")) {
      nodes.push({ type: "em", children: parseInline(token.slice(1, -1)) });
    } else {
      const split = token.indexOf("](");
      const label = token.slice(1, split);
      const href = token.slice(split + 2, -1);
      nodes.push({ type: "link", href, children: parseInline(label) });
    }
    rest = rest.slice(match.index + token.length);
  }
  return nodes;
}

/** Inline nodes for a paragraph, with source line breaks kept as soft breaks. */
function parseParagraph(lines: readonly string[]): Inline[] {
  const nodes: Inline[] = [];
  lines.forEach((line, position) => {
    if (position > 0) nodes.push({ type: "break" });
    nodes.push(...parseInline(line));
  });
  return nodes;
}

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    const fence = /^```(\w*)\s*$/.exec(line);
    if (fence !== null) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index] ?? "")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      index += 1;
      blocks.push({ type: "code", text: body.join("\n"), language: fence[1] || null });
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading !== null) {
      blocks.push({
        type: "heading",
        level: (heading[1] ?? "#").length,
        children: parseInline(heading[2] ?? ""),
      });
      index += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ type: "rule" });
      index += 1;
      continue;
    }

    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet !== null || numbered !== null) {
      const ordered = bullet === null;
      const items: Inline[][] = [];
      while (index < lines.length) {
        const current = lines[index] ?? "";
        const next = ordered
          ? /^\s*\d+[.)]\s+(.*)$/.exec(current)
          : /^\s*[-*+]\s+(.*)$/.exec(current);
        if (next === null) break;
        items.push(parseInline(next[1] ?? ""));
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const body: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index] ?? "")) {
        body.push((lines[index] ?? "").replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", children: parseParagraph(body) });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? "";
      if (
        current.trim() === "" ||
        /^(#{1,6})\s+/.test(current) ||
        /^```/.test(current) ||
        /^\s*[-*+]\s+/.test(current) ||
        /^\s*\d+[.)]\s+/.test(current) ||
        /^>\s?/.test(current)
      ) {
        break;
      }
      paragraph.push(current);
      index += 1;
    }
    blocks.push({ type: "paragraph", children: parseParagraph(paragraph) });
  }

  return blocks;
}
