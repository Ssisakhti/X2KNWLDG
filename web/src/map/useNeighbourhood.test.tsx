/**
 * The two requests a selection makes (`T-207`).
 *
 * The interesting cases are all about *keeping two answers apart*:
 *
 * - The entity and its neighbourhood are separate endpoints with separate
 *   failure modes, and a reader must not lose a statement they can read
 *   because the list beside it could not be fetched.
 * - A `404` on the entity is a real and different answer from "the Map has not
 *   loaded that node": it says the id names nothing at all.
 * - A response that answers a *replaced* selection is dropped whole, cursorless
 *   or not, because a neighbour list attributed to the wrong centre is worse
 *   than an empty one (D-079's lesson, and the reason the contract echoes
 *   `center_id` back).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiClient } from "../api/client";
import type { EntityRef, IndexedRelation } from "../api/contract";
import { concept, edge, unit } from "../test/graphRecords";
import { jsonFetch } from "../test/render";
import { useNeighbourhood } from "./useNeighbourhood";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const C1 = "library:concepts:C-000001";

function entityBody(entity: EntityRef) {
  return { api_version: "v1", schema_version: "1.0", data: entity };
}

function hoodBody(
  centre: string,
  nodes: EntityRef[],
  edges: IndexedRelation[] = [],
  depth = 1,
) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: { center_id: centre, depth, nodes, edges, truncated: false },
  };
}

const notFound = {
  status: 404,
  body: { error: { code: "not_found", message: "No entity in the index has that id." } },
};

/** The hook, reduced to the facts a view reads off it. */
function Probe({ focus, client }: { focus: string | null; client: ApiClient }) {
  const hood = useNeighbourhood(focus, { client });
  return (
    <div>
      <output data-status>{hood.status}</output>
      <output data-depth>{hood.depth}</output>
      <output data-centre>{hood.centre?.global_id ?? ""}</output>
      <output data-centre-error>{hood.centreError?.message ?? ""}</output>
      <output data-hood>{hood.neighbourhood?.centreId ?? ""}</output>
      <output data-related>
        {(hood.neighbourhood?.related ?? []).map((entity) => entity.globalId).join(",")}
      </output>
      <output data-hood-error>{hood.neighbourhoodError?.message ?? ""}</output>
      <button type="button" onClick={() => hood.setDepth(3)}>
        deeper
      </button>
    </div>
  );
}

const read = (name: string) => document.querySelector(`[data-${name}]`)?.textContent ?? "";

function mount(focus: string | null, fetch: typeof globalThis.fetch) {
  const client = new ApiClient({ fetch });
  return render(<Probe focus={focus} client={client} />);
}

