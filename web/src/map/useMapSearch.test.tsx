/**
 * The Map's search (`T-206`): two corpora, verbatim previews, and a stale
 * response that is dropped whole.
 *
 * The last one is the reason this file mounts a component instead of calling
 * pure functions only. D-079's lesson is about *timing*: a page that answers a
 * question the user has replaced must not reach the screen, and must not leave
 * its cursor behind for the next "More" to paginate a collection nobody is
 * looking at. That is only observable with a request still in flight while the
 * query changes, so the fetch below is deferred by hand and the abort signal is
 * inspected rather than assumed.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EntityRef, SearchHit } from "../api/contract";
import { concept, unit } from "../test/graphRecords";
import { createMapGraph, nodeAttributes } from "./graphProjection";
import {
  LOADED_MATCH_LIMIT,
  previewOfEntity,
  previewOfHit,
  recordLookup,
  searchLoadedNodes,
  useMapSearch,
} from "./useMapSearch";

const KU1 = unit("KU-000001", { label: "Coverage is audited window by window." });
const KU2 = unit("KU-000002", {
  label: "A derived unit must show its work.",
  provenance_class: "derived",
  confidence: null,
});
const C1 = concept("C-000001", { label: "Autonomy loop: intent, context, action, feedback." });

function graphOf(records: readonly EntityRef[] = [KU1, KU2, C1]) {
  const graph = createMapGraph();
  for (const record of records) graph.addNode(record.global_id, nodeAttributes(record));
  return graph;
}

const CAPTION_HIT: SearchHit = {
  type: "transcript_caption",
  video_id: "pqlWNihgdjI",
  title: "A fixture",
  caption_id: "cap_000002",
  content: "Coverage is audited window by window.",
  start_sec: 30,
  end_sec: 60,
  source_url: "https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s",
  source_id: "youtube:pqlWNihgdjI",
};

/** A knowledge unit whose run states no `video_id`: no global id, by design. */
const ORPHAN_HIT: SearchHit = {
  type: "knowledge_unit",
  video_id: null,
  title: null,
  id: "KU-000007",
  kind: "claim",
  source_class: "source",
  content: "A unit from a run whose metadata states no video id.",
  confidence: null,
  global_id: null,
  source_id: null,
};

function unitHit(overrides: Partial<Extract<SearchHit, { type: "knowledge_unit" }>> = {}) {
  return {
    type: "knowledge_unit",
    video_id: "pqlWNihgdjI",
    title: "A fixture",
    id: "KU-000001",
    kind: "principle",
    source_class: "source",
    content: "Coverage is audited window by window.",
    confidence: 0.9,
    start_sec: 30,
    source_url: "https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s",
    global_id: KU1.global_id,
    source_id: "youtube:pqlWNihgdjI",
    ...overrides,
  } as SearchHit;
}

describe("searchLoadedNodes", () => {
  it("matches a stored statement, case-insensitively", () => {
    const found = searchLoadedNodes(graphOf(), "COVERAGE");
    expect(found.items.map((preview) => preview.globalId)).toEqual([KU1.global_id]);
    expect(found.matched).toBe(1);
    expect(found.searched).toBe(3);
  });

  it("matches identity as well as text", () => {
    // The three id spellings a person may have in front of them: the global
    // id, the canonical local id, and the library id.
    expect(searchLoadedNodes(graphOf(), "KU-000002").matched).toBe(1);
    expect(searchLoadedNodes(graphOf(), "library:concepts").matched).toBe(1);
    expect(searchLoadedNodes(graphOf(), "concept:C-000001").matched).toBe(1);
  });

  it("asks nothing of an empty query, and nothing of an empty Map", () => {
    expect(searchLoadedNodes(graphOf(), "   ").matched).toBe(0);
    expect(searchLoadedNodes(null, "coverage")).toEqual({ items: [], matched: 0, searched: 0 });
    // A Map with no nodes loaded and a Map whose nodes do not match are
    // different statements, and `searched` is what keeps them apart.
    expect(searchLoadedNodes(graphOf([]), "coverage").searched).toBe(0);
    expect(searchLoadedNodes(graphOf(), "nothing matches this").searched).toBe(3);
  });

  it("bounds the list without under-reporting the matches", () => {
    const many = Array.from({ length: LOADED_MATCH_LIMIT + 5 }, (_value, index) =>
      unit(`KU-${String(index).padStart(6, "0")}`, { label: "shared word here" }),
    );
    const found = searchLoadedNodes(graphOf(many), "shared");
    expect(found.items).toHaveLength(LOADED_MATCH_LIMIT);
    // The count is the truth; the list is what fits.
    expect(found.matched).toBe(LOADED_MATCH_LIMIT + 5);
  });

  it("keeps the graph's own order, and invents no ranking", () => {
    const found = searchLoadedNodes(graphOf([KU2, KU1]), "unit must show");
    expect(found.items.map((preview) => preview.globalId)).toEqual([KU2.global_id]);
  });
});

