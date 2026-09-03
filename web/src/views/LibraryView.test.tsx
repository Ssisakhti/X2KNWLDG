/**
 * `T-111`, and the distinction the Library exists to hold: an **unbuilt**
 * index is not an empty library.
 *
 * D-030 added `503 index_unavailable` precisely so a client could tell those
 * apart, and the failure it prevents is a UI that renders the refusal as "no
 * sources yet" -- a confident statement about the user's data, made from a
 * server that said it could not answer. Both states are asserted here, and so
 * is the third one nobody thinks about: an index that is ready and genuinely
 * holds nothing.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Source } from "../api/contract";
import { jsonFetch, renderApp } from "../test/render";
import { LibraryView } from "./LibraryView";

function statusBody(state: string, sources: number) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: {
      index: { state, built_at: null, index_version: null },
      counts: { sources, artifacts: 0, entities: 0, relations: 0 },
      sources_by_status: { PASS: 0, PARTIAL: 0, FAIL: 0, UNKNOWN: 0 },
      adapters: [{ name: "youtube", version: "1.0" }],
    },
  };
}

function source(id: string, overall: string, validation: string, coverage: string): Source {
  return {
    schema_version: "1.0",
    id,
    source_type: "youtube",
    external_id: id.split(":")[1],
    title: `Title of ${id}`,
    canonical_dir: `output/${id}`,
    adapter: { name: "youtube", version: "1.0" },
    status: { validation, coverage, overall },
    counts: { knowledge_units: 2, relationships: 1 },
  } as Source;
}

function listBody(sources: Source[], total: number | null) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: sources,
    page: { limit: 50, next_cursor: null, total },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("the library", () => {
  it("renders an unbuilt index as a refusal, not as an empty library", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/api/status")
          ? { body: statusBody("absent", 0) }
          : {
              status: 503,
              body: {
                api_version: "v1",
                schema_version: "1.0",
                error: { code: "index_unavailable", message: "no index has been built" },
              },
            },
      ),
    );
    renderApp(<LibraryView />);

    await waitFor(() =>
      expect(document.querySelector('[data-error-code="index_unavailable"]')).not.toBeNull(),
    );
    expect(screen.queryByText("The index holds no source matching these filters.")).toBeNull();
    expect(screen.getByText("No index has been built yet.")).not.toBeNull();
  });

  it("renders a ready but genuinely empty index as empty", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/api/status") ? { body: statusBody("ready", 0) } : { body: listBody([], 0) },
      ),
    );
    renderApp(<LibraryView />);

    await waitFor(() =>
      expect(screen.getByText("The index holds no source matching these filters.")).not.toBeNull(),
    );
    expect(document.querySelector("[data-error-code]")).toBeNull();
  });

  it("shows PARTIAL and FAIL as themselves, beside PASS", async () => {
    const sources = [
      source("youtube:a", "PASS", "PASS", "PASS"),
      source("youtube:b", "PARTIAL", "PARTIAL", "PARTIAL"),
      source("youtube:c", "FAIL", "FAIL", "PASS"),
    ];
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/api/status")
          ? { body: statusBody("ready", 3) }
          : { body: listBody(sources, 3) },
      ),
    );
    renderApp(<LibraryView />);

    await waitFor(() => expect(screen.getAllByText(/Title of youtube:/)).toHaveLength(3));
    const statuses = [...document.querySelectorAll("[data-source-id] [data-status]")].map((node) =>
      node.getAttribute("data-status"),
    );
    expect(statuses).toContain("PARTIAL");
    expect(statuses).toContain("FAIL");
    // The FAIL source's coverage is PASS: both are shown, neither is collapsed.
    const failCard = document.querySelector('[data-source-id="youtube:c"]');
    const failStatuses = [...(failCard?.querySelectorAll("[data-status]") ?? [])].map((node) =>
      node.getAttribute("data-status"),
    );
    expect(failStatuses).toEqual(["FAIL", "FAIL", "PASS"]);
  });

  it("filters sources through the server, not in the browser", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) => {
        seen.push(url);
        return url.includes("/api/status")
          ? { body: statusBody("ready", 1) }
          : { body: listBody([source("youtube:a", "PASS", "PASS", "PASS")], 1) };
      }),
    );
    renderApp(<LibraryView />);
    await waitFor(() => expect(screen.getAllByText(/Title of youtube:a/)).toHaveLength(1));

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(screen.getByLabelText(/Validation status/), {
      target: { value: "PARTIAL" },
    });
    await waitFor(() => expect(seen.some((url) => url.includes("status=PARTIAL"))).toBe(true));
  });

  it("renders right to left in Persian without a second stylesheet", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/api/status")
          ? { body: statusBody("ready", 1) }
          : { body: listBody([source("youtube:a", "PARTIAL", "PARTIAL", "PARTIAL")], 1) },
      ),
    );
    renderApp(<LibraryView />, { locale: "fa" });

    await waitFor(() => expect(screen.getAllByText(/Title of youtube:a/)).toHaveLength(1));
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.getAttribute("lang")).toBe("fa");
    // The status word itself is not translated: PARTIAL is copied from the
    // validator file and stays the value it is in every locale.
    expect(screen.getAllByText("PARTIAL").length).toBeGreaterThan(0);
  });

  it("reads the source-type vocabulary off the status it already fetched", async () => {
    /*
     * D-203: this used to be a second, unfiltered `listSources` at
     * `limit: 500` on every mount — five hundred records fetched, parsed and
     * thrown away to populate one `<select>`, beside the paged request that
     * answers the page.
     *
     * `/api/status` carries `adapters`, and `adapters[].name` *is* the
     * `source_type`, so the vocabulary was already on the wire.
     */
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) => {
        urls.push(url);
        if (url.includes("/api/status")) return { body: statusBody("ready", 1) };
        return { body: listBody([source("youtube:a", "PASS", "PASS", "PASS")], 1) };
      }),
    );
    renderApp(<LibraryView />);
    await waitFor(() => expect(screen.getByText("Title of youtube:a")).toBeTruthy());

    // The vocabulary is offered, from the adapters the status names.
    const select = document.querySelector<HTMLSelectElement>("select");
    expect(select).not.toBeNull();
    const options = [...document.querySelectorAll("option")].map((o) => o.textContent);
    expect(options).toContain("youtube");

    // And nothing asked for five hundred records to learn it.
    const listCalls = urls.filter((url) => url.includes("/api/sources"));
    expect(listCalls).toHaveLength(1);
    expect(listCalls.every((url) => !url.includes("limit=500"))).toBe(true);
  });
});