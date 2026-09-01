/**
 * The client against the **real** server, not a mock.
 *
 * A mock agrees with whatever the frontend assumed, which is why the brief for
 * this track says to prefer the real API: `create_app(project_root=...)`
 * serves all eleven endpoints over the committed run fixtures, and it
 * disagrees when this code is wrong.
 *
 * Skipped unless `X2KNWLDG_API_BASE` names a running server, so `npm test`
 * stays hermetic:
 *
 *     npm run dev:api                                  # terminal one
 *     X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test # terminal two
 *
 * Every assertion here is about a property the UI depends on and a mock could
 * not have taught us: that the fixture statuses really are `PASS`, `PARTIAL`
 * and `FAIL`; that an `external` artifact really answers `404 unavailable`
 * rather than `503`; that a malformed id really is `400` while a well-formed
 * unknown one is `404`; and that a caption hit really carries no `global_id`.
 */

import { describe, expect, it } from "vitest";

import { readCaptions } from "./canonical";
import { ApiClient } from "./client";
import { ApiFailure } from "./errors";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;
const client = new ApiClient({ baseUrl: BASE ?? "" });

async function failureOf(call: Promise<unknown>): Promise<ApiFailure> {
  try {
    await call;
  } catch (cause) {
    if (cause instanceof ApiFailure) return cause;
    throw cause;
  }
  throw new Error("the call was expected to be refused and was not");
}

describe.skipIf(BASE === undefined || BASE === "")("against a running server", () => {
  it("reports the index state and honest tallies", async () => {
    const status = await client.call("getStatus");
    expect(status.api_version).toBe("v1");
    expect(["absent", "building", "ready", "error"]).toContain(status.data.index.state);
    expect(status.data.counts.sources).toBeGreaterThanOrEqual(0);
  });

  it("serves the three labelled fixture statuses without coercing any of them", async () => {
    const sources = await client.call("listSources", { query: { limit: 500 } });
    const byStatus = new Set(sources.data.map((source) => source.status.overall));
    expect(byStatus.has("PASS")).toBe(true);
    expect(byStatus.has("PARTIAL")).toBe(true);
    expect(byStatus.has("FAIL")).toBe(true);
  });

  it("keeps a failing run's passing coverage visible", async () => {
    const sources = await client.call("listSources", { query: { limit: 500 } });
    const failing = sources.data.find((source) => source.status.overall === "FAIL");
    expect(failing).toBeDefined();
    expect(failing?.status.validation).toBe("FAIL");
    expect(failing?.status.coverage).toBe("PASS");
  });

  it("serves a transcript through the byte channel that the reader can parse", async () => {
    const sources = await client.call("listSources", { query: { limit: 1 } });
    const first = sources.data[0];
    expect(first).toBeDefined();
    const detail = await client.call("getSource", { params: { source_id: first!.id } });
    const transcript = detail.data.artifacts.find((artifact) => artifact.kind === "transcript");
    expect(transcript).toBeDefined();
    const captions = readCaptions(await client.media(transcript!.id));
    expect(captions).not.toBeNull();
    expect((captions ?? []).length).toBeGreaterThan(0);
  });

  it("answers 404 unavailable for an external artifact, never 503", async () => {
    const sources = await client.call("listSources", { query: { limit: 1 } });
    const first = sources.data[0]!;
    const detail = await client.call("getSource", { params: { source_id: first.id } });
    const external = detail.data.artifacts.find((artifact) => artifact.role === "external");
    expect(external).toBeDefined();
    const failure = await failureOf(client.media(external!.id));
    expect(failure.code).toBe("unavailable");
    expect(failure.status).toBe(404);
  });

  it("keeps a malformed id and an unknown one apart (D-020)", async () => {
    const malformed = await failureOf(
      client.call("getEntity", { params: { entity_id: "not-a-global-id" } }),
    );
    expect(malformed.code).toBe("invalid_id");
    expect(malformed.status).toBe(400);

    const unknown = await failureOf(
      client.call("getEntity", { params: { entity_id: "youtube:nothing:KU-000001" } }),
    );
    expect(unknown.code).toBe("not_found");
    expect(unknown.status).toBe(404);
  });

  it("never names a host path in a refusal", async () => {
    const failure = await failureOf(
      client.call("getSource", { params: { source_id: "youtube:../../etc" } }),
    );
    expect(failure.message).not.toContain("/Users/");
    expect(failure.message).not.toContain("/home/");
  });

  it("returns caption hits with no global_id to address (D-023)", async () => {
    const results = await client.call("search", {
      query: { q: "coverage", include_transcript: true, limit: 25 },
    });
    expect(results.query).toBe("coverage");
    const captions = results.data.filter((hit) => hit.type === "transcript_caption");
    expect(captions.length).toBeGreaterThan(0);
    for (const hit of captions) {
      expect("global_id" in hit).toBe(false);
      expect(hit.source_url).toMatch(/&t=\d+s$/);
    }
  });

  it("pages a collection through the cursor it was given", async () => {
    const first = await client.call("listSources", { query: { limit: 1 } });
    expect(first.data).toHaveLength(1);
    if (first.page.next_cursor !== null) {
      const second = await client.call("listSources", {
        query: { limit: 1, cursor: first.page.next_cursor },
      });
      expect(second.data[0]?.id).not.toBe(first.data[0]?.id);
    }
  });
});
