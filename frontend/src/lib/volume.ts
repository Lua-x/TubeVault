/** The player's volume, kept on this device (a phone and a TV want different ones). */
const VOLUME_KEY = "tubevault.volume";

export interface StoredVolume {
  volume: number;
  muted: boolean;
}

export function storedVolume(): StoredVolume | null {
  try {
    const value = JSON.parse(localStorage.getItem(VOLUME_KEY) ?? "null") as unknown;
    if (typeof value !== "object" || value === null) return null;
    const { volume, muted } = value as Partial<StoredVolume>;
    if (typeof volume !== "number" || !(volume >= 0 && volume <= 1)) return null;
    return { volume, muted: muted === true };
  } catch {
    return null;
  }
}

export function storeVolume(volume: number, muted: boolean): void {
  try {
    const rounded = Math.round(Math.min(1, Math.max(0, volume)) * 100) / 100;
    localStorage.setItem(VOLUME_KEY, JSON.stringify({ volume: rounded, muted }));
  } catch {
    // Private mode: the volume just isn't remembered.
  }
}
