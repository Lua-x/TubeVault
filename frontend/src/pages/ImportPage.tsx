import { ArrowLeft, ChevronDown, FolderSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import {
  useImportOverview,
  useLibraryTask,
  useStartImport,
  useStartImportScan,
} from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryTaskStatus } from "@/components/settings/LibraryGroup";
import { Button } from "@/components/ui/Button";
import { Group, Row } from "@/components/ui/Group";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PageSpinner } from "@/components/ui/Spinner";
import { Switch } from "@/components/ui/Switch";
import { useYoutube } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn } from "@/lib/cn";
import { formatBytes, formatRelative } from "@/lib/format";
import type { ImportCandidate, ImportMode } from "@/lib/types";

export function ImportPage() {
  useDocumentTitle("Import");
  const { data, isLoading } = useImportOverview();
  const { data: task } = useLibraryTask(true);
  const scan = useStartImportScan();
  const run = useStartImport();
  const toast = useToast();
  const youtube = useYoutube();
  // Keys whose checkbox differs from what is picked by default.
  const [toggled, setToggled] = useState<Set<string>>(() => new Set());
  const [mode, setMode] = useState<ImportMode>("move");
  const [fetchMetadata, setFetchMetadata] = useState(true);

  if (isLoading || !data) return <PageSpinner />;

  const busy = task?.state === "running";
  const ready = data.candidates.filter((c) => c.status === "ready");
  const readyYoutube = ready.filter((c) => c.kind === "youtube");
  const readyOwn = ready.filter((c) => c.kind === "own");
  const known = data.candidates.filter((c) => c.status === "known");
  // Own videos are only picked by default on a pure media server, so an old archive
  // without IDs doesn't land in the library by accident.
  const pickedByDefault = (c: ImportCandidate) => c.kind === "youtube" || !youtube;
  const isSelected = (c: ImportCandidate) => toggled.has(c.key) !== pickedByDefault(c);
  const selected = ready.filter(isSelected);
  const keepPossible = selected.length > 0 && selected.every((c) => c.root === "media");
  const effectiveMode = mode === "keep" && !keepPossible ? "move" : mode;

  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");
  const toggle = (key: string) =>
    setToggled((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const setAll = (items: ImportCandidate[], on: boolean) =>
    setToggled((current) => {
      const next = new Set(current);
      for (const c of items) {
        if (on === pickedByDefault(c)) next.delete(c.key);
        else next.add(c.key);
      }
      return next;
    });

  return (
    <>
      <Link
        to="/admin"
        className="mb-3 inline-flex items-center gap-1.5 text-[15px] text-secondary transition-colors hover:text-primary"
      >
        <ArrowLeft className="size-4" strokeWidth={2} />
        Verwaltung
      </Link>
      <PageHeader
        title="Import"
        subtitle="Vorhandene Videos in die Bibliothek übernehmen"
        desktopActions
        actions={
          <Button
            icon={<FolderSearch className="size-4" strokeWidth={2} />}
            loading={scan.isPending}
            disabled={busy}
            onClick={() => scan.mutate(undefined, { onError: fail })}
          >
            Ordner durchsuchen
          </Button>
        }
      />

      <div className="flex max-w-3xl flex-col gap-6 pb-16">
        <section className="rounded-2xl bg-elevated p-4 text-[14px] leading-relaxed text-secondary sm:p-5">
          <p>
            TubeVault sucht in <code className="text-primary">{data.import_dir}</code>
            {data.import_dir_exists ? "" : " (nicht eingebunden)"} und nach Videos unter{" "}
            <code className="text-primary">/media</code>, die noch nicht in der Bibliothek sind. Die
            YouTube-ID kommt aus einer <code className="text-primary">.info.json</code> von yt-dlp
            oder aus dem Dateinamen, z. B.{" "}
            <code className="text-primary">Titel [dQw4w9WgXcQ].mp4</code>.
          </p>
          <p className="mt-2">
            Dateien ohne YouTube-ID sind <span className="text-primary">eigene Videos</span>, etwa
            von Kamera oder Handy. Ihr Ordner wird zum Kanal (
            <code className="text-primary">/import/Urlaub 2024/…</code> → „Urlaub 2024“), Titel und
            Aufnahmedatum kommen aus der Datei.
          </p>
          {!data.import_dir_exists && (
            <p className="mt-2">
              Für einen eigenen Import-Ordner in der <code>docker-compose.yml</code> ergänzen:{" "}
              <code className="text-primary">- ./import:/import</code>
            </p>
          )}
          <Button
            className="mt-4 md:hidden"
            icon={<FolderSearch className="size-4" strokeWidth={2} />}
            loading={scan.isPending}
            disabled={busy}
            onClick={() => scan.mutate(undefined, { onError: fail })}
          >
            Ordner durchsuchen
          </Button>
        </section>

        <LibraryTaskStatus />

        {data.scanned_at && (
          <>
            {ready.length === 0 && (
              <Group
                title="Bereit zum Import"
                footer={`Durchsucht ${formatRelative(data.scanned_at)}`}
              >
                <Row className="text-[15px] text-secondary">Nichts Neues gefunden.</Row>
              </Group>
            )}
            <CandidateGroup
              title="YouTube-Videos"
              items={readyYoutube}
              isSelected={isSelected}
              onToggle={toggle}
              onAll={(on) => setAll(readyYoutube, on)}
            />
            <CandidateGroup
              title="Eigene Videos"
              footer="Ohne YouTube-ID – Kommentare, SponsorBlock und Abos gibt es für sie nicht."
              items={readyOwn}
              isSelected={isSelected}
              onToggle={toggle}
              onAll={(on) => setAll(readyOwn, on)}
            />
            {ready.length > 0 && (
              <p className="-mt-3 px-4 text-[13px] text-tertiary">
                {selected.length} von {ready.length} ausgewählt ·{" "}
                {formatBytes(selected.reduce((sum, c) => sum + c.size, 0))} · Durchsucht{" "}
                {formatRelative(data.scanned_at)}
              </p>
            )}

            {ready.length > 0 && (
              <Group title="Optionen">
                <Row className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-[15px]">Dateien</span>
                  <SegmentedControl
                    label="Dateien"
                    value={effectiveMode}
                    onChange={setMode}
                    options={[
                      { value: "move", label: "Verschieben" },
                      { value: "copy", label: "Kopieren" },
                      ...(keepPossible ? [{ value: "keep" as const, label: "Liegen lassen" }] : []),
                    ]}
                  />
                </Row>
                {youtube && selected.some((c) => c.kind === "youtube") && (
                  <Row>
                    <Switch
                      label="Fehlende Infos von YouTube laden"
                      description="Für Dateien ohne .info.json. Gibt es das Video nicht mehr, nimmt TubeVault den Dateinamen."
                      checked={fetchMetadata}
                      onChange={setFetchMetadata}
                    />
                  </Row>
                )}
              </Group>
            )}

            {ready.length > 0 && (
              <div className="flex justify-end">
                <Button
                  disabled={busy || selected.length === 0}
                  loading={run.isPending}
                  onClick={() =>
                    run.mutate(
                      {
                        keys: selected.map((c) => c.key),
                        mode: effectiveMode,
                        fetch_metadata: youtube && fetchMetadata,
                      },
                      { onError: fail },
                    )
                  }
                >
                  {selected.length === 1
                    ? "1 Video importieren"
                    : `${selected.length} Videos importieren`}
                </Button>
              </div>
            )}

            <Collapsible title={`Schon in der Bibliothek (${known.length})`} items={known} />
          </>
        )}
      </div>
    </>
  );
}

function CandidateGroup({
  title,
  footer,
  items,
  isSelected,
  onToggle,
  onAll,
}: {
  title: string;
  footer?: string;
  items: ImportCandidate[];
  isSelected: (c: ImportCandidate) => boolean;
  onToggle: (key: string) => void;
  onAll: (on: boolean) => void;
}) {
  if (items.length === 0) return null;
  const count = items.filter(isSelected).length;
  const all = count === items.length;
  return (
    <Group title={`${title} (${items.length})`} footer={footer}>
      <Row className="flex items-center justify-between gap-4 text-[14px]">
        <span className="text-secondary">
          {count} von {items.length} ausgewählt
        </span>
        <button
          type="button"
          className="font-medium text-accent hover:underline"
          onClick={() => onAll(!all)}
        >
          {all ? "Keine" : "Alle"}
        </button>
      </Row>
      {items.map((candidate) => (
        <CandidateRow
          key={candidate.key}
          candidate={candidate}
          checked={isSelected(candidate)}
          onToggle={() => onToggle(candidate.key)}
        />
      ))}
    </Group>
  );
}

function CandidateRow({
  candidate,
  checked,
  onToggle,
}: {
  candidate: ImportCandidate;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-surface/40">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-1 size-4 shrink-0 accent-[var(--tv-accent)]"
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px]">{candidate.title}</span>
        <span className="block truncate font-mono text-[12px] text-secondary">
          {candidate.root === "import" ? "/import/" : "/media/"}
          {candidate.relative}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1 text-[12px] text-secondary">
        <span className="tabular-nums">{formatBytes(candidate.size)}</span>
        {candidate.source && (
          <span className="rounded-full bg-surface px-2 py-0.5">{candidate.source}</span>
        )}
      </span>
    </label>
  );
}

function Collapsible({
  title,
  items,
  hint,
}: {
  title: string;
  items: ImportCandidate[];
  hint?: string;
}) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-4 text-left text-[13px] font-medium tracking-wide text-secondary uppercase"
      >
        {title}
        <ChevronDown
          className={cn("size-4 transition-transform duration-200", open && "rotate-180")}
          strokeWidth={2}
        />
      </button>
      {open && (
        <div className="tv-group-card divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
          {hint && <p className="px-4 py-3 text-[13px] text-secondary">{hint}</p>}
          {items.map((c) => (
            <div key={c.key} className="px-4 py-2.5">
              <p className="truncate text-[14px]">{c.title}</p>
              <p className="truncate font-mono text-[12px] text-secondary">
                {c.root === "import" ? "/import/" : "/media/"}
                {c.relative}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
