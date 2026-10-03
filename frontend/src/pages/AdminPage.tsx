import {
  ChevronRight,
  FolderInput,
  ImageDown,
  RefreshCw,
  ScanSearch,
  FileText,
  SearchCheck,
  Trash2,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import {
  useAdminLogs,
  useAdminOverview,
  useCheckYtDlp,
  useLibraryTask,
  useMaintenance,
  useRestart,
  useUpdateYtDlp,
  useYtDlp,
} from "@/api/queries";
import { BackupGroup } from "@/components/admin/BackupGroup";
import { DownloadColumns, StorageBars } from "@/components/admin/Charts";
import { RestartingDialog } from "@/components/admin/Restarting";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryTaskStatus } from "@/components/settings/LibraryGroup";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PageSpinner } from "@/components/ui/Spinner";
import { useToast } from "@/hooks/toast";
import { useAwaitRestart } from "@/hooks/useAwaitRestart";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { AdminOverview, MaintenanceAction } from "@/lib/types";

const HWACCEL_LABELS = { none: "Software", vaapi: "Intel/AMD (VAAPI)", nvenc: "NVIDIA (NVENC)" };

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return `${days} ${days === 1 ? "Tag" : "Tagen"}`;
  if (hours > 0) return `${hours} ${hours === 1 ? "Stunde" : "Stunden"}`;
  const minutes = Math.max(1, Math.floor(seconds / 60));
  return `${minutes} ${minutes === 1 ? "Minute" : "Minuten"}`;
}

const compact = new Intl.NumberFormat("de-DE", { notation: "compact", maximumFractionDigits: 1 });

export function AdminPage() {
  useDocumentTitle("Verwaltung");
  const { data } = useAdminOverview();
  if (!data) return <PageSpinner />;
  return (
    <>
      <PageHeader
        title="Verwaltung"
        subtitle={`TubeVault ${data.versions.tubevault ?? ""} · läuft seit ${formatUptime(data.uptime_s)}`}
      />
      <div className="flex flex-col gap-9 pb-16">
        <StatTiles data={data} />
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Speicher pro Kanal">
            <StorageBars data={data.storage_by_channel} />
          </Card>
          <Card title="Downloads">
            <DownloadColumns data={data.downloads_per_day} />
          </Card>
        </div>
        <div className="grid items-start gap-9 lg:grid-cols-2">
          <div className="flex flex-col gap-9">
            <YtDlpGroup />
            <SystemGroup data={data} />
          </div>
          <div className="flex flex-col gap-9">
            <MaintenanceGroup />
            <BackupGroup />
          </div>
        </div>
        <LogViewer />
      </div>
    </>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-elevated p-4 sm:p-5">
      <h2 className="mb-4 text-[17px] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function StatTile({
  label,
  value,
  detail,
  children,
}: {
  label: string;
  value: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-elevated p-4">
      <p className="text-[13px] text-secondary">{label}</p>
      <p className="mt-1 text-[26px] leading-tight font-semibold tracking-tight">{value}</p>
      {detail && <p className="mt-0.5 text-[13px] text-secondary">{detail}</p>}
      {children}
    </div>
  );
}

function StatTiles({ data }: { data: AdminOverview }) {
  const used =
    data.disk_total && data.disk_free != null ? 1 - data.disk_free / data.disk_total : null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <StatTile
        label="Videos"
        value={compact.format(data.videos)}
        detail={`${data.channels} ${data.channels === 1 ? "Kanal" : "Kanäle"}`}
      />
      <StatTile label="Bibliothek" value={formatBytes(data.library_size)} />
      <StatTile
        label="Freier Speicher"
        value={data.disk_free != null ? formatBytes(data.disk_free) : "–"}
        detail={data.disk_total ? `von ${formatBytes(data.disk_total)}` : undefined}
      >
        {used != null && <ProgressBar value={used} label="Belegter Speicher" className="mt-2.5" />}
      </StatTile>
      <StatTile
        label="Downloads (7 Tage)"
        value={compact.format(data.downloads_7d)}
        detail={data.failed_7d ? `${data.failed_7d} fehlgeschlagen` : "keine Fehler"}
      />
      <StatTile label="In der Warteschlange" value={compact.format(data.queued)} />
      <StatTile label="Abos" value={compact.format(data.subscriptions)} />
    </div>
  );
}

