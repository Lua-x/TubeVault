import { apiUrl } from "./base";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  }
  if (status === 0) return "Keine Verbindung zum Server.";
  return `Unerwarteter Fehler (${status}).`;
}

type Unauthorized = () => void;
let onUnauthorized: Unauthorized | null = null;

/** Called whenever the server answers 401, e.g. after the session expired. */
export function setUnauthorizedHandler(handler: Unauthorized | null): void {
  onUnauthorized = handler;
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  { quiet401 = false }: { quiet401?: boolean } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "TubeVault",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, errorMessage(null, 0));
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !quiet401) onUnauthorized?.();
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T = void>(path: string) => request<T>("DELETE", path),
};
