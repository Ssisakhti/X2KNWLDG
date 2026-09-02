/**
 * The two endpoints a selection opens (`T-207`).
 *
 * `GET /api/entities/{entity_id}` and `GET /api/graph/neighborhood/{entity_id}`
 * are the last two operations of the frozen contract nothing had called. One
 * says what the selected entity *is*, authoritatively and whether or not the
 * Map has drawn it; the other says what it is connected to, bounded by `depth`
 * and by the server's `limit`.
 *
 * **Why the entity is fetched at all, when the graph may already hold it.**
 * Because it may not. A focus can arrive from a URL, from a search hit the
 * pages have not reached, or from a filtered walk that excludes the entity's
 * own provenance class -- and in each of those cases the loaded graph has no
 * record, so a Quick Read built from the graph would be an empty panel over a
 * real entity. Asking the endpoint that addresses an entity by id is also the
 * only way a `404 not_found` can be *stated*: the difference between "this id
 * names nothing" and "this Map has not loaded it yet" is exactly the
 * distinction the rail has been unable to make until now.
 *
 * **The two halves fail separately, so they are reported separately.** A
 * rejected `Promise.all` would lose a perfectly good centre record because the
 * neighbourhood request failed, and would lose the neighbourhood because the
 * centre 404'd. Each call is therefore caught on its own and its refusal is
 * carried as a value, while anything that is not an `ApiFailure` -- an
 * `AbortError` above all -- is rethrown so `useAsync`'s own generation logic
 * still drops a stale answer whole (D-079).
 *
 * **One request per selection, and none without one.** `deps` are the focus
 * and the depth, so a new focus is a new question and a re-render is not;
 * `enabled` is false with nothing selected, which is what keeps the Map's
 * unfocused overview free of requests it has no use for.
 *
 * **Depth is not in the URL.** D-119 froze the Map's grammar at selection plus
 * three filters, and `mapLink` is deliberately the only thing that spells a
 * Map URL. A depth control writes no history for the same reason the search
 * query does not (D-136): it is a bound on one request, it changes nothing
 * about which graph is drawn, and a fifth parameter is a change to the frozen
 * grammar rather than a component's local decision.
 */

import { useCallback, useMemo, useState } from "react";

import { api, type ApiClient } from "../api/client";
import { ApiFailure } from "../api/errors";
import type { EntityRef } from "../api/contract";
import { useAsync, type AsyncStatus } from "../api/useAsync";
import { GraphConflictError } from "./graphProjection";
import {
  MAP_DEFAULT_DEPTH,
  type MapDepth,
  type Neighbourhood,
  projectNeighbourhood,
} from "./neighbourhood";

/**
 * Neighbours requested per selection.
 *
 * The contract's `limit` maximum, the same value `GRAPH_PAGE_LIMIT` is and for
 * the same reason: the bound should be one the server declares rather than one
 * the client hopes for. A neighbourhood is not paged -- `NeighborhoodResponse`
 * carries no `page` and there is no cursor to resume from -- so this is the
 * only bound there is, and `truncated` is how the server says it bit.
 */
export const NEIGHBOURHOOD_LIMIT = 500;

/** What one refusal looks like: the server's, or a response that contradicts itself. */
export type NeighbourhoodFailure = ApiFailure | GraphConflictError;

export interface NeighbourhoodBinding {
  /** The depth being asked for. */
  depth: MapDepth;
  /** Ask again at another depth. Not a URL change, and no history entry. */
  setDepth: (depth: MapDepth) => void;
  /** `idle` with nothing selected; never `loading` for a selection there isn't. */
  status: AsyncStatus;
  /** The selected entity as `/api/entities/{id}` states it, or `null`. */
  centre: EntityRef | null;
  /** Why the entity could not be read. A `404` here means the id names nothing. */
  centreError: NeighbourhoodFailure | null;
  /** The bounded neighbourhood, projected, or `null`. */
  neighbourhood: Neighbourhood | null;
  /** Why the neighbourhood could not be read. */
  neighbourhoodError: NeighbourhoodFailure | null;
  /** Ask both questions again. */
  reload: () => void;
}

/** One half's answer, or its refusal. Never both, never neither. */
interface Half<T> {
  value: T | null;
  error: NeighbourhoodFailure | null;
}

/**
 * Run one call, keeping an `ApiFailure` as a value.
 *
 * Anything else is rethrown untouched -- an `AbortError` most of all, because
 * `useAsync` aborts the request it has replaced and swallowing that here would
 * turn a retired question into a rendered failure.
 */
async function half<T>(run: () => Promise<T>): Promise<Half<T>> {
  try {
    return { value: await run(), error: null };
  } catch (cause) {
    if (cause instanceof ApiFailure || cause instanceof GraphConflictError) {
      return { value: null, error: cause };
    }
    throw cause;
  }
}

export function useNeighbourhood(
  focus: string | null,
  options: { client?: ApiClient; initialDepth?: MapDepth; limit?: number } = {},
): NeighbourhoodBinding {
  const client = options.client ?? api;
  const limit = options.limit ?? NEIGHBOURHOOD_LIMIT;
  const [depth, setDepth] = useState<MapDepth>(options.initialDepth ?? MAP_DEFAULT_DEPTH);

  const run = useCallback(
    async (signal: AbortSignal) => {
      // Narrowed for the closure: `enabled` already keeps this from running
      // with nothing selected, and an id built here would be an id invented
      // here.
      if (focus === null) throw new ApiFailure("internal", "No entity is selected.");
      const [entity, hood] = await Promise.all([
        half(() => client.call("getEntity", { params: { entity_id: focus }, signal })),
        half(async () => {
          const response = await client.call("getNeighborhood", {
            params: { entity_id: focus },
            query: { depth, limit },
            signal,
          });
          // Projected inside the guarded half, so a response that states one
          // identity twice with two different records is reported the same way
          // a refusal is rather than thrown into the render (D-125).
          return projectNeighbourhood(response.data);
        }),
      ]);
      // Which selection this answer belongs to, carried with it. `useAsync`
      // keeps the previous `data` while the next request is in flight -- which
      // is right for a list being refreshed and wrong here, because it would
      // show one entity's statement under another entity's id for as long as
      // the request took.
      return { focus, entity, hood };
    },
    [client, focus, depth, limit],
  );

  const state = useAsync(run, [focus, depth, limit], { enabled: focus !== null });

  // Only an answer to the *current* question is reported. Two things make this
  // necessary rather than defensive: `useAsync` holds the previous `data`
  // while the next request is in flight, and clearing the focus disables the
  // hook without clearing anything. Either way the previous selection's answer
  // is still in hand, and rendering it beside the new selection's id is the
  // mis-attribution the contract echoes `center_id` back to prevent.
  const answer = state.data?.focus === focus && focus !== null ? state.data : null;
  const centre = answer?.entity.value?.data ?? null;
  const neighbourhood = answer?.hood.value ?? null;

  return useMemo(
    () => ({
      depth,
      setDepth,
      status: state.status,
      centre,
      // `state.error` is the one path `half` re-raised: a failure that is not
      // one of the two halves' own. It is reported against the centre, because
      // that is the panel a reader is looking at when nothing appears.
      centreError: answer?.entity.error ?? (focus === null ? null : state.error),
      neighbourhood,
      neighbourhoodError: answer?.hood.error ?? null,
      reload: state.reload,
    }),
    [depth, focus, state.status, state.error, state.reload, answer, centre, neighbourhood],
  );
}