describe("useNeighbourhood", () => {
  it("asks for the entity and its neighbourhood, at the default depth", async () => {
    const urls: string[] = [];
    mount(
      KU1,
      jsonFetch((url) => {
        urls.push(url);
        return url.includes("/api/entities/")
          ? { body: entityBody(unit("KU-000001")) }
          : { body: hoodBody(KU1, [unit("KU-000001"), unit("KU-000002")], [edge(KU1, KU2)]) };
      }),
    );

    await waitFor(() => expect(read("centre")).toBe(KU1));
    expect(read("hood")).toBe(KU1);
    expect(read("related")).toBe(KU2);
    expect(urls.some((url) => url.includes(`/api/entities/${encodeURIComponent(KU1)}`))).toBe(true);
    const hood = urls.find((url) => url.includes("/api/graph/neighborhood/"));
    expect(hood).toContain(encodeURIComponent(KU1));
    expect(hood).toContain("depth=1");
    // The bound is the contract's maximum, not a hope: a neighbourhood has no
    // cursor, so `limit` is the only bound there is.
    expect(hood).toContain("limit=500");
  });

  it("asks nothing at all with nothing selected", async () => {
    const urls: string[] = [];
    mount(
      null,
      jsonFetch((url) => {
        urls.push(url);
        return { body: entityBody(unit("KU-000001")) };
      }),
    );
    await waitFor(() => expect(read("status")).toBe("idle"));
    expect(urls).toEqual([]);
    expect(read("centre")).toBe("");
  });

  it("keeps the entity when the neighbourhood is refused", async () => {
    mount(
      KU1,
      jsonFetch((url) =>
        url.includes("/api/entities/")
          ? { body: entityBody(unit("KU-000001")) }
          : {
              status: 503,
              body: { error: { code: "index_unavailable", message: "The index is rebuilding." } },
            },
      ),
    );
    await waitFor(() => expect(read("centre")).toBe(KU1));
    expect(read("hood-error")).toContain("rebuilding");
    expect(read("centre-error")).toBe("");
    expect(read("hood")).toBe("");
  });

  it("keeps the neighbourhood when the entity is refused", async () => {
    mount(
      KU1,
      jsonFetch((url) =>
        url.includes("/api/entities/")
          ? notFound
          : { body: hoodBody(KU1, [unit("KU-000001"), concept("C-000001")]) },
      ),
    );
    await waitFor(() => expect(read("hood")).toBe(KU1));
    expect(read("related")).toBe(C1);
    expect(read("centre")).toBe("");
    // A `404` here is its own statement: the id names nothing in the index,
    // which is not the same as the Map not having loaded it.
    expect(read("centre-error")).toContain("No entity in the index has that id.");
  });

  it("carries a self-contradicting neighbourhood as a refusal rather than throwing", async () => {
    mount(
      KU1,
      jsonFetch((url) =>
        url.includes("/api/entities/")
          ? { body: entityBody(unit("KU-000001")) }
          : {
              body: hoodBody(KU1, [
                unit("KU-000001"),
                unit("KU-000002"),
                unit("KU-000002", { confidence: 0.1 }),
              ]),
            },
      ),
    );
    await waitFor(() => expect(read("hood-error")).toContain("confidence differs"));
    // And the entity is still readable, because the halves fail separately.
    expect(read("centre")).toBe(KU1);
  });

  it("asks again at a new depth, and says which depth it is asking for", async () => {
    const urls: string[] = [];
    mount(
      KU1,
      jsonFetch((url) => {
        urls.push(url);
        return url.includes("/api/entities/")
          ? { body: entityBody(unit("KU-000001")) }
          : { body: hoodBody(KU1, [unit("KU-000001")], [], 1) };
      }),
    );
    await waitFor(() => expect(read("centre")).toBe(KU1));
    expect(read("depth")).toBe("1");

    screen.getByRole("button", { name: "deeper" }).click();

    await waitFor(() => expect(read("depth")).toBe("3"));
    await waitFor(() =>
      expect(urls.some((url) => url.includes("depth=3"))).toBe(true),
    );
  });

  it("reports nothing for a selection whose answer has not arrived", async () => {
    // `useAsync` keeps the previous `data` while the next request is in
    // flight. Showing it here would put one entity's statement under another
    // entity's id for as long as the request took -- and a slow request is
    // exactly when a reader is looking.
    // Both of the second selection's requests are held: `Promise.all` waits
    // for the pair, so releasing one would prove nothing.
    const held: (() => void)[] = [];
    const fetch = ((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const first = url.includes(encodeURIComponent(KU1));
      const body = url.includes("/api/entities/")
        ? entityBody(unit(first ? "KU-000001" : "KU-000002"))
        : hoodBody(first ? KU1 : KU2, [unit(first ? "KU-000001" : "KU-000002")]);
      const answer = () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      if (first) return Promise.resolve(answer());
      return new Promise<Response>((resolve) => {
        held.push(() => resolve(answer()));
      });
    }) as typeof globalThis.fetch;

    const client = new ApiClient({ fetch });
    const view = render(<Probe focus={KU1} client={client} />);
    await waitFor(() => expect(read("centre")).toBe(KU1));

    view.rerender(<Probe focus={KU2} client={client} />);

    // The second selection's answer is still in flight, so nothing is
    // reported: not the previous entity, and not the previous list.
    await waitFor(() => expect(read("status")).toBe("loading"));
    expect(read("centre")).toBe("");
    expect(read("hood")).toBe("");
    expect(read("related")).toBe("");

    for (const release of held) release();
    await waitFor(() => expect(read("centre")).toBe(KU2));
  });

  it("reports nothing once the focus is cleared", async () => {
    const client = new ApiClient({
      fetch: jsonFetch((url) =>
        url.includes("/api/entities/")
          ? { body: entityBody(unit("KU-000001")) }
          : { body: hoodBody(KU1, [unit("KU-000001"), unit("KU-000002")]) },
      ),
    });
    const view = render(<Probe focus={KU1} client={client} />);
    await waitFor(() => expect(read("centre")).toBe(KU1));

    view.rerender(<Probe focus={null} client={client} />);

    await waitFor(() => expect(read("status")).toBe("idle"));
    expect(read("centre")).toBe("");
    expect(read("hood")).toBe("");
    expect(read("centre-error")).toBe("");
  });

  it("drops the answer to a selection that has been replaced", async () => {
    // The first request is left in flight while the focus changes. Its late
    // answer must not attribute `KU-000001`'s neighbours to `KU-000002`.
    const pending: (() => void)[] = [];
    const fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const first = url.includes(encodeURIComponent(KU1));
      const body = url.includes("/api/entities/")
        ? entityBody(unit(first ? "KU-000001" : "KU-000002"))
        : hoodBody(
            first ? KU1 : KU2,
            first ? [unit("KU-000001"), concept("C-000001")] : [unit("KU-000002")],
          );
      const answer = () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      if (!first) return Promise.resolve(answer());
      return new Promise<Response>((resolve, reject) => {
        pending.push(() => resolve(answer()));
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      });
    }) as typeof globalThis.fetch;

    const client = new ApiClient({ fetch });
    const view = render(<Probe focus={KU1} client={client} />);
    view.rerender(<Probe focus={KU2} client={client} />);

    // The retired request answers late; the hook has already moved on.
    for (const answer of pending) answer();

    await waitFor(() => expect(read("hood")).toBe(KU2));
    expect(read("related")).toBe("");
    expect(read("centre")).toBe(KU2);
    // No trace of the retired question, and no rendered failure for the abort
    // that retired it.
    expect(read("hood-error")).toBe("");
    expect(read("centre-error")).toBe("");
  });
});
