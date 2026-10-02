import { CircleAlert, CircleCheck } from "lucide-react";

import { useLibraryTask } from "@/api/queries";
import { Group, Row } from "@/components/ui/Group";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Switch } from "@/components/ui/Switch";
import type { Layout, LibraryOptions, LibraryTask } from "@/lib/types";

const LAYOUTS: { value: Layout; label: string }[] = [
  { value: "tubevault", label: "TubeVault" },
  { value: "series", label: "Serien" },
];

const EXAMPLES: Record<Layout, string> = {
  tubevault: "Kanal/2026/Titel [ID].mp4",
  series: "Kanal/Season 2026/2026-08-23 - Titel [ID].mp4",
};

interface LibraryGroupProps {
  value: LibraryOptions;
  onChange: (patch: Partial<LibraryOptions>) => void;
}

/** Folder layout and NFO files for Jellyfin, Emby, Kodi and Plex (admins only). */
export function LibraryGroup({ value, onChange }: LibraryGroupProps) {
  return (
    <Group
      title="Mediaserver"
      footer={
        value.layout === "series"
          ? "Jeder Kanal wird in Jellyfin, Emby, Kodi oder Plex zur Serie, jedes Jahr zur Staffel. Bibliothekstyp dort: „Serien“."
          : "Bibliothekstyp in Jellyfin oder Emby: „Filme“ oder „Heimvideos“. Für Serien das Schema „Serien“ wählen."
      }
    >
      <Row className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-[15px]">Ordnerstruktur</p>
          <p className="truncate font-mono text-[12px] text-secondary">{EXAMPLES[value.layout]}</p>
        </div>
        <SegmentedControl
          label="Ordnerstruktur"
          value={value.layout}
          onChange={(layout) => onChange({ layout })}
          options={LAYOUTS}
        />
      </Row>
      <Row>
        <Switch
          label="NFO-Dateien schreiben"
          description="Titel, Beschreibung und Datum für Jellyfin, Emby und Kodi. Eigene NFO-Dateien bleiben unangetastet."
          checked={value.write_nfo}
          onChange={(write_nfo) => onChange({ write_nfo })}
        />
      </Row>
    </Group>
  );
}

/** Live progress of moving files or writing NFOs. */
export function LibraryTaskStatus() {
  const { data: task } = useLibraryTask(true);
  if (!task || !isRecent(task)) return null;
  const share = task.total > 0 ? task.done / task.total : 0;
  return (
    <div
      role="status"
      className="tv-group-card rounded-2xl bg-elevated px-4 py-3"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 text-[15px]">
        {task.state === "done" && <CircleCheck className="size-4 text-success" strokeWidth={2} />}
        {task.state === "failed" && <CircleAlert className="size-4 text-danger" strokeWidth={2} />}
        <span className="font-medium">{task.label}</span>
        {task.state === "running" && task.total > 0 && (
          <span className="ml-auto text-[13px] text-secondary tabular-nums">
            {task.done} / {task.total}
          </span>
        )}
      </div>
      {task.state === "running" ? (
        <>
          <ProgressBar value={share} label={task.label} className="mt-2.5" />
          {task.message && (
            <p className="mt-1.5 truncate text-[13px] text-secondary">{task.message}</p>
          )}
        </>
      ) : (
        <p className="mt-1 text-[13px] text-secondary">
          {task.state === "done" ? `Fertig – ${task.message ?? ""}` : task.message}
        </p>
      )}
    </div>
  );
}

function isRecent(task: LibraryTask): boolean {
  if (task.state === "running" || !task.finished_at) return true;
  return Date.now() - new Date(task.finished_at).getTime() < 10 * 60_000;
}
