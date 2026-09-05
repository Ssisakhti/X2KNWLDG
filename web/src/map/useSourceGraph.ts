/**
 * The two reads the Source Map is made of (`T-256`).
 *
 * Both go through `useAsync`, so the generation rule that drops a stale answer
 * is one implementation and not three (D-079), and both are deliberately
 * *simpler* than their Knowledge Map counterparts:
 *
 * **The field is one page, not an accumulated snapshot.** `GraphSnapshot`
 * accumulates because `/api/graph` pages over nodes *and* edges and a walk of
 * several pages is one graph. `/api/source-graph` pages over nodes and returns
 * its relations whole, so a second page re-states relations the first already
 * carried: accumulating them would double-count, and merging them would need a
 * rule about which page's copy of a relation wins. One page is one picture, and
 * `page.next_cursor` is how the view says there is more.
 *
 * **A neighbourhood takes no depth.** The endpoint has none (D-272), so there
 * is no control to render and none in the URL. The `limit` is the response's
 * own bound and is reported rather than chosen here.
 */

import { useCallback, useMemo } from "react";

import { api, type ApiClient } from "../api/client";
import type { SourceGraphResponse, SourceNeighborhoodResponse } from "../api/contract";
import { useAsync, type AsyncState } from "../api/useAsync";
import { projectSourceGraph, type SourceProjection } from "./sourceProjection";
import {
  projectSourceNeighbourhood,
  type SourceNeighbourhoodView,
} from "./sourceNeighbourhood";

/** What the field read, and what the response said about it. */
export interface SourceGraphRead {
  readonly projection: SourceProjection;
  readonly counts: SourceGraphResponse["data"]["counts"];
  readonly truncated: boolean;
  readonly page: SourceGraphResponse["page"];
}

export interface SourceGraphState extends AsyncState<SourceGraphRead> {
  /** True while the first answer has not arrived and nothing is drawn yet. */
  readonly unasked: boolean;
}

export function useSourceGraph(client: ApiClient = api): SourceGraphState {
  const run = useCallback(
    async (signal: AbortSignal): Promise<SourceGraphRead> => {
      const response = await client.call("getSourceGraph", { signal });
      return {
        projection: projectSourceGraph(response.data),
        counts: response.data.counts,
        truncated: response.data.truncated,
        page: response.page,
      };
    },
    [client],
  );
  const state = useAsync(run, [client]);
  return useMemo(
    () => ({ ...state, unasked: state.status === "idle" }),
    [state],
  );
}

export interface SourceNeighbourhoodState extends AsyncState<SourceNeighbourhoodView> {
  /** The two-part id the request was made with, or `null` when none was. */
  readonly sourceId: string | null;
}

/**
 * One selected source's brief and relationships.
 *
 * `enabled` is false with nothing selected, which is what keeps the unfocused
 * overview free of a request it has no use for — the same rule
 * `useNeighbourhood` follows. A `404` arrives as an `ApiFailure` and is the
 * view's to render: absence is an answer, and the client does not pre-judge
 * whether an id the URL named exists.
 */
export function useSourceNeighbourhood(
  sourceId: string | null,
  client: ApiClient = api,
): SourceNeighbourhoodState {
  const run = useCallback(
    async (signal: AbortSignal): Promise<SourceNeighbourhoodView> => {
      if (sourceId === null) throw new Error("no source selected");
      const response: SourceNeighborhoodResponse = await client.call("getSourceNeighborhood", {
        params: { source_id: sourceId },
        signal,
      });
      return projectSourceNeighbourhood(response.data);
    },
    [client, sourceId],
  );
  const state = useAsync(run, [client, sourceId], { enabled: sourceId !== null });
  return useMemo(() => ({ ...state, sourceId }), [state, sourceId]);
}
