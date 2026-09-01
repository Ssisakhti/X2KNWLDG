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
    const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
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

  it("translates through the catalogue of the requested locale", () => {
    expect(translator("en")("status.PARTIAL")).toBe("PARTIAL");
    expect(translator("fa")("status.PARTIAL")).toBe("PARTIAL");
  });
});
