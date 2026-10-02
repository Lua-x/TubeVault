/** Base path of the app, e.g. "/" or "/tubevault/". The server injects it as <base href>. */
export function basePath(): string {
  const href = document.querySelector("base")?.getAttribute("href") ?? "/";
  return href.endsWith("/") ? href : `${href}/`;
}

/** URL of an API endpoint below the base path: apiUrl("videos/1") → "/tubevault/api/videos/1". */
export function apiUrl(path: string): string {
  return `${basePath()}api/${path.replace(/^\//, "")}`;
}

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${apiUrl(path)}`;
}
