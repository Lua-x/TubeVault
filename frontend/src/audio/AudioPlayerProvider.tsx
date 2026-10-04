import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { keys, reportProgress } from "@/api/queries";
import { useAuth } from "@/hooks/auth";
import { withChannelRate } from "@/hooks/useChannelRate";
import { apiUrl } from "@/lib/base";

import {
  AudioPlayerContext,
  RATES,
  type AudioPlayerValue,
  type AudioTrack,
  type SleepTimer,
} from "./context";

const RATE_KEY = "tubevault.audio.rate";
const SAVE_EVERY_MS = 10_000;

function storedRate(): number {
  try {
    const rate = Number(localStorage.getItem(RATE_KEY));
    return RATES.includes(rate) ? rate : 1;
  } catch {
    return 1;
  }
}

function mediaSession(): MediaSession | null {
  return typeof navigator !== "undefined" && "mediaSession" in navigator
    ? navigator.mediaSession
    : null;
}

/** One sound for the whole app: keeps playing while you browse, with lock-screen controls. */
export function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const { user, updatePreferences } = useAuth();
  const channelRates = useRef(user?.preferences.channel_rates);
  useEffect(() => {
    channelRates.current = user?.preferences.channel_rates;
  });
  const audio = useRef<HTMLAudioElement>(null);
  const [queue, setQueue] = useState<AudioTrack[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRateState] = useState(storedRate);
  const [sleep, setSleepState] = useState<SleepTimer | null>(null);
  const [expanded, setExpanded] = useState(false);

  // The latest values for event handlers that live as long as the element.
  const state = useRef({
    queue: [] as AudioTrack[],
    index: 0,
    rate,
    sleep: null as SleepTimer | null,
  });
  const pendingStart = useRef(0);
  const lastSaved = useRef(0);

  const save = useCallback(
    (final: boolean) => {
      const el = audio.current;
      const track = state.current.queue[state.current.index];
      if (!el || !track || !Number.isFinite(el.currentTime) || el.currentTime < 1) return;
      const length = Number.isFinite(el.duration) ? el.duration : (track.duration ?? 0);
      lastSaved.current = Date.now();
      if (track.save) {
        track.save(el.currentTime, length);
        return;
      }
      void reportProgress(track.id, el.currentTime, length).then(() => {
        if (final) void client.invalidateQueries({ queryKey: keys.videos });
      });
    },
    [client],
  );

  const start = useCallback(
    (tracks: AudioTrack[], at: number) => {
      const el = audio.current;
      const track = tracks[at];
      if (!el || !track) return;
      save(true);
      const leaving = state.current.queue[state.current.index];
      // Free what the old track held – unless the new queue still plays the same file.
      const kept = tracks.some((t) => t === leaving || (t.src && t.src === leaving?.src));
      if (leaving && !kept) leaving.release?.();
      state.current.queue = tracks;
      state.current.index = at;
      setQueue(tracks);
      setIndex(at);
      setError(null);
      setPosition(track.startAt ?? 0);
      setDuration(track.duration ?? 0);
      setPreparing(true);
      pendingStart.current = track.startAt ?? 0;
      // Set and play right away – iOS only allows sound inside the tap that asked for it.
      el.src = track.src ?? apiUrl(`videos/${track.id}/audio.m4a`);
      // The speed remembered for the channel, else the last one used for listening.
      const channelRate =
        track.channelId != null ? channelRates.current?.[String(track.channelId)] : undefined;
      const rate = channelRate ?? storedRate();
      state.current.rate = rate;
      setRateState(rate);
      el.defaultPlaybackRate = rate;
      el.playbackRate = rate;
      void el.play().catch(() => undefined);
      const session = mediaSession();
      if (session && typeof MediaMetadata !== "undefined") {
        session.metadata = new MediaMetadata({
          title: track.title,
          artist: track.channel ?? "",
          album: "TubeVault",
          artwork: track.artwork
            ? [{ src: track.artwork, sizes: "1280x720", type: "image/jpeg" }]
            : [],
        });
      }
    },
    [save],
  );

  const next = useCallback(() => {
    const { queue: tracks, index: at } = state.current;
    if (at + 1 < tracks.length) start(tracks, at + 1);
  }, [start]);

  const previous = useCallback(() => {
    const el = audio.current;
    const { queue: tracks, index: at } = state.current;
    // Like every music app: first back to the start, then the previous track.
    if (el && (el.currentTime > 5 || at === 0)) el.currentTime = 0;
    else start(tracks, at - 1);
  }, [start]);

  const seek = useCallback((seconds: number) => {
    const el = audio.current;
    if (!el) return;
    el.currentTime = Math.max(
      0,
      Math.min(seconds, Number.isFinite(el.duration) ? el.duration : seconds),
    );
    setPosition(el.currentTime);
  }, []);

  const skip = useCallback(
    (delta: number) => {
      const el = audio.current;
      if (el) seek(el.currentTime + delta);
    },
    [seek],
  );

  const close = useCallback(() => {
    const el = audio.current;
    save(true);
    state.current.queue[state.current.index]?.release?.();
    if (el) {
      el.pause();
      el.removeAttribute("src");
      el.load();
    }
    state.current.queue = [];
    state.current.index = 0;
    state.current.sleep = null;
    setQueue([]);
    setIndex(0);
    setPlaying(false);
    setPreparing(false);
    setSleepState(null);
    setExpanded(false);
    const session = mediaSession();
    if (session) session.metadata = null;
  }, [save]);

  // Element events: they change state, the effect only subscribes.
  useEffect(() => {
    const el = audio.current;
    if (!el) return;
    const onTime = () => {
      setPosition(el.currentTime);
      if (!el.paused && Date.now() - lastSaved.current > SAVE_EVERY_MS) save(false);
      const session = mediaSession();
      if (session && Number.isFinite(el.duration) && el.duration > 0) {
        try {
          session.setPositionState({
            duration: el.duration,
            position: Math.min(el.currentTime, el.duration),
            playbackRate: el.playbackRate,
          });
        } catch {
          // older browsers: no position on the lock screen
        }
      }
    };
    const onMeta = () => {
      setDuration(el.duration);
      if (pendingStart.current > 0) {
        el.currentTime = pendingStart.current;
        pendingStart.current = 0;
      }
    };
    const onPlay = () => {
      setPlaying(true);
      // One thing at a time: a playing video stops.
      document.querySelectorAll("video").forEach((video) => video.pause());
    };
    const onPause = () => {
      setPlaying(false);
      save(true);
    };
    const onEnded = () => {
      save(true);
      if (state.current.sleep?.kind === "end") {
        state.current.sleep = null;
        setSleepState(null);
        return;
      }
      next();
    };
    const onReady = () => setPreparing(false);
    const onWaiting = () => setPreparing(true);
    const onError = () => {
      if (!el.getAttribute("src")) return;
      setPreparing(false);
      setError("Der Ton ließ sich nicht laden. Ist der Server erreichbar?");
    };
    const events: [string, () => void][] = [
      ["timeupdate", onTime],
      ["loadedmetadata", onMeta],
      ["play", onPlay],
      ["pause", onPause],
      ["ended", onEnded],
      ["canplay", onReady],
      ["playing", onReady],
      ["waiting", onWaiting],
      ["error", onError],
    ];
    for (const [name, handler] of events) el.addEventListener(name, handler);
    // A video starting somewhere else pauses the sound.
    const onAnyPlay = (event: Event) => {
      if (event.target instanceof HTMLVideoElement) el.pause();
    };
    document.addEventListener("play", onAnyPlay, true);
    const onHide = () => save(true);
    window.addEventListener("pagehide", onHide);
    return () => {
      for (const [name, handler] of events) el.removeEventListener(name, handler);
      document.removeEventListener("play", onAnyPlay, true);
      window.removeEventListener("pagehide", onHide);
    };
  }, [save, next]);

  // Lock screen and headphone buttons.
  useEffect(() => {
    const session = mediaSession();
    const el = audio.current;
    if (!session || !el) return;
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => void el.play()],
      ["pause", () => el.pause()],
      ["seekbackward", (details) => skip(-(details.seekOffset ?? 15))],
      ["seekforward", (details) => skip(details.seekOffset ?? 15)],
      ["seekto", (details) => details.seekTime != null && seek(details.seekTime)],
      ["previoustrack", () => previous()],
      ["nexttrack", () => next()],
      ["stop", () => close()],
    ];
    for (const [action, handler] of handlers) {
      try {
        session.setActionHandler(action, handler);
      } catch {
        // not supported here
      }
    }
    return () => {
      for (const [action] of handlers) {
        try {
          session.setActionHandler(action, null);
        } catch {
          // not supported here
        }
      }
    };
  }, [skip, seek, previous, next, close]);

  // Sleep timer: stops the sound when the time is up.
  useEffect(() => {
    if (sleep?.kind !== "minutes") return;
    const timer = window.setInterval(() => {
      if (Date.now() >= sleep.until) {
        audio.current?.pause();
        state.current.sleep = null;
        setSleepState(null);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [sleep]);

  const value = useMemo<AudioPlayerValue>(
    () => ({
      track: queue[index] ?? null,
      queue,
      index,
      playing,
      preparing,
      error,
      position,
      duration,
      rate,
      sleep,
      expanded,
      play: (tracks, at = 0) => start(tracks, at),
      toggle: () => {
        const el = audio.current;
        if (!el) return;
        if (el.paused) void el.play().catch(() => undefined);
        else el.pause();
      },
      pause: () => audio.current?.pause(),
      seek,
      skip,
      next,
      previous,
      setRate: (value) => {
        state.current.rate = value;
        setRateState(value);
        const el = audio.current;
        if (el) {
          el.defaultPlaybackRate = value;
          el.playbackRate = value;
        }
        try {
          localStorage.setItem(RATE_KEY, String(value));
        } catch {
          // not remembered
        }
        const channelId = state.current.queue[state.current.index]?.channelId;
        if (channelId != null) {
          const next = withChannelRate(channelRates.current, channelId, value);
          if (next) {
            channelRates.current = next;
            void updatePreferences({ channel_rates: next }).catch(() => undefined);
          }
        }
      },
      setSleep: (minutes) => {
        const timer: SleepTimer | null =
          minutes === null
            ? null
            : minutes === "end"
              ? { kind: "end" }
              : { kind: "minutes", until: Date.now() + minutes * 60_000 };
        state.current.sleep = timer;
        setSleepState(timer);
      },
      setExpanded,
      close,
    }),
    [
      queue,
      index,
      playing,
      preparing,
      error,
      position,
      duration,
      rate,
      sleep,
      expanded,
      start,
      seek,
      skip,
      next,
      previous,
      close,
      updatePreferences,
    ],
  );

  return (
    <AudioPlayerContext.Provider value={value}>
      {children}
      <audio ref={audio} preload="auto" className="hidden" />
    </AudioPlayerContext.Provider>
  );
}
