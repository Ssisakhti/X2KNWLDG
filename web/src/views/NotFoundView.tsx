/**
 * A route this application does not have.
 *
 * Distinct from the API's `404 not_found`, which is a statement about the
 * user's data. This one is a statement about the URL, and saying so keeps a
 * mistyped link from reading as an empty library.
 */

import { Link } from "react-router-dom";

import { useI18n } from "../i18n";

export function NotFoundView() {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1>{t("error.not_found")}</h1>
      <Link to="/">{t("common.back")}</Link>
    </div>
  );
}
