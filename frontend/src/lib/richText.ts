/** Splits description and comment text into plain text, links and timestamps. */

export type Token =
  | { kind: "text"; text: string }
  | { kind: "link"; text: string }
  | { kind: "time"; text: string; seconds: number };

const URL_PATTERN = /(https?:\/\/[^\s<]+[^\s<.,:;"')\]!?])/g;
// 1:05, 12:34, 1:02:03 – not part of a longer number like 2024:01:02 or 1:2345.
const TIME_PATTERN = /(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])/g;

function timestamps(text: string, duration: number | null): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  for (const match of text.matchAll(TIME_PATTERN)) {
    const [whole, hours, minutes, seconds] = match;
    const index = match.index;
    const m = Number(minutes);
    const s = Number(seconds);
    if (s > 59 || (hours !== undefined && m > 59)) continue;
    const total = Number(hours ?? 0) * 3600 + m * 60 + s;
    // A time of day ("um 14:30") is only a timestamp when the video is that long.
    if (duration != null && total > duration) continue;
    if (index > last) tokens.push({ kind: "text", text: text.slice(last, index) });
    tokens.push({ kind: "time", text: whole, seconds: total });
    last = index + whole.length;
  }
  if (last < text.length) tokens.push({ kind: "text", text: text.slice(last) });
  return tokens;
}

export function tokenize(text: string, duration: number | null = null): Token[] {
  const tokens: Token[] = [];
  text.split(URL_PATTERN).forEach((part, index) => {
    if (!part) return;
    if (index % 2 === 1) tokens.push({ kind: "link", text: part });
    else tokens.push(...timestamps(part, duration));
  });
  return tokens;
}
