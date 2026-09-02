/**
 * `T-110`: English default, `dir` switching, and a catalogue that cannot go
 * half-translated without the build noticing.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Shell } from "../components/Shell";
import { CATALOGS, DEFAULT_LOCALE, DIRECTION, en, fa, LOCALES } from "./catalog";
import { I18nProvider, interpolate, translator, useI18n } from ".";
import { MemoryRouter } from "react-router-dom";

function Probe() {
  const { locale, dir, t } = useI18n();
  return <p data-testid="probe">{`${locale}|${dir}|${t("library.title")}`}</p>;
}

describe("the locale shell", () => {
  it("defaults to English (D-012)", () => {
    expect(DEFAULT_LOCALE).toBe("en");
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("probe").textContent).toBe("en|ltr|Library");
  });

  it("writes lang and dir onto the document", () => {
    render(
      <I18nProvider initialLocale="fa">
        <Probe />
      </I18nProvider>,
    );
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.getAttribute("lang")).toBe("fa");
  });

  it("switches direction from the shell's own control", () => {
    render(
      <I18nProvider initialLocale="en">
        <MemoryRouter>
          <Shell>
            <Probe />
          </Shell>
        </MemoryRouter>
      </I18nProvider>,
    );
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "fa" } });
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(screen.getByTestId("probe").textContent).toBe("fa|rtl|کتابخانه");
  });

  it("gives every locale a direction", () => {
    for (const locale of LOCALES) {
      expect(DIRECTION[locale]).toMatch(/^(ltr|rtl)$/);
      expect(CATALOGS[locale]).toBeTypeOf("object");
    }
  });
});

describe("the catalogues", () => {
  it("hold exactly the same keys", () => {
    expect(Object.keys(fa).sort()).toEqual(Object.keys(en).sort());
  });

  it("leave no message empty", () => {
    for (const locale of LOCALES) {
      const empty = Object.entries(CATALOGS[locale])
        .filter(([, value]) => value.trim() === "")
        .map(([key]) => key);
      expect(empty).toEqual([]);
    }
  });

  it("keep every placeholder that English states", () => {
    // Both forms: `{name}` prints the value and `{name|one|other}` agrees with
    // it (`T-209`), and a message that referred to a parameter only through
    // the plural form would otherwise slip past this guard. Names are made
    // unique, because English may well mention one count three times in a
    // sentence where Persian mentions it once -- Persian keeps the singular
    // after a numeral, so its catalogue carries no plural form at all.
    const placeholders = (text: string) =>
      [...new Set([...text.matchAll(/\{(\w+)(?:\|[^{}|]*\|[^{}|]*)?\}/g)].map((m) => m[1]))].sort();
    for (const [key, english] of Object.entries(en)) {
      expect({ key, names: placeholders(fa[key as keyof typeof en]) }).toEqual({
        key,
        names: placeholders(english),
      });
    }
  });
});

describe("interpolation", () => {
  it("substitutes named parameters", () => {
    expect(interpolate("{count} total", { count: 3 })).toBe("3 total");
  });

  it("leaves an unknown placeholder alone rather than blanking it", () => {
    expect(interpolate("{missing} here", {})).toBe("{missing} here");
  });

  describe("the plural form (`T-209`)", () => {
    // The browser walk read "1 hops from the focus" and "1 related entities"
    // off the real route, in one sentence about one real neighbourhood.
    const hops = "{count} {count|hop|hops} from the focus";

    it("agrees with a count of one", () => {
      expect(interpolate(hops, { count: 1 })).toBe("1 hop from the focus");
    });

    it("agrees with every other count, zero included", () => {
      expect(interpolate(hops, { count: 2 })).toBe("2 hops from the focus");
      expect(interpolate(hops, { count: 0 })).toBe("0 hops from the focus");
      expect(interpolate(hops, { count: 11 })).toBe("11 hops from the focus");
    });

    it("reads a numeric string the same way as a number", () => {
      expect(interpolate(hops, { count: "1" })).toBe("1 hop from the focus");
    });

    it("agrees several times in one sentence, from one parameter", () => {
      const message = "{count} related {count|entity has|entities have} no card";
      expect(interpolate(message, { count: 1 })).toBe("1 related entity has no card");
      expect(interpolate(message, { count: 7 })).toBe("7 related entities have no card");
    });

    it("leaves a form alone when the parameter is missing", () => {
      // The same rule as the bare placeholder: an unsubstituted message is a
      // visible defect, and a silently chosen plural is not.
      expect(interpolate("{count|hop|hops}", {})).toBe("{count|hop|hops}");
    });

    it("takes an empty alternative literally", () => {
      // "1 file" / "2 files" is the common shape, and the singular side of it
      // is the empty string rather than a word.
      expect(interpolate("{count} file{count||s}", { count: 1 })).toBe("1 file");
      expect(interpolate("{count} file{count||s}", { count: 2 })).toBe("2 files");
    });
  });

  it("translates through the catalogue of the requested locale", () => {
    expect(translator("en")("status.PARTIAL")).toBe("PARTIAL");
    expect(translator("fa")("status.PARTIAL")).toBe("PARTIAL");
  });
});
