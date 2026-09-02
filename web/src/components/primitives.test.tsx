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

import { renderApp } from "../test/render";
import { ExternalLink } from "./primitives";

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
