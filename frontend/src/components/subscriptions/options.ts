import type { SponsorBlockMode, Subscription, SubscriptionSettings } from "@/lib/types";

export const INTERVALS: { value: number; label: string }[] = [
  { value: 15, label: "Alle 15 Minuten" },
  { value: 30, label: "Alle 30 Minuten" },
  { value: 60, label: "Stündlich" },
  { value: 180, label: "Alle 3 Stunden" },
  { value: 360, label: "Alle 6 Stunden" },
  { value: 720, label: "Alle 12 Stunden" },
  { value: 1440, label: "Täglich" },
  { value: 10080, label: "Wöchentlich" },
];

export const BACKFILL: { value: string; label: string }[] = [
  { value: "0", label: "Keine – nur neue Videos" },
  { value: "5", label: "Die neuesten 5" },
  { value: "25", label: "Die neuesten 25" },
  { value: "100", label: "Die neuesten 100" },
  { value: "all", label: "Alle" },
];

export const KEEP_DAYS: { value: string; label: string }[] = [
  { value: "", label: "Nie" },
  { value: "7", label: "Älter als 7 Tage" },
  { value: "14", label: "Älter als 14 Tage" },
  { value: "30", label: "Älter als 30 Tage" },
  { value: "60", label: "Älter als 60 Tage" },
  { value: "90", label: "Älter als 90 Tage" },
  { value: "180", label: "Älter als 6 Monate" },
  { value: "365", label: "Älter als 1 Jahr" },
];

export const SPONSORBLOCK: { value: "" | SponsorBlockMode; label: string }[] = [
  { value: "", label: "Standard (Einstellungen)" },
  { value: "off", label: "Aus" },
  { value: "skip", label: "Beim Abspielen überspringen" },
  { value: "cut", label: "Beim Download herausschneiden" },
];

export const WEEKDAYS: { value: number; short: string; label: string }[] = [
  { value: 0, short: "Mo", label: "Montag" },
  { value: 1, short: "Di", label: "Dienstag" },
  { value: 2, short: "Mi", label: "Mittwoch" },
  { value: 3, short: "Do", label: "Donnerstag" },
  { value: 4, short: "Fr", label: "Freitag" },
  { value: 5, short: "Sa", label: "Samstag" },
  { value: 6, short: "So", label: "Sonntag" },
];

export interface FormValues {
  enabled: boolean;
  interval: string;
  /** Checked on chosen weekdays at a set time instead of the interval. */
  scheduled: boolean;
  days: number[];
  time: string;
  backfill: string;
  includeShorts: boolean;
  includeLive: boolean;
  minMinutes: string;
  maxMinutes: string;
  dateAfter: string;
  maxHeight: string;
  container: "default" | "mp4" | "mkv";
  preferH264: "default" | "yes" | "no";
  sponsorblock: "" | SponsorBlockMode;
  comments: "default" | "yes" | "no";
  keepDays: string;
  keepLast: string;
}

export const DEFAULT_VALUES: FormValues = {
  enabled: true,
  interval: "360",
  scheduled: false,
  days: [],
  time: "18:00",
  backfill: "5",
  includeShorts: false,
  includeLive: false,
  minMinutes: "",
  maxMinutes: "",
  dateAfter: "",
  maxHeight: "",
  container: "default",
  preferH264: "default",
  sponsorblock: "",
  comments: "default",
  keepDays: "",
  keepLast: "",
};

const minutesToSeconds = (value: string) => {
  const minutes = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(minutes) && minutes > 0 ? Math.round(minutes * 60) : null;
};
const positiveInt = (value: string) => {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number > 0 ? number : null;
};
const secondsToMinutes = (value: number | null) =>
  value ? String(Math.round((value / 60) * 10) / 10) : "";

export function toSettings(values: FormValues): SubscriptionSettings {
  const options: SubscriptionSettings["download_options"] = {};
  if (values.maxHeight) options.max_height = Number(values.maxHeight) as 2160;
  if (values.container !== "default") options.container = values.container;
  if (values.preferH264 !== "default") options.prefer_h264 = values.preferH264 === "yes";
  if (values.sponsorblock) options.sponsorblock_mode = values.sponsorblock;
  if (values.comments !== "default") options.comments = values.comments === "yes";
  return {
    enabled: values.enabled,
    check_interval_minutes: Number(values.interval),
    check_days: values.scheduled ? [...values.days].sort((a, b) => a - b) : null,
    check_time: values.scheduled ? values.time : null,
    include_shorts: values.includeShorts,
    include_live: values.includeLive,
    min_duration_s: minutesToSeconds(values.minMinutes),
    max_duration_s: minutesToSeconds(values.maxMinutes),
    date_after: values.dateAfter || null,
    keep_days: positiveInt(values.keepDays),
    keep_last: positiveInt(values.keepLast),
    download_options: options,
  };
}

export function fromSubscription(sub: Subscription): FormValues {
  const options = sub.download_options;
  return {
    enabled: sub.enabled,
    interval: String(sub.check_interval_minutes),
    scheduled: Boolean(sub.check_days?.length),
    days: sub.check_days ?? [],
    time: sub.check_time ?? DEFAULT_VALUES.time,
    backfill: sub.backfill == null ? "all" : String(sub.backfill),
    includeShorts: sub.include_shorts,
    includeLive: sub.include_live,
    minMinutes: secondsToMinutes(sub.min_duration_s),
    maxMinutes: secondsToMinutes(sub.max_duration_s),
    dateAfter: sub.date_after ?? "",
    maxHeight: options.max_height ? String(options.max_height) : "",
    container: options.container ?? "default",
    preferH264: options.prefer_h264 == null ? "default" : options.prefer_h264 ? "yes" : "no",
    sponsorblock: options.sponsorblock_mode ?? "",
    comments: options.comments == null ? "default" : options.comments ? "yes" : "no",
    keepDays: sub.keep_days ? String(sub.keep_days) : "",
    keepLast: sub.keep_last ? String(sub.keep_last) : "",
  };
}

export function backfillValue(values: FormValues): number | null {
  return values.backfill === "all" ? null : Number(values.backfill);
}

/** Why the schedule can't be saved yet, if it can't. */
export function scheduleProblem(values: FormValues): string | null {
  if (!values.scheduled) return null;
  if (values.days.length === 0) return "Wähle mindestens einen Tag.";
  if (!/^\d{2}:\d{2}$/.test(values.time)) return "Wähle eine Uhrzeit.";
  return null;
}

/** "Mo, Mi und Fr um 18:00", "Täglich um 6:30". */
export function scheduleLabel(days: number[], time: string): string {
  const sorted = [...days].sort((a, b) => a - b);
  const clock = time.replace(/^0(\d)/, "$1");
  if (sorted.length === 7) return `Täglich um ${clock}`;
  const names = sorted.map((d) => WEEKDAYS[d]?.short ?? "");
  const list =
    names.length > 1 ? `${names.slice(0, -1).join(", ")} und ${names[names.length - 1]}` : names[0];
  return `${list} um ${clock}`;
}
