import { twMerge } from "tailwind-merge";

/** Joins class names, skipping falsy values; later Tailwind utilities override earlier ones. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return twMerge(classes.filter(Boolean).join(" "));
}
