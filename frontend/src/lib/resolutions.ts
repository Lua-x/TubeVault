import type { MaxHeight } from "@/lib/types";

/** Download resolutions, named like Pinchflat's profiles. A video without the chosen one
 *  comes in the next smaller resolution it has. */
export const RESOLUTIONS: { value: MaxHeight; label: string }[] = [
  { value: 2160, label: "2160p (4K)" },
  { value: 1440, label: "1440p" },
  { value: 1080, label: "1080p (Full HD)" },
  { value: 720, label: "720p" },
  { value: 480, label: "480p" },
  { value: 360, label: "360p" },
];

export const BEST_RESOLUTION = "Beste verfügbare";

export const RESOLUTION_HINT =
  "Hat ein Video die gewählte Auflösung nicht, nimmt TubeVault die nächstkleinere.";

export function resolutionLabel(height: MaxHeight | null | undefined): string {
  if (height == null) return BEST_RESOLUTION;
  return RESOLUTIONS.find((r) => r.value === height)?.label ?? `${height}p`;
}

/** Options for a select where "" follows the settings, e.g. "Standard (2160p (4K))". */
export function resolutionChoices(
  standard: MaxHeight | null | undefined,
): { value: string; label: string }[] {
  const current = standard === undefined ? "Standard" : `Standard (${resolutionLabel(standard)})`;
  return [
    { value: "", label: current },
    ...RESOLUTIONS.map((r) => ({ value: String(r.value), label: r.label })),
  ];
}
