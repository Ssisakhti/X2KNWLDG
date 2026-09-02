/**
 * D-023 and D-028 in the UI: a caption hit has no entity to address, and must
 * not be given one.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp, jsonFetch } from "../test/render";
import { SearchResults } from "./SearchResults";

const CAPTION_HIT = {
  type: "transcript_caption",
  video_id: "fixture-pass",
  title: "A fixture",
  caption_id: "cap_000002",
  content: "Coverage is audited window by window.",
  start_sec: 30,
  end_sec: 60,
  source_url: "https://www.youtube.com/watch?v=fixture-pass&t=30s",
  source_id: "youtube:fixture-pass",
};

const UNIT_HIT = {
  type: "knowledge_unit",
  video_id: "fixture-pass",
  title: "A fixture",
  id: "KU-000001",
  kind: "principle",
  source_class: "source",
  content: "A knowledge unit must carry the evidence it rests on.",
  confidence: 0.9,
  start_sec: 0,
  source_url: "https://www.youtube.com/watch?v=fixture-pass&t=0s",
  global_id: "youtube:fixture-pass:KU-000001",
  source_id: "youtube:fixture-pass",
};

function respondWith(hits: unknown[], total: number | null = null) {
  vi.stubGlobal(
    "fetch",
    jsonFetch(() => ({
      body: {
        api_version: "v1",
        schema_version: "1.0",
        query: "coverage",
        data: hits,
        page: { limit: 25, next_cursor: null, total },
      },
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("search results", () => {
  it("says a caption is not addressable, and links only to its source and timestamp", async () => {
    respondWith([CAPTION_HIT]);
    renderApp(<SearchResults query="coverage" includeTranscript />);

    await waitFor(() => expect(screen.getByText(/not an addressable entity/)).not.toBeNull());
    const card = document.querySelector('[data-hit-type="transcript_caption"]');
    expect(card).not.toBeNull();
    // No global id is rendered for a caption, because there is none.
    expect(card?.textContent).not.toContain("youtube:fixture-pass:cap");
    const links = [...(card?.querySelectorAll("a") ?? [])].map((a) => a.getAttribute("href"));
    expect(links).toContain("https://www.youtube.com/watch?v=fixture-pass&t=30s");
    // D-069: the internal link carries the offset the hit was found at, so the
    // Reader can arrive there. Before it did, this read
    // `/sources/youtube%3Afixture-pass` and the `0:30` was dropped at the
    // click -- the scenario was satisfied only by leaving for YouTube.
    expect(links).toContain("/sources/youtube%3Afixture-pass?tab=transcript&t=30");
    // The two spellings stay distinct on purpose: `t=30` in, `&t=30s` out.
    expect(links.filter((href) => href?.includes("t=30s"))).toHaveLength(1);
  });

  it("sends a knowledge unit hit to the units tab", async () => {
    respondWith([UNIT_HIT]);
    renderApp(<SearchResults query="coverage" includeTranscript />);
    await waitFor(() =>
      expect(document.querySelector('[data-hit-type="knowledge_unit"]')).not.toBeNull(),
    );
    const card = document.querySelector('[data-hit-type="knowledge_unit"]');
    const links = [...(card?.querySelectorAll("a") ?? [])].map((a) => a.getAttribute("href"));
    // No `t`: a unit hit is addressed by the tab it lives on, not by an
    // offset. Some units state no locator at all, and inventing one to make
    // the link uniform is exactly what the Reader refuses to render.
    expect(links).toContain("/sources/youtube%3Afixture-pass?tab=units");
  });

  it("renders a knowledge unit hit with its own global id", async () => {
    respondWith([UNIT_HIT]);
    renderApp(<SearchResults query="coverage" includeTranscript />);
    await waitFor(() =>
      expect(screen.getByText("youtube:fixture-pass:KU-000001")).not.toBeNull(),
    );
  });

  it("reports an uncounted total as uncounted, never as zero", async () => {
    respondWith([UNIT_HIT], null);
    renderApp(<SearchResults query="coverage" includeTranscript />);
    await waitFor(() => expect(screen.getByText(/did not count/)).not.toBeNull());
  });

  it("distinguishes no results from a refusal", async () => {
    respondWith([], 0);
    renderApp(<SearchResults query="coverage" includeTranscript />);
    await waitFor(() => expect(screen.getByText("No result for this query.")).not.toBeNull());
  });

  it("renders an index_unavailable refusal as itself", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch(() => ({
        status: 503,
        body: {
          api_version: "v1",
          schema_version: "1.0",
          error: { code: "index_unavailable", message: "no index" },
        },
      })),
    );
    renderApp(<SearchResults query="coverage" includeTranscript />);
    await waitFor(() =>
      expect(document.querySelector('[data-error-code="index_unavailable"]')).not.toBeNull(),
    );
    expect(screen.queryByText("No result for this query.")).toBeNull();
  });
});
