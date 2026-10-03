import { ArchiveRestore, Download, History, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import {
  useAppSettings,
  useBackups,
  useCreateBackup,
  useDeleteBackup,
  useRestoreBackup,
  useSaveSettings,
} from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/hooks/toast";
import { useAwaitRestart } from "@/hooks/useAwaitRestart";
import { apiUrl } from "@/lib/base";
import { formatBytes } from "@/lib/format";
import type { Backup, BackupOptions } from "@/lib/types";

import { RestartingDialog } from "./Restarting";

const KEEP = [3, 7, 14, 30];
const when = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" });

type Pending = { kind: "stored"; backup: Backup } | { kind: "file"; file: File };

/** Backups of settings, users, subscriptions, playlists and watch progress. */
export function BackupGroup() {
  const { data } = useBackups();
  const { data: settings } = useAppSettings();
  const save = useSaveSettings();
  const create = useCreateBackup();
  const remove = useDeleteBackup();
  const restore = useRestoreBackup();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const { restarting, begin } = useAwaitRestart();

  const options = settings?.backup;
  const backups = data?.backups ?? [];
  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");

  const change = (patch: Partial<BackupOptions>) => {
    if (!settings || !options) return;
    save.mutate({ ...settings, backup: { ...options, ...patch } }, { onError: fail });
  };

  const confirmRestore = () => {
    if (!pending) return;
    restore.mutate(pending.kind === "stored" ? pending.backup.name : pending.file, {
      onSuccess: () => {
        setPending(null);
        begin();
      },
      onError: fail,
    });
  };

  return (
    <Group
      title="Sicherung"
      footer="Enthält alle Einstellungen, Benutzer, Abos, Playlists und den Wiedergabestand – nicht die Videos selbst, die liegen in /media. Die Sicherungen liegen unter /config/backups; lade ab und zu eine herunter und bewahre sie woanders auf."
    >
      {options && (
        <>
          <Row>
            <Switch
              label="Täglich automatisch sichern"
              checked={options.auto}
              onChange={(auto) => change({ auto })}
            />
          </Row>
          {options.auto && (
            <Row>
              <Select
                inline
                label="Aufbewahren"
                value={String(options.keep)}
                onChange={(event) => change({ keep: Number(event.target.value) })}
              >
                {[...new Set([...KEEP, options.keep])]
                  .sort((a, b) => a - b)
                  .map((keep) => (
                    <option key={keep} value={keep}>
                      {`Die letzten ${keep}`}
                    </option>
                  ))}
              </Select>
            </Row>
          )}
        </>
      )}

      {backups.map((backup) => (
        <Row key={backup.name} className="flex items-center gap-3">
          <History className="hidden size-5 shrink-0 text-secondary sm:block" strokeWidth={1.75} />
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] whitespace-nowrap">
              {when.format(new Date(backup.created_at))}
            </span>
            <span className="block text-[13px] text-secondary">
              {formatBytes(backup.size)} · {backup.auto ? "automatisch" : "von Hand"}
            </span>
          </span>
          <a
            href={apiUrl(`admin/backups/${encodeURIComponent(backup.name)}`)}
            download={backup.name}
            aria-label="Herunterladen"
            title="Herunterladen"
            className="flex size-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-surface hover:text-primary"
          >
            <Download className="size-4" strokeWidth={2} />
          </a>
          <Button
            variant="secondary"
            size="sm"
            aria-label="Wiederherstellen"
            icon={<ArchiveRestore className="size-4 sm:hidden" strokeWidth={2} />}
            onClick={() => setPending({ kind: "stored", backup })}
          >
            <span className="hidden sm:inline">Wiederherstellen</span>
          </Button>
          <button
            type="button"
            aria-label="Löschen"
            title="Löschen"
            onClick={() => remove.mutate(backup.name, { onError: fail })}
            className="flex size-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-surface hover:text-danger"
          >
            <Trash2 className="size-4" strokeWidth={2} />
          </button>
        </Row>
      ))}

      <Row className="flex flex-wrap justify-end gap-2.5">
        <input
          ref={fileInput}
          type="file"
          accept=".zip,application/zip"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) setPending({ kind: "file", file });
          }}
        />
        <Button
          variant="secondary"
          size="sm"
          icon={<Upload className="size-4" strokeWidth={2} />}
          onClick={() => fileInput.current?.click()}
        >
          Aus Datei wiederherstellen
        </Button>
        <Button
          size="sm"
          loading={create.isPending}
          onClick={() =>
            create.mutate(undefined, {
              onSuccess: () => toast("Sicherung erstellt", "success"),
              onError: fail,
            })
          }
        >
          Jetzt sichern
        </Button>
      </Row>

      <Dialog
        open={pending !== null}
        onClose={() => setPending(null)}
        title={
          pending?.kind === "stored"
            ? `Stand vom ${when.format(new Date(pending.backup.created_at))} wiederherstellen?`
            : "Sicherung wiederherstellen?"
        }
      >
        <p className="text-[15px] text-secondary">
          {pending?.kind === "file" && (
            <>
              Datei: <span className="text-primary">{pending.file.name}</span>
              <br />
            </>
          )}
          Einstellungen, Benutzer, Abos, Playlists und der Wiedergabestand werden durch den Stand
          der Sicherung ersetzt. Die Videodateien bleiben, wie sie sind. Der jetzige Stand wird
          vorher automatisch gesichert. TubeVault startet dazu neu; danach musst du dich eventuell
          neu anmelden.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setPending(null)}>
            Abbrechen
          </Button>
          <Button loading={restore.isPending} onClick={confirmRestore}>
            Wiederherstellen
          </Button>
        </div>
      </Dialog>
      <RestartingDialog
        open={restarting}
        message="Die Sicherung wird eingespielt. Die Seite lädt gleich neu."
      />
    </Group>
  );
}
