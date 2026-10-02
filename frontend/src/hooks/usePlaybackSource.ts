import { useCallback, useState } from "react";
import videojs from "video.js";

import { usePlayback, useRemux } from "@/api/queries";
import type { QualityOption } from "@/components/video/QualityMenu";
import type { PlayerSource } from "@/components/video/VideoPlayer";
import { apiUrl } from "@/lib/base";
import {
  choosePlan,
  directSourceType,
  storedQuality,
  storeQuality,
  type Fallback,
  type QualityChoice,
} from "@/lib/playback";
import type { VideoDetail } from "@/lib/types";

// Safari and every browser on iOS share WebKit, which can't read Matroska.
const IS_WEBKIT = Boolean(videojs.browser.IS_ANY_SAFARI || videojs.browser.IS_IOS);
// MediaError codes that mean "this browser can't handle the format".
const FORMAT_ERRORS = new Set([3, 4]);

/**
 * Decides how a video is played: the original file, a remuxed MP4 or converted HLS.
 * Falls back step by step when the browser rejects a source.
 */
export function usePlaybackSource(video: VideoDetail) {
  const { data: info, isError: infoFailed } = usePlayback(video.id);
  const [stored, setStored] = useState<QualityChoice>(storedQuality);
  const [failed, setFailed] = useState<ReadonlySet<Fallback>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const choice: QualityChoice =
    stored !== "auto" && info?.qualities.includes(stored) ? stored : "auto";
  const firstPlan = info ? choosePlan(info, choice, failed, IS_WEBKIT) : null;
  const remux = useRemux(video.id, firstPlan?.kind === "remux");
  const remuxFailed = remux.isError || remux.data?.state === "failed";
  const effectiveFailed: ReadonlySet<Fallback> = remuxFailed
    ? new Set([...failed, "remux"])
    : failed;
  const plan = info ? choosePlan(info, choice, effectiveFailed, IS_WEBKIT) : null;

  const retrySuffix = attempt > 0 ? `?r=${attempt}` : "";
  let source: PlayerSource | null = null;
  let preparing: number | null = null;
  if (!info) {
    // Without playback info (e.g. ffprobe missing) just try the file itself.
    if (infoFailed) {
      source = {
        src: apiUrl(`videos/${video.id}/stream`),
        type: directSourceType(video.container),
      };
    }
  } else if (plan?.kind === "direct") {
    source = {
      src: apiUrl(`videos/${video.id}/stream${retrySuffix}`),
      type: directSourceType(info.container),
    };
  } else if (plan?.kind === "remux") {
    if (remux.data?.state === "ready") {
      source = { src: apiUrl(`videos/${video.id}/remux.mp4${retrySuffix}`), type: "video/mp4" };
    } else {
      preparing = remux.data?.progress ?? 0;
    }
  } else if (plan?.kind === "hls") {
    source = {
      src: apiUrl(`videos/${video.id}/hls/${plan.quality}/index.m3u8${retrySuffix}`),
      type: "application/x-mpegURL",
    };
  }

  const kind = plan?.kind;
  const onSourceError = useCallback(
    (code: number) => {
      if ((kind === "direct" || kind === "remux") && FORMAT_ERRORS.has(code)) {
        setFailed((current) => new Set([...current, kind]));
        return;
      }
      if (kind !== "hls") setError("Die Datei konnte nicht geladen werden.");
      else if (code === 4) setError("Dieser Browser kann das umgewandelte Video nicht abspielen.");
      else setError("Die Umwandlung ist fehlgeschlagen. Details stehen im Server-Log.");
    },
    [kind],
  );

  const setChoice = useCallback((value: QualityChoice) => {
    storeQuality(value);
    setStored(value);
    setError(null);
  }, []);

  const retry = useCallback(() => {
    setError(null);
    setAttempt((n) => n + 1);
  }, []);

  let options: QualityOption[] = [];
  let showMenu = false;
  if (info) {
    const autoPlan = choosePlan(info, "auto", effectiveFailed, IS_WEBKIT);
    const autoHint =
      autoPlan.kind === "hls"
        ? `Umgewandelt · ${info.transcode_height}p`
        : `Original${info.height ? ` · ${info.height}p` : ""}`;
    options = [
      { value: "auto", label: "Automatisch", hint: autoHint },
      ...info.qualities.map((height) => ({
        value: height,
        label: `${height}p`,
        hint: "Umgewandelt, spart Bandbreite",
      })),
    ];
    showMenu = info.qualities.length > 0 || autoPlan.kind !== "direct";
  }

  return {
    source,
    onSourceError,
    preparing,
    error: error ?? (remuxFailed && plan?.kind !== "hls" ? (remux.data?.error ?? null) : null),
    retry,
    choice,
    setChoice,
    options,
    showMenu,
  };
}
