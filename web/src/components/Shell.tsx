/**
 * The application frame: brand, navigation, and the language switch.
 *
 * The switch is here rather than in a settings page because direction is part
 * of the layout, and the fastest way to find a place where a physical CSS
 * property survived is to flip the whole UI to `rtl` and look at it (D-012).
 */

import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

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
      {/*
        D-108: `nav.skipToContent` was translated in both catalogs and
        `<main id="content">` was rendered, and nothing linked the two — a
        half-built affordance, which for accessibility is the same as none: a
        keyboard user still tabs through the brand, the nav and the language
        switch on every page. `HashRouter` puts the whole location after `#`
        (D-060), so an `href="#content"` would be read as a route; this scrolls
        and focuses the target itself instead of asking the browser to follow a
        fragment that means something else here.
      */}
      <a
        className="shell__skip"
        href="#content"
        onClick={(event) => {
          event.preventDefault();
          const main = document.getElementById("content");
          if (main === null) return;
          main.setAttribute("tabindex", "-1");
          main.focus();
          main.scrollIntoView();
        }}
      >
        {t("nav.skipToContent")}
      </a>
      <header className="shell__bar">
        <Link className="shell__brand" to="/">
          {t("app.title")}
        </Link>
        {/*
          The nav is labelled for itself now that it holds more than one
          destination (`T-204`): labelling it "Library" was fine while the
          Library was the only entry and would announce the Map as part of it.
          `NavLink` sets `aria-current="page"` on the active entry, which
          `.button[aria-current="page"]` already styles.
        */}
        <nav className="shell__nav" aria-label={t("nav.sections")}>
          <NavLink className="button" to="/" end>
            {t("nav.library")}
          </NavLink>
          <NavLink className="button" to="/map">
            {t("nav.map")}
          </NavLink>
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
