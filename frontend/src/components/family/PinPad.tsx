import { Delete } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"] as const;

interface PinPadProps {
  /** Shown above the dots, e.g. the profile's name. */
  title: string;
  error: string | null;
  busy: boolean;
  onSubmit: (pin: string) => void;
  onCancel: () => void;
  /** Big keys for the TV, reachable with the arrow keys of a remote. */
  tv?: boolean;
}

/** PIN entry: digit keys on screen, the number keys of a keyboard or remote work too. */
export function PinPad({ title, error, busy, onSubmit, onCancel, tv }: PinPadProps) {
  const [pin, setPin] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (/^[0-9]$/.test(event.key)) {
        event.preventDefault();
        setPin((value) => (value.length < 8 ? value + event.key : value));
      } else if (event.key === "Backspace" && !tv) {
        event.preventDefault();
        setPin((value) => value.slice(0, -1));
      } else if (event.key === "Escape") {
        onCancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, tv]);

  const press = (key: (typeof KEYS)[number]) => {
    if (key === "del") setPin((value) => value.slice(0, -1));
    else if (key) setPin((value) => (value.length < 8 ? value + key : value));
  };
  const keyClass = tv
    ? "size-[max(4.5rem,5.5vw)] text-[max(24px,2vw)] focus:bg-primary focus:text-canvas"
    : "size-16 text-[22px] hover:bg-surface-hover";

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Takes the place of "Wer schaut?" – the page's heading. */}
      <h1 className={cn("font-semibold", tv ? "text-[max(24px,2vw)]" : "text-[19px]")}>{title}</h1>
      <div className="flex h-4 items-center gap-3" aria-live="polite">
        <span className="sr-only">{pin.length} Ziffern eingegeben</span>
        {Array.from({ length: Math.max(4, pin.length) }, (_, i) => (
          <span
            key={i}
            className={cn(
              "size-3.5 rounded-full border-2 border-primary transition-colors",
              i < pin.length && "bg-primary",
            )}
          />
        ))}
      </div>
      <p role="alert" className="min-h-5 text-[14px] text-danger">
        {error}
      </p>
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((key, i) =>
          key === "" ? (
            <span key={i} />
          ) : (
            <button
              key={i}
              type="button"
              data-tv-focus={tv ? "" : undefined}
              data-tv-key={tv ? `pin-${key}` : undefined}
              aria-label={key === "del" ? "Letzte Ziffer löschen" : key}
              onClick={() => press(key)}
              className={cn(
                "flex items-center justify-center rounded-full bg-surface font-medium tabular-nums outline-none transition-colors",
                keyClass,
              )}
            >
              {key === "del" ? <Delete className="size-6" strokeWidth={1.75} /> : key}
            </button>
          ),
        )}
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          data-tv-focus={tv ? "" : undefined}
          data-tv-key={tv ? "pin-cancel" : undefined}
          onClick={onCancel}
          className={cn(
            "h-11 rounded-full bg-surface px-6 text-[15px] font-medium outline-none hover:bg-surface-hover",
            tv
              ? "focus:ring-4 focus:ring-primary"
              : "focus-visible:ring-2 focus-visible:ring-accent",
          )}
        >
          Abbrechen
        </button>
        <button
          type="button"
          data-tv-focus={tv ? "" : undefined}
          data-tv-key={tv ? "pin-ok" : undefined}
          disabled={pin.length < 4 || busy}
          onClick={() => {
            onSubmit(pin);
            setPin("");
          }}
          className={cn(
            "h-11 rounded-full bg-accent-fill px-8 text-[15px] font-medium text-white outline-none hover:bg-accent-fill-hover disabled:opacity-40",
            tv
              ? "focus:ring-4 focus:ring-primary"
              : "focus-visible:ring-2 focus-visible:ring-accent",
          )}
        >
          OK
        </button>
      </div>
    </div>
  );
}
