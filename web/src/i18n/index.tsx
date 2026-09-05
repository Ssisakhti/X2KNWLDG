/**
 * The locale and direction shell (T-110, D-012).
 *
 * Direction is architectural, not cosmetic: the provider writes `lang` and
 * `dir` onto the document element, every stylesheet rule is written against
 * the logical axis, and no component branches on "is this RTL". Adding a
 * third locale is a catalogue and a row in `DIRECTION`.
 *
 * English is the default (D-012). A stored preference is honoured, and an
 * unrecognised stored value falls back to English rather than to whatever the
 * browser happens to prefer -- a default that changes with the environment is
 * not a default.
 */

import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  CATALOGS,
  DEFAULT_LOCALE,
  DIRECTION,
  LOCALES,
  type Locale,
  type MessageKey,
} from "./catalog";

const STORAGE_KEY = "x2knwldg.locale";

export type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

export interface I18n {
  locale: Locale;
  dir: "ltr" | "rtl";
  setLocale: (locale: Locale) => void;
  t: Translate;
}

const I18nContext = createContext<I18n | null>(null);

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/**
 * `{name}` placeholders, substituted from *params*, plus the one plural form
 * (`T-209`).
 *
 * `{name}` is the value. `{name|singular|plural}` is the word that agrees
 * with it: the first alternative when the value is exactly one, the second
 * otherwise -- so "{count} related {count|entity|entities}" reads correctly
 * at one and at eight. The browser walk found "1 hops from the focus", "1
 * related entities" and "1 returned relations name an endpoint" on the real
 * route, all of them in one sentence about a real neighbourhood.
 *
 * Two things this deliberately is not. It is not a plural *library*: the form
 * chooses between exactly two alternatives on `=== 1`, which is English's
 * rule and is written out per message rather than inferred, and a locale
 * whose rule is different simply does not use the form -- Persian keeps the
 * singular after a numeral, so its catalogue has no `|` in it and needs none.
 * And it is not a second placeholder syntax: the name is the same parameter,
 * so a message can print the number and agree with it without the caller
 * passing anything extra.
 *
 * An unknown placeholder is left alone, in both forms.
 */
export function interpolate(template: string, params?: Record<string, string | number>): string {
  if (params === undefined) return template;
  return template.replace(
    /\{(\w+)(?:\|([^{}|]*)\|([^{}|]*))?\}/g,
    (whole, name: string, singular?: string, plural?: string) => {
      const value = params[name];
      if (value === undefined) return whole;
      if (singular === undefined || plural === undefined) return String(value);
      return Number(value) === 1 ? singular : plural;
    },
  );
}

export function translator(locale: Locale): Translate {
  const catalog = CATALOGS[locale];
  return (key, params) => {
    /*
     * A key the catalog does not hold falls back to the key itself.
     *
     * `MessageKey = keyof typeof en` and `fa` is typed `Record<MessageKey,
     * string>`, so a missing key is normally a compile error and three runtime
     * tests check the two catalogues agree — this is not a substitute for any
     * of that. It is for the case the type system cannot see: a key arriving
     * from outside the module graph, or a catalogue mutated at runtime. There
     * the previous behaviour was `interpolate(undefined, params)`, which
     * rendered **silently blank** with no params and threw
     * `undefined.replace` with them — a whole view lost to a typo, with
     * nothing logged. A visible key is an honest "this string is missing",
     * which is the same choice the rest of this UI makes about absent values.
     */
    const message = catalog[key];
    if (typeof message !== "string") return key;
    return interpolate(message, params);
  };
}

function readStored(): Locale | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isLocale(stored) ? stored : null;
  } catch {
    // A browser with site data blocked is not an error state for the UI.
    return null;
  }
}

export function I18nProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(
    () => initialLocale ?? readStored() ?? DEFAULT_LOCALE,
  );

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Preference not persisted; the session still switches.
    }
  }, []);

  const dir = DIRECTION[locale];

  /*
   * Written before the browser paints, not after.
   *
   * The locale is read synchronously in the `useState` initialiser above, so a
   * returning Persian reader's *content* is Persian on the very first render —
   * while `index.html` ships `lang="en" dir="ltr"` and a plain `useEffect`
   * runs after paint. That is at least one frame of Persian text in a fully
   * mirrored-wrong shell on every cold load, and every logical property in the
   * stylesheet resolves the wrong way round for it.
   *
   * `useLayoutEffect` closes the gap: it runs after the DOM is written and
   * before the paint, which is exactly the window this attribute has to be
   * correct in. It is not a substitute for `index.html`'s own default — that
   * is still what a reader sees before any script runs at all.
   */
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.setAttribute("lang", locale);
    root.setAttribute("dir", dir);
  }, [locale, dir]);

  const value = useMemo<I18n>(
    () => ({ locale, dir, setLocale, t: translator(locale) }),
    [locale, dir, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n was called outside I18nProvider");
  }
  return value;
}

export { DEFAULT_LOCALE, DIRECTION, LOCALES };
export type { Locale, MessageKey };
