/**
 * `T-112`'s transcript, and the timestamp it must not invent.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Artifact } from "../api/contract";
import { renderApp } from "../test/render";
import { TranscriptPanel } from "./TranscriptPanel";

const ARTIFACT = {
  schema_version: "1.0",
  id: "youtube:fixture-pass:transcript",
  source_id: "youtube:fixture-pass",
  kind: "transcript",
  role: "canonical",
  media_type: "application/json",
  path: "output/pass-run/transcript.json",
  immutable: false,
  available: true,
} as Artifact;

const BODY = JSON.stringify({
  schema_version: "1.0",
  captions: [
    { segment_id: "cap_000001", start_sec: 0, end_sec: 30, text: "first caption" },
    { segment_id: "cap_000002", end_sec: 60, text: "a caption with no recorded start" },
  ],
});

function serve(body: string, status = 200): typeof fetch {
  return (async () => new Response(body, { status })) as typeof fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("the transcript panel", () => {
  it("reads the captions out of the byte channel", async () => {
    vi.stubGlobal("fetch", serve(BODY));
    renderApp(<TranscriptPanel artifact={ARTIFACT} sourceUrl={null} onSeek={() => {}} />);
    await waitFor(() => expect(screen.getByText("first caption")).not.toBeNull());
    expect(screen.getByText("2 captions")).not.toBeNull();
  });

  it("offers a seek only where a start time exists", async () => {
    const seeks: number[] = [];
    vi.stubGlobal("fetch", serve(BODY));
    renderApp(
      <TranscriptPanel artifact={ARTIFACT} sourceUrl={null} onSeek={(s) => seeks.push(s)} />,
    );
    await waitFor(() => expect(screen.getByText("first caption")).not.toBeNull());

    const rows = document.querySelectorAll(".caption-row");
    expect(rows[0]?.querySelector("button")).not.toBeNull();
    // The second caption states no start: no seek control, and an em dash
    // rather than 0:00.
    expect(rows[1]?.querySelector("button")).toBeNull();
    expect(rows[1]?.textContent).toContain("—");
    expect(rows[1]?.textContent).not.toContain("0:00");

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(rows[0]?.querySelector("button") as HTMLButtonElement);
    expect(seeks).toEqual([0]);
  });

  it("builds a deep link only from a real URL and a real timestamp", async () => {
    vi.stubGlobal("fetch", serve(BODY));
    renderApp(
      <TranscriptPanel
        artifact={ARTIFACT}
        sourceUrl="https://www.youtube.com/watch?v=fixture-pass"
        onSeek={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getByText("first caption")).not.toBeNull());
    const rows = document.querySelectorAll(".caption-row");
    expect(rows[0]?.querySelector("a")?.getAttribute("href")).toBe(
      "https://www.youtube.com/watch?v=fixture-pass&t=0s",
    );
    expect(rows[1]?.querySelector("a")).toBeNull();
  });

  it("says which failure it hit", async () => {
    renderApp(<TranscriptPanel artifact={null} sourceUrl={null} onSeek={() => {}} />);
    expect(screen.getByText("This source has no readable transcript artifact.")).not.toBeNull();
  });

  it("reports a 404 unavailable as unavailable, not as an empty transcript", async () => {
    vi.stubGlobal(
      "fetch",
      serve(
        JSON.stringify({
          api_version: "v1",
          schema_version: "1.0",
          error: { code: "unavailable", message: "no local bytes" },
        }),
        404,
      ),
    );
    renderApp(<TranscriptPanel artifact={ARTIFACT} sourceUrl={null} onSeek={() => {}} />);
    await waitFor(() =>
      expect(document.querySelector('[data-error-code="unavailable"]')).not.toBeNull(),
    );
  });

  it("tells a document that is not a transcript from one with no captions", async () => {
    vi.stubGlobal("fetch", serve(JSON.stringify({ schema_version: "1.0" })));
    renderApp(<TranscriptPanel artifact={ARTIFACT} sourceUrl={null} onSeek={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/does not hold a caption list/)).not.toBeNull(),
    );
  });
});

const THREE = JSON.stringify({
  schema_version: "1.0",
  captions: [
    { segment_id: "cap_000001", start_sec: 0, end_sec: 30, text: "first caption" },
    { segment_id: "cap_000002", start_sec: 30, end_sec: 60, text: "second caption" },
    { segment_id: "cap_000003", start_sec: 60, end_sec: 90, text: "third caption" },
  ],
});

// A transcript with a real gap: nothing claims 5s-10s, and a caption follows
// it. That is what tells a gap apart from the end of the medium (D-093).
const GAPPED = JSON.stringify({
  schema_version: "1.0",
  captions: [
    { segment_id: "cap_000001", start_sec: 0, end_sec: 5, text: "before the gap" },
    { segment_id: "cap_000002", start_sec: 10, end_sec: 15, text: "after the gap" },
  ],
});

describe("the linked timestamp (D-069)", () => {
  it("marks the caption covering the linked offset", async () => {
    vi.stubGlobal("fetch", serve(THREE));
    renderApp(
      <TranscriptPanel
        artifact={ARTIFACT}
        sourceUrl={null}
        onSeek={() => {}}
        highlightSec={30}
      />,
    );
    await waitFor(() => expect(screen.getByText("second caption")).not.toBeNull());
    const marked = document.querySelectorAll('[data-linked="true"]');
    expect(marked).toHaveLength(1);
    expect(marked[0]?.textContent).toContain("second caption");
    // Announced, not merely tinted: colour alone would leave the mark
    // invisible to a screen reader and to anyone who cannot see the tint.
    expect(marked[0]?.getAttribute("aria-current")).toBe("location");
  });

  it("marks nothing when no offset is linked", async () => {
    vi.stubGlobal("fetch", serve(THREE));
    renderApp(<TranscriptPanel artifact={ARTIFACT} sourceUrl={null} onSeek={() => {}} />);
    await waitFor(() => expect(screen.getByText("first caption")).not.toBeNull());
    expect(document.querySelectorAll('[data-linked="true"]')).toHaveLength(0);
  });

  it("says so when no caption covers the linked offset, and marks nothing", async () => {
    // Past the end of the transcript. Snapping to the last caption would put
    // the reader somewhere the link never named; saying nothing at all would
    // leave them wondering why the jump did nothing.
    vi.stubGlobal("fetch", serve(THREE));
    renderApp(
      <TranscriptPanel
        artifact={ARTIFACT}
        sourceUrl={null}
        onSeek={() => {}}
        highlightSec={9999}
      />,
    );
    await waitFor(() => expect(screen.getByText("third caption")).not.toBeNull());
    // D-093: this used to assert `toHaveLength(1)` — the "was playing"
    // fallback claimed an offset past the last caption's *end* — while this
    // test's own name and the comment above it both described the opposite.
    // The fallback exists for a gap the transcript spans; past the end is
    // outside the medium, and marking the final caption for it is a rendered
    // position no data supports.
    expect(document.querySelectorAll('[data-linked="true"]')).toHaveLength(0);
    expect(screen.getByText(/no caption/i)).not.toBeNull();
  });

  it("still marks the caption that was playing across a gap", async () => {
    // The behaviour D-093 kept: an offset the transcript spans but no caption
    // claims lands on the caption that was playing, because a later caption
    // proves the offset is inside the medium.
    vi.stubGlobal("fetch", serve(GAPPED));
    renderApp(
      <TranscriptPanel
        artifact={ARTIFACT}
        sourceUrl={null}
        onSeek={() => {}}
        highlightSec={7}
      />,
    );
    await waitFor(() => expect(screen.getByText("before the gap")).not.toBeNull());
    const marked = document.querySelectorAll('[data-linked="true"]');
    expect(marked).toHaveLength(1);
    expect(marked[0]?.textContent).toContain("before the gap");
  });

  it("marks nothing for an offset before the transcript starts", async () => {
    vi.stubGlobal("fetch", serve(THREE));
    renderApp(
      <TranscriptPanel
        artifact={ARTIFACT}
        sourceUrl={null}
        onSeek={() => {}}
        highlightSec={0}
      />,
    );
    await waitFor(() => expect(screen.getByText("first caption")).not.toBeNull());
    const marked = document.querySelectorAll('[data-linked="true"]');
    expect(marked[0]?.textContent).toContain("first caption");
  });
});
