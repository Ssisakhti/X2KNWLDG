/**
 * The Map's URL grammar (`T-206`, D-119).
 *
 * Built and parsed by one module, so these tests are the round trip: what
 * `mapPath` writes, `parseMapState` must read back, and what `parseMapState`
 * refuses, `mapPath` must never write.
 *
 * The tests that matter most are the refusals. A grammar that *repaired* a
 * malformed value would select an entity nobody chose or filter a graph nobody
 * filtered, and both would look exactly like working software.
 */

import { describe, expect, it } from "vitest";

import {
  MAP_PATH,
  NO_MAP_STATE,
  graphFiltersOf,
  mapPath,
  parseFocus,
  parseMapState,
  parseProvenance,
  parseSourceScope,
  parseVocabulary,
  sameMapState,
} from "./mapLink";

const KU = "youtube:pqlWNihgdjI:KU-000001";
const CONCEPT = "library:concepts:C-000001";
const SOURCE = "youtube:pqlWNihgdjI";

describe("mapPath", () => {
  it("is the bare route when the state says nothing", () => {
    expect(mapPath()).toBe("/map");
    expect(mapPath(NO_MAP_STATE)).toBe("/map");
    expect(MAP_PATH).toBe("/map");
  });

  it("writes the API's own parameter names, in one order", () => {
    // The three filters are spelled as `GET /api/graph` spells them, so the
    // URL and the request cannot drift into two vocabularies for one filter
    // (ADR 0005 invariant 7).
    expect(
      mapPath({
        focus: KU,
        source: SOURCE,
        provenance: "derived",
        vocabulary: "library_synthetic",
      }),
    ).toBe(
      "/map?focus=youtube%3ApqlWNihgdjI%3AKU-000001&source_id=youtube%3ApqlWNihgdjI" +
        "&provenance_class=derived&relation_vocabulary=library_synthetic",
    );
  });

  it("omits what the state does not say", () => {
    expect(mapPath({ focus: KU })).toBe("/map?focus=youtube%3ApqlWNihgdjI%3AKU-000001");
    expect(mapPath({ provenance: "source" })).toBe("/map?provenance_class=source");
  });

  it("refuses to write a value its own reader would ignore", () => {
    // A hit with no `global_id` has no Map address (D-023, D-119). If this
    // wrote one anyway, the selection would survive exactly one navigation and
    // vanish on reload -- an address that resolves to nothing.
    for (const focus of [null, "", "youtube", "youtube:pqlWNihgdjI", "a:b:c:d", "you tube:a:b"]) {
      expect(mapPath({ focus, provenance: "source" })).toBe("/map?provenance_class=source");
    }
    expect(mapPath({ source: KU })).toBe("/map");
    expect(mapPath({ provenance: "Derived" as never })).toBe("/map");
    expect(mapPath({ vocabulary: "synthetic" as never })).toBe("/map");
  });

  it("round-trips every field through the parser", () => {
    const state = {
      focus: CONCEPT,
      source: SOURCE,
      provenance: "derived",
      vocabulary: "canonical",
    } as const;
    const path = mapPath(state);
    const parsed = parseMapState(path.slice(path.indexOf("?")));
    expect(parsed).toEqual(state);
    expect(sameMapState(parsed, state)).toBe(true);
    // And again, so a second trip through the grammar is a fixed point.
    expect(mapPath(parsed)).toBe(path);
  });
});

describe("parseMapState", () => {
  it("reads nothing out of a URL that states nothing", () => {
    expect(parseMapState("")).toEqual(NO_MAP_STATE);
    expect(parseMapState("?tab=transcript&t=30")).toEqual(NO_MAP_STATE);
  });

  it("invents no selection out of malformed state", () => {
    // The whole of D-119's second half: an unreadable value leaves the Map
    // where it was, with nothing selected and nothing filtered.
    expect(parseMapState("?focus=&provenance_class=&relation_vocabulary=")).toEqual(NO_MAP_STATE);
    expect(parseMapState("?focus=KU-000001&provenance_class=derivd")).toEqual(NO_MAP_STATE);
  });

  it("costs one malformed value only itself", () => {
    const parsed = parseMapState(new URLSearchParams({ focus: "nonsense", provenance_class: "derived" }));
    expect(parsed.focus).toBeNull();
    expect(parsed.provenance).toBe("derived");
  });

  it("accepts a URLSearchParams as readily as a string", () => {
    expect(parseMapState(new URLSearchParams({ focus: KU })).focus).toBe(KU);
  });
});

