/**
 * The typed client for the eleven frozen endpoints.
 *
 * Two properties are worth the small amount of machinery here:
 *
 * 1. `PATHS` is typed as `{ [K in OperationId]: Endpoints[K]["path"] }`, so
 *    the compiler checks every path literal against the frozen contract and
 *    refuses a table that has drifted from it or forgotten an operation. A
 *    path this file could not spell correctly is a build failure, not a 404
 *    at runtime.
 * 2. Parameters and query values are the contract's own types. There is no
 *    way to call a path the contract does not define, pass a query parameter
 *    it does not accept, or read a field it does not return.
 *
 * Widening any of that is a change to the frozen document first
 * (`openapi.json`), a regenerated declaration second, and this file third --
 * never this file alone.
 */

import type { Endpoints, OperationId } from "./contract";
import { ApiFailure, failureFromBody } from "./errors";

type Operation<K extends OperationId> = Endpoints[K];

/** Runtime paths, checked against the contract's literal types by the compiler. */
export const PATHS: { [K in OperationId]: Operation<K>["path"] } = {
  getStatus: "/api/status",
  listSources: "/api/sources",
  getSource: "/api/sources/{source_id}",
  listSourceEntities: "/api/sources/{source_id}/entities",
  listSourceRelations: "/api/sources/{source_id}/relations",
  getEntity: "/api/entities/{entity_id}",
  getArtifact: "/api/artifacts/{artifact_id}",
  getArtifactMedia: "/api/media/{artifact_id}",
  search: "/api/search",
  getGraph: "/api/graph",
  getNeighborhood: "/api/graph/neighborhood/{entity_id}",
};

export type QueryValue = string | number | boolean | undefined;

export interface CallOptions<K extends OperationId> {
  params?: Operation<K>["params"];
  query?: Operation<K>["query"];
  signal?: AbortSignal;
}

/**
 * Substitute `{name}` path parameters.
 *
 * Every value is percent-encoded. A global id's colons survive the round trip
 * as `%3A`, and a value carrying a slash becomes `%2F`, which the server
 * answers `404` by segment matching (D-056) -- refused, never rewritten into a
 * different path.
 */
export function buildPath(template: string, params: Record<string, unknown> | undefined): string {
  return template.replace(/\{(\w+)\}/g, (_whole, name: string) => {
    const value = params?.[name];
    if (value === undefined || value === null) {
      throw new ApiFailure("invalid_request", `The path parameter ${name} was not supplied.`);
    }
    return encodeURIComponent(String(value));
  });
}

export function buildQuery(query: Record<string, QueryValue> | undefined): string {
  if (query === undefined) return "";
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value === undefined) continue;
    search.set(name, typeof value === "boolean" ? String(value) : String(value));
  }
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

export interface ClientOptions {
  /** Origin the API is served from. Empty means "the page's own origin". */
  baseUrl?: string;
  fetch?: typeof fetch;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly doFetch: typeof fetch;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.doFetch = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  }

  /** The absolute URL of an operation, which is also what a media element needs as `src`. */
  url<K extends OperationId>(operation: K, options: CallOptions<K> = {}): string {
    const path = buildPath(PATHS[operation], options.params as Record<string, unknown> | undefined);
    const query = buildQuery(options.query as Record<string, QueryValue> | undefined);
    return `${this.baseUrl}${path}${query}`;
  }

  private async send<K extends OperationId>(
    operation: K,
    options: CallOptions<K>,
    accept: string,
  ): Promise<Response> {
    const url = this.url(operation, options);
    let response: Response;
    try {
      const init: RequestInit = { headers: { Accept: accept } };
      if (options.signal !== undefined) init.signal = options.signal;
      response = await this.doFetch(url, init);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new ApiFailure(
        "transport",
        cause instanceof Error ? cause.message : "The request could not be sent.",
      );
    }
    if (!response.ok) {
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        body = null;
      }
      throw failureFromBody(response.status, body);
    }
    return response;
  }

  /** Call a JSON operation and return its body, typed by the contract. */
  async call<K extends Exclude<OperationId, "getArtifactMedia">>(
    operation: K,
    options: CallOptions<K> = {},
  ): Promise<Operation<K>["response"]> {
    const response = await this.send(operation, options, "application/json");
    return (await response.json()) as Operation<K>["response"];
  }

  /**
   * The bytes of one artifact, as text.
   *
   * Canonical JSON and the Markdown report go out byte for byte, so this is
   * how the Reader gets a transcript or a report. The refusals are the same
   * taxonomy as everywhere else: an `external` artifact answers `404
   * unavailable`, which is permanent, and never `503`.
   */
  async media(artifactId: string, signal?: AbortSignal): Promise<string> {
    const options: CallOptions<"getArtifactMedia"> = { params: { artifact_id: artifactId } };
    if (signal !== undefined) options.signal = signal;
    const response = await this.send("getArtifactMedia", options, "*/*");
    return await response.text();
  }

  /** The URL a `<video>` or `<a>` would use for an artifact's bytes. */
  mediaUrl(artifactId: string): string {
    return this.url("getArtifactMedia", { params: { artifact_id: artifactId } });
  }
}

/** The client the application uses. Same origin: the dev server proxies `/api`. */
export const api = new ApiClient();
