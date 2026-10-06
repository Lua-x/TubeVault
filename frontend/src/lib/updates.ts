/**
 * After a server update an open tab (or the installed app) still runs the old version until
 * it is reloaded – with old screens and old behaviour. When the app comes back into view,
 * look whether the server has a newer build and load it, unless something is playing.
 */
const CHECK_EVERY = 5 * 60_000;
const ENTRY = /assets\/(index-[\w-]+\.js)/;

function loadedEntry(): string | null {
  const script = document.querySelector<HTMLScriptElement>('script[type="module"][src*="assets/"]');
  return script ? (ENTRY.exec(script.src)?.[1] ?? null) : null;
}

function playing(): boolean {
  return Array.from(document.querySelectorAll<HTMLMediaElement>("video, audio")).some(
    (media) => !media.paused,
  );
}

export function reloadOnUpdate(): void {
  const loaded = loadedEntry();
  if (!loaded) return;
  let checked = Date.now();
  let outdated = false;

  const check = async () => {
    if (document.visibilityState !== "visible") return;
    if (!outdated) {
      if (Date.now() - checked < CHECK_EVERY) return;
      checked = Date.now();
      try {
        // A query string keeps the service worker's cached app shell out of the way.
        const url = new URL("./", document.baseURI);
        url.searchParams.set("v", String(checked));
        const html = await (await fetch(url, { cache: "no-store" })).text();
        const latest = ENTRY.exec(html)?.[1];
        outdated = latest !== undefined && latest !== loaded;
      } catch {
        return; // server not reachable: try again next time
      }
    }
    // Don't cut off a video or podcast – the next time the app comes back is soon enough.
    if (outdated && !playing()) window.location.reload();
  };
  document.addEventListener("visibilitychange", () => void check());
}
