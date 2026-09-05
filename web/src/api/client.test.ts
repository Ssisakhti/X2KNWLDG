/**
 * The client, and the error taxonomy it must not blur (D-030).
 */

import { describe, expect, it } from "vitest";

import { ApiClient, buildPath, buildQuery, PATHS } from "./client";
import { ApiFailure, failureFromBody, isIndexUnavailable } from "./errors";

function respond(status: number, body: unknown): typeof fetch {
  return (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;
}

function envelope(code: string, message: string) {
  return { api_version: "v1", schema_version: "1.0", error: { code, message } };
}

describe("the path table", () => {
  it("covers exactly the thirteen frozen operations", () => {
    expect(Object.keys(PATHS).sort()).toEqual(
      [
        "getArtifact",
        "getArtifactMedia",
        "getEntity",
        "getGraph",
        "getNeighborhood",
        "getSource",
        // T-254's two. They have no caller yet — the Source Map mode is T-256 —
        // but the table is typed as `{ [K in OperationId]: ... }`, so a missing
        // row is a build failure rather than a 404 discovered later.
        "getSourceGraph",
        "getSourceNeighborhood",
        "getStatus",
        "listSourceEntities",
        "listSourceRelations",
        "listSources",
        "search",
      ].sort(),
    );
  });

  it("names only /api paths", () => {
    for (const path of Object.values(PATHS)) expect(path.startsWith("/api/")).toBe(true);
  });
});

describe("building a request", () => {
  it("percent-encodes an id's colons rather than splitting on them", () => {
    expect(buildPath(PATHS.getSource, { source_id: "youtube:fixture-pass" })).toBe(
      "/api/sources/youtube%3Afixture-pass",
    );
  });

  it("encodes a slash instead of creating a new path segment (D-056)", () => {
    expect(buildPath(PATHS.getEntity, { entity_id: "a/b" })).toBe("/api/entities/a%2Fb");
  });

  it("refuses a missing path parameter before sending anything", () => {
    expect(() => buildPath(PATHS.getSource, {})).toThrow(ApiFailure);
  });

  it("omits an undefined query value and keeps a false one", () => {
    expect(buildQuery({ limit: 50, cursor: undefined, include_transcript: false })).toBe(
      "?limit=50&include_transcript=false",
    );
  });

  it("builds a media URL a video element can use", () => {
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:8931" });
    expect(client.mediaUrl("youtube:x:transcript")).toBe(
      "http://127.0.0.1:8931/api/media/youtube%3Ax%3Atranscript",
    );
  });
});

describe("the four refusals stay distinguishable", () => {
  const cases: readonly [number, string][] = [
    [400, "invalid_id"],
    [404, "not_found"],
    [404, "unavailable"],
    [503, "index_unavailable"],
  ];

  for (const [status, code] of cases) {
    it(`${status} ${code} arrives as itself`, async () => {
      const client = new ApiClient({ fetch: respond(status, envelope(code, "refused")) });
      await expect(client.call("getStatus")).rejects.toMatchObject({ code, status });
    });
  }

  it("tells an unbuilt index from anything else", () => {
    expect(isIndexUnavailable(new ApiFailure("index_unavailable", ""))).toBe(true);
    expect(isIndexUnavailable(new ApiFailure("not_found", ""))).toBe(false);
  });

  it("does not invent one of the four for a body that is not the envelope", () => {
    const failure = failureFromBody(502, "<html>gateway</html>");
    expect(failure.code).toBe("internal");
    expect(failure.status).toBe(502);
  });

  it("reports an unreachable server as transport, not as a server error", async () => {
    const client = new ApiClient({
      fetch: (() => Promise.reject(new TypeError("connection refused"))) as typeof fetch,
    });
    await expect(client.call("getStatus")).rejects.toMatchObject({ code: "transport" });
  });
});

describe("a successful call", () => {
  it("returns the body the contract types", async () => {
    const body = {
      api_version: "v1",
      schema_version: "1.0",
      data: {
        index: { state: "ready", built_at: null },
        counts: { sources: 1, artifacts: 2, entities: 3, relations: 4 },
        sources_by_status: { PASS: 1, PARTIAL: 0, FAIL: 0, UNKNOWN: 0 },
        adapters: [],
      },
    };
    const client = new ApiClient({ fetch: respond(200, body) });
    const response = await client.call("getStatus");
    expect(response.data.counts.sources).toBe(1);
  });
});

describe("a 200 whose shape the contract does not permit", () => {
  /*
   * The defect: `call` ended in `(await response.json()) as Operation<K>`, so a
   * malformed 200 became a typed object by assertion and failed later, at the
   * point of use. `MapFilters.tsx:100` reads `data.page.next_cursor` **during
   * render**, so the whole Map route was replaced by `RouteErrorBoundary`; and
   * where the same read sat inside an async loader the `TypeError` was caught
   * and reported to the reader as "The server refused this request. Code:
   * internal" — blaming a server that had answered 200.
   *
   * Only the envelope is checked. The records inside are the frozen contract's
   * business and are pinned by `tests/test_api_contract.py`.
   */
  it("refuses a body with no data envelope, as an internal failure", async () => {
    const client = new ApiClient({
      fetch: respond(200, { api_version: "v1", schema_version: "1.0" }),
    });
    await expect(client.call("getStatus")).rejects.toMatchObject({ code: "internal" });
  });

  it("refuses a malformed page cursor", async () => {
    const client = new ApiClient({
      fetch: respond(200, {
        api_version: "v1",
        schema_version: "1.0",
        data: [],
        page: { limit: 50, next_cursor: 42, total: 0 },
      }),
    });
    await expect(client.call("listSources")).rejects.toMatchObject({ code: "internal" });
  });

  it("says the client rejected the shape, so the message does not blame the server", async () => {
    const client = new ApiClient({
      fetch: respond(200, { api_version: "v1", schema_version: "1.0" }),
    });
    await expect(client.call("getStatus")).rejects.toThrow(/did not carry a data envelope/);
  });

  it("still accepts a well-formed page whose cursor is null", async () => {
    const client = new ApiClient({
      fetch: respond(200, {
        api_version: "v1",
        schema_version: "1.0",
        data: [],
        page: { limit: 50, next_cursor: null, total: 0 },
      }),
    });
    await expect(client.call("listSources")).resolves.toBeTruthy();
  });
});