function YtDlpGroup() {
  const { data } = useYtDlp();
  const check = useCheckYtDlp();
  const update = useUpdateYtDlp();
  const restart = useRestart();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const { restarting, begin } = useAwaitRestart();

  const newer = data?.latest && data.installed && data.latest !== data.installed;
  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");

  const doRestart = () => {
    restart.mutate(undefined, {
      onSuccess: () => {
        setConfirm(false);
        begin();
      },
      onError: fail,
    });
  };

  return (
    <Group
      title="yt-dlp"
      footer="YouTube ändert häufig Details – ein aktuelles yt-dlp hält Downloads am Laufen. TubeVault aktualisiert es außerdem bei jedem Start."
    >
      <Row className="flex items-center justify-between gap-4 text-[15px]">
        <span>Installiert</span>
        <span className="text-secondary tabular-nums">{data?.installed ?? "–"}</span>
      </Row>
      {data?.latest && (
        <Row className="flex items-center justify-between gap-4 text-[15px]">
          <span>Neueste Version</span>
          <span className={cn("tabular-nums", newer ? "text-accent" : "text-secondary")}>
            {data.latest}
          </span>
        </Row>
      )}
      {data?.restart_required && (
        <Row className="text-[14px] text-secondary">
          Neu installiert, aktiv wird {data.installed} nach einem Neustart (läuft noch:{" "}
          {data.loaded}).
        </Row>
      )}
      <Row className="flex flex-wrap justify-end gap-2.5">
        <Button
          variant="secondary"
          size="sm"
          loading={check.isPending}
          onClick={() => check.mutate(undefined, { onError: fail })}
        >
          Nach Updates suchen
        </Button>
        <Button
          variant="secondary"
          size="sm"
          loading={update.isPending}
          onClick={() =>
            update.mutate(undefined, {
              onSuccess: (result) => toast(result.message, result.updated ? "success" : "info"),
              onError: fail,
            })
          }
        >
          Jetzt aktualisieren
        </Button>
        {data?.restart_required && (
          <Button size="sm" onClick={() => setConfirm(true)}>
            Neu starten
          </Button>
        )}
      </Row>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="TubeVault neu starten?">
        <p className="text-[15px] text-secondary">
          Laufende Downloads werden unterbrochen und danach automatisch fortgesetzt. Die Seite lädt
          neu, sobald TubeVault wieder da ist – meist nach wenigen Sekunden.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirm(false)}>
            Abbrechen
          </Button>
          <Button loading={restart.isPending} onClick={doRestart}>
            Neu starten
          </Button>
        </div>
      </Dialog>
      <RestartingDialog open={restarting} />
    </Group>
  );
}

function SystemGroup({ data }: { data: AdminOverview }) {
  const rows: [string, string][] = [
    ["yt-dlp (aktiv)", data.versions["yt-dlp"] ?? "–"],
    ["ffmpeg", data.versions.ffmpeg ?? "nicht gefunden"],
    ["Python", data.versions.python ?? "–"],
    ["SQLite", data.versions.sqlite ?? "–"],
    ["Umwandlung", HWACCEL_LABELS[data.hwaccel]],
    ["Laufende Umwandlungen", String(data.transcode_sessions)],
    ["Umwandlungs-Cache", formatBytes(data.cache_size) || "0 B"],
    ["Datenbank", formatBytes(data.database_size)],
  ];
  return (
    <Group title="System">
      {rows.map(([label, value]) => (
        <Row key={label} className="flex justify-between gap-4 text-[15px]">
          <span>{label}</span>
          <span className="text-right text-secondary">{value}</span>
        </Row>
      ))}
    </Group>
  );
}

