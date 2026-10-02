import type { SponsorBlockMode, SponsorCategory } from "./types";

export const SPONSOR_CATEGORIES: { value: SponsorCategory; label: string; hint: string }[] = [
  { value: "sponsor", label: "Sponsor", hint: "Bezahlte Werbung" },
  { value: "selfpromo", label: "Eigenwerbung", hint: "Merch, Patreon, eigene Kanäle" },
  { value: "interaction", label: "Abo-Erinnerung", hint: "„Abonnieren und liken“" },
  { value: "intro", label: "Intro", hint: "Vorspann ohne Inhalt" },
  { value: "outro", label: "Abspann", hint: "Endcards und Credits" },
  { value: "preview", label: "Vorschau", hint: "Rückblick oder Ausblick" },
  { value: "filler", label: "Abschweifung", hint: "Nicht zum Thema gehörend" },
  { value: "music_offtopic", label: "Nicht-Musik", hint: "In Musikvideos" },
];

export const SPONSORBLOCK_MODES: { value: SponsorBlockMode; label: string }[] = [
  { value: "off", label: "Aus" },
  { value: "skip", label: "Überspringen" },
  { value: "cut", label: "Herausschneiden" },
];

export function categoryLabel(category: SponsorCategory): string {
  return SPONSOR_CATEGORIES.find((c) => c.value === category)?.label ?? "Abschnitt";
}
