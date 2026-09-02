/**
 * Formatting only. Nothing here fills a gap in the data.
 *
 * Every function that takes a value the canonical files may not state returns
 * `null` for "not stated" instead of a placeholder, and the components render
 * that as a visible absence. There is no `?? 0` in this file, and there must
 * not be one: a zero is a measurement.
 */

/** `H:MM:SS` past an hour, `M:SS` below it. Null in, null out. */
export function formatSeconds(seconds: number | null | undefined): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${minutes}:${pad(rest)}`;
}

/** A confidence exactly as recorded, to two decimals. Never defaulted. */
export function formatConfidence(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value.toFixed(2);
}

export function formatBytes(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * An ISO timestamp rendered for *locale*, or the original text when it will
 * not parse. An unparseable timestamp is shown as written rather than dropped.
 */
export function formatTimestamp(value: string | null | undefined, locale: string): string | null {
  if (typeof value !== "string" || value === "") return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

/**
 * A deep link into a YouTube watch URL at *seconds*.
 *
 * The `&t=<int>s` form is the one `io.timestamp_url` produces and
 * `tests/test_core_pipeline.py` contract-locks, so a link built here and a
 * link the API returns in a search hit are the same link. Both inputs are
 * real -- the source's own URL and a locator's own start -- and a URL that is
 * not a YouTube watch link returns null rather than being rewritten into one.
 */
export function youtubeTimestampUrl(
  watchUrl: string | null | undefined,
  seconds: number | null | undefined,
): string | null {
  if (typeof watchUrl !== "string" || watchUrl === "") return null;
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return null;
  let parsed: URL;
  try {
    parsed = new URL(watchUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
  if (!/(^|\.)youtube\.com$/.test(parsed.hostname) || parsed.pathname !== "/watch") return null;
  parsed.searchParams.set("t", `${Math.max(0, Math.trunc(seconds))}s`);
  return parsed.toString();
}

/** The three parts of a global id, or null when it is not one (D-011). */
export function splitGlobalId(
  value: string,
): { sourceType: string; externalId: string; localId: string } | null {
  const parts = value.split(":");
  if (parts.length !== 3) return null;
  const [sourceType, externalId, localId] = parts;
  if (!sourceType || !externalId || !localId) return null;
  return { sourceType, externalId, localId };
}

/** The two-part source id a global id belongs to, or null. */
export function sourceIdOf(globalId: string): string | null {
  const parts = splitGlobalId(globalId);
  return parts === null ? null : `${parts.sourceType}:${parts.externalId}`;
}
