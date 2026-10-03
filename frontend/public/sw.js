/* TubeVault service worker.
 *
 * Makes the app installable and starts it instantly – also without the server: the
 * app shell and all hashed build assets are cached. The API, streams and thumbnails are
 * never cached here; videos saved with "Aufs Gerät" live in their own storage.
 *
 * __BUILD_ID__ is replaced at build time, so every release gets a fresh cache.
 */
const BUILD_ID = "__BUILD_ID__";
const CACHE = `tubevault-${BUILD_ID}`;
const SCOPE = new URL(self.registration.scope);
const SHELL = new URL("./", SCOPE).href;
// The build fills in every hashed asset (JS chunks, CSS), so the whole app – the
// player included – works offline from the first visit on.
const ASSETS = [] /* __ASSETS__ */;
const PRECACHE = [
  SHELL,
  "manifest.webmanifest",
  "favicon.svg",
  "icon-192.png",
  "apple-touch-icon.png",
  ...ASSETS,
].map((path) => new URL(path, SCOPE).href);
const API_PREFIX = new URL("api/", SCOPE).pathname;
const ASSETS_PREFIX = new URL("assets/", SCOPE).pathname;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("tubevault-") && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

async function networkFirstShell(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(SHELL, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(SHELL);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== SCOPE.origin || !url.pathname.startsWith(SCOPE.pathname)) return;
  if (url.pathname.startsWith(API_PREFIX)) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstShell(request));
  } else if (url.pathname.startsWith(ASSETS_PREFIX) || PRECACHE.includes(url.href)) {
    event.respondWith(cacheFirst(request));
  }
});