describe("parseFocus", () => {
  it("accepts a three-part global id, whatever its source type", () => {
    expect(parseFocus(KU)).toBe(KU);
    // A canonical concept belongs to no source and is still addressable.
    expect(parseFocus(CONCEPT)).toBe(CONCEPT);
  });

  it("ignores what is not one, rather than completing it", () => {
    for (const value of [
      null,
      undefined,
      "",
      "KU-000001",
      "youtube:pqlWNihgdjI",
      "youtube:pqlWNihgdjI:KU-000001:extra",
      "::",
      "youtube::KU-000001",
      " youtube:pqlWNihgdjI:KU-000001",
      "youtube:pqlW NihgdjI:KU-000001",
    ]) {
      expect(parseFocus(value)).toBeNull();
    }
  });

  it("does not decide whether the entity exists", () => {
    // Well formed and unknown is the server's `not_found` to state. A client
    // that judged it here would drop a valid link to an entity no page of the
    // graph has loaded yet.
    expect(parseFocus("youtube:never-ingested:KU-999999")).toBe("youtube:never-ingested:KU-999999");
  });
});

describe("parseSourceScope", () => {
  it("accepts a two-part source id", () => {
    expect(parseSourceScope(SOURCE)).toBe(SOURCE);
    expect(parseSourceScope("library:concepts")).toBe("library:concepts");
  });

  it("never truncates a global id into a source scope", () => {
    // Silently scoping the Map to `youtube:pqlWNihgdjI` because the URL
    // carried an entity id would filter a graph the URL never asked to filter.
    expect(parseSourceScope(KU)).toBeNull();
    for (const value of [null, "", "youtube", "youtube:", ":pqlWNihgdjI", "youtube: x"]) {
      expect(parseSourceScope(value)).toBeNull();
    }
  });
});

describe("parseProvenance and parseVocabulary", () => {
  it("accept exactly the contract's members", () => {
    for (const value of ["source", "derived", "user"]) {
      expect(parseProvenance(value)).toBe(value);
    }
    for (const value of ["canonical", "library_synthetic", "user"]) {
      expect(parseVocabulary(value)).toBe(value);
    }
  });

  it("ignore anything else, including a near miss and a different case", () => {
    for (const value of [null, undefined, "", "Source", "DERIVED", "sources", "kind"]) {
      expect(parseProvenance(value)).toBeNull();
    }
    for (const value of [null, "", "Canonical", "library-synthetic", "synthetic"]) {
      expect(parseVocabulary(value)).toBeNull();
    }
  });
});

describe("graphFiltersOf", () => {
  it("carries only what the URL stated", () => {
    expect(graphFiltersOf(NO_MAP_STATE)).toEqual({});
    expect(Object.keys(graphFiltersOf(NO_MAP_STATE))).toHaveLength(0);
    expect(graphFiltersOf({ ...NO_MAP_STATE, provenance: "derived" })).toEqual({
      provenance_class: "derived",
    });
  });

  it("is an identity over the three parameters the operation declares", () => {
    expect(
      graphFiltersOf({
        focus: KU,
        source: SOURCE,
        provenance: "source",
        vocabulary: "canonical",
      }),
    ).toEqual({
      source_id: SOURCE,
      provenance_class: "source",
      relation_vocabulary: "canonical",
    });
  });

  it("never sends the selection as a filter", () => {
    // Focus changes what is *read*, not what is *drawn*. A `focus` reaching
    // the graph request would return a different graph for a selection, and
    // the counts beside the canvas would be answering another question.
    expect(graphFiltersOf({ ...NO_MAP_STATE, focus: KU })).toEqual({});
  });
});

describe("sameMapState", () => {
  it("compares every field", () => {
    expect(sameMapState(NO_MAP_STATE, { ...NO_MAP_STATE })).toBe(true);
    expect(sameMapState(NO_MAP_STATE, { ...NO_MAP_STATE, focus: KU })).toBe(false);
    expect(
      sameMapState({ ...NO_MAP_STATE, vocabulary: "user" }, { ...NO_MAP_STATE, vocabulary: "canonical" }),
    ).toBe(false);
  });
});
