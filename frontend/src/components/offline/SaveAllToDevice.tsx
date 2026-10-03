import { useQuery } from "@tanstack/react-query";
import { HardDriveDownload } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { VideoSummary } from "@/lib/types";
import { notEnoughSpace, QUALITY_LABELS, useOffline } from "@/offline/context";

const CHOICES = ["best", 720, 480] as const;
type Choice = (typeof CHOICES)[number];

interface DeviceEstimate {
  count: number;
  original_size: number;
  estimates: Record<string, number>;
}

/** "Aufs Gerät" for a whole playlist: everything that isn't on this device yet. */
export function SaveAllToDevice({ videos }: { videos: VideoSummary[] }) {
  const offline = useOffline();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<Choice | null>(null);

  const missing = videos.filter(
    (v) =>
      v.status === "ready" && !offline.entries[v.id] && !offline.tasks.some((t) => t.id === v.id),
  );
  const ids = missing.map((v) => v.id);
  const { data: estimate } = useQuery({
    queryKey: ["videos", "device", "estimate", ids],
    queryFn: () => api.post<DeviceEstimate>("videos/device/estimate", { video_ids: ids }),
    enabled: open && ids.length > 0,
    staleTime: 60_000,
  });

  if (!offline.supported) return null;
  const sizeOf = (choice: Choice) =>
    (choice === "best" ? estimate?.original_size : estimate?.estimates[String(choice)]) ?? 0;
  // Compact by default – unless it wouldn't save anything.
  const selected =
    picked ?? (estimate && sizeOf(720) >= estimate.original_size * 0.9 ? "best" : 720);
  const space = notEnoughSpace(sizeOf(selected), offline.usage);
  const everything = videos.length > 0 && missing.length === 0;

  return (
    <>
      <Button
        variant="secondary"
        icon={<HardDriveDownload className="size-4" strokeWidth={2} />}
        disabled={everything}
        onClick={() => setOpen(true)}
      >
        {everything ? "Auf dem Gerät" : "Aufs Gerät"}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Playlist aufs Gerät laden">
        <p className="text-[15px] text-secondary">
          {missing.length} {missing.length === 1 ? "Video" : "Videos"} zum Schauen ohne Verbindung
          zum Server. Die App muss geöffnet bleiben, bis alles geladen ist.
        </p>
        <div className="mt-5 flex flex-col gap-2" role="radiogroup" aria-label="Fassung">
          {!estimate && missing.length > 0 && <ProgressBar value={null} />}
          {estimate &&
            CHOICES.map((choice) => (
              <button
                key={choice}
                type="button"
                role="radio"
                aria-checked={selected === choice}
                onClick={() => setPicked(choice)}
                className={cn(
                  "flex items-center justify-between gap-4 rounded-xl border px-4 py-3 text-left transition-colors",
                  selected === choice
                    ? "border-accent bg-accent/10"
                    : "border-separator hover:bg-surface",
                )}
              >
                <span>
                  <span className="block text-[15px]">{QUALITY_LABELS[String(choice)]}</span>
                  <span className="block text-[13px] text-secondary">
                    {choice === "best"
                      ? "Beste Qualität"
                      : sizeOf(choice) < sizeOf("best") * 0.9
                        ? "Spart Platz – etwa"
                        : "Läuft überall – etwa"}
                  </span>
                </span>
                <span className="text-[14px] text-secondary tabular-nums">
                  {formatBytes(sizeOf(choice))}
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
            disabled={!estimate || missing.length === 0 || Boolean(space)}
            onClick={() => {
              for (const video of missing) offline.save(video, selected);
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
