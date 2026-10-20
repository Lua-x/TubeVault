import { Shuffle } from "lucide-react";

import { Switch } from "@/components/ui/Switch";
import { useAuth } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { Preferences } from "@/lib/types";

/** Autoplay and shuffle, right where the next video comes from; saved for the account. */
export function AutoplayControls() {
  const { user, updatePreferences } = useAuth();
  const toast = useToast();
  const preferences = user?.preferences ?? {};
  const shuffle = preferences.shuffle === true;
  const update = (patch: Preferences) =>
    void updatePreferences(patch).catch((err: unknown) =>
      toast(err instanceof Error ? err.message : "Speichern fehlgeschlagen", "error"),
    );

  return (
    <div className="flex items-center gap-3 rounded-2xl bg-elevated py-2 pr-2 pl-4">
      <div className="flex-1">
        <Switch
          label="Autoplay"
          checked={preferences.autoplay_next !== false}
          onChange={(autoplay_next) => update({ autoplay_next })}
        />
      </div>
      <button
        type="button"
        aria-pressed={shuffle}
        aria-label="Zufällige Reihenfolge"
        title="Zufällige Reihenfolge"
        onClick={() => update({ shuffle: !shuffle })}
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full transition-colors duration-200",
          shuffle
            ? "bg-accent/15 text-accent"
            : "text-secondary hover:bg-surface hover:text-primary",
        )}
      >
        <Shuffle className="size-[18px]" strokeWidth={2} />
      </button>
    </div>
  );
}
