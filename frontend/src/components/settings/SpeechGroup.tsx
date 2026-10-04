import { CircleAlert, CircleCheck } from "lucide-react";
import { useState } from "react";

import {
  useLibraryTask,
  useSpeechMissing,
  useSpeechRemove,
  useSpeechSetup,
  useSpeechState,
} from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/hooks/toast";
import type { SpeechModel, SpeechOptions } from "@/lib/types";

/** Roughly what pip pulls in once: faster-whisper with CTranslate2, ONNX Runtime and PyAV. */
const PROGRAM_MB = 450;

const MODEL_NAMES: Record<SpeechModel, string> = {
  tiny: "Klein – am schnellsten",
  base: "Mittel – meist die beste Wahl",
  small: "Groß – genauer, langsamer",
};

const LANGUAGES: [string, string][] = [
  ["auto", "Automatisch erkennen"],
  ["de", "Deutsch"],
  ["en", "Englisch"],
  ["fr", "Französisch"],
  ["es", "Spanisch"],
  ["it", "Italienisch"],
  ["nl", "Niederländisch"],
  ["pl", "Polnisch"],
  ["pt", "Portugiesisch"],
  ["tr", "Türkisch"],
  ["ru", "Russisch"],
  ["uk", "Ukrainisch"],
  ["ja", "Japanisch"],
];

interface SpeechGroupProps {
  value: SpeechOptions;
  onChange: (patch: Partial<SpeechOptions>) => void;
}

