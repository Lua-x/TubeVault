import { useCallback, useEffect, useRef, useState } from "react";

import { websocketUrl } from "@/lib/base";

/**
 * Watching together: follows what the others do (play, pause, seek) and tells them what
 * happens here. Echoes of our own changes are held back for a moment, and the server's
 * regular tick pulls a drifting player back.
 */

export interface PartyMember {
  id: string;
  user_id: number;
  name: string;
  role: "host" | "guest";
}

interface PartyMessage {
  type: string;
  action?: "play" | "pause" | "seek";
  paused?: boolean;
  position?: number;
  by?: string;
  you?: string;
  video_id?: number;
  members?: PartyMember[];
  reason?: string;
}

// Off by more than this while playing: pulled back to the room's position.
const DRIFT_S = 1.5;
// After someone else seeked, or when joining.
const EXACT_S = 0.3;
// A local event this close to the room's state is our own adjustment coming back.
const ECHO_S = 0.75;

export function useParty(roomId: string, media: () => HTMLVideoElement | null) {
  const [status, setStatus] = useState<"connecting" | "joined" | "closed">("connecting");
  const [videoId, setVideoId] = useState<number | null>(null);
  const [members, setMembers] = useState<PartyMember[]>([]);
  const [you, setYou] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<{ action: string; by: string } | null>(null);
  // The viewer joined with a tap – only then may the player start on its own.
  const [ready, setReady] = useState(false);
  const readyRef = useRef(false);
  const socket = useRef<WebSocket | null>(null);
  const room = useRef<{ paused: boolean; position: number; at: number }>({
    paused: true,
    position: 0,
    at: 0, // set by the first message from the room
  });

  const expected = () => {
    const state = room.current;
    return state.paused ? state.position : state.position + (Date.now() - state.at) / 1000;
  };

  /** Brings the player here to the room's state; `tolerance`: how far off is fine. */
  const apply = useCallback(
    (tolerance: number) => {
      const el = media();
      if (!el || !readyRef.current) return;
      const target = expected();
      if (Math.abs(el.currentTime - target) > tolerance) el.currentTime = target;
      if (room.current.paused && !el.paused) el.pause();
      if (!room.current.paused && el.paused) void el.play().catch(() => undefined);
    },
    [media],
  );

  useEffect(() => {
    const ws = new WebSocket(websocketUrl(`party/${encodeURIComponent(roomId)}`));
    socket.current = ws;
    let closedReason: string | null = null;
    ws.onmessage = (event) => {
      let message: PartyMessage;
      try {
        message = JSON.parse(String(event.data)) as PartyMessage;
      } catch {
        return;
      }
      const remember = () => {
        room.current = {
          paused: message.paused ?? true,
          position: message.position ?? 0,
          at: Date.now(),
        };
      };
      if (message.type === "joined") {
        remember();
        setYou(message.you ?? null);
        setVideoId(message.video_id ?? null);
        setStatus("joined");
      } else if (message.type === "presence") {
        setMembers(message.members ?? []);
      } else if (message.type === "sync") {
        remember();
        setLastAction({ action: message.action ?? "", by: message.by ?? "" });
        apply(EXACT_S);
      } else if (message.type === "tick") {
        remember();
        apply(DRIFT_S);
      } else if (message.type === "closed") {
        closedReason = message.reason ?? null;
      }
    };
    ws.onclose = () => {
      setStatus("closed");
      setError(closedReason ?? "Die Verbindung zum Raum ist abgebrochen.");
    };
    return () => {
      socket.current = null;
      ws.close();
    };
  }, [roomId, apply]);

  /** Something happened here (the viewer pressed play, pause or seeked). */
  const report = useCallback((action: "play" | "pause" | "seek", position: number) => {
    // What already matches the room is the echo of our own adjustment – nothing to tell.
    const state = room.current;
    const near = Math.abs(position - expected()) < ECHO_S;
    if (action === "play" && !state.paused && near) return;
    if (action === "pause" && state.paused && near) return;
    if (action === "seek" && near) return;
    const paused = action === "pause" || (action === "seek" && room.current.paused);
    room.current = { paused, position, at: Date.now() };
    const ws = socket.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "sync", action, position }));
    }
  }, []);

  const join = useCallback(() => {
    readyRef.current = true;
    setReady(true);
    apply(EXACT_S);
  }, [apply]);

  return { status, videoId, members, you, error, lastAction, ready, join, report };
}
