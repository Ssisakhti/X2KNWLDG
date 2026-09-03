/**
 * The report renderer, and the sanitisation canvas plan §14 requires.
 *
 * The parser emits data, never HTML, so the safety property is checked where
 * it lives: a `<script>` in a report becomes *text*, and a `javascript:` URL
 * never becomes a link.
 */

import { describe, expect, it } from "vitest";

import { isSafeHref, parseInline, parseMarkdown } from "./markdown";

describe("parseMarkdown", () => {
  it("reads the block shapes a canonical report uses", () => {
    const blocks = parseMarkdown(
      ["# Title", "", "## Metadata", "", "- Source: x", "- Channel: y", "", "Plain text."].join(
        "\n",
      ),
    );
    expect(blocks.map((block) => block.type)).toEqual([
      "heading",
      "heading",
      "list",
      "paragraph",
    ]);
    expect(blocks[2]).toMatchObject({ type: "list", ordered: false });
  });

  it("keeps a fenced code block verbatim", () => {
    const blocks = parseMarkdown("```json\n{\"a\": 1}\n```");
    expect(blocks[0]).toEqual({ type: "code", text: '{"a": 1}', language: "json" });
  });

  it("keeps consecutive lines of one paragraph as soft breaks", () => {
    const blocks = parseMarkdown("**Statement:** a\n**Confidence:** 0.9");
    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.type).toBe("paragraph");
    const paragraph = blocks[0];
    if (paragraph?.type !== "paragraph") throw new Error("expected a paragraph");
    expect(paragraph.children.some((node) => node.type === "break")).toBe(true);
  });

  it("treats raw HTML as the text it is, never as markup", () => {
    const blocks = parseMarkdown("<script>alert(1)</script>");
    expect(blocks[0]).toMatchObject({ type: "paragraph" });
    const paragraph = blocks[0];
    if (paragraph?.type !== "paragraph") throw new Error("expected a paragraph");
    expect(paragraph.children).toEqual([{ type: "text", text: "<script>alert(1)</script>" }]);
  });
});

describe("parseInline", () => {
  it("reads code, emphasis and links", () => {
    expect(parseInline("`x` **b** [t](https://example.org)")).toMatchObject([
      { type: "code", text: "x" },
      { type: "text", text: " " },
      { type: "strong" },
      { type: "text", text: " " },
      { type: "link", href: "https://example.org" },
    ]);
  });
});

describe("isSafeHref", () => {
  it("allows the three schemes a report may link with", () => {
    expect(isSafeHref("https://www.youtube.com/watch?v=x&t=0s")).toBe(true);
    expect(isSafeHref("http://127.0.0.1:8931/api/status")).toBe(true);
    expect(isSafeHref("mailto:someone@example.org")).toBe(true);
  });

  it("refuses everything else", () => {
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
    expect(isSafeHref("data:text/html,<script>alert(1)</script>")).toBe(false);
    expect(isSafeHref("/relative")).toBe(false);
  });
});

describe("two constructs that rendered as literal text (D-203)", () => {
  it("ends a paragraph at a thematic break", () => {
    // A thematic break was not a paragraph terminator, so `---` directly after
    // a paragraph was swallowed into it and rendered inline. A blank line in
    // between happened to work, which is why it survived.
    const blocks = parseMarkdown(["Some prose.", "---", "More prose."].join("\n"));
    expect(blocks.map((block) => block.type)).toEqual(["paragraph", "rule", "paragraph"]);
    const first = blocks[0];
    if (first?.type !== "paragraph") throw new Error("the first block is not a paragraph");
    expect(JSON.stringify(first.children)).not.toContain("---");
  });

  it("still reads a break with a blank line before it", () => {
    const blocks = parseMarkdown(["Some prose.", "", "---", "", "More prose."].join("\n"));
    expect(blocks.map((block) => block.type)).toEqual(["paragraph", "rule", "paragraph"]);
  });

  it("does not mistake a setext-looking list for a break", () => {
    // `- one` is a bullet, not three dashes.
    const blocks = parseMarkdown(["- one", "- two"].join("\n"));
    expect(blocks.map((block) => block.type)).toEqual(["list"]);
  });

  it.each(["objective-c", "c++", "c#", "f#", "asp.net", "ts", ""])(
    "reads a fence whose language is %o",
    (language) => {
      // `\w*` matched no hyphen and no plus, so the opening line, the whole
      // code body and the closing line all fell through to prose — and the
      // code was rendered as paragraphs with its own backticks in them.
      const blocks = parseMarkdown(
        ["```" + language, "int main() { return 0; }", "```"].join("\n"),
      );
      expect(blocks).toHaveLength(1);
      const block = blocks[0];
      if (block?.type !== "code") throw new Error(`\`\`\`${language} is not a fence`);
      expect(block.text).toBe("int main() { return 0; }");
      expect(block.language).toBe(language === "" ? null : language);
    },
  );

  it("leaves a line that only looks like a fence as prose", () => {
    const blocks = parseMarkdown("``` not a language at all\ntext\n");
    expect(blocks.map((block) => block.type)).toEqual(["paragraph"]);
  });

  it("classifies every line, so no input can hang the parser", () => {
    /*
     * Found by the fence tests above, and worse than the rendering fault they
     * were written for: a line that *starts* with three backticks and is not
     * a fence broke the paragraph loop on its first iteration while the block
     * loop declined to consume it, so `parseMarkdown` looped for ever pushing
     * empty paragraphs until the process ran out of memory. ```` ```c++ ````
     * was such a line.
     *
     * The predicates are shared now, so the two loops cannot disagree; this
     * asserts the belt that keeps a future divergence a rendering fault.
     */
    for (const line of ["``` not a language", "```py extra", "~~~", "```` four"]) {
      const blocks = parseMarkdown(`${line}\ntext\n`);
      expect(blocks.length).toBeGreaterThan(0);
      expect(blocks.length).toBeLessThan(6);
      // Nothing is dropped: the line is somewhere in the output.
      expect(JSON.stringify(blocks)).toContain(line.trim().slice(0, 3));
    }
  });
});