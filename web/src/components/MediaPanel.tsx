/**
 * Playback, and the timestamp seek that makes a transcript navigable (`T-114`).
 *
 * The rule this component exists to hold: **never assume a local media file
 * exists.** The pipeline stores a transcript, not necessarily the medium. A
 * YouTube source's `video` artifact has `role: "external"` and no path, and
 * `/api/media` answers `404 unavailable` for it permanently and by design --
 * so local playback is offered only for an artifact that is non-external,
 * carries a path, and was present when the index was built. Everything else
 * says so plainly instead of rendering a dead player.
 *
 * The embed is a facade until the user asks for it. Canvas plan §14 forbids
 * default outbound requests and requires external embeds to be allowlisted and
 * an external open to be an explicit, visible action, so nothing is requested
 * from the embed host until the button is pressed, the host is named in the
 * button's own note, and `EMBED_HOSTS` is the allowlist.
 *
 * Seeking works without loading YouTube's own script: an `enablejsapi=1` frame
 * accepts a `seekTo` command over `postMessage`, sent to that one origin. When
 * the player is not loaded yet, the requested time becomes the frame's `start`
 * parameter instead, so the first thing it plays is the right thing.
 */

import { useEffect, useRef, useState } from "react";

import { externalMedium, localMedium } from "../api/canonical";
import { api } from "../api/client";
import type { Artifact, Source } from "../api/contract";
import { useI18n } from "../i18n";
import { formatSeconds } from "../lib/format";

/** The one allowlisted embed host, keyed by source type. */
export const EMBED_HOSTS: Record<string, string> = {
  youtube: "https://www.youtube-nocookie.com",
};

export interface SeekRequest {
  seconds: number;
  /** Bumped on every request so repeating the same timestamp still seeks. */
  nonce: number;
}

export function embedUrl(source: Source, startSec: number | null): string | null {
  const host = EMBED_HOSTS[source.source_type];
  if (host === undefined || source.external_id === "") return null;
  const url = new URL(`${host}/embed/${encodeURIComponent(source.external_id)}`);
  url.searchParams.set("enablejsapi", "1");
  url.searchParams.set("rel", "0");
  if (startSec !== null && Number.isFinite(startSec)) {
    url.searchParams.set("start", String(Math.max(0, Math.trunc(startSec))));
  }
  return url.toString();
}

function LocalPlayer({ artifact, seek }: { artifact: Artifact; seek: SeekRequest | null }) {
  const { t } = useI18n();
  const element = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (seek === null || element.current === null) return;
    element.current.currentTime = Math.max(0, seek.seconds);
    void element.current.play().catch(() => {
      // Autoplay refusals are the browser's decision, not an error state.
    });
  }, [seek]);

  return (
    <div className="stack">
      <h2>{t("player.localTitle")}</h2>
      <div className="embed">
        <video ref={element} controls src={api.mediaUrl(artifact.id)} />
      </div>
    </div>
  );
}

function ExternalPlayer({ source, seek }: { source: Source; seek: SeekRequest | null }) {
  const { t } = useI18n();
  // `frameUrl` is fixed at load time and never recomputed: changing an
  // iframe's `src` reloads the player, which would undo the seek that
  // prompted the change. Before the frame exists a requested time is held in
  // `pending` and becomes the frame's `start`; after it exists, a seek is a
  // `postMessage` to that one origin and the URL does not move.
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  const frame = useRef<HTMLIFrameElement | null>(null);
  const host = EMBED_HOSTS[source.source_type];

  useEffect(() => {
    if (seek === null) return;
    setPending(seek.seconds);
    const target = frame.current?.contentWindow;
    if (frameUrl === null || target == null || host === undefined) return;
    target.postMessage(
      JSON.stringify({ event: "command", func: "seekTo", args: [seek.seconds, true] }),
      host,
    );
  }, [seek, frameUrl, host]);

  if (host === undefined || embedUrl(source, null) === null) {
    return <p className="muted">{t("player.noEmbed")}</p>;
  }

  return (
    <div className="stack">
      <h2>{t("player.title")}</h2>
      {frameUrl !== null ? (
        <>
          <div className="embed">
            <iframe
              ref={frame}
              src={frameUrl}
              title={source.title ?? source.id}
              allow="accelerometer; encrypted-media; picture-in-picture"
              referrerPolicy="strict-origin-when-cross-origin"
            />
          </div>
          <p className="faint">{t("player.loaded", { host })}</p>
          <button type="button" className="button" onClick={() => setFrameUrl(null)}>
            {t("player.unload")}
          </button>
        </>
      ) : (
        <>
          <div className="embed">
            <p className="muted">{t("player.externalOnly")}</p>
          </div>
          <p className="faint">{t("player.privacyNote", { host })}</p>
          {pending !== null && (
            <p className="faint">
              {t("player.seekPending", { time: formatSeconds(pending) ?? String(pending) })}
            </p>
          )}
          <button
            type="button"
            className="button"
            onClick={() => setFrameUrl(embedUrl(source, pending))}
          >
            {t("player.load")}
          </button>
        </>
      )}
    </div>
  );
}

export function MediaPanel({
  source,
  artifacts,
  seek,
}: {
  source: Source;
  artifacts: readonly Artifact[];
  seek: SeekRequest | null;
}) {
  const { t } = useI18n();
  const local = localMedium(artifacts);
  const remote = externalMedium(artifacts);
  const watchUrl = remote?.url ?? source.url ?? null;

  return (
    <section className="panel stack" aria-label={t("player.title")}>
      {local !== null ? (
        <LocalPlayer artifact={local} seek={seek} />
      ) : (
        <>
          <p className="muted">{t("player.noLocalMedia")}</p>
          <ExternalPlayer source={source} seek={seek} />
        </>
      )}
      {watchUrl !== null && (
        <a href={watchUrl} target="_blank" rel="noopener noreferrer">
          {t("player.openExternal")}
        </a>
      )}
    </section>
  );
}
