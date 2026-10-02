import { formatRelative } from "@/lib/format";
import type { ItemState, Subscription } from "@/lib/types";

export const ITEM_STATE_LABEL: Record<ItemState, string> = {
  queued: "In der Warteschlange",
  downloaded: "Heruntergeladen",
  filtered: "Gefiltert",
  skipped: "Übersprungen",
  failed: "Fehlgeschlagen",
  removed: "Entfernt",
};

export function checkStatus(sub: Subscription): {
  text: string;
  tone: "muted" | "danger" | "accent";
} {
  if (sub.checking) return { text: "Wird geprüft …", tone: "accent" };
  if (sub.last_check_error) return { text: sub.last_check_error, tone: "danger" };
  if (!sub.enabled) return { text: "Pausiert", tone: "muted" };
  if (!sub.last_checked_at) return { text: "Erste Prüfung steht an", tone: "muted" };
  const next =
    sub.next_check_at && new Date(sub.next_check_at).getTime() > Date.now()
      ? ` · nächste ${formatRelative(sub.next_check_at)}`
      : "";
  return { text: `Geprüft ${formatRelative(sub.last_checked_at)}${next}`, tone: "muted" };
}
