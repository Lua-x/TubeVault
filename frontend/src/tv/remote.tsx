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
import { useNavigate } from "react-router";

import { websocketUrl } from "@/lib/base";

/**
 * The TV side of the phone remote: keeps a socket open while the TV view is shown,
 * offers a pairing code and turns commands from phones into actions here.
 */

export interface RemoteCommand {
  action: "toggle" | "play" | "pause" | "seek" | "skip" | "next" | "previous" | "open" | "back";
  value: number | null;
  from: string;
}

export interface TvState {
  video_id?: number;
  title?: string;
  channel?: string;
  position?: number;
  duration?: number;
  paused?: boolean;
  has_next?: boolean;
  has_previous?: boolean;
}

interface RemoteReceiver {
  code: string | null;
  phones: { id: string; name: string }[];
  /** What is playing now – sent on to the phones. */
  publish: (state: TvState) => void;
  subscribe: (handler: (command: RemoteCommand) => void) => () => void;
  newCode: () => void;
  unpair: () => void;
}

const ReceiverContext = createContext<RemoteReceiver | null>(null);

export function RemoteReceiverProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [code, setCode] = useState<string | null>(null);
  const [phones, setPhones] = useState<{ id: string; name: string }[]>([]);
  const socket = useRef<WebSocket | null>(null);
  const handlers = useRef(new Set<(command: RemoteCommand) => void>());
  const lastState = useRef<TvState>({});
  // navigate() changes with every page – the socket must not follow it.
  const navigateRef = useRef(navigate);
  useEffect(() => {
    navigateRef.current = navigate;
  });

  useEffect(() => {
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      const ws = new WebSocket(websocketUrl("remote/tv"));
      socket.current = ws;
      ws.onopen = () => {
        retry = 0;
        ws.send(JSON.stringify({ type: "state", ...lastState.current }));
      };
      ws.onmessage = (event) => {
        let message: { type?: string } & Record<string, unknown>;
        try {
          message = JSON.parse(String(event.data)) as typeof message;
        } catch {
          return;
        }
        if (message.type === "code") setCode(String(message.code));
        else if (message.type === "phones") {
          setPhones((message.phones as { id: string; name: string }[]) ?? []);
        } else if (message.type === "command") {
          const command = message as unknown as RemoteCommand;
          if (command.action === "open" && command.value) {
            // From the pairing screen, "back" should lead home, not to the code again.
            const replace = window.location.pathname.endsWith("/tv/remote");
            navigateRef.current(`/tv/play/${command.value}`, { replace });
            return;
          }
          if (handlers.current.size === 0 && command.action === "back") navigateRef.current("/tv");
          for (const handler of handlers.current) handler(command);
        }
      };
      ws.onclose = (event) => {
        setCode(null);
        setPhones([]);
        if (closed || event.code === 4401) return;
        retry += 1;
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** Math.min(retry, 5)));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket.current?.close();
    };
  }, []);

  const send = useCallback((message: object) => {
    const ws = socket.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
  }, []);

  const value = useMemo<RemoteReceiver>(
    () => ({
      code,
      phones,
      publish: (state) => {
        lastState.current = state;
        send({ type: "state", ...state });
      },
      subscribe: (handler) => {
        handlers.current.add(handler);
        return () => handlers.current.delete(handler);
      },
      newCode: () => send({ type: "new_code" }),
      unpair: () => send({ type: "unpair" }),
    }),
    [code, phones, send],
  );

  return <ReceiverContext.Provider value={value}>{children}</ReceiverContext.Provider>;
}

export function useRemoteReceiver(): RemoteReceiver | null {
  return useContext(ReceiverContext);
}

/** Commands for the view that is shown right now (the player). */
export function useRemoteCommands(handler: (command: RemoteCommand) => void) {
  const receiver = useRemoteReceiver();
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => receiver?.subscribe((command) => latest.current(command)), [receiver]);
}
