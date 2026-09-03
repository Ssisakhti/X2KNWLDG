/**
 * The application frame: brand, navigation, and the language switch.
 *
 * The switch is here rather than in a settings page because direction is part
 * of the layout, and the fastest way to find a place where a physical CSS
 * property survived is to flip the whole UI to `rtl` and look at it (D-012).
 */

import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

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

/**
 * The routes whose content is a workspace rather than a document (`T-212`).
 *
 * D-153 makes the Map a viewport workspace: the graph fills the usable route
 * viewport and every control floats over it, so the frame must stop being a
 * centred, scrolling text column for that route and become a two-row grid
 * with no overflow of its own.
 *
 * The path is named here rather than reported upwards by the view, and that
 * is deliberate on two counts. It is a fact about the *frame* -- how tall the
 * bar is and whether the document scrolls -- which is this component's
 * subject and not the view's. And a child that told the frame what to be
 * would have to do it in an effect, which means one render of the Map in the
 * document composition before the workspace one: on a route whose whole
 * purpose is that the stage is measured and handed to a renderer, that first
 * layout is a renderer created against the wrong box.
 *
 * `Shell` already names `/map` twice, in the nav.
 */
const WORKSPACE_ROUTES: readonly string[] = ["/map"];

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const workspace = WORKSPACE_ROUTES.includes(useLocation().pathname);
  return (
    <div className={`shell${workspace ? " shell--workspace" : ""}`}>
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
