import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useToast } from "@/hooks/toast";
import { api } from "@/lib/api";
import { apiUrl } from "@/lib/base";
import type { PlaybackInfo, RemuxStatus, VideoDetail } from "@/lib/types";

import {
  originalQuality,
  OfflineContext,
  type OfflineContextValue,
  type OfflineEntry,
  type OfflineFiles,
  type OfflineQuality,
  type OfflineTask,
  type SaveQuality,
  type StorageUsage,
} from "./context";
import { forgetLocalProgress, loadLocalProgress, rememberOwner } from "./progress";
import { offlineBackend, readText, writeText, type OfflineBackend } from "./storage";

const INDEX = "index.json";
const POLL_MS = 1500;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

class Cancelled extends Error {}

async function usage(): Promise<StorageUsage | null> {
  const estimate = await navigator.storage?.estimate?.().catch(() => null);
  if (!estimate?.quota) return null;
  return { used: estimate.usage ?? 0, quota: estimate.quota };
}

/** Asks the server to prepare a file (repack or compact copy) and waits for it. */
async function prepare(
  id: number,
  quality: OfflineQuality,
  onProgress: (value: number) => void,
  signal: AbortSignal,
): Promise<string> {
  if (quality === "original") return apiUrl(`videos/${id}/stream`);
  const base = quality === "remux" ? `videos/${id}/remux` : `videos/${id}/device/${quality}`;
  let status = await api.post<RemuxStatus>(base);
  while (status.state === "running") {
    if (signal.aborted) throw new Cancelled();
    onProgress(status.progress);
    await sleep(POLL_MS);
    status = await api.get<RemuxStatus>(base);
  }
  if (status.state !== "ready") {
    throw new Error(status.error ?? "Der Server konnte die Datei nicht vorbereiten.");
  }
  return apiUrl(quality === "remux" ? `videos/${id}/remux.mp4` : `${base}/file`);
}

async function fetchInto(
  store: OfflineBackend,
  url: string,
  path: string,
  signal: AbortSignal,
  onProgress?: (done: number, total: number) => void,
): Promise<number> {
  const response = await fetch(url, { credentials: "same-origin", signal });
  if (!response.ok || !response.body)
    throw new Error(`Download fehlgeschlagen (${response.status})`);
  const total = Number(response.headers.get("Content-Length") ?? 0);
  const type = response.headers.get("Content-Type") ?? "application/octet-stream";
  return store.write(path, response.body, type, (done) => onProgress?.(done, total), signal);
}

interface OfflineProviderProps {
  online: boolean;
  /** Whose videos: the signed-in user, or the last one when the server is away. */
  owner: number | null;
  children: ReactNode;
}

