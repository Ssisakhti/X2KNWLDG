/**
 * The D-030 error taxonomy, as something the UI can branch on.
 *
 * The four HTTP refusals mean four different things and the UI must not blur
 * them:
 *
 * - `400 invalid_id`      the identifier was malformed; nothing was looked up.
 * - `404 not_found`       the identifier was well formed and names nothing.
 * - `404 unavailable`     the record exists and its bytes do not.
 * - `503 index_unavailable` the index is not built, so the server cannot say
 *   what the library holds. This code exists precisely so that "no sources
 *   yet" is never presented as a fact about the user's data -- rendering it
 *   as an empty library would be the failure the code was added to prevent.
 *
 * `transport` is ours, not the contract's: the request never reached a server
 * that could answer. It is kept distinct from `internal` so a stopped backend
 * does not read as a server bug.
 */

import type { ErrorCode, ErrorResponse } from "./contract";
import { keysOf } from "./vocabulary";

export type FailureCode = ErrorCode | "transport";

export class ApiFailure extends Error {
  readonly code: FailureCode;
  readonly status: number | null;
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: FailureCode,
    message: string,
    status: number | null = null,
    detail: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiFailure";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

/** True when the failure means "the index is not built", not "the library is empty". */
export function isIndexUnavailable(error: unknown): boolean {
  return error instanceof ApiFailure && error.code === "index_unavailable";
}

// D-107: `readonly ErrorCode[]` accepts a *subset*, so adding a seventh
// `ErrorCode` compiled silently and `failureFromBody` reclassified it as
// `internal` — discarding the server's own code and message on the one path
// whose job is to carry them. `keysOf` takes a `Record<T, true>`, so a missing
// member is a compile error; `vocabulary.ts` documents exactly this and has
// used it since D-058. It is the same helper, imported, not a second copy.
const CODES = keysOf<ErrorCode>({
  invalid_id: true,
  invalid_request: true,
  not_found: true,
  unavailable: true,
  index_unavailable: true,
  internal: true,
});

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && (CODES as readonly string[]).includes(value);
}

/**
 * The failure a non-2xx response describes.
 *
 * The server's own `code` is used verbatim when the body is the frozen
 * `ErrorResponse`. When it is not -- a proxy, a crash before the handler --
 * the status is reported as `internal` and carried, rather than being guessed
 * into one of the four meanings.
 */
export function failureFromBody(status: number, body: unknown): ApiFailure {
  if (typeof body === "object" && body !== null && "error" in body) {
    const envelope = body as ErrorResponse;
    const error = envelope.error;
    if (error !== undefined && isErrorCode(error.code)) {
      return new ApiFailure(
        error.code,
        typeof error.message === "string" ? error.message : "",
        status,
        error.detail ?? null,
      );
    }
  }
  return new ApiFailure("internal", `The server answered ${status}.`, status);
}
