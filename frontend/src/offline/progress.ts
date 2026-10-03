/**
 * Who saved what, and the watch progress made while the server was out of reach.
 *
 * Everything on the device belongs to one TubeVault user: a kids profile on a shared
 * tablet doesn't see what the parents saved. Progress is kept in localStorage and
 * handed to the server, for that user, the next time it answers.
 */

const OWNER_KEY = "tubevault.offline.user";

export interface LocalProgress {
  position_s: number;
  duration_s: number;
  updated_at: number;
}

/** The user signed in last – whose videos the app shows when the server is away. */
export function lastOwner(): number | null {
  try {
    const value = Number(localStorage.getItem(OWNER_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function rememberOwner(userId: number): void {
  try {
    localStorage.setItem(OWNER_KEY, String(userId));
  } catch {
    // blocked: without the server, the device page just stays empty
  }
}

/** After signing out, nobody's videos show up without the server. */
export function forgetOwner(): void {
  try {
    localStorage.removeItem(OWNER_KEY);
  } catch {
    // nothing to forget
  }
}

const progressKey = (owner: number) => `tubevault.offline.progress.u${owner}`;

export function loadLocalProgress(owner: number | null): Record<string, LocalProgress> {
  if (owner === null) return {};
  try {
    const value = JSON.parse(localStorage.getItem(progressKey(owner)) ?? "{}") as unknown;
    return value && typeof value === "object" ? (value as Record<string, LocalProgress>) : {};
  } catch {
    return {};
  }
}

function store(owner: number, all: Record<string, LocalProgress>): void {
  try {
    localStorage.setItem(progressKey(owner), JSON.stringify(all));
  } catch {
    // storage full or blocked: progress just isn't remembered
  }
}

export function saveLocalProgress(
  owner: number | null,
  videoId: number,
  position_s: number,
  duration_s: number,
): void {
  if (owner === null) return;
  store(owner, {
    ...loadLocalProgress(owner),
    [videoId]: { position_s, duration_s, updated_at: Date.now() },
  });
}

export function forgetLocalProgress(owner: number | null, videoId: number): void {
  if (owner === null) return;
  const all = loadLocalProgress(owner);
  delete all[videoId];
  store(owner, all);
}
