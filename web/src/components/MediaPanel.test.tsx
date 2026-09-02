/**
 * `T-114`: the embed, the seek, and the rule that a local media file must
 * never be assumed.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Artifact, Source } from "../api/contract";
import { renderApp } from "../test/render";
import { EMBED_HOSTS, MediaPanel, embedUrl } from "./MediaPanel";

const SOURCE = {
  schema_version: "1.0",
  id: "youtube:fixture-pass",
  source_type: "youtube",
  external_id: "fixture-pass",
  url: "https://www.youtube.com/watch?v=fixture-pass",
  title: "A fixture",
  canonical_dir: "output/pass-run",
  adapter: { name: "youtube", version: "1.0" },
  status: { validation: "PASS", coverage: "PASS", overall: "PASS" },
} as Source;

const EXTERNAL_VIDEO = {
  schema_version: "1.0",
  id: "youtube:fixture-pass:video",
  source_id: "youtube:fixture-pass",
  kind: "video",
  role: "external",
  path: null,
  url: "https://www.youtube.com/watch?v=fixture-pass",
  immutable: false,
  available: true,
} as Artifact;

describe("embedUrl", () => {
  it("builds an allowlisted embed from the source's own external id", () => {
    const url = embedUrl(SOURCE, 42);
    expect(url).not.toBeNull();
    expect(url?.startsWith(`${EMBED_HOSTS.youtube}/embed/fixture-pass`)).toBe(true);
    expect(new URL(url as string).searchParams.get("start")).toBe("42");
    expect(new URL(url as string).searchParams.get("enablejsapi")).toBe("1");
  });

  it("omits start when no timestamp was requested, rather than sending zero", () => {
    expect(new URL(embedUrl(SOURCE, null) as string).searchParams.has("start")).toBe(false);
  });

  it("has no embed for a source type outside the allowlist", () => {
    expect(embedUrl({ ...SOURCE, source_type: "medium" }, null)).toBeNull();
  });
});

describe("MediaPanel", () => {
  it("says there is no local media rather than rendering a dead player", () => {
    renderApp(<MediaPanel source={SOURCE} artifacts={[EXTERNAL_VIDEO]} seek={null} />);
    expect(screen.getByText(/No local media file is indexed/)).not.toBeNull();
    expect(document.querySelector("video")).toBeNull();
  });

  it("requests nothing from the embed host until the user asks", () => {
    renderApp(<MediaPanel source={SOURCE} artifacts={[EXTERNAL_VIDEO]} seek={null} />);
    expect(document.querySelector("iframe")).toBeNull();
    fireEvent.click(screen.getByText("Load the embedded player"));
    const frame = document.querySelector("iframe");
    expect(frame).not.toBeNull();
    expect(frame?.getAttribute("src")?.startsWith(EMBED_HOSTS.youtube as string)).toBe(true);
  });

  it("carries a pending seek into the frame's start parameter", () => {
    const { rerender } = renderApp(
      <MediaPanel source={SOURCE} artifacts={[EXTERNAL_VIDEO]} seek={null} />,
    );
    rerender(
      <MediaPanel source={SOURCE} artifacts={[EXTERNAL_VIDEO]} seek={{ seconds: 30, nonce: 1 }} />,
    );
    expect(screen.getByText(/0:30/)).not.toBeNull();
    fireEvent.click(screen.getByText("Load the embedded player"));
    expect(
      new URL(document.querySelector("iframe")?.getAttribute("src") as string).searchParams.get(
        "start",
      ),
    ).toBe("30");
  });

  it("plays a genuinely local medium through the byte channel", () => {
    const local = {
      ...EXTERNAL_VIDEO,
      id: "youtube:fixture-pass:local",
      role: "canonical",
      path: "output/pass-run/media.mp4",
      url: null,
    } as Artifact;
    renderApp(<MediaPanel source={SOURCE} artifacts={[local]} seek={null} />);
    const video = document.querySelector("video");
    expect(video?.getAttribute("src")).toBe(
      "/api/media/youtube%3Afixture-pass%3Alocal",
    );
  });

  it("offers the source's own URL as an explicit external open", () => {
    renderApp(<MediaPanel source={SOURCE} artifacts={[EXTERNAL_VIDEO]} seek={null} />);
    const link = screen.getByText("Open on the source site") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(SOURCE.url);
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
