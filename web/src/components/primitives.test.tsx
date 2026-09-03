/**
 * D-105 — an API-supplied URL is checked before it becomes an `href`.
 *
 * Five sites rendered `hit.source_url`, `source.url` and `artifact.url`
 * straight into `href`, with `target` and `rel` repeated at each one and no
 * scheme check, while the markdown path a few lines away had used
 * `isSafeHref` all along. React 19 neutralises `javascript:` but passes
 * `data:` and `vbscript:` through verbatim; browsers block top-level `data:`
 * navigation, so this was never more than latent — and "the browser refuses
 * it" is not a check the application performed.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import base from "../styles/base.css?raw";

import { renderApp } from "../test/render";
import { ExternalLink, InlineArrow } from "./primitives";

describe("ExternalLink", () => {
  it("links an ordinary URL, with the rel every external link needs", () => {
    renderApp(<ExternalLink href="https://example.com/x">open</ExternalLink>);
    const link = screen.getByText("open") as HTMLAnchorElement;
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe("https://example.com/x");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox",
    "blob:https://example.com/x",
    "filesystem:https://example.com/x",
    "//evil.example.com/x",
  ])("refuses %s and keeps the label as text", (href) => {
    renderApp(<ExternalLink href={href}>the label</ExternalLink>);
    expect(document.querySelector("a")).toBeNull();
    // Nothing is silently dropped: the reader still sees what the record said.
    expect(document.body.textContent).toContain("the label");
    expect(document.body.textContent).toContain(href);
  });

  it.each([null, undefined, ""])("renders the label alone for %s", (href) => {
    renderApp(<ExternalLink href={href}>just text</ExternalLink>);
    expect(document.querySelector("a")).toBeNull();
    expect(document.body.textContent).toContain("just text");
  });
});

describe("the inline arrow", () => {
  /*
   * D-203: `→` (U+2192) was written as its own flex item in three places —
   * the relation row, the Map's relation cue and the legend. Under `dir="rtl"`
   * a `row` reverses its items, so `A → supports → B` correctly renders B
   * first — but U+2192 does not mirror, so both arrows went on pointing
   * right, which in Persian is back at A. The edge direction was shown
   * backwards.
   */
  it("carries the class the stylesheet mirrors, and is not announced", () => {
    renderApp(<InlineArrow />);
    const arrow = document.querySelector(".glyph-inline-forward");
    expect(arrow).not.toBeNull();
    expect(arrow?.textContent).toBe("\u2192");
    // The relation is named in words beside it; "rightwards arrow" says
    // nothing about a graph.
    expect(arrow?.getAttribute("aria-hidden")).toBe("true");
  });

  it("is the only arrow those three surfaces write", () => {
    // A bare U+2192 anywhere in a component is the defect coming back.
    const modules = import.meta.glob("../{components,views}/**/*.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(modules)) {
      if (path.includes(".test.") || path.endsWith("primitives.tsx")) continue;
      for (const line of source.split("\n")) {
        const code = line.trimStart();
        if (code.startsWith("*") || code.startsWith("//")) continue;
        if (code.includes("\u2192")) offenders.push(`${path}: ${code.slice(0, 80)}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the stylesheet mirrors it, and only under rtl", () => {
    expect(base).toMatch(/\.glyph-inline-forward\s*\{[^}]*display:\s*inline-block/);
    expect(base).toMatch(/\[dir="rtl"\]\s+\.glyph-inline-forward\s*\{[^}]*scaleX\(-1\)/);
  });
});
