/**
 * The search rail (`T-206`), walked the way the journey is walked: type a
 * query, read both answers, peek at one, focus another.
 *
 * The rail is where D-130's acceptance question is actually asked -- before
 * opening a result, can the user say what it states? So these tests assert on
 * the *content* of the cards, not only on their presence, and they assert that
 * the two hits which have no Map address carry an explanation and no Focus
 * control.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useMemo, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EntityRef, SearchHit } from "../api/contract";
import { createMapGraph, nodeAttributes } from "../map/graphProjection";
import { recordLookup } from "../map/useMapSearch";
import { useMapPeek } from "../map/useMapPeek";
import { concept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import { MapPeekCard } from "./MapPeekCard";
import { MapSearchRail } from "./MapSearchRail";

const KU1 = unit("KU-000001", { label: "Coverage is audited window by window." });
const KU2 = unit("KU-000002", { label: "A derived unit must show its work." });
const C1 = concept("C-000001", { label: "Autonomy loop: intent, context, action, feedback." });

const INDEXED_HIT: SearchHit = {
  type: "knowledge_unit",
  video_id: "pqlWNihgdjI",
  title: "A fixture",
  id: "KU-000042",
  kind: "principle",
  source_class: "source",
  content: "A statement held by the index but not loaded on this Map.",
  confidence: 0.75,
  global_id: "youtube:pqlWNihgdjI:KU-000042",
  source_id: "youtube:pqlWNihgdjI",
};

const CAPTION_HIT: SearchHit = {
  type: "transcript_caption",
  video_id: "pqlWNihgdjI",
  title: "A fixture",
  caption_id: "cap_000002",
  content: "Coverage is audited window by window, said out loud.",
  start_sec: 30,
  end_sec: 60,
  source_url: "https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s",
  source_id: "youtube:pqlWNihgdjI",
};

/** A capturing `fetch`: the rail's questions are as much under test as its answers. */
function stubSearch(hits: SearchHit[], total: number | null = null) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    (async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      urls.push(url);
      return new Response(
        JSON.stringify({
          api_version: "v1",
          schema_version: "1.0",
          query: "coverage",
          data: hits,
          page: { limit: 25, next_cursor: null, total },
        }),
        { status: 200 },
      );
    }) as typeof fetch,
  );
  return urls;
}

function Harness({
  records = [KU1, KU2, C1],
  onFocus,
  initialFocus = null,
}: {
  records?: readonly EntityRef[];
  onFocus?: (globalId: string | null) => void;
  initialFocus?: string | null;
}) {
  const graph = useMemo(() => {
    const built = createMapGraph();
    for (const record of records) built.addNode(record.global_id, nodeAttributes(record));
    return built;
  }, [records]);
  const [focus, setFocus] = useState<string | null>(initialFocus);
  const peek = useMapPeek(recordLookup(graph));
  return (
    <>
      <MapSearchRail
        graph={graph}
        revision={1}
        focus={focus}
        onFocus={(globalId) => {
          setFocus(globalId);
          onFocus?.(globalId);
        }}
        peek={peek}
        // The route decides this from the tier as well as from the focus
        // (`T-216`); the harness renders the rail the way the `full` tier
        // does with nothing selected, which is the state these tests are of.
        preferOpen={focus === null}
      />
      {/*
        The route renders the one Peek, not the rail (`T-208`), so the harness
        renders it the way `MapView` does. What is under test is unchanged: a
        row reports the node and the origin to the one binding, and the card
        shows what that binding holds.
      */}
      {peek.peek !== null && <MapPeekCard peek={peek.peek} onClose={() => peek.close()} />}
    </>
  );
}

