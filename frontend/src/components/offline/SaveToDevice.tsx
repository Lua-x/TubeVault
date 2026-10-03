import { useQuery } from "@tanstack/react-query";
import { Check, HardDriveDownload, X } from "lucide-react";
import { useState } from "react";

import { usePlayback } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { VideoDetail } from "@/lib/types";
import {
  notEnoughSpace,
  originalQuality,
  QUALITY_LABELS,
  useOffline,
  type OfflineQuality,
} from "@/offline/context";

interface DeviceOptions {
  duration: number;
  source_height: number | null;
  original_size: number;
  estimates: Record<string, number>;
  can_remux: boolean;
  audio_size: number | null;
}

interface Choice {
  quality: OfflineQuality;
  size: number;
  hint: string;
}

function useChoices(video: VideoDetail, enabled: boolean): Choice[] | null {
  const { data: info } = usePlayback(video.id);
  const { data: options } = useQuery({
    queryKey: ["videos", "device", video.id],
    queryFn: () => api.get<DeviceOptions>(`videos/${video.id}/device`),
    enabled,
    staleTime: 60_000,
  });
  if (!info || !options) return null;
  const choices: Choice[] = [];
  const original = originalQuality(info);
  if (original) {
    choices.push({ quality: original, size: options.original_size, hint: "Beste Qualität" });
  }
  const playable = choices.length > 0;
  for (const height of [720, 480] as const) {
    const estimate = options.estimates[String(height)];
    // A compact copy is worth it when it saves space – or when nothing else plays here.
    if (estimate && (!playable || estimate < options.original_size * 0.9)) {
      choices.push({
        quality: height,
        size: estimate,
        hint: playable ? "Spart Platz – etwa" : "Läuft auf diesem Gerät – etwa",
      });
    }
  }
  if (options.audio_size) {
    choices.push({ quality: "audio", size: options.audio_size, hint: "Zum Hören – etwa" });
  }
  return choices;
}

/** "Aufs Gerät": save a video for watching without the server. */
export function SaveToDevice({ video, className }: { video: VideoDetail; className?: string }) {
  const offline = useOffline();
  const [open, setOpen] = useState(false);
  const choices = useChoices(video, open);
  const [picked, setPicked] = useState<OfflineQuality | null>(null);
  const task = offline.tasks.find((t) => t.id === video.id);
  const saved = offline.entries[video.id];

  if (!offline.supported) return null;

  if (task) {
    const label =
      task.phase === "queued"
        ? "Wartet …"
        : task.phase === "preparing"
          ? `Wird vorbereitet ${Math.round(task.progress * 100)} %`
          : `Lädt ${Math.round(task.progress * 100)} %`;
    return (
      <span
        className={cn(
          "inline-flex h-9 items-center gap-2 rounded-full bg-surface pr-1.5 pl-4 text-[14px]",
          className,
        )}
      >
        <span className="tabular-nums">{label}</span>
        <ProgressBar value={task.phase === "queued" ? null : task.progress} className="w-16" />
        <button
          type="button"
          aria-label="Abbrechen"
          onClick={() => offline.cancel(video.id)}
          className="flex size-7 items-center justify-center rounded-full text-secondary hover:bg-surface-hover"
        >
          <X className="size-4" strokeWidth={2} />
        </button>
      </span>
    );
  }

  if (saved) {
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "inline-flex h-9 items-center gap-2 rounded-full bg-success/15 px-4 text-[14px] font-medium text-success",
            className,
          )}
        >
          <Check className="size-4" strokeWidth={2.5} />
          Auf dem Gerät
        </button>
        <Dialog open={open} onClose={() => setOpen(false)} title="Auf diesem Gerät">
          <p className="text-[15px] text-secondary">
            {QUALITY_LABELS[String(saved.quality)]} · {formatBytes(saved.size)}. Läuft auch ohne
            Verbindung zum Server – unter „Auf diesem Gerät“.
          </p>
          <div className="mt-6 flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Behalten
            </Button>
            <Button
              className="bg-danger hover:bg-danger/90"
              onClick={() => {
                void offline.remove(video.id);
                setOpen(false);
              }}
            >
              Vom Gerät löschen
            </Button>
          </div>
        </Dialog>
      </>
    );
  }

  const selected = picked ?? choices?.[0]?.quality ?? null;
  const size = choices?.find((c) => c.quality === selected)?.size ?? 0;
  const space = notEnoughSpace(size, offline.usage);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors hover:bg-surface-hover",
          className,
        )}
      >
        <HardDriveDownload className="size-4" strokeWidth={2} />
        Aufs Gerät
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Aufs Gerät laden">
        <p className="text-[15px] text-secondary">
          Zum Schauen ohne Verbindung zum Server, etwa unterwegs. Die App muss geöffnet bleiben, bis
          der Download fertig ist.
        </p>
        <div className="mt-5 flex flex-col gap-2" role="radiogroup" aria-label="Fassung">
          {choices === null && <ProgressBar value={null} />}
          {choices?.length === 0 && (
            <p className="text-[14px] text-secondary">
              Dieses Video lässt sich auf diesem Gerät nicht speichern.
            </p>
          )}
          {choices?.map((choice) => (
            <button
              key={choice.quality}
              type="button"
              role="radio"
              aria-checked={selected === choice.quality}
              onClick={() => setPicked(choice.quality)}
              className={cn(
                "flex items-center justify-between gap-4 rounded-xl border px-4 py-3 text-left transition-colors",
                selected === choice.quality
                  ? "border-accent bg-accent/10"
                  : "border-separator hover:bg-surface",
              )}
            >
              <span>
                <span className="block text-[15px]">{QUALITY_LABELS[String(choice.quality)]}</span>
                <span className="block text-[13px] text-secondary">{choice.hint}</span>
              </span>
              <span className="text-[14px] text-secondary tabular-nums">
                {formatBytes(choice.size)}
              </span>
            </button>
          ))}
        </div>
        {offline.usage && (
          <p className="mt-3 text-[13px] text-tertiary">
            Frei auf diesem Gerät: {formatBytes(offline.usage.quota - offline.usage.used)}
          </p>
        )}
        {space && <p className="mt-2 text-[13px] text-danger">{space}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button
            disabled={selected === null || Boolean(space)}
            onClick={() => {
              if (selected === null) return;
              offline.save(video, selected);
              setOpen(false);
            }}
          >
            Laden
          </Button>
        </div>
      </Dialog>
    </>
  );
}
