import { AnimatePresence, motion } from "motion/react";
import { Check, Settings2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import type { QualityChoice } from "@/lib/playback";

export interface QualityOption {
  value: QualityChoice;
  label: string;
  hint?: string;
}

interface QualityMenuProps {
  options: QualityOption[];
  value: QualityChoice;
  onChange: (value: QualityChoice) => void;
}

/** Quality picker for the top right corner of the player; fades out with the controls. */
export function QualityMenu({ options, value, onChange }: QualityMenuProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  return (
    <div ref={root} className={cn("relative", !open && "tv-autohide")}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 items-center gap-1.5 rounded-full bg-[rgb(28_28_30/0.6)] px-3 text-[13px] font-medium text-white backdrop-blur-xl backdrop-saturate-150 transition-colors duration-200 hover:bg-[rgb(44_44_46/0.8)]"
      >
        <Settings2 className="size-4" strokeWidth={2} />
        {value === "auto" ? "Auto" : `${value}p`}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute top-10 right-0 w-60 origin-top-right rounded-2xl bg-[rgb(28_28_30/0.85)] p-1.5 text-white shadow-[0_12px_32px_rgb(0_0_0/0.4)] backdrop-blur-xl backdrop-saturate-150"
          >
            <p className="px-3 pt-1.5 pb-1 text-[11px] font-semibold tracking-wide text-white/55 uppercase">
              Qualität
            </p>
            {options.map((option) => {
              const active = option.value === value;
              return (
                <button
                  key={String(option.value)}
                  type="button"
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left transition-colors duration-150 hover:bg-white/10"
                >
                  <span className="flex size-4 shrink-0 items-center justify-center">
                    {active && <Check className="size-4 text-[#0a84ff]" strokeWidth={2.5} />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[14px] font-medium">{option.label}</span>
                    {option.hint && (
                      <span className="block text-[12px] text-white/55">{option.hint}</span>
                    )}
                  </span>
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface PlaybackStatusProps {
  preparing: number | null;
  error: string | null;
  onRetry: () => void;
}

/** Shown in the middle of the player while a file is prepared or when playback failed. */
export function PlaybackStatus({ preparing, error, onRetry }: PlaybackStatusProps) {
  if (preparing == null && !error) return null;
  return (
    <div
      role={error ? "alert" : "status"}
      className="absolute top-1/2 left-1/2 w-[min(320px,calc(100%-32px))] -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-[rgb(28_28_30/0.78)] p-4 text-center text-white shadow-[0_12px_32px_rgb(0_0_0/0.4)] backdrop-blur-xl backdrop-saturate-150"
    >
      {error ? (
        <>
          <p className="text-[15px] font-semibold">Wiedergabe nicht möglich</p>
          <p className="mt-1 line-clamp-4 text-[13px] break-words text-white/70">{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex h-8 items-center rounded-full bg-white px-4 text-[13px] font-semibold text-black transition-opacity duration-200 hover:opacity-90"
          >
            Erneut versuchen
          </button>
        </>
      ) : (
        <>
          <p className="text-[14px] font-medium">Wird für dieses Gerät vorbereitet …</p>
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/20">
            <div
              className="h-full rounded-full bg-white transition-[width] duration-500"
              style={{ width: `${Math.round((preparing ?? 0) * 100)}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
}