function ask(query: string) {
  fireEvent.change(screen.getByLabelText("Search"), { target: { value: query } });
  fireEvent.click(screen.getByText("Search", { selector: "button" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("MapSearchRail", () => {
  it("asks nothing until a query is submitted", () => {
    const urls = stubSearch([]);
    renderApp(<Harness />);
    expect(urls).toHaveLength(0);
    expect(screen.queryByText("On the Map")).toBeNull();
  });

  it("answers from the loaded graph and from the index, in two labelled lists", async () => {
    const urls = stubSearch([INDEXED_HIT], 1);
    renderApp(<Harness />);
    ask("coverage");

    // The local answer needs no request and is already true.
    expect(screen.getByText("Coverage is audited window by window.")).not.toBeNull();
    expect(document.querySelector("[data-map-loaded-matches]")?.textContent).toContain(
      "1 of 1 matching node, out of 3 loaded",
    );

    await waitFor(() =>
      expect(
        screen.getByText("A statement held by the index but not loaded on this Map."),
      ).not.toBeNull(),
    );
    expect(urls[0]).toContain("include_transcript=false");
    // The two lists stay distinguishable in the DOM as well as on screen.
    expect(document.querySelectorAll('[data-map-result="graph"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-map-result="index"]')).toHaveLength(1);
    expect(document.body.textContent).toContain("Not loaded on the Map yet");
  });

  it("focuses by the record's own global id", async () => {
    stubSearch([]);
    const focused = vi.fn();
    renderApp(<Harness onFocus={focused} />);
    ask("coverage");

    const card = document.querySelector('[data-map-result="graph"]') as HTMLElement;
    fireEvent.click(card.querySelector("[data-map-focus-action]") as HTMLElement);
    expect(focused).toHaveBeenCalledWith("youtube:pqlWNihgdjI:KU-000001");
    await waitFor(() => expect(screen.getByText("Focused")).not.toBeNull());
  });

  it("clears the focus without touching anything else", () => {
    stubSearch([]);
    const focused = vi.fn();
    renderApp(<Harness onFocus={focused} initialFocus="youtube:pqlWNihgdjI:KU-000001" />);
    fireEvent.click(screen.getByText("Clear the focus"));
    expect(focused).toHaveBeenCalledWith(null);
  });

  it("says when the focused entity is not among the loaded nodes", () => {
    stubSearch([]);
    renderApp(<Harness initialFocus="youtube:pqlWNihgdjI:KU-999999" />);
    expect(document.body.textContent).toContain("not among the nodes loaded so far");
  });

  it("peeks a loaded result on hover and on keyboard focus, and closes on Escape", () => {
    stubSearch([]);
    renderApp(<Harness />);
    ask("coverage");
    const card = document.querySelector('[data-map-result="graph"]') as HTMLElement;

    fireEvent.mouseEnter(card);
    expect(document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek")).toBe(
      "youtube:pqlWNihgdjI:KU-000001",
    );

    fireEvent.mouseLeave(card);
    expect(document.querySelector("[data-map-peek]")).toBeNull();

    fireEvent.focus(card);
    expect(document.querySelector("[data-peek-origin]")?.getAttribute("data-peek-origin")).toBe(
      "keyboard",
    );

    // Escape is the keyboard's "leave": without it a Peek opened by focus
    // would stay until focus moved.
    fireEvent.keyDown(card, { key: "Escape" });
    expect(document.querySelector("[data-map-peek]")).toBeNull();
  });

  it("never peeks an indexed hit the Map has not loaded", async () => {
    stubSearch([INDEXED_HIT], 1);
    renderApp(<Harness />);
    ask("coverage");
    await waitFor(() =>
      expect(document.querySelector('[data-map-result="index"]')).not.toBeNull(),
    );
    fireEvent.mouseEnter(document.querySelector('[data-map-result="index"]') as HTMLElement);
    // There is no record to show, and one would have to be invented.
    expect(document.querySelector("[data-map-peek]")).toBeNull();
  });

  it("explains a caption hit and refuses to make it selectable", async () => {
    const urls = stubSearch([CAPTION_HIT], 1);
    renderApp(<Harness />);
    fireEvent.click(screen.getByLabelText("Search"));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "coverage" } });
    fireEvent.click(screen.getByText("Include transcript text"));
    fireEvent.click(screen.getByText("Search", { selector: "button" }));

    await waitFor(() => expect(document.body.textContent).toContain("not an addressable entity"));
    expect(urls[urls.length - 1]).toContain("include_transcript=true");
    const card = document.querySelector('[data-map-result="index"]') as HTMLElement;
    expect(card.getAttribute("data-addressable")).toBe("false");
    expect(card.querySelector("[data-map-focus-action]")).toBeNull();
  });

  it("says the server did not count rather than showing a zero", async () => {
    stubSearch([INDEXED_HIT], null);
    renderApp(<Harness />);
    ask("coverage");
    await waitFor(() =>
      expect(document.body.textContent).toContain("The server did not count the matches."),
    );
  });

  it("states an empty index answer as empty, not as a failure", async () => {
    stubSearch([], 0);
    renderApp(<Harness />);
    ask("nothing matches this");
    await waitFor(() => expect(screen.getByText("No result for this query.")).not.toBeNull());
    expect(screen.getByText("No node loaded on the Map matches this query.")).not.toBeNull();
  });
});
