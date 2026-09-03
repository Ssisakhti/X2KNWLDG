/**
 * D-095 — the jump reaches the player, not only the transcript.
 *
 * D-069 carried a search hit's offset into the Reader as `?t=`, and the Reader
 * dropped it here: `linkedSeconds` went only to `TranscriptPanel`'s
 * `highlightSec`, so `?tab=transcript&t=300` highlighted the right caption and
 * then "Load player" started the embed at `0` — while `embedUrl` had supported
 * `start` all along. Only the external YouTube link preserved the offset,
 * which answers canvas plan §17.3 scenario 2 by *leaving the application*.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonFetch, renderApp } from "../test/render";
import { ReaderView } from "./ReaderView";

const SOURCE_ID = "youtube:fixture-pass";

const SOURCE = {
  schema_version: "1.0",
  id: SOURCE_ID,
  source_type: "youtube",
  external_id: "fixture-pass",
  url: "https://www.youtube.com/watch?v=fixture-pass",
  title: "A fixture",
  canonical_dir: "output/pass-run",
  adapter: { name: "youtube", version: "1.0" },
  status: { validation: "PASS", coverage: "PASS", overall: "PASS" },
  counts: { knowledge_units: 1, relationships: 0 },
};

const ARTIFACTS = [
  {
    schema_version: "1.0",
    id: "youtube:fixture-pass:video",
    source_id: SOURCE_ID,
    kind: "video",
    role: "external",
    media_type: "video/mp4",
    path: null,
    url: "https://www.youtube.com/watch?v=fixture-pass",
    available: false,
  },
];

function serve() {
  return jsonFetch(() => ({
    body: {
      api_version: "v1",
      schema_version: "1.0",
      data: { source: SOURCE, artifacts: ARTIFACTS },
    },
  }));
}

function open(search: string) {
  // A `Route` rather than a bare element: `ReaderView` reads `sourceId` from
  // `useParams`, so without one it renders for the empty id.
  return renderApp(
    <Routes>
      <Route path="/sources/:sourceId" element={<ReaderView />} />
    </Routes>,
    { route: `/sources/${encodeURIComponent(SOURCE_ID)}${search}` },
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the linked offset reaching the player (D-095)", () => {
  /**
   * `ExternalPlayer` holds a request made before the frame exists in `pending`
   * and renders it as a notice, so waiting for that notice is waiting for the
   * effect to have run — clicking on the render before it is a race, and one
   * that only shows up when another tab's fetch changes the ordering.
   */
  async function loadPlayer(): Promise<URL> {
    const button = await waitFor(() => screen.getByText("Load the embedded player"));
    fireEvent.click(button);
    const frame = await waitFor(() => {
      const found = document.querySelector("iframe");
      if (found === null) throw new Error("the frame did not load");
      return found;
    });
    return new URL(frame.getAttribute("src")!);
  }

  it("starts the embed at the linked offset", async () => {
    vi.stubGlobal("fetch", serve());
    open("?t=300");
    // "Loading the player will start at 5:00." — the notice `ExternalPlayer`
    // renders once it holds a pending request, so waiting for it is waiting
    // for the effect rather than for a render.
    await waitFor(() => expect(screen.getByText(/will start at 5:00/)).not.toBeNull());
    expect((await loadPlayer()).searchParams.get("start")).toBe("300");
  });

  it("starts at the beginning when nothing was linked", async () => {
    vi.stubGlobal("fetch", serve());
    open("");
    await waitFor(() => expect(screen.getByText("Load the embedded player")).not.toBeNull());
    // Nothing is being held, which is the state this asserts — not merely that
    // the effect had yet to run.
    expect(screen.queryByText(/will start at/)).toBeNull();
    expect((await loadPlayer()).searchParams.get("start")).toBeNull();
  });

  it("ignores an offset it cannot read rather than seeking to zero", async () => {
    // D-069: `parseSeconds` ignores what it cannot read, and must not coerce.
    vi.stubGlobal("fetch", serve());
    open("?t=not-a-number");
    await waitFor(() => expect(screen.getByText("Load the embedded player")).not.toBeNull());
    // Nothing is being held, which is the state this asserts — not merely that
    // the effect had yet to run.
    expect(screen.queryByText(/will start at/)).toBeNull();
    expect((await loadPlayer()).searchParams.get("start")).toBeNull();
  });

  it("carries the offset even when the link opens another tab", async () => {
    vi.stubGlobal("fetch", serve());
    open("?tab=transcript&t=300");
    await waitFor(() => expect(screen.getByText(/will start at 5:00/)).not.toBeNull());
    expect((await loadPlayer()).searchParams.get("start")).toBe("300");
  });

  it("a negative offset is ignored, never clamped to zero", async () => {
    vi.stubGlobal("fetch", serve());
    open("?t=-30");
    await waitFor(() => expect(screen.getByText("Load the embedded player")).not.toBeNull());
    // Nothing is being held, which is the state this asserts — not merely that
    // the effect had yet to run.
    expect(screen.queryByText(/will start at/)).toBeNull();
    expect((await loadPlayer()).searchParams.get("start")).toBeNull();
  });
});

