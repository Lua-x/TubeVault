/**
 * Watch progress made while the server was out of reach. Kept in localStorage and
 * handed to the server the next time it answers.
 */

const KEY = "tubevault.offline.progress";

export interface LocalProgress {
  position_s: number;
  duration_s: number;
  updated_at: number;
}

export function loadLocalProgress(): Record<string, LocalProgress> {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "{}") as unknown;
    return value && typeof value === "object" ? (value as Record<string, LocalProgress>) : {};
  } catch {
    return {};
  }
}

function store(all: Record<string, LocalProgress>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // storage full or blocked: progress just isn't remembered
  }
}

export function saveLocalProgress(videoId: number, position_s: number, duration_s: number): void {
  store({ ...loadLocalProgress(), [videoId]: { position_s, duration_s, updated_at: Date.now() } });
}

export function forgetLocalProgress(videoId: number): void {
  const all = loadLocalProgress();
  delete all[videoId];
  store(all);
}
