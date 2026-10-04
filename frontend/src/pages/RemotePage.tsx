import {
  CornerUpLeft,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  SkipBack,
  SkipForward,
  Tv2,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Group, Row } from "@/components/ui/Group";
import { useRemoteControl } from "@/hooks/remoteControl";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { apiUrl } from "@/lib/base";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";

/** The phone as a remote for the TV view. */
export function RemotePage() {
  useDocumentTitle("Fernbedienung");
  const remote = useRemoteControl();
  const [params, setParams] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const fromLink = params.get("code");

  // Opened from the QR code on the TV: pair right away.
  useEffect(() => {
    if (fromLink && /^\d{6}$/.test(fromLink) && remote.status === "idle") {
      remote.connect(fromLink);
      setParams({}, { replace: true });
    }
  }, [fromLink, remote, setParams]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    remote.connect(code);
  };

  return (
    <>
      <PageHeader title="Fernbedienung" />
      <div className="flex max-w-lg flex-col gap-6 pb-12">
        {remote.status !== "paired" ? (
          <form onSubmit={submit} className="flex flex-col gap-5">
            <p className="text-[15px] text-secondary">
              Öffne auf dem Fernseher die TV-Ansicht und wähle „Handy verbinden“. Dann die Kamera
              auf den QR-Code richten – oder die Zahl hier eingeben.
            </p>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              aria-label="Code vom Fernseher"
              placeholder="000000"
              className="h-16 rounded-2xl bg-elevated text-center font-mono text-[34px] tracking-[0.3em] tabular-nums outline-none placeholder:text-tertiary focus:ring-2 focus:ring-accent"
            />
            {remote.error && (
              <p role="alert" className="text-[14px] text-danger">
                {remote.error}
              </p>
            )}
            <Button
              type="submit"
              disabled={code.length !== 6}
              loading={remote.status === "connecting"}
            >
              Verbinden
            </Button>
          </form>
        ) : (
          <Controls />
        )}
      </div>
    </>
  );
}

function Controls() {
  const { tv, state, send, disconnect } = useRemoteControl();
  const playing = state?.video_id != null;
  const duration = state?.duration ?? 0;
  const [seeking, setSeeking] = useState<number | null>(null);
  const position = seeking ?? state?.position ?? 0;
  const [imageFailed, setImageFailed] = useState<number | null>(null);
  const button =
    "flex items-center justify-center rounded-full bg-surface transition-colors hover:bg-surface-hover active:scale-95 disabled:opacity-40";

  return (
    <>
      <Group
        footer={`Verbunden mit dem Fernseher (Profil ${tv}). Auf jeder Videoseite gibt es jetzt „Auf Fernseher“.`}
      >
        <Row className="flex items-center gap-3">
          <Tv2 className="size-5 text-success" strokeWidth={2} />
          <span className="flex-1 text-[15px]">Verbunden</span>
          <Button variant="secondary" size="sm" onClick={disconnect}>
            Trennen
          </Button>
        </Row>
      </Group>

      <section className="flex flex-col gap-5 rounded-3xl bg-elevated p-5">
        {playing ? (
          <>
            <div className="flex items-center gap-4">
              {state.video_id !== imageFailed && (
                <img
                  src={apiUrl(`videos/${state.video_id}/thumbnail`)}
                  alt=""
                  onError={() => setImageFailed(state.video_id ?? null)}
                  className="aspect-video w-28 shrink-0 rounded-xl bg-surface object-cover"
                />
              )}
              <div className="min-w-0">
                <p className="line-clamp-2 text-[16px] font-semibold">{state.title}</p>
                {state.channel && (
                  <p className="truncate text-[14px] text-secondary">{state.channel}</p>
                )}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <input
                type="range"
                min={0}
                max={Math.max(1, duration)}
                step={1}
                value={Math.min(position, duration)}
                aria-label="Position"
                onChange={(e) => setSeeking(Number(e.target.value))}
                onPointerUp={() => {
                  if (seeking != null) send("seek", seeking);
                  setSeeking(null);
                }}
                onKeyUp={() => {
                  if (seeking != null) send("seek", seeking);
                  setSeeking(null);
                }}
                className="w-full accent-[var(--tv-accent)]"
              />
              <div className="flex justify-between text-[12px] text-secondary tabular-nums">
                <span>{formatDuration(Math.round(position))}</span>
                <span>{formatDuration(Math.round(duration))}</span>
              </div>
            </div>
          </>
        ) : (
          <p className="text-[15px] text-secondary">
            Gerade läuft nichts. Wähle ein Video und tippe auf „Auf Fernseher“.
          </p>
        )}

        <div className="flex items-center justify-center gap-4">
          <button
            type="button"
            aria-label="Voriges Video"
            disabled={!playing}
            onClick={() => send("previous")}
            className={cn(button, "size-12")}
          >
            <SkipBack className="size-5" strokeWidth={2} />
          </button>
          <button
            type="button"
            aria-label="10 Sekunden zurück"
            disabled={!playing}
            onClick={() => send("skip", -10)}
            className={cn(button, "size-14")}
          >
            <RotateCcw className="size-6" strokeWidth={2} />
          </button>
          <button
            type="button"
            aria-label={state?.paused ? "Abspielen" : "Pause"}
            disabled={!playing}
            onClick={() => send("toggle")}
            className={cn(
              button,
              "size-[72px] bg-accent-fill text-white hover:bg-accent-fill-hover",
            )}
          >
            {state?.paused ? (
              <Play className="size-8 fill-current" strokeWidth={0} />
            ) : (
              <Pause className="size-8 fill-current" strokeWidth={0} />
            )}
          </button>
          <button
            type="button"
            aria-label="10 Sekunden vor"
            disabled={!playing}
            onClick={() => send("skip", 10)}
            className={cn(button, "size-14")}
          >
            <RotateCw className="size-6" strokeWidth={2} />
          </button>
          <button
            type="button"
            aria-label="Nächstes Video"
            disabled={!playing || !state?.has_next}
            onClick={() => send("next")}
            className={cn(button, "size-12")}
          >
            <SkipForward className="size-5" strokeWidth={2} />
          </button>
        </div>
        <button
          type="button"
          onClick={() => send("back")}
          className="mx-auto flex items-center gap-2 rounded-full px-4 py-2 text-[14px] text-secondary hover:text-primary"
        >
          <CornerUpLeft className="size-4" strokeWidth={2} />
          Zurück auf dem Fernseher
        </button>
      </section>
    </>
  );
}
