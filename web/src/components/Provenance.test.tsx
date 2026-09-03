/**
 * `T-113`, and ADR 0001 invariant 10 as an assertion.
 *
 * The invariant is that provenance is never signalled by colour alone. A test
 * cannot read a stylesheet's rendered colour in jsdom, and it does not need
 * to: what it *can* check is that two non-colour signals differ for every pair
 * of classes -- the glyph and the border style -- and that a human-readable
 * label is present. If someone later reduces the badge to a coloured dot,
 * these fail.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProvenanceClass, RunStatus, Source } from "../api/contract";
import { renderApp } from "../test/render";
import {
  KindBadge,
  PROVENANCE_GLYPH,
  PROVENANCE_LINE,
  ProvenanceBadge,
  RunStatusPanel,
  StatusBadge,
  VocabularyBadge,
} from "./Provenance";

const CLASSES: readonly ProvenanceClass[] = ["source", "derived", "user"];

function source(status: Partial<Source["status"]>): Source {
  return {
    schema_version: "1.0",
    id: "youtube:fixture-fail",
    source_type: "youtube",
    external_id: "fixture-fail",
    canonical_dir: "output/fail-run",
    adapter: { name: "youtube", version: "1.0" },
    status: {
      validation: "FAIL",
      coverage: "PASS",
      overall: "FAIL",
      ...status,
    },
  } as Source;
}

describe("provenance is distinguishable without colour", () => {
  it("gives each class its own glyph", () => {
    const glyphs = CLASSES.map((value) => PROVENANCE_GLYPH[value]);
    expect(new Set(glyphs).size).toBe(CLASSES.length);
  });

  it("gives each class its own line style", () => {
    const lines = CLASSES.map((value) => PROVENANCE_LINE[value]);
    expect(new Set(lines).size).toBe(CLASSES.length);
  });

  it("renders a glyph and a word, not only a swatch", () => {
    for (const value of CLASSES) {
      const { unmount } = renderApp(<ProvenanceBadge provenance={value} />);
      const badge = document.querySelector(`[data-provenance="${value}"]`);
      expect(badge).not.toBeNull();
      expect(badge?.getAttribute("data-line-style")).toBe(PROVENANCE_LINE[value]);
      expect(badge?.textContent ?? "").toContain(PROVENANCE_GLYPH[value]);
      // The label is the third signal: a real word, not just the glyph.
      expect((badge?.textContent ?? "").replace(PROVENANCE_GLYPH[value], "").trim().length).toBeGreaterThan(2);
      unmount();
    }
  });

  it("labels the three edge vocabularies apart", () => {
    renderApp(
      <>
        <VocabularyBadge vocabulary="canonical" />
        <VocabularyBadge vocabulary="library_synthetic" />
        <VocabularyBadge vocabulary="user" />
      </>,
    );
    const labels = ["canonical", "library_synthetic", "user"].map(
      (value) => document.querySelector(`[data-vocabulary="${value}"]`)?.textContent ?? "",
    );
    expect(new Set(labels).size).toBe(3);
  });
});

describe("run status is copied, never coerced", () => {
  const statuses: readonly RunStatus[] = ["PASS", "PARTIAL", "FAIL", "UNKNOWN"];

  it("renders each of the four as itself", () => {
    for (const status of statuses) {
      const { unmount } = renderApp(<StatusBadge status={status} />);
      expect(screen.getByText(status)).not.toBeNull();
      unmount();
    }
  });

  it("shows validation and coverage separately when they disagree", () => {
    renderApp(<RunStatusPanel source={source({})} />);
    const badges = [...document.querySelectorAll("[data-status]")].map((node) => ({
      status: node.getAttribute("data-status"),
      text: node.textContent,
    }));
    expect(badges.filter((badge) => badge.status === "FAIL")).toHaveLength(2);
    expect(badges.filter((badge) => badge.status === "PASS")).toHaveLength(1);
  });

  it("reports an unrecorded audit_attempts as unrecorded, not as zero", () => {
    const { container } = renderApp(<RunStatusPanel source={source({})} />);
    const rows = within(container).getByText("Audit attempts").parentElement;
    expect(rows?.textContent).not.toContain("0");
  });
});

describe("a kind badge", () => {
  it("names the kind in the record's own vocabulary, with the hue beside it", () => {
    // Hue is the *second* signal: the word is the first, and it is the
    // record's own token rather than a prettified phrase.
    renderApp(<KindBadge kind="canonical_concept" />);
    expect(screen.getByText("canonical_concept")).toBeDefined();
    const badge = document.querySelector("[data-kind-family]");
    expect(badge?.getAttribute("data-kind-family")).toBe("concept");
    const swatch = badge?.querySelector(".badge__swatch");
    expect(swatch).not.toBeNull();
    // From the one table the legend explains and the mark is drawn with.
    expect((swatch as HTMLElement).style.background).not.toBe("");
    // And decoration: a screen reader hears the word, not the colour.
    expect(swatch?.getAttribute("aria-hidden")).toBe("true");
  });

  it("says a kind is not stated rather than folding it into a family", () => {
    // An absent `kind` is `unstated`, which has a hue of its own precisely so
    // it is not silently drawn as a real family.
    renderApp(<KindBadge kind={null} />);
    expect(screen.getByText("not stated")).toBeDefined();
    expect(
      document.querySelector("[data-kind-family]")?.getAttribute("data-kind-family"),
    ).toBe("unstated");
  });

  it("does not round a kind this build has never heard of", () => {
    renderApp(<KindBadge kind="a_kind_from_a_later_schema" />);
    expect(screen.getByText("a_kind_from_a_later_schema")).toBeDefined();
    expect(
      document.querySelector("[data-kind-family]")?.getAttribute("data-kind-family"),
    ).toBe("unrecognised");
  });
});
