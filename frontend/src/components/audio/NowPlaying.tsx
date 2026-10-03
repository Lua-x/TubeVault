import {
  ChevronDown,
  Headphones,
  Moon,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  SkipBack,
  SkipForward,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { RATES, SLEEP_MINUTES, useAudioPlayer } from "@/audio/context";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

const rateLabel = (rate: number) => `${String(rate).replace(".", ",")}×`;

/** The full player: artwork, scrubbing, speed, sleep timer and what comes next. */
export function NowPlaying() {
  const player = useAudioPlayer();
  const { track, expanded, setExpanded } = player;
  const now = useNow(expanded && player.sleep?.kind === "minutes");

  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, setExpanded]);

  const duration = player.duration || track?.duration || 0;
  const remaining = Math.max(0, duration - player.position);
  const sleepLabel =
    player.sleep?.kind === "end"
      ? "Ende des Videos"
      : player.sleep?.kind === "minutes"
        ? `Noch ${Math.max(1, Math.round((player.sleep.until - now) / 60_000))} Min.`
        : "Schlaf-Timer";
  const upcoming = player.queue.slice(player.index + 1);
  const nextRate = RATES[(RATES.indexOf(player.rate) + 1) % RATES.length] ?? 1;

  return (
    <AnimatePresence>
      {expanded && track && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Wird abgespielt"
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", damping: 32, stiffness: 320 }}
          className="fixed inset-0 z-50 overflow-y-auto bg-canvas"
        >
          {track.artwork && (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 scale-125 bg-cover bg-center opacity-30 blur-3xl"
              style={{ backgroundImage: `url("${track.artwork}")` }}
            />
          )}
          <div className="relative mx-auto flex min-h-full max-w-xl flex-col px-6 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1.5rem,env(safe-area-inset-bottom))]">
            <div className="flex items-center justify-between py-2">
              <button
                type="button"
                onClick={() => setExpanded(false)}
                aria-label="Schließen"
                className="-ml-2 flex size-10 items-center justify-center rounded-full hover:bg-surface"
              >
                <ChevronDown className="size-6" strokeWidth={2} />
              </button>
              <p className="text-[13px] font-medium text-secondary">Wird abgespielt</p>
              <Link
                to={track.src ? `/device/${track.id}` : `/videos/${track.id}`}
                onClick={() => setExpanded(false)}
                className="text-[14px] font-medium text-accent"
              >
                Video
              </Link>
            </div>

            <div className="mt-6 flex aspect-video w-full items-center justify-center overflow-hidden rounded-2xl bg-surface shadow-card">
              {track.artwork ? (
                <img src={track.artwork} alt="" className="size-full object-cover" />
              ) : (
                <Headphones className="size-12 text-tertiary" strokeWidth={1.25} />
              )}
            </div>

            <div className="mt-8">
              <h2 className="line-clamp-2 text-[22px] leading-tight font-bold tracking-tight">
                {track.title}
              </h2>
              <p className="mt-1 text-[16px] text-secondary">{track.channel}</p>
              {player.error && <p className="mt-2 text-[14px] text-danger">{player.error}</p>}
            </div>

            <div className="mt-6">
              <input
                type="range"
                min={0}
                max={duration || 1}
                step={1}
                value={Math.min(player.position, duration || 1)}
                onChange={(e) => player.seek(Number(e.target.value))}
                aria-label="Position"
                className="w-full accent-[var(--tv-accent)]"
              />
              <div className="mt-1 flex justify-between text-[12px] text-secondary tabular-nums">
                <span>{formatDuration(player.position) || "0:00"}</span>
                <span>−{formatDuration(remaining) || "0:00"}</span>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <button
                type="button"
                onClick={player.previous}
                aria-label="Zurück"
                className="flex size-12 items-center justify-center rounded-full hover:bg-surface"
              >
                <SkipBack className="size-6 fill-current" strokeWidth={1.5} />
              </button>
              <button
                type="button"
                onClick={() => player.skip(-15)}
                aria-label="15 Sekunden zurück"
                className="flex size-12 items-center justify-center rounded-full hover:bg-surface"
              >
                <RotateCcw className="size-7" strokeWidth={1.75} />
              </button>
              <button
                type="button"
                onClick={player.toggle}
                aria-label={player.playing ? "Pause" : "Abspielen"}
                className="flex size-[72px] items-center justify-center rounded-full bg-primary text-canvas transition-transform active:scale-95"
              >
                {player.preparing && player.playing ? (
                  <Spinner className="size-7" />
                ) : player.playing ? (
                  <Pause className="size-8 fill-current" strokeWidth={0} />
                ) : (
                  <Play className="ml-1 size-8 fill-current" strokeWidth={0} />
                )}
              </button>
              <button
                type="button"
                onClick={() => player.skip(15)}
                aria-label="15 Sekunden vor"
                className="flex size-12 items-center justify-center rounded-full hover:bg-surface"
              >
                <RotateCw className="size-7" strokeWidth={1.75} />
              </button>
              <button
                type="button"
                onClick={player.next}
                disabled={upcoming.length === 0}
                aria-label="Weiter"
                className="flex size-12 items-center justify-center rounded-full hover:bg-surface disabled:opacity-30"
              >
                <SkipForward className="size-6 fill-current" strokeWidth={1.5} />
              </button>
            </div>

            <div className="mt-8 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => player.setRate(nextRate)}
                aria-label={`Geschwindigkeit ${rateLabel(player.rate)} – tippen für ${rateLabel(nextRate)}`}
                className={cn(
                  "h-9 min-w-16 rounded-full px-4 text-[14px] font-semibold tabular-nums",
                  player.rate !== 1 ? "bg-primary text-canvas" : "bg-surface",
                )}
              >
                {rateLabel(player.rate)}
              </button>
              <label
                className={cn(
                  "relative inline-flex h-9 items-center gap-2 rounded-full px-4 text-[14px] font-medium",
                  player.sleep ? "bg-primary text-canvas" : "bg-surface",
                )}
              >
                <Moon className="size-4" strokeWidth={2} aria-hidden />
                <span aria-hidden>{sleepLabel}</span>
                <select
                  aria-label="Schlaf-Timer"
                  value={player.sleep?.kind === "end" ? "end" : player.sleep ? "running" : "off"}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value === "running") return;
                    player.setSleep(
                      value === "off" ? null : value === "end" ? "end" : Number(value),
                    );
                  }}
                  className="absolute inset-0 cursor-pointer opacity-0"
                >
                  <option value="off">Aus</option>
                  {player.sleep?.kind === "minutes" && (
                    <option value="running">{sleepLabel}</option>
                  )}
                  {SLEEP_MINUTES.map((minutes) => (
                    <option key={minutes} value={minutes}>
                      In {minutes} Minuten
                    </option>
                  ))}
                  <option value="end">Am Ende des Videos</option>
                </select>
              </label>
            </div>

            {upcoming.length > 0 && (
              <section aria-labelledby="up-next-heading" className="mt-10">
                <h3 id="up-next-heading" className="mb-2 text-[15px] font-semibold">
                  Als Nächstes
                </h3>
                <ul className="flex flex-col">
                  {upcoming.slice(0, 20).map((item, offset) => (
                    <li key={`${item.id}-${offset}`}>
                      <button
                        type="button"
                        onClick={() => player.play(player.queue, player.index + 1 + offset)}
                        className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface/60"
                      >
                        <span className="aspect-video w-16 shrink-0 overflow-hidden rounded-md bg-surface">
                          {item.artwork && (
                            <img src={item.artwork} alt="" className="size-full object-cover" />
                          )}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-[14px]">{item.title}</span>
                          <span className="block truncate text-[12px] text-secondary">
                            {[item.channel, formatDuration(item.duration)]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
