import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { websocketUrl } from "@/lib/base";
import type { RemoteCommand, TvState } from "@/tv/remote";

/** The phone side of the remote: one pairing for the whole app, kept while browsing. */

type Status = "idle" | "connecting" | "paired";

interface RemoteControl {
  status: Status;
  /** Account the TV is signed in with. */
  tv: string | null;
  state: TvState | null;
  error: string | null;
  connect: (code: string) => void;
  disconnect: () => void;
  send: (action: RemoteCommand["action"], value?: number) => void;
}

const RemoteControlContext = createContext<RemoteControl | null>(null);
// Survives a reload of the page (not a new tab): back to the same TV without a code.
const TOKEN_KEY = "tubevault.remote.token";

function storedToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function storeToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // not remembered
  }
}

export function RemoteControlProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>(() => (storedToken() ? "connecting" : "idle"));
  const [tv, setTv] = useState<string | null>(null);
  const [state, setState] = useState<TvState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const retries = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const disconnect = useCallback(() => {
    const ws = socket.current;
    socket.current = null;
    clearTimeout(retryTimer.current);
    storeToken(null);
    ws?.close();
    setStatus("idle");
    setTv(null);
    setState(null);
  }, []);

  // Only wires the socket up; state changes happen in its callbacks.
  const attach = useCallback((query: string, quiet: boolean) => {
    const run = (query: string, quiet: boolean) => {
      socket.current?.close();
      const ws = new WebSocket(websocketUrl(`remote/phone?${query}`));
      socket.current = ws;
      let reason: string | null = null;
      ws.onmessage = (event) => {
        let message: { type?: string } & Record<string, unknown>;
        try {
          message = JSON.parse(String(event.data)) as typeof message;
        } catch {
          return;
        }
        if (message.type === "paired") {
          retries.current = 0;
          setStatus("paired");
          setTv(String(message.tv ?? ""));
          if (typeof message.token === "string") storeToken(message.token);
        } else if (message.type === "state") {
          setState(message as TvState);
        } else if (message.type === "closed") {
          reason = String(message.reason ?? "");
        }
      };
      ws.onclose = () => {
        if (socket.current !== ws) return; // replaced or ended on purpose
        socket.current = null;
        const token = storedToken();
        // The connection dropped (Wi-Fi, server restart) while paired: try again shortly.
        if (reason === null && token && retries.current < 5) {
          retries.current += 1;
          setStatus("connecting");
          retryTimer.current = setTimeout(
            () => run(`token=${encodeURIComponent(token)}`, true),
            1000 * retries.current,
          );
          return;
        }
        setStatus("idle");
        setTv(null);
        setState(null);
        // Only the server ending it (or a dead token) forgets the pairing – not a reload.
        storeToken(null);
        if (!quiet) setError(reason || "Die Verbindung zum Fernseher ist abgebrochen.");
      };
    };
    run(query, quiet);
  }, []);

  const connect = useCallback(
    (code: string) => {
      setError(null);
      setStatus("connecting");
      attach(`code=${encodeURIComponent(code)}`, false);
    },
    [attach],
  );

  // After a reload: rejoin the TV this phone was paired with.
  useEffect(() => {
    const token = storedToken();
    if (token) attach(`token=${encodeURIComponent(token)}`, true);
    return () => {
      clearTimeout(retryTimer.current);
      const ws = socket.current;
      socket.current = null; // leaving the page is not a reason to forget the TV
      ws?.close();
    };
  }, [attach]);

  const send = useCallback((action: RemoteCommand["action"], value?: number) => {
    const ws = socket.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", action, value: value ?? null }));
    }
  }, []);

  const value = useMemo<RemoteControl>(
    () => ({ status, tv, state, error, connect, disconnect, send }),
    [status, tv, state, error, connect, disconnect, send],
  );
  return <RemoteControlContext.Provider value={value}>{children}</RemoteControlContext.Provider>;
}

export function useRemoteControl(): RemoteControl {
  const value = useContext(RemoteControlContext);
  if (!value) throw new Error("useRemoteControl must be used inside <RemoteControlProvider>");
  return value;
}
