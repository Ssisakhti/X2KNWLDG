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
  useEffect,
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

/** `{name}` placeholders, substituted from *params*. An unknown placeholder is left alone. */
export function interpolate(template: string, params?: Record<string, string | number>): string {
  if (params === undefined) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params[name];
    return value === undefined ? whole : String(value);
  });
}

export function translator(locale: Locale): Translate {
  const catalog = CATALOGS[locale];
  return (key, params) => interpolate(catalog[key], params);
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

  useEffect(() => {
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
