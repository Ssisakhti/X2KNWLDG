/**
 * Reading canonical bytes without inventing anything.
 *
 * `transcript.json` is a canonical pipeline file. The frozen API serves it
 * verbatim through the byte channel and types none of its interior -- so this
 * module reads it defensively and, crucially, *partially*: a caption whose
 * `start_sec` is absent keeps a `null`, and the Reader renders that as
 * missing. Substituting a zero would be an invented timestamp, which is the
 * one thing this project forbids outright.
 *
 * A document whose shape is not recognised at all returns `null` rather than
 * an empty list, so "no captions" and "this is not a transcript" stay
 * distinguishable.
 */

import type { Artifact } from "./contract";

export interface Caption {
  /** Canonical caption id (`segment_id` in `transcript.json`), or null. */
  id: string | null;
  startSec: number | null;
  endSec: number | null;
  text: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function optionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toCaption(raw: unknown): Caption {
  if (!isRecord(raw)) return { id: null, startSec: null, endSec: null, text: null };
  return {
    id: optionalString(raw["segment_id"]),
    startSec: optionalNumber(raw["start_sec"]),
    endSec: optionalNumber(raw["end_sec"]),
    text: optionalString(raw["text"]),
  };
}

/** The captions of a transcript document, or `null` when it is not one. */
export function readCaptions(text: string): Caption[] | null {
  let document: unknown;
  try {
    document = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(document)) return null;
  const captions = document["captions"];
  if (!Array.isArray(captions)) return null;
  return captions.map(toCaption);
}

/**
 * The first artifact of a given kind, or null.
 *
 * Kinds come from the frozen `Artifact` record, so a kind this project does
 * not define is a compile error rather than a lookup that quietly finds
 * nothing.
 */
export function artifactOfKind(
  artifacts: readonly Artifact[],
  kind: Artifact["kind"],
): Artifact | null {
  return artifacts.find((artifact) => artifact.kind === kind) ?? null;
}

/**
 * A local, readable medium for this source, or null.
 *
 * Never assume one exists (`T-114`): a YouTube source's `video` artifact has
 * `role: "external"` and no path, and `/api/media` answers `404 unavailable`
 * for it by design. Only an artifact that is both non-external and was present
 * at index time is offered for local playback.
 */
export function localMedium(artifacts: readonly Artifact[]): Artifact | null {
  return (
    artifacts.find(
      (artifact) =>
        (artifact.kind === "video" || artifact.kind === "audio") &&
        artifact.role !== "external" &&
        artifact.path != null &&
        artifact.available,
    ) ?? null
  );
}

/** The remote medium's URL, or null when the source records none. */
export function externalMedium(artifacts: readonly Artifact[]): Artifact | null {
  return (
    artifacts.find(
      (artifact) =>
        (artifact.kind === "video" || artifact.kind === "audio") &&
        artifact.role === "external" &&
        typeof artifact.url === "string" &&
        artifact.url !== "",
    ) ?? null
  );
}

export interface Diagnostic {
  path: string;
  reason: string;
}

function readDiagnostics(value: unknown): Diagnostic[] {
  if (!Array.isArray(value)) return [];
  const entries: Diagnostic[] = [];
  for (const item of value) {
    if (!isRecord(item)) continue;
    const path = optionalString(item["path"]);
    const reason = optionalString(item["reason"]);
    if (path === null && reason === null) continue;
    entries.push({ path: path ?? "", reason: reason ?? "" });
  }
  return entries;
}

/**
 * The adapter's two diagnostic channels (D-045).
 *
 * Both are free-form by schema and **absent** when there is nothing to
 * report -- an empty list reads like an unread finding -- so absence here
 * means "nothing to say", and a non-empty list must be surfaced wherever the
 * source is shown rather than left to disappear between the run and the
 * Reader.
 */
export function adapterDiagnostics(metadata: Record<string, unknown> | undefined): {
  unmappableArtifacts: Diagnostic[];
  unreadableFiles: Diagnostic[];
} {
  return {
    unmappableArtifacts: readDiagnostics(metadata?.["unmappable_artifacts"]),
    unreadableFiles: readDiagnostics(metadata?.["unreadable_files"]),
  };
}
