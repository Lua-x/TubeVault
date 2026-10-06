import { AnimatePresence, motion } from "motion/react";
import { Check, Moon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { SLEEP_MINUTES } from "@/audio/context";
import { cn } from "@/lib/cn";
import { remainingLabel, setVideoSleep, useVideoSleep } from "@/lib/sleepTimer";

/** Sleep timer in the corner of the player – reachable in full screen too. */
export function SleepMenu() {
  const sleep = useVideoSleep();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sleep?.kind !== "minutes") return;
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0); // right away after choosing, then every second
    const timer = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [sleep]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const label =
    sleep?.kind === "minutes"
      ? remainingLabel(sleep.until, now)
      : sleep?.kind === "end"
        ? "Videoende"
        : null;
  const choose = (value: number | "end" | null) => {
    setVideoSleep(value);
    setOpen(false);
  };
  const option = (key: string, text: string, active: boolean, value: number | "end" | null) => (
    <button
      key={key}
      type="button"
      role="menuitemradio"
      aria-checked={active}
      onClick={() => choose(value)}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[14px] font-medium transition-colors duration-150 hover:bg-white/10"
    >
      <span className="flex size-4 shrink-0 items-center justify-center">
        {active && <Check className="size-4 text-[#0a84ff]" strokeWidth={2.5} />}
      </span>
      {text}
    </button>
  );

  return (
    <div ref={root} className={cn("relative", !open && !sleep && "tv-autohide")}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label ? `Schlaf-Timer: ${label}` : "Schlaf-Timer"}
        title="Schlaf-Timer"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium backdrop-blur-xl backdrop-saturate-150 transition-colors duration-200",
          sleep
            ? "bg-[#0a84ff]/85 text-white hover:bg-[#0a84ff]"
            : "bg-[rgb(28_28_30/0.6)] text-white hover:bg-[rgb(44_44_46/0.8)]",
        )}
      >
        <Moon className="size-4" strokeWidth={2} />
        {label && <span className="tabular-nums">{label}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label="Schlaf-Timer"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute top-10 right-0 z-10 w-52 origin-top-right rounded-2xl bg-[rgb(28_28_30/0.85)] p-1.5 text-white shadow-[0_12px_32px_rgb(0_0_0/0.4)] backdrop-blur-xl backdrop-saturate-150"
          >
            <p className="px-3 pt-1.5 pb-1 text-[11px] font-semibold tracking-wide text-white/55 uppercase">
              Schlaf-Timer
            </p>
            {option("off", "Aus", !sleep, null)}
            {SLEEP_MINUTES.map((minutes) =>
              option(String(minutes), `${minutes} Minuten`, false, minutes),
            )}
            {option("end", "Ende des Videos", sleep?.kind === "end", "end")}
            <p className="px-3 pt-1 pb-1.5 text-[12px] text-white/55">
              Blendet den Ton aus und hält an – auch mitten in einer Playlist.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
