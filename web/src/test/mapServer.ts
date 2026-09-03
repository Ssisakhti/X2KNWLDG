/**
 * The Map route's own server, and the stage it draws on (`T-204`-`T-208`).
 *
 * Extracted from `MapView.test.tsx` when `T-208` gave the route a second
 * suite, for the reason the shared renderer fake already exists: two copies
 * of a stub server are two chances for one suite to assert against a server
 * that answers unlike the other. Everything here is shaped like the real
 * payloads -- `mapFetch` routes by path rather than answering everything the
 * same way, and its defaults are the *empty honest answers* (no sources, a
 * `404` for an entity, an empty neighbourhood), so a test that cares about
 * one of them says so by overriding it.
 *
 * `library()` is the one small library the walks are performed against: three
 * entities, two vocabularies of relation between them, and a statement long
 * enough that "the card shortens it visibly" and "Quick Read shows it whole"
 * are two assertions about one record.
 */

import { vi } from "vitest";

import type { EntityRef, IndexedRelation } from "../api/contract";
import { concept, edge, expressesConcept, unit } from "./graphRecords";
import { jsonFetch } from "./render";

/**
 * The graph responder, plus the four other endpoints this route touches.
 *
 * `MapFilters` fetches `listSources` to fill its one server-backed control,
 * and a selection fetches `getEntity` and `getNeighborhood` (`T-207`) -- so a
 * stub answering every URL with a graph page hands the filter a page envelope
 * where a source array belongs, and hands the neighbourhood a payload with no
 * `center_id`. Routing by path rather than answering everything the same way
 * is also what keeps a test honest about *which* request it is asserting on.
 *
 * The defaults are deliberately the *empty* honest answers -- no sources, a
 * `404` for an entity, an empty neighbourhood -- so a test that cares about
 * one of them says so by overriding it, and a test that does not is not
 * quietly relying on a fixture.
 */
export function mapFetch(
  responder: (url: string) => { status?: number; body: unknown },
  extra: (url: string) => { status?: number; body: unknown } | null = () => null,
): typeof fetch {
  return jsonFetch((url) => {
    const override = extra(url);
    if (override !== null) return override;
    if (url.includes("/api/sources")) {
      return { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } };
    }
    if (url.includes("/api/entities/")) {
      return {
        status: 404,
        body: { error: { code: "not_found", message: "No entity in the index has that id." } },
      };
    }
    if (url.includes("/api/graph/neighborhood/")) {
      return { body: neighbourhoodBody(entityIdOf(url), []) };
    }
    if (url.includes("/api/search")) {
      // Counted, and none: the rail renders `total: null` differently, so the
      // default must not be the ambiguous one.
      return { body: { data: [], page: { limit: 25, next_cursor: null, total: 0 } } };
    }
    return responder(url);
  });
}

/** The `entity_id` a path parameter carried, decoded the way the client encoded it. */
export function entityIdOf(url: string): string {
  const last = url.split("?")[0]?.split("/").pop() ?? "";
  return decodeURIComponent(last);
}

export function entityBody(entity: EntityRef) {
  return { api_version: "v1", schema_version: "1.0", data: entity };
}

export function neighbourhoodBody(
  centre: string,
  nodes: EntityRef[],
  edges: IndexedRelation[] = [],
  options: { depth?: number; truncated?: boolean } = {},
) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: {
      center_id: centre,
      depth: options.depth ?? 1,
      nodes,
      edges,
      truncated: options.truncated ?? false,
    },
  };
}

export const KU1 = "youtube:pqlWNihgdjI:KU-000001";
export const KU2 = "youtube:pqlWNihgdjI:KU-000002";
export const C1 = "library:concepts:C-000001";

/**
 * A statement longer than any preview budget.
 *
 * So that "the card shortens it visibly" and "Quick Read shows it whole" are
 * two assertions about one record rather than two fixtures.
 */
export const LONG_STATEMENT = `${"A statement the transcript actually makes, at length. ".repeat(12)}End.`;

export function graphBody(
  nodes: EntityRef[],
  edges: IndexedRelation[],
  options: { truncated?: boolean; next?: string | null; total?: number | null } = {},
) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: { nodes, edges, truncated: options.truncated ?? false },
    page: { limit: 500, next_cursor: options.next ?? null, total: options.total ?? null },
  };
}

export const STAGE = { width: 900, height: 600 };

/** A stage with a real size, which jsdom does not otherwise provide. */
export function sizeTheStage(stage: { width: number; height: number } = STAGE): void {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
    this: Element,
  ) {
    const sized = this.hasAttribute("data-map-stage");
    const width = sized ? stage.width : 0;
    const height = sized ? stage.height : 0;
    return {
      x: 0,
      y: 0,
      width,
      height,
      top: 0,
      left: 0,
      right: width,
      bottom: height,
      toJSON: () => ({}),
    } as DOMRect;
  });
}

/** The graph, the two entities and the two neighbourhoods of one small library. */
export function library(): typeof fetch {
  const one = unit("KU-000001", { label: LONG_STATEMENT });
  const two = unit("KU-000002");
  const three = concept("C-000001");
  return mapFetch(
    () => ({
      body: graphBody([one, two, three], [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)], {
        total: 3,
      }),
    }),
    (url) => {
      if (url.includes("/api/entities/")) {
        const id = entityIdOf(url);
        const record = [one, two, three].find((entity) => entity.global_id === id);
        return record === undefined
          ? {
              status: 404,
              body: { error: { code: "not_found", message: "No entity has that id." } },
            }
          : { body: entityBody(record) };
      }
      if (url.includes("/api/graph/neighborhood/")) {
        const id = entityIdOf(url);
        if (id === KU1) {
          return {
            body: neighbourhoodBody(
              KU1,
              [one, two, three],
              [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)],
            ),
          };
        }
        if (id === KU2) {
          return { body: neighbourhoodBody(KU2, [two, one], [edge(KU1, KU2, "supports")]) };
        }
        return { body: neighbourhoodBody(id, []) };
      }
      return null;
    },
  );
}
