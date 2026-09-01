/**
 * Reading canonical bytes: partial where the data is partial, absent where it
 * is absent, and never a substituted zero.
 */

import { describe, expect, it } from "vitest";

import { adapterDiagnostics, externalMedium, localMedium, readCaptions } from "./canonical";
import type { Artifact } from "./contract";

const TRANSCRIPT = JSON.stringify({
  schema_version: "1.0",
  video_id: "fixture-pass",
  captions: [
    { segment_id: "cap_000001", start_sec: 0, end_sec: 30, text: "first" },
    { segment_id: "cap_000002", end_sec: 60, text: "no start recorded" },
  ],
});

function artifact(overrides: Partial<Artifact>): Artifact {
  return {
    schema_version: "1.0",
    id: "youtube:x:video",
    source_id: "youtube:x",
    kind: "video",
    role: "external",
    immutable: false,
    available: true,
    ...overrides,
  } as Artifact;
}

describe("readCaptions", () => {
  it("reads the caption list verbatim", () => {
    const captions = readCaptions(TRANSCRIPT);
    expect(captions).not.toBeNull();
    expect(captions?.[0]).toEqual({ id: "cap_000001", startSec: 0, endSec: 30, text: "first" });
  });

  it("keeps a missing start as null rather than seeking to the beginning", () => {
    expect(readCaptions(TRANSCRIPT)?.[1]?.startSec).toBeNull();
  });

  it("tells 'not a transcript' from 'no captions'", () => {
    expect(readCaptions("not json")).toBeNull();
    expect(readCaptions(JSON.stringify({ schema_version: "1.0" }))).toBeNull();
    expect(readCaptions(JSON.stringify({ captions: [] }))).toEqual([]);
  });
});

describe("media artifacts", () => {
  it("never treats an external artifact as a local file (T-114)", () => {
    const artifacts = [artifact({ role: "external", url: "https://www.youtube.com/watch?v=x" })];
    expect(localMedium(artifacts)).toBeNull();
    expect(externalMedium(artifacts)?.url).toBe("https://www.youtube.com/watch?v=x");
  });

  it("refuses a local medium that was absent at index time", () => {
    const artifacts = [
      artifact({ role: "canonical", path: "output/x/video.mp4", available: false }),
    ];
    expect(localMedium(artifacts)).toBeNull();
  });

  it("accepts a local medium that is present and pathed", () => {
    const artifacts = [
      artifact({ id: "youtube:x:local", role: "canonical", path: "output/x/v.mp4", available: true }),
    ];
    expect(localMedium(artifacts)?.id).toBe("youtube:x:local");
  });
});

describe("adapter diagnostics (D-045)", () => {
  it("is empty when the adapter reported nothing", () => {
    expect(adapterDiagnostics({})).toEqual({ unmappableArtifacts: [], unreadableFiles: [] });
    expect(adapterDiagnostics(undefined).unreadableFiles).toEqual([]);
  });

  it("carries both channels through with their reasons", () => {
    const found = adapterDiagnostics({
      unmappable_artifacts: [{ path: "output/x/vault/a b.md", reason: "filename cannot spell an id" }],
      unreadable_files: [{ path: "output/x/coverage.json", reason: "invalid JSON" }],
    });
    expect(found.unmappableArtifacts).toHaveLength(1);
    expect(found.unreadableFiles[0]?.reason).toBe("invalid JSON");
  });
});