describe("the Reader's tablist", () => {
  /*
   * D-203: it was a tablist in name only. Six `role="tab"` buttons with no
   * `id`, no `aria-controls`, no `role="tabpanel"` anywhere in `src/`, no
   * roving `tabIndex` and no arrow keys — so a screen reader announced
   * "Transcript, tab, 2 of 6" and nothing told the reader where its content
   * was, and the keyboard had to walk all six to reach the panel. A role that
   * lies is worse than no role.
   */
  it("names the panel each tab controls, and the tab that labels it", async () => {
    vi.stubGlobal("fetch", serve());
    open("");
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBe(6));

    const selected = screen.getByRole("tab", { selected: true });
    const controls = selected.getAttribute("aria-controls");
    expect(controls).toBeTruthy();

    const panel = screen.getByRole("tabpanel");
    expect(panel.id).toBe(controls);
    expect(panel.getAttribute("aria-labelledby")).toBe(selected.id);
    expect(selected.id).toBeTruthy();
  });

  it("is one tab stop, not six", async () => {
    vi.stubGlobal("fetch", serve());
    open("");
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBe(6));

    const tabs = screen.getAllByRole("tab");
    const reachable = tabs.filter((tab) => tab.tabIndex === 0);
    expect(reachable).toHaveLength(1);
    expect(reachable[0]).toBe(screen.getByRole("tab", { selected: true }));
    // And what it controls is the keyboard's next stop.
    expect(screen.getByRole("tabpanel").tabIndex).toBe(0);
  });

  it("moves through the set with the arrow keys the role promises", async () => {
    vi.stubGlobal("fetch", serve());
    open("");
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBe(6));

    const first = screen.getByRole("tab", { selected: true });
    expect(first.textContent).toBe("Overview");
    first.focus();

    fireEvent.keyDown(first, { key: "ArrowRight" });
    await waitFor(() =>
      expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Transcript"),
    );
    // Selection and focus move together: a roving tabIndex that does not
    // follow focus leaves the keyboard on an element that is no longer a stop.
    expect(document.activeElement).toBe(screen.getByRole("tab", { selected: true }));

    // The set is a ring, and `End`/`Home` are its two ends.
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "End" });
    await waitFor(() =>
      expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Artifacts"),
    );
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowRight" });
    await waitFor(() =>
      expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Overview"),
    );
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowLeft" });
    await waitFor(() =>
      expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Artifacts"),
    );
  });

  it("leaves a key it does not own to the browser", async () => {
    vi.stubGlobal("fetch", serve());
    open("");
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBe(6));
    const selected = screen.getByRole("tab", { selected: true });
    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    selected.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