describe("previewOfEntity", () => {
  it("copies the record and completes nothing", () => {
    const preview = previewOfEntity(KU2);
    expect(preview.text).toBe(KU2.label);
    expect(preview.globalId).toBe(KU2.global_id);
    expect(preview.provenance).toBe("derived");
    // Null, not zero. A zero is a measurement (D-131).
    expect(preview.confidence).toBeNull();
    expect(preview.unaddressable).toBeNull();
    expect(preview.loaded).toBe(true);
  });

  it("reads a recorded time range and states nothing when there is none", () => {
    const located = unit("KU-000003", {
      locator: { type: "time_range", start_sec: 30, end_sec: 60, excerpt: "verbatim" },
    });
    expect(previewOfEntity(located).startSec).toBe(30);
    expect(previewOfEntity(located).endSec).toBe(60);
    expect(previewOfEntity(KU1).startSec).toBeNull();
  });
});

describe("previewOfHit", () => {
  it("gives a caption hit no address at all", () => {
    // v1 emits no caption entities (D-023). An id here would resolve to
    // nothing, which is worse than having none.
    const preview = previewOfHit(CAPTION_HIT, 0, false);
    expect(preview.globalId).toBeNull();
    expect(preview.unaddressable).toBe("caption");
    expect(preview.text).toBe(CAPTION_HIT.content);
    expect(preview.readerTab).toBe("transcript");
    expect(preview.startSec).toBe(30);
  });

  it("gives a unit with no global id no address either, for its own reason", () => {
    const preview = previewOfHit(ORPHAN_HIT, 0, false);
    expect(preview.globalId).toBeNull();
    expect(preview.unaddressable).toBe("no_global_id");
    expect(preview.confidence).toBeNull();
    expect(preview.kind).toBe("claim");
  });

  it("copies an addressable unit hit field for field", () => {
    const preview = previewOfHit(unitHit(), 0, true);
    expect(preview.globalId).toBe(KU1.global_id);
    expect(preview.unaddressable).toBeNull();
    expect(preview.loaded).toBe(true);
    expect(preview.confidence).toBe(0.9);
    expect(preview.sourceUrl).toBe("https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s");
    expect(preview.readerTab).toBe("units");
  });

  it("shows an unrecognised source class as written rather than rounding it", () => {
    const preview = previewOfHit(unitHit({ source_class: "workspace" }), 0, false);
    expect(preview.provenance).toBeNull();
    expect(preview.provenanceRaw).toBe("workspace");
  });
});

describe("recordLookup", () => {
  it("answers only for nodes the Map has loaded", () => {
    const lookup = recordLookup(graphOf());
    expect(lookup(KU1.global_id)).toEqual(KU1);
    expect(lookup("youtube:pqlWNihgdjI:KU-999999")).toBeNull();
    expect(recordLookup(null)(KU1.global_id)).toBeNull();
  });
});

