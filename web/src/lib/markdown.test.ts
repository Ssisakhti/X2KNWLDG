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
