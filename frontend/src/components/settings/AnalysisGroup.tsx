import { useAnalysisState } from "@/api/queries";
import { Group, Row } from "@/components/ui/Group";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Switch } from "@/components/ui/Switch";
import type { AppSettings } from "@/lib/types";

type Options = AppSettings["analysis"];

interface AnalysisGroupProps {
  value: Options;
  onChange: (patch: Partial<Options>) => void;
}

/** Seek previews and loudness, measured once per video in the background. */
export function AnalysisGroup({ value, onChange }: AnalysisGroupProps) {
  const { data: state } = useAnalysisState(value.trickplay || value.loudness);
  const parts = [
    value.trickplay ? (state?.trickplay_done ?? 0) : null,
    value.loudness ? (state?.loudness_done ?? 0) : null,
  ].filter((n): n is number => n !== null);
  const done = parts.length ? Math.min(...parts) : 0;
  const total = state?.total ?? 0;

  return (
    <Group
      title="Medienanalyse"
      footer="Läuft im Hintergrund mit niedrigster Priorität, ein Video nach dem anderen – Abspielen und Downloads gehen immer vor. Für eine Stunde Video braucht es meist nur Sekunden."
    >
      <Row>
        <Switch
          label="Vorschaubilder beim Spulen"
          description="Kleine Bilder über der Zeitleiste, wie bei YouTube. Etwa 1–2 MB pro Stunde Video."
          checked={value.trickplay}
          onChange={(trickplay) => onChange({ trickplay })}
        />
      </Row>
      <Row>
        <Switch
          label="Lautheit messen"
          description="Damit der Player laute und leise Videos angleichen kann (einstellbar unter Wiedergabe)."
          checked={value.loudness}
          onChange={(loudness) => onChange({ loudness })}
        />
      </Row>
      {state && parts.length > 0 && total > 0 && (
        <Row className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3 text-[13px]">
            <span className="min-w-0 truncate text-secondary">
              {done >= total
                ? "Alle Videos sind analysiert."
                : state.current
                  ? `Gerade: ${state.current}`
                  : "Wartet auf die nächste Runde …"}
            </span>
            <span className="shrink-0 text-tertiary tabular-nums">
              {done.toLocaleString("de-DE")} von {total.toLocaleString("de-DE")}
            </span>
          </div>
          {done < total && <ProgressBar value={done / total} label="Fortschritt der Analyse" />}
        </Row>
      )}
    </Group>
  );
}
