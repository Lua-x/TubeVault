/**
 * Files saved on this device, for watching without the server.
 *
 * Videos go into the browser's private file system (OPFS), written while they
 * download – a 1 GB video never has to fit into memory. Where OPFS can't be written
 * as a stream (older Safari), Cache Storage takes its place. Both live in the
 * browser's storage for this site: deleting site data deletes them too.
 */

import { basePath } from "@/lib/base";

export interface OfflineBackend {
  readonly kind: "opfs" | "cache";
  /** Writes a stream to `path`; returns the number of bytes. */
  write(
    path: string,
    body: ReadableStream<Uint8Array>,
    type: string,
    onBytes: (bytes: number) => void,
    signal: AbortSignal,
  ): Promise<number>;
  read(path: string): Promise<Blob | null>;
  /** Removes `path` and everything below it. */
  remove(path: string): Promise<void>;
}

const ROOT = "tubevault";
const CACHE = "tubevault-offline";

function parts(path: string): string[] {
  return path.split("/").filter(Boolean);
}

class OpfsBackend implements OfflineBackend {
  readonly kind = "opfs";

  private async dir(names: string[], create: boolean): Promise<FileSystemDirectoryHandle> {
    let dir = await (
      await navigator.storage.getDirectory()
    ).getDirectoryHandle(ROOT, {
      create: true,
    });
    for (const name of names) dir = await dir.getDirectoryHandle(name, { create });
    return dir;
  }

  async write(
    path: string,
    body: ReadableStream<Uint8Array>,
    _type: string,
    onBytes: (bytes: number) => void,
    signal: AbortSignal,
  ): Promise<number> {
    const names = parts(path);
    const file = names.pop() ?? "file";
    const dir = await this.dir(names, true);
    const handle = await dir.getFileHandle(file, { create: true });
    const writable = await handle.createWritable();
    const reader = body.getReader();
    let total = 0;
    try {
      for (;;) {
        if (signal.aborted) throw new DOMException("Abgebrochen", "AbortError");
        const { done, value } = await reader.read();
        if (done) break;
        await writable.write(value as Uint8Array<ArrayBuffer>);
        total += value.byteLength;
        onBytes(total);
      }
      await writable.close();
      return total;
    } catch (error) {
      await writable.abort().catch(() => undefined);
      throw error;
    }
  }

  async read(path: string): Promise<Blob | null> {
    const names = parts(path);
    const file = names.pop() ?? "file";
    try {
      const dir = await this.dir(names, false);
      return await (await dir.getFileHandle(file)).getFile();
    } catch {
      return null;
    }
  }

  async remove(path: string): Promise<void> {
    const names = parts(path);
    const last = names.pop();
    if (!last) return;
    try {
      const dir = await this.dir(names, false);
      await dir.removeEntry(last, { recursive: true });
    } catch {
      // already gone
    }
  }
}

class CacheBackend implements OfflineBackend {
  readonly kind = "cache";

  private key(path: string): string {
    return new URL(`${basePath()}__offline__/${parts(path).join("/")}`, window.location.origin)
      .href;
  }

  async write(
    path: string,
    body: ReadableStream<Uint8Array>,
    type: string,
    onBytes: (bytes: number) => void,
    signal: AbortSignal,
  ): Promise<number> {
    let total = 0;
    const counted = body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          if (signal.aborted) {
            controller.error(new DOMException("Abgebrochen", "AbortError"));
            return;
          }
          total += chunk.byteLength;
          onBytes(total);
          controller.enqueue(chunk);
        },
      }),
    );
    const cache = await caches.open(CACHE);
    await cache.put(this.key(path), new Response(counted, { headers: { "Content-Type": type } }));
    return total;
  }

  async read(path: string): Promise<Blob | null> {
    const response = await (await caches.open(CACHE)).match(this.key(path));
    return response ? response.blob() : null;
  }

  async remove(path: string): Promise<void> {
    const cache = await caches.open(CACHE);
    const prefix = this.key(path);
    for (const request of await cache.keys()) {
      if (request.url === prefix || request.url.startsWith(`${prefix}/`)) {
        await cache.delete(request);
      }
    }
  }
}

function opfsWritable(): boolean {
  return (
    typeof navigator !== "undefined" &&
    typeof navigator.storage?.getDirectory === "function" &&
    typeof FileSystemFileHandle !== "undefined" &&
    "createWritable" in FileSystemFileHandle.prototype
  );
}

let backend: OfflineBackend | null | undefined;

/** The storage to use, or null when this browser can't keep videos. */
export function offlineBackend(): OfflineBackend | null {
  if (backend !== undefined) return backend;
  let forced: string | null;
  try {
    forced = localStorage.getItem("tubevault.offline.backend");
  } catch {
    forced = null;
  }
  if (forced !== "cache" && opfsWritable()) backend = new OpfsBackend();
  else if (typeof caches !== "undefined") backend = new CacheBackend();
  else backend = null;
  return backend;
}

export async function readText(store: OfflineBackend, path: string): Promise<string | null> {
  const blob = await store.read(path);
  return blob ? blob.text() : null;
}

export async function writeText(store: OfflineBackend, path: string, text: string): Promise<void> {
  const body = new Blob([text], { type: "application/json" }).stream();
  await store.write(path, body, "application/json", () => undefined, new AbortController().signal);
}