const ACTIONS: {
  action: MaintenanceAction;
  label: string;
  hint: string;
  icon: typeof RefreshCw;
}[] = [
  {
    action: "verify",
    label: "Dateien prüfen",
    hint: "Findet Videos, deren Datei fehlt, und solche, die wieder da sind",
    icon: SearchCheck,
  },
  {
    action: "search-index",
    label: "Suchindex neu aufbauen",
    hint: "Falls die Suche Videos nicht findet",
    icon: ScanSearch,
  },
  {
    action: "artwork",
    label: "Kanalbilder neu laden",
    hint: "Avatar und Banner aller Kanäle frisch von YouTube",
    icon: ImageDown,
  },
  {
    action: "nfo",
    label: "NFO-Dateien neu schreiben",
    hint: "Nach Änderungen an Titeln oder Kanälen",
    icon: FileText,
  },
  {
    action: "cache",
    label: "Umwandlungs-Cache leeren",
    hint: "Löscht umgewandelte Fassungen; die Originale bleiben",
    icon: Trash2,
  },
];

function MaintenanceGroup() {
  const run = useMaintenance();
  const { data: task } = useLibraryTask(true);
  const toast = useToast();
  const busy = task?.state === "running";
  return (
    <div className="flex flex-col gap-3">
      <Group title="Wartung">
        <Link
          to="/admin/import"
          className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface/40"
        >
          <FolderInput className="size-5 shrink-0 text-accent" strokeWidth={1.75} />
          <span className="min-w-0 flex-1">
            <span className="block text-[15px]">Vorhandene Videos importieren</span>
            <span className="block text-[13px] text-secondary">
              Aus /import oder unbekannten Dateien unter /media
            </span>
          </span>
          <ChevronRight className="size-4 text-tertiary" strokeWidth={2} />
        </Link>
        {ACTIONS.map(({ action, label, hint, icon: Icon }) => (
          <Row key={action} className="flex items-center gap-3">
            <Icon className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
            <span className="min-w-0 flex-1">
              <span className="block text-[15px]">{label}</span>
              <span className="block text-[13px] text-secondary">{hint}</span>
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() =>
                run.mutate(action, {
                  onError: (err) => toast(err.message, "error"),
                })
              }
            >
              Starten
            </Button>
          </Row>
        ))}
      </Group>
      <LibraryTaskStatus />
    </div>
  );
}

const LEVELS = [
  { value: "INFO", label: "Alle" },
  { value: "WARNING", label: "Warnungen" },
  { value: "ERROR", label: "Fehler" },
];

function LogViewer() {
  const [level, setLevel] = useState("INFO");
  const { data, refetch, isFetching } = useAdminLogs(level);
  const entries = [...(data ?? [])].reverse();
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4">
        <h2 className="text-[13px] font-medium tracking-wide text-secondary uppercase">
          Protokoll
        </h2>
        <div className="flex items-center gap-2">
          <SegmentedControl label="Stufe" value={level} onChange={setLevel} options={LEVELS} />
          <Button
            variant="secondary"
            size="sm"
            loading={isFetching}
            icon={<RefreshCw className="size-3.5" strokeWidth={2} />}
            onClick={() => void refetch()}
          >
            Neu laden
          </Button>
        </div>
      </div>
      <div className="max-h-[440px] overflow-auto rounded-2xl bg-elevated px-4 py-3 font-mono text-[12px] leading-relaxed">
        {entries.length === 0 ? (
          <p className="font-sans text-[14px] text-secondary">Keine Einträge.</p>
        ) : (
          entries.map((entry, index) => (
            <div
              key={`${entry.time}-${index}`}
              className="border-b border-separator/60 py-1.5 last:border-0"
            >
              <span className="text-tertiary">{entry.time}</span>{" "}
              <span
                className={cn(
                  "font-semibold",
                  entry.level === "ERROR" || entry.level === "CRITICAL"
                    ? "text-danger"
                    : entry.level === "WARNING"
                      ? "text-warning"
                      : "text-secondary",
                )}
              >
                {entry.level}
              </span>{" "}
              <span className="text-tertiary">{entry.logger}</span>
              <pre className="mt-0.5 break-words whitespace-pre-wrap text-primary">
                {entry.message}
              </pre>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