/** A `fetch` whose responses are resolved by hand, and that honours abort. */
function deferredFetch() {
  const calls: { url: string; signal: AbortSignal | null; settle: (body: unknown) => void }[] = [];
  const impl = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const signal = init?.signal ?? null;
    return new Promise<Response>((resolve, reject) => {
      if (signal !== null) {
        signal.addEventListener("abort", () =>
          reject(new DOMException("The operation was aborted.", "AbortError")),
        );
      }
      calls.push({
        url,
        signal,
        settle: (body: unknown) =>
          resolve(new Response(JSON.stringify(body), { status: 200 })),
      });
    });
  }) as typeof fetch;
  return { calls, impl };
}

function searchBody(hits: SearchHit[], query: string) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    query,
    data: hits,
    page: { limit: 25, next_cursor: null, total: hits.length },
  };
}

function SearchProbe({ query }: { query: string }) {
  const search = useMapSearch({ query, graph: graphOf(), revision: 1 });
  return (
    <div>
      <output data-status>{search.status}</output>
      <output data-indexed>{search.indexed.map((preview) => preview.text ?? "").join("|")}</output>
      <output data-loaded>{search.loaded.matched}</output>
    </div>
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("useMapSearch", () => {
  it("asks the contract's own parameters, and asks nothing without a query", async () => {
    const { calls, impl } = deferredFetch();
    vi.stubGlobal("fetch", impl);

    const { rerender } = render(<SearchProbe query="" />);
    expect(calls).toHaveLength(0);

    rerender(<SearchProbe query="coverage" />);
    await waitFor(() => expect(calls).toHaveLength(1));
    const asked = new URL(calls[0]?.url ?? "", "http://localhost");
    expect(asked.pathname).toBe("/api/search");
    expect(asked.searchParams.get("q")).toBe("coverage");
    // A caption is not an entity, so the Map does not ask for captions by
    // default. The parameter is the operation's own.
    expect(asked.searchParams.get("include_transcript")).toBe("false");
    expect(asked.searchParams.get("source_id")).toBeNull();
  });

  it("scopes the request to the Map's source when there is one", async () => {
    const { calls, impl } = deferredFetch();
    vi.stubGlobal("fetch", impl);
    function Scoped() {
      const search = useMapSearch({
        query: "coverage",
        graph: null,
        revision: 0,
        sourceId: "youtube:pqlWNihgdjI",
      });
      return <output data-status>{search.status}</output>;
    }
    render(<Scoped />);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(new URL(calls[0]?.url ?? "", "http://localhost").searchParams.get("source_id")).toBe(
      "youtube:pqlWNihgdjI",
    );
  });

  it("drops a response that answers a replaced question, and aborts it", async () => {
    const { calls, impl } = deferredFetch();
    vi.stubGlobal("fetch", impl);

    const { rerender } = render(<SearchProbe query="alpha" />);
    await waitFor(() => expect(calls).toHaveLength(1));

    rerender(<SearchProbe query="beta" />);
    await waitFor(() => expect(calls).toHaveLength(2));

    // The first question was retired the moment it was replaced: its request
    // is aborted rather than merely ignored, so the network stops too.
    expect(calls[0]?.signal?.aborted).toBe(true);

    calls[1]?.settle(searchBody([unitHit({ content: "beta answer" })], "beta"));
    await waitFor(() =>
      expect(document.querySelector("[data-indexed]")?.textContent).toBe("beta answer"),
    );

    // The stale answer arrives late. It is dropped whole -- not appended, not
    // merged, and its cursor is not kept (D-079).
    calls[0]?.settle(searchBody([unitHit({ content: "alpha answer" })], "alpha"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.querySelector("[data-indexed]")?.textContent).toBe("beta answer");
  });

  it("answers from the loaded graph without waiting for the server", async () => {
    const { impl } = deferredFetch();
    vi.stubGlobal("fetch", impl);
    render(<SearchProbe query="coverage" />);
    // The request is still in flight; the local answer is already on screen.
    expect(document.querySelector("[data-loaded]")?.textContent).toBe("1");
    expect(screen.queryByText("beta answer")).toBeNull();
  });
});