/** Saves videos on this device and plays them without the server. */
export function OfflineProvider({ online, owner, children }: OfflineProviderProps) {
  const backend = useMemo(() => offlineBackend(), []);
  // Each user has a folder of their own; without anyone signed in there's nothing.
  const store = owner === null ? null : backend;
  const root = `u${owner}`;
  const folder = useCallback((id: number) => `${root}/v${id}`, [root]);
  const index = `${root}/${INDEX}`;
  const toast = useToast();
  const [entries, setEntries] = useState<Record<number, OfflineEntry>>({});
  const [loaded, setLoaded] = useState<string | null>(null);
  const ready = store === null || loaded === root;
  const [tasks, setTasks] = useState<OfflineTask[]>([]);
  const [storage, setStorage] = useState<StorageUsage | null>(null);
  const running = useRef<{ id: number; controller: AbortController } | null>(null);
  const entriesRef = useRef(entries);

  const refreshUsage = useCallback(() => void usage().then(setStorage), []);

  useEffect(() => {
    if (online && owner !== null) rememberOwner(owner);
  }, [online, owner]);

  useEffect(() => {
    if (!store) return;
    let cancelled = false;
    void readText(store, index)
      .then((text) => {
        if (cancelled) return;
        const list = text ? (JSON.parse(text) as OfflineEntry[]) : [];
        entriesRef.current = Object.fromEntries(list.map((entry) => [entry.id, entry]));
        setEntries(entriesRef.current);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoaded(root);
      });
    refreshUsage();
    return () => {
      cancelled = true;
    };
  }, [store, index, root, refreshUsage]);

  const persist = useCallback(
    async (next: Record<number, OfflineEntry>) => {
      entriesRef.current = next;
      setEntries(next);
      if (store) await writeText(store, index, JSON.stringify(Object.values(next)));
      refreshUsage();
    },
    [store, index, refreshUsage],
  );

  // Progress made offline goes to the server once it answers again.
  useEffect(() => {
    if (!online) return;
    for (const [id, progress] of Object.entries(loadLocalProgress(owner))) {
      void api
        .put(`videos/${id}/progress`, {
          position_s: progress.position_s,
          duration_s: progress.duration_s,
        })
        .then(() => forgetLocalProgress(owner, Number(id)))
        .catch(() => undefined);
    }
  }, [online, owner]);

  const update = (id: number, patch: Partial<OfflineTask>) =>
    setTasks((all) => all.map((task) => (task.id === id ? { ...task, ...patch } : task)));

  const run = useCallback(
    async (task: OfflineTask, controller: AbortController) => {
      if (!store) return;
      const { signal } = controller;
      const path = folder(task.id);
      try {
        const video = await api.get<VideoDetail>(`videos/${task.id}`);
        // "Best" is the original where it plays here, else a compact copy that does.
        const quality =
          task.quality === "best"
            ? (originalQuality(await api.get<PlaybackInfo>(`videos/${task.id}/playback`)) ?? 720)
            : task.quality;
        update(task.id, { phase: "preparing", progress: 0 });
        const url = await prepare(
          task.id,
          quality,
          (progress) => update(task.id, { progress }),
          signal,
        );
        update(task.id, { phase: "downloading", progress: 0 });
        const size = await fetchInto(store, url, `${path}/video`, signal, (done, total) =>
          update(task.id, { progress: total ? done / total : 0 }),
        );
        const subtitles: number[] = [];
        for (const sub of video.subtitles) {
          await fetchInto(
            store,
            apiUrl(`videos/${task.id}/subtitles/${sub.id}.vtt`),
            `${path}/sub-${sub.id}.vtt`,
            signal,
          )
            .then(() => subtitles.push(sub.id))
            .catch(() => undefined);
        }
        const hasChapters =
          video.chapters.length > 0 &&
          (await fetchInto(
            store,
            apiUrl(`videos/${task.id}/chapters.vtt`),
            `${path}/chapters.vtt`,
            signal,
          )
            .then(() => true)
            .catch(() => false));
        const hasThumbnail =
          video.has_thumbnail &&
          (await fetchInto(store, apiUrl(`videos/${task.id}/thumbnail`), `${path}/thumb`, signal)
            .then(() => true)
            .catch(() => false));
        await persist({
          ...entriesRef.current,
          [task.id]: {
            id: task.id,
            video,
            quality,
            size,
            saved_at: new Date().toISOString(),
            subtitles,
            has_chapters: hasChapters,
            has_thumbnail: hasThumbnail,
          },
        });
        toast(`„${video.title}“ ist auf dem Gerät`, "success");
      } catch (error) {
        await store.remove(path);
        if (!(error instanceof Cancelled) && !signal.aborted) {
          toast(error instanceof Error ? error.message : "Speichern fehlgeschlagen", "error");
        }
      } finally {
        running.current = null;
        setTasks((all) => all.filter((t) => t.id !== task.id));
        refreshUsage();
      }
    },
    [store, folder, persist, toast, refreshUsage],
  );

  // One download at a time, in order.
  useEffect(() => {
    if (running.current) return;
    const next = tasks.find((task) => task.phase === "queued");
    if (!next) return;
    const controller = new AbortController();
    running.current = { id: next.id, controller };
    window.setTimeout(() => void run(next, controller), 0);
  }, [tasks, run]);

  // Leaving the page stops a download – browsers can't keep it running.
  useEffect(() => {
    if (tasks.length === 0) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [tasks.length]);

  const save = useCallback(
    (video: { id: number; title: string }, quality: SaveQuality) => {
      if (!store) return;
      void navigator.storage?.persist?.();
      setTasks((all) =>
        all.some((task) => task.id === video.id) || entriesRef.current[video.id]
          ? all
          : [...all, { id: video.id, title: video.title, quality, phase: "queued", progress: 0 }],
      );
    },
    [store],
  );

  const cancel = useCallback((id: number) => {
    if (running.current?.id === id) running.current.controller.abort();
    setTasks((all) => all.filter((task) => task.id !== id || task.phase !== "queued"));
  }, []);

  const remove = useCallback(
    async (id: number) => {
      if (!store) return;
      await store.remove(folder(id));
      const next = { ...entriesRef.current };
      delete next[id];
      await persist(next);
    },
    [store, folder, persist],
  );

  const open = useCallback(
    async (id: number): Promise<OfflineFiles | null> => {
      const entry = entriesRef.current[id];
      if (!store || !entry) return null;
      const urls: string[] = [];
      const url = async (path: string) => {
        const blob = await store.read(`${folder(id)}/${path}`);
        if (!blob) return undefined;
        const value = URL.createObjectURL(blob);
        urls.push(value);
        return value;
      };
      const video = await url("video");
      if (!video) return null;
      const subtitles: Record<number, string> = {};
      for (const subId of entry.subtitles) {
        const value = await url(`sub-${subId}.vtt`);
        if (value) subtitles[subId] = value;
      }
      return {
        video,
        poster: entry.has_thumbnail ? await url("thumb") : undefined,
        subtitles,
        chapters: entry.has_chapters ? await url("chapters.vtt") : undefined,
        revoke: () => urls.forEach((value) => URL.revokeObjectURL(value)),
      };
    },
    [store, folder],
  );

  const value = useMemo<OfflineContextValue>(
    () => ({
      supported: backend !== null,
      owner,
      ready,
      entries,
      tasks,
      usage: storage,
      save,
      cancel,
      remove,
      open,
    }),
    [backend, owner, ready, entries, tasks, storage, save, cancel, remove, open],
  );

  return <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>;
}
