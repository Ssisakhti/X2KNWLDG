/**
 * The application frame: brand, navigation, and the language switch.
 *
 * The switch is here rather than in a settings page because direction is part
 * of the layout, and the fastest way to find a place where a physical CSS
 * property survived is to flip the whole UI to `rtl` and look at it (D-012).
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { LOCALES, useI18n } from "../i18n";
import type { Locale } from "../i18n";

function LocaleSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <label className="field">
      <span className="visually-hidden">{t("locale.label")}</span>
      <select
        value={locale}
        aria-label={t("locale.label")}
        onChange={(event) => setLocale(event.currentTarget.value as Locale)}
      >
        {LOCALES.map((value) => (
          <option key={value} value={value}>
            {t(value === "en" ? "locale.en" : "locale.fa")}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="shell">
      <header className="shell__bar">
        <Link className="shell__brand" to="/">
          {t("app.title")}
        </Link>
        <nav className="shell__nav" aria-label={t("nav.library")}>
          <Link className="button" to="/">
            {t("nav.library")}
          </Link>
        </nav>
        <span className="shell__spacer" />
        <LocaleSwitch />
      </header>
      <main className="shell__main" id="content">
        {children}
      </main>
    </div>
  );
}
