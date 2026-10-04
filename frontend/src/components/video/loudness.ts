/**
 * Evens out loud and quiet videos: the server measured each video's loudness (EBU R128),
 * the player turns it towards the level YouTube uses. A limiter keeps raised quiet videos
 * from clipping.
 *
 * Sound only goes through Web Audio once the audio context really runs – a suspended
 * context would leave the video silent. iPhones and iPads are left alone: iOS doesn't let
 * pages change a video's volume, and routing their sound has its own pitfalls.
 */

const TARGET_LUFS = -14;
const MAX_BOOST_DB = 6;
const MAX_CUT_DB = 12;

let context: AudioContext | null = null;
const routes = new WeakMap<HTMLMediaElement, GainNode>();

function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
}

export function gainFor(lufs: number): number {
  const db = Math.min(MAX_BOOST_DB, Math.max(-MAX_CUT_DB, TARGET_LUFS - lufs));
  return 10 ** (db / 20);
}

/** Sets the level for this element; call it from a "play" event (a user gesture). */
export async function evenOut(media: HTMLMediaElement, lufs: number | null, enabled: boolean) {
  const gain = enabled && lufs != null ? gainFor(lufs) : 1;
  const route = routes.get(media);
  if (route) {
    route.gain.value = gain;
    return;
  }
  // Nothing to change – and once routed, an element stays routed. So only when needed.
  if (Math.abs(gain - 1) < 0.06 || isIos() || typeof AudioContext === "undefined") return;
  try {
    context ??= new AudioContext();
    if (context.state !== "running") {
      await Promise.race([context.resume(), new Promise((resolve) => setTimeout(resolve, 500))]);
    }
    if (context.state !== "running" || routes.has(media)) return;
    const source = context.createMediaElementSource(media);
    const node = context.createGain();
    node.gain.value = gain;
    const limiter = context.createDynamicsCompressor();
    limiter.threshold.value = -1;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.25;
    source.connect(node).connect(limiter).connect(context.destination);
    routes.set(media, node);
  } catch {
    // Not possible here (old browser, element already taken): the volume stays as it is.
  }
}

/** Adjusts an element that is already routed, e.g. after the setting changed. */
export function updateLevel(media: HTMLMediaElement, lufs: number | null, enabled: boolean) {
  const route = routes.get(media);
  if (route) route.gain.value = enabled && lufs != null ? gainFor(lufs) : 1;
}
