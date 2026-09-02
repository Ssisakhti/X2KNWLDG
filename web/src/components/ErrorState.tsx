/**
 * A refusal, rendered as the thing it actually is (D-030).
 *
 * The four HTTP codes carry four different meanings and this component keeps
 * them apart, in the UI and not only in the network tab:
 *
 * - `invalid_id` -- the identifier was malformed, so nothing was looked up.
 * - `not_found` -- the identifier was fine and names nothing here.
 * - `unavailable` -- the record exists, its bytes do not. Permanent for an
 *   `external` artifact, so it is not offered as retryable.
 * - `index_unavailable` -- the index is not built. Rendering this as an empty
 *   library would present "no sources yet" as a fact about the user's data,
 *   which is precisely what D-030 added the code to prevent.
 *
 * The server's own message is shown beneath the explanation, never instead of
 * it, and never rewritten.
 */

import type { ApiFailure, FailureCode } from "../api/errors";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n";

const EXPLANATION: Record<FailureCode, MessageKey> = {
  invalid_id: "error.invalid_id",
  invalid_request: "error.invalid_request",
  not_found: "error.not_found",
  unavailable: "error.unavailable",
  index_unavailable: "error.index_unavailable",
  internal: "error.internal",
  transport: "error.transport",
};

/** A refusal is worth retrying only when it might answer differently. */
const RETRYABLE: readonly FailureCode[] = ["index_unavailable", "internal", "transport"];

export function ErrorState({ error, onRetry }: { error: ApiFailure; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className={`notice notice--${error.code}`} role="alert" data-error-code={error.code}>
      <strong>{t("error.title")}</strong>
      <p>{t(EXPLANATION[error.code])}</p>
      {error.message !== "" && (
        <p className="faint" dir="auto">
          {error.message}
        </p>
      )}
      <p className="notice__code">
        {t("error.code")}: {error.code}
        {error.status !== null ? ` · HTTP ${error.status}` : ""}
      </p>
      {onRetry !== undefined && RETRYABLE.includes(error.code) && (
        <button type="button" className="button" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
