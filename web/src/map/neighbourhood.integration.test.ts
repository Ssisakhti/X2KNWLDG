/**
 * The bounded neighbourhood against the **real** server (`T-207`).
 *
 * The unit tests establish that the projection keeps every neighbour a
 * *fixture* returns. What no fixture can establish is that it keeps every
 * neighbour the **repository** returns -- over the real 86-node/118-edge graph,
 * where the most connected entity is a derived unit with eight neighbours,
 * thirteen edges among them, both relation vocabularies, and a canonical
 * concept that belongs to no source at all. A mock would agree with whatever
 * this client assumed about the shape of that answer; the server does not.
 *
 * Three properties are checked that only a real answer can settle:
 *
 * 1. **Nothing is dropped.** Every node the response carries is in the related
 *    list, every edge is either joined or counted, and nothing is unreachable.
 * 2. **The two endpoints agree.** `/api/entities/{id}` and the graph page
 *    return the same record for one id, field by field -- which is why the
 *    Map can read a selection from either without the projection refusing a
 *    contradiction.
 * 3. **The density policy accounts for everything it does not place.** Cards
 *    placed plus omissions counted equals the number of neighbours returned,
 *    on the real fan-out rather than on a hand-built one.
 *
 * Skipped unless `X2KNWLDG_API_BASE` names a running server, so `npm test`
 * stays hermetic:
 *
 *     npm run dev:api                                  # terminal one
 *     X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test # terminal two
 */

import { describe, expect, it } from "vitest";

import { ApiClient } from "../api/client";
import { sameRecord } from "./graphProjection";
import { placeConstellation } from "./constellation";
import { MAP_DEPTH_MAX, projectNeighbourhood } from "./neighbourhood";
import { NEIGHBOURHOOD_LIMIT } from "./useNeighbourhood";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;
const client = new ApiClient({ baseUrl: BASE ?? "" });

/** The entity with the most edges in the served graph, and the whole graph. */
async function busiest() {
  const graph = await client.call("getGraph", { query: { limit: 500 } });
  // If this fires, the comparison below is against a cut graph rather than a
  // failure of the projection.
  expect(graph.data.truncated).toBe(false);
  const degree = new Map<string, number>();
  for (const edge of graph.data.edges) {
    for (const endpoint of [edge.from_id, edge.to_id]) {
      degree.set(endpoint, (degree.get(endpoint) ?? 0) + 1);
    }
  }
  const [entityId] = [...degree.entries()].sort(
    (left, right) => right[1] - left[1] || (left[0] < right[0] ? -1 : 1),
  )[0] ?? [null];
  expect(entityId).not.toBeNull();
  return { graph: graph.data, entityId: entityId as string };
}

describe.skipIf(BASE === undefined || BASE === "")(
  "the Map's neighbourhood against a running server",
  () => {
    it("lists every neighbour the server returned, and accounts for every edge", async () => {
      const { entityId } = await busiest();
      const response = await client.call("getNeighborhood", {
        params: { entity_id: entityId },
        query: { depth: 1, limit: NEIGHBOURHOOD_LIMIT },
      });
      const payload = response.data;
      const hood = projectNeighbourhood(payload);

      expect(hood.centreId).toBe(entityId);
      expect(payload.center_id).toBe(entityId);
      // The real fan-out is worth having as a number: a centre with one
      // neighbour would not exercise the comparison `T-207` is judged on.
      expect(payload.nodes.length).toBeGreaterThan(2);

      const returned = new Set(payload.nodes.map((node) => node.global_id));
      returned.delete(entityId);
      expect(new Set(hood.related.map((entity) => entity.globalId))).toEqual(returned);
      expect(hood.related).toHaveLength(returned.size);

      const edgeIds = new Set(payload.edges.map((edge) => edge.id));
      expect(hood.edgesReturned + hood.edgesUnjoinable).toBe(edgeIds.size);
      // Both repository implementations guarantee every returned edge runs
      // between returned nodes, and this is where that is checked rather than
      // assumed.
      expect(hood.edgesUnjoinable).toBe(0);
      expect(hood.unreachable).toBe(0);

      // Every neighbour is one hop out at depth 1, and every one of them names
      // at least one real relation to the centre.
      for (const entity of hood.related) {
        expect(entity.hops).toBe(1);
        expect(entity.toCentre.length).toBeGreaterThan(0);
        for (const relation of entity.toCentre) {
          expect([relation.record.from_id, relation.record.to_id]).toContain(entityId);
          expect(relation.record.relation.length).toBeGreaterThan(0);
        }
      }
    });

    it("reads the same record from the entity endpoint as from the graph", async () => {
      // Two endpoints, one record. If they ever disagreed, a Map that merged
      // them through one projection would refuse the page -- so this is the
      // assumption that lets a selection be read from either.
      const { graph, entityId } = await busiest();
      const fromGraph = graph.nodes.find((node) => node.global_id === entityId);
      const fromEndpoint = await client.call("getEntity", {
        params: { entity_id: entityId },
      });
      expect(fromGraph).toBeDefined();
      expect(sameRecord(fromGraph, fromEndpoint.data)).toBe(true);
    });

    it("grows with depth and stays reachable at the contract's maximum", async () => {
      const { entityId } = await busiest();
      const walked = [];
      for (const depth of [1, 2, MAP_DEPTH_MAX] as const) {
        const response = await client.call("getNeighborhood", {
          params: { entity_id: entityId },
          query: { depth, limit: NEIGHBOURHOOD_LIMIT },
        });
        const hood = projectNeighbourhood(response.data);
        expect(response.data.depth).toBe(depth);
        expect(hood.unreachable).toBe(0);
        expect(hood.edgesUnjoinable).toBe(0);
        // Every neighbour is within the depth that was asked for, which is the
        // client's own check on a bound it did not compute.
        for (const entity of hood.related) expect(entity.hops).toBeLessThanOrEqual(depth);
        walked.push(hood);
      }
      const [one, two, three] = walked;
      expect(two!.related.length).toBeGreaterThanOrEqual(one!.related.length);
      expect(three!.related.length).toBeGreaterThanOrEqual(two!.related.length);
    });

    it("places some cards and accounts for every neighbour it does not", async () => {
      const { entityId } = await busiest();
      const response = await client.call("getNeighborhood", {
        params: { entity_id: entityId },
        query: { depth: 1, limit: NEIGHBOURHOOD_LIMIT },
      });
      const hood = projectNeighbourhood(response.data);
      // Every mark loaded and spread out, which is the *most* favourable case
      // for the stage -- and the budget still bites on the real fan-out, which
      // is exactly why the related list exists (R20).
      let index = 0;
      const placement = placeConstellation({
        centreId: entityId,
        related: hood.related,
        position: () => {
          index += 1;
          return { x: 60 + (index % 3) * 260, y: 60 + Math.floor(index / 3) * 200 };
        },
        stage: { width: 900, height: 600 },
      });
      expect(placement.cards.length + placement.omittedTotal).toBe(hood.related.length);
      expect(placement.cards.length).toBeLessThanOrEqual(hood.related.length);
    });
  },
);
