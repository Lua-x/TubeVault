const numberFormat = new Intl.NumberFormat("de-DE");
const dateFormat = new Intl.DateTimeFormat("de-DE", {
  day: "numeric",
  month: "long",
  year: "numeric",
});
const relativeFormat = new Intl.RelativeTimeFormat("de-DE", { numeric: "auto" });

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || Number.isNaN(totalSeconds)) return "";
  const seconds = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  const digits = value >= 100 || unit === 0 ? 0 : 1;
  return `${value.toLocaleString("de-DE", { maximumFractionDigits: digits })} ${units[unit]}`;
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  return bytesPerSecond ? `${formatBytes(bytesPerSecond)}/s` : "";
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null) return "";
  if (seconds < 60) return `noch ${Math.max(1, Math.round(seconds))} s`;
  if (seconds < 3600) return `noch ${Math.round(seconds / 60)} min`;
  return `noch ${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return dateFormat.format(new Date(iso.length === 10 ? `${iso}T12:00:00` : iso));
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  const diff = (date.getTime() - now) / 1000;
  const abs = Math.abs(diff);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (abs >= size) return relativeFormat.format(Math.round(diff / size), unit);
  }
  return "gerade eben";
}

export function formatCount(value: number | null | undefined): string {
  return value == null ? "" : numberFormat.format(value);
}

export function formatResolution(height: number | null | undefined): string {
  if (!height) return "";
  if (height >= 2160) return "4K";
  if (height >= 1440) return "1440p";
  return `${height}p`;
}

export function codecLabel(codec: string | null | undefined): string {
  if (!codec || codec === "none") return "";
  const c = codec.toLowerCase();
  if (c.startsWith("avc")) return "H.264";
  if (c.startsWith("hev") || c.startsWith("hvc")) return "H.265";
  if (c.startsWith("vp09") || c.startsWith("vp9")) return "VP9";
  if (c.startsWith("av01")) return "AV1";
  if (c.startsWith("mp4a")) return "AAC";
  if (c.startsWith("opus")) return "Opus";
  return codec;
}