/** Subtitles from speech recognition – set up with one click, then made on this server. */
export function SpeechGroup({ value, onChange }: SpeechGroupProps) {
  const { data: task } = useLibraryTask(true);
  const ownTask = task?.kind === "speech" ? task : null;
  const settingUp = ownTask?.state === "running";
  const { data: state } = useSpeechState(true, settingUp);
  const setup = useSpeechSetup();
  const missing = useSpeechMissing();
  const remove = useSpeechRemove();
  const toast = useToast();
  const [removing, setRemoving] = useState(false);

  const model = state?.models.find((m) => m.size === value.model);
  const ready = Boolean(state?.installed && model?.ready);
  const downloadMb = (state?.installed ? 0 : PROGRAM_MB) + (model?.ready ? 0 : (model?.mb ?? 0));

  const startSetup = () =>
    setup.mutate(value.model, { onError: (err) => toast(err.message, "error") });

  return (
    <Group
      title="Untertitel per Spracherkennung"
      footer={
        <>
          Die Erkennung läuft ganz auf deinem Server, mit niedriger Priorität – nichts davon
          verlässt ihn. Nur beim Einrichten lädt TubeVault einmalig das Programm (faster-whisper)
          von PyPI und das Modell von Hugging Face. Ohne Internet: das Modell selbst nach{" "}
          <code className="font-mono text-[12px]">/config/models/faster-whisper-{value.model}</code>{" "}
          legen (siehe Anleitung).
        </>
      }
    >
      <Row>
        <Select
          inline
          label="Modell"
          value={value.model}
          onChange={(e) => onChange({ model: e.target.value as SpeechModel })}
        >
          {(state?.models ?? []).map((m) => (
            <option key={m.size} value={m.size}>
              {MODEL_NAMES[m.size]} ({m.mb} MB{m.ready ? ", geladen" : ""})
            </option>
          ))}
          {!state && <option value={value.model}>{MODEL_NAMES[value.model]}</option>}
        </Select>
      </Row>

      {settingUp ? (
        <Row>
          <div role="status" aria-live="polite" className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-3 text-[15px]">
              <span>Wird eingerichtet …</span>
              <span className="text-[13px] text-secondary tabular-nums">
                {ownTask.done} / {ownTask.total}
              </span>
            </div>
            <ProgressBar
              value={ownTask.total > 0 ? (ownTask.done + 0.5) / ownTask.total : null}
              label="Spracherkennung einrichten"
            />
            <p className="text-[13px] text-secondary">
              {ownTask.done === 0 && !state?.installed
                ? "Das Programm wird installiert – das dauert ein paar Minuten."
                : "Das Modell wird geladen …"}
            </p>
          </div>
        </Row>
      ) : ready && state ? (
        <Row>
          <div role="status" aria-live="polite" className="flex flex-col gap-1">
            <div className="flex items-center gap-2 text-[15px]">
              <CircleCheck className="size-4 text-success" strokeWidth={2} aria-hidden />
              <span>Bereit</span>
              <span className="ml-auto text-[13px] text-tertiary">
                faster-whisper {state.installed}
              </span>
            </div>
            <p className="truncate text-[13px] text-secondary">
              {state.current
                ? `Gerade: ${state.current}${state.queued ? ` · noch ${state.queued} danach` : ""}`
                : "Nichts zu tun – im Video unter „Untertitel erzeugen“ starten."}
            </p>
            {state.last_error && (
              <p className="flex items-start gap-1.5 text-[13px] text-danger">
                <CircleAlert className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden />
                {state.last_error}
              </p>
            )}
          </div>
        </Row>
      ) : (
        <Row className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-[13px] text-secondary">
            <p>
              {state?.installed ? "Dieses Modell fehlt noch." : "Noch nicht eingerichtet."} Lädt
              einmalig rund {downloadMb.toLocaleString("de-DE")} MB.
            </p>
            {ownTask?.state === "failed" && (
              <p className="mt-1 flex items-start gap-1.5 text-danger">
                <CircleAlert className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden />
                {ownTask.message}
              </p>
            )}
          </div>
          <Button
            type="button"
            size="sm"
            className="shrink-0 self-start sm:self-auto"
            loading={setup.isPending}
            disabled={!state || task?.state === "running"}
            onClick={startSetup}
          >
            {state?.installed ? "Modell laden" : "Einrichten"}
          </Button>
        </Row>
      )}

      {ready && state && (
        <>
          <Row>
            <Select
              inline
              label="Sprache"
              value={value.language}
              onChange={(e) => onChange({ language: e.target.value })}
            >
              {LANGUAGES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
              {!LANGUAGES.some(([code]) => code === value.language) && (
                <option value={value.language}>{value.language}</option>
              )}
            </Select>
          </Row>
          <Row>
            <Switch
              label="Neue eigene Videos automatisch"
              description="Nach dem Import bekommen eigene Videos ohne Untertitel welche."
              checked={value.auto_own_videos}
              onChange={(auto_own_videos) => onChange({ auto_own_videos })}
            />
          </Row>
          <Row className="flex flex-wrap items-center justify-between gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={state.missing === 0}
              loading={missing.isPending}
              onClick={() =>
                missing.mutate(undefined, {
                  onSuccess: ({ queued }) =>
                    toast(
                      queued === 1
                        ? "Ein Video kommt dran"
                        : `${queued.toLocaleString("de-DE")} Videos kommen dran`,
                    ),
                  onError: (err) => toast(err.message, "error"),
                })
              }
            >
              Eigene Videos ohne Untertitel ({state.missing.toLocaleString("de-DE")})
            </Button>
            <Button type="button" variant="danger" size="sm" onClick={() => setRemoving(true)}>
              Entfernen
            </Button>
          </Row>
        </>
      )}

      <Dialog open={removing} onClose={() => setRemoving(false)} title="Spracherkennung entfernen?">
        <p className="text-[15px] text-secondary">
          Programm und Modelle werden gelöscht und geben den Platz wieder frei. Die Untertitel, die
          schon erzeugt wurden, bleiben. Einrichten lässt es sich jederzeit wieder.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => setRemoving(false)}>
            Abbrechen
          </Button>
          <Button
            type="button"
            variant="danger"
            loading={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => {
                  setRemoving(false);
                  toast("Spracherkennung entfernt");
                },
                onError: (err) => {
                  setRemoving(false);
                  toast(err.message, "error");
                },
              })
            }
          >
            Entfernen
          </Button>
        </div>
      </Dialog>
    </Group>
  );
}
