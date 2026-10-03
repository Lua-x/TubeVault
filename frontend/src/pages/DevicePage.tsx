import { HardDriveDownload, Play, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatBytes, formatDuration } from "@/lib/format";
import { QUALITY_LABELS, useOffline, type OfflineEntry } from "@/offline/context";
import { loadLocalProgress } from "@/offline/progress";

function Poster({ entry }: { entry: OfflineEntry }) {
  const { thumbnail } = useOffline();
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    void thumbnail(entry.id).then((blob) => {
      if (!blob || cancelled) return;
      url = URL.createObjectURL(blob);
      setSrc(url);
    });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [entry.id, thumbnail]);
  return src ? (
    <img src={src} alt="" className="size-full object-cover" />
  ) : (
    <div className="size-full bg-surface" />
  );
}

/** Videos saved on this device – also the whole app when the server is out of reach. */
export function DevicePage({ offlineMode = false }: { offlineMode?: boolean }) {
  useDocumentTitle("Auf diesem Gerät");
  const { supported, owner, ready, entries, tasks, usage, cancel, remove } = useOffline();
  const local = loadLocalProgress(owner);
  const list = Object.values(entries).sort((a, b) => b.saved_at.localeCompare(a.saved_at));
  const total = list.reduce((sum, entry) => sum + entry.size, 0);

  if (!ready) return <PageSpinner />;
  return (
    <>
      <header className="mb-6 md:mb-8">
        <h1 className="text-[32px] leading-tight font-bold tracking-tight md:text-[34px]">
          Auf diesem Gerät
        </h1>
        <p className="mt-0.5 text-[15px] text-secondary">
          {list.length} {list.length === 1 ? "Video" : "Videos"} · {formatBytes(total) || "0 B"}
          {usage && ` · ${formatBytes(usage.quota - usage.used)} frei`}
        </p>
      </header>
      {!offlineMode && <LibraryTabs />}

      {!supported && (
        <EmptyState
          icon={<HardDriveDownload className="size-7" strokeWidth={1.5} />}
          title="Nicht verfügbar"
        >
          Dieser Browser kann keine Videos speichern. Installiere TubeVault als App (über HTTPS),
          dann klappt es.
        </EmptyState>
      )}

      {tasks.length > 0 && (
        <section aria-labelledby="loading-heading" className="mb-8">
          <h2 id="loading-heading" className="mb-3 px-1 text-[20px] font-semibold tracking-tight">
            Wird geladen
          </h2>
          <ul className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px]">{task.title}</p>
                  <p className="text-[13px] text-secondary">
                    {QUALITY_LABELS[String(task.quality)]} ·{" "}
                    {task.phase === "queued"
                      ? "wartet"
                      : task.phase === "preparing"
                        ? `Server bereitet vor (${Math.round(task.progress * 100)} %)`
                        : `lädt (${Math.round(task.progress * 100)} %)`}
                  </p>
                  {task.phase !== "queued" && (
                    <ProgressBar value={task.progress} className="mt-2" />
                  )}
                </div>
                <button
                  type="button"
                  aria-label="Abbrechen"
                  onClick={() => cancel(task.id)}
                  className="flex size-8 items-center justify-center rounded-full text-secondary hover:bg-surface"
                >
                  <X className="size-4" strokeWidth={2} />
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2 px-1 text-[13px] text-tertiary">
            Lass die App geöffnet, bis alles geladen ist.
          </p>
        </section>
      )}

      {supported && list.length === 0 && tasks.length === 0 && (
        <EmptyState
          icon={<HardDriveDownload className="size-7" strokeWidth={1.5} />}
          title={offlineMode ? "Keine Videos auf diesem Gerät" : "Noch nichts gespeichert"}
        >
          {offlineMode
            ? "Sobald der Server wieder erreichbar ist, kannst du Videos mit „Aufs Gerät“ für unterwegs speichern."
            : "Öffne ein Video und tippe auf „Aufs Gerät“ – dann läuft es auch ohne Verbindung zum Server."}
        </EmptyState>
      )}

      {list.length > 0 && (
        <ul className="grid gap-x-5 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {list.map((entry) => {
            const position = local[entry.id]?.position_s ?? entry.video.progress?.position_s ?? 0;
            const duration = entry.video.duration_s ?? 0;
            return (
              <li key={entry.id} className="group">
                <Link
                  to={`/device/${entry.id}`}
                  className="relative block aspect-video overflow-hidden rounded-2xl"
                >
                  <Poster entry={entry} />
                  <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-opacity group-hover:bg-black/30 group-hover:opacity-100">
                    <Play className="size-10 fill-white text-white" strokeWidth={0} />
                  </span>
                  {duration > 0 && (
                    <span className="absolute right-2 bottom-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[12px] font-medium text-white tabular-nums">
                      {formatDuration(duration)}
                    </span>
                  )}
                  {position > 0 && duration > 0 && (
                    <span className="absolute inset-x-0 bottom-0 h-1 bg-white/25">
                      <span
                        className="block h-full bg-accent"
                        style={{ width: `${Math.min(100, (position / duration) * 100)}%` }}
                      />
                    </span>
                  )}
                </Link>
                <div className="mt-3 flex items-start gap-3 px-1">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/device/${entry.id}`}
                      className="line-clamp-2 text-[15px] leading-snug font-medium"
                    >
                      {entry.video.title}
                    </Link>
                    <p className="mt-1 truncate text-[13px] text-secondary">
                      {[
                        entry.video.channel?.name,
                        QUALITY_LABELS[String(entry.quality)],
                        formatBytes(entry.size),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    aria-label={`„${entry.video.title}“ vom Gerät löschen`}
                    icon={<Trash2 className="size-4" strokeWidth={2} />}
                    onClick={() => {
                      if (window.confirm(`„${entry.video.title}“ vom Gerät löschen?`)) {
                        void remove(entry.id);
                      }
                    }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
