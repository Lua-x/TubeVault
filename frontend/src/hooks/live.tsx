import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { keys } from "@/api/queries";
import { websocketUrl } from "@/lib/base";
import type { Job, LiveEvent, Page, QueueState } from "@/lib/types";

const LiveContext = createContext(false);

function updateJobs(client: QueryClient, update: (jobs: Job[]) => Job[]) {
  client.setQueryData<Page<Job>>(keys.jobs, (old) => {
    if (!old) return old;
    const items = update(old.items);
    return { items, total: items.length };
  });
}

function handleEvent(client: QueryClient, event: LiveEvent) {
  switch (event.type) {
    case "job.updated": {
      const job = event.job;
      if (job.subscription) void client.invalidateQueries({ queryKey: keys.subscriptions });
      void client.invalidateQueries({ queryKey: keys.queue });
      const cached = client.getQueryData<Page<Job>>(keys.jobs);
      if (!cached) break;
      updateJobs(client, (jobs) =>
        jobs.some((j) => j.id === job.id)
          ? jobs.map((j) => (j.id === job.id ? job : j))
          : [job, ...jobs],
      );
      break;
    }
    case "job.progress":
      updateJobs(client, (jobs) =>
        jobs.map((j) =>
          j.id === event.job_id
            ? {
                ...j,
                stage: event.stage,
                progress: event.progress,
                downloaded_bytes: event.downloaded_bytes,
                total_bytes: event.total_bytes,
                speed: event.speed,
                eta: event.eta,
              }
            : j,
        ),
      );
      break;
    case "job.deleted":
      updateJobs(client, (jobs) => jobs.filter((j) => j.id !== event.job_id));
      break;
    case "jobs.cleared":
      void client.invalidateQueries({ queryKey: keys.jobs });
      break;
    case "video.updated":
    case "video.deleted":
      void client.invalidateQueries({ queryKey: keys.videos });
      void client.invalidateQueries({ queryKey: keys.channels });
      void client.invalidateQueries({ queryKey: keys.playlists });
      void client.invalidateQueries({ queryKey: keys.system });
      break;
    case "channels.updated":
      void client.invalidateQueries({ queryKey: keys.channels });
      void client.invalidateQueries({ queryKey: keys.home });
      break;
    case "subscription.updated":
    case "subscription.deleted":
      void client.invalidateQueries({ queryKey: keys.subscriptions });
      break;
    case "queue.state":
      client.setQueryData<QueueState>(keys.queue, (old) =>
        old ? { ...old, paused: event.paused } : old,
      );
      break;
    case "library.task":
      client.setQueryData(keys.libraryTask, event.task);
      if (event.task.state !== "running") {
        // Files moved: paths, thumbnails and counts may have changed.
        void client.invalidateQueries({ queryKey: keys.videos });
        void client.invalidateQueries({ queryKey: keys.channels });
        void client.invalidateQueries({ queryKey: keys.system });
      }
      break;
    case "ping":
      break;
  }
}

/** Keeps a WebSocket open while signed in and feeds events into the query cache. */
export function LiveEventsProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(websocketUrl("ws"));
      socket.onopen = () => {
        retry = 0;
        setConnected(true);
        // Catch up on anything missed while disconnected.
        void client.invalidateQueries({ queryKey: keys.jobs });
      };
      socket.onmessage = (message) => {
        try {
          handleEvent(client, JSON.parse(String(message.data)) as LiveEvent);
        } catch {
          // ignore malformed events
        }
      };
      socket.onclose = (event) => {
        setConnected(false);
        if (closed || event.code === 4401) return;
        retry += 1;
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** Math.min(retry, 5)));
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [client]);

  return <LiveContext.Provider value={connected}>{children}</LiveContext.Provider>;
}

export function useLiveConnected(): boolean {
  return useContext(LiveContext);
}
