import type { VideoSummary } from "./types";

const PLAYED_KEY = "tubevault.played";
const REMEMBERED = 100;

/** Notes a video as played in this tab and returns the list – shuffle avoids repeating them. */
export function rememberPlayed(id: number): number[] {
  let played: number[] = [];
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(PLAYED_KEY) ?? "[]");
    if (Array.isArray(stored)) played = stored.filter((v): v is number => typeof v === "number");
  } catch {
    // unreadable: start over
  }
  const list = [id, ...played.filter((p) => p !== id)].slice(0, REMEMBERED);
  try {
    sessionStorage.setItem(PLAYED_KEY, JSON.stringify(list));
  } catch {
    // private mode: shuffle may repeat a video sooner, nothing more
  }
  return list;
}

/** Shuffle: a video not played yet, the unwatched ones first. */
export function shuffleFrom(
  videos: VideoSummary[],
  played: number[],
  random: () => number = Math.random,
): VideoSummary | null {
  const fresh = videos.filter((v) => !played.includes(v.id));
  const unwatched = fresh.filter((v) => !v.progress?.watched);
  const pool = unwatched.length > 0 ? unwatched : fresh;
  return pool[Math.floor(random() * pool.length)] ?? null;
}

/** In order: the first video not played yet, preferably one not watched. */
export function nextInOrder(videos: VideoSummary[], played: number[]): VideoSummary | null {
  const fresh = videos.filter((v) => !played.includes(v.id));
  return fresh.find((v) => !v.progress?.watched) ?? fresh[0] ?? null;
}
