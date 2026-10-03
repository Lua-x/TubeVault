import { Headphones, Pause, Play, RotateCw, X } from "lucide-react";

import { useAudioPlayer } from "@/audio/context";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";

import { NowPlaying } from "./NowPlaying";

/** The bar that keeps playing while you browse – tap it for the full player. */
export function MiniPlayer({ aboveTabBar = false }: { aboveTabBar?: boolean }) {
  const player = useAudioPlayer();
  const { track } = player;
  if (!track) return null;
  const progress = player.duration > 0 ? Math.min(1, player.position / player.duration) : 0;

  return (
    <>
      <div
        className={cn(
          "fixed inset-x-2 z-30 md:right-6 md:left-[calc(15rem+1.5rem)] md:mx-auto md:max-w-2xl",
          aboveTabBar
            ? "bottom-[calc(53px+env(safe-area-inset-bottom)+0.5rem)] md:bottom-5"
            : "bottom-[calc(env(safe-area-inset-bottom)+0.75rem)] md:left-6",
        )}
      >
        <div className="glass relative flex items-center gap-3 overflow-hidden rounded-2xl border border-separator p-2 pr-3 shadow-card">
          <button
            type="button"
            onClick={() => player.setExpanded(true)}
            className="flex min-w-0 flex-1 items-center gap-3 text-left"
            aria-label="Wiedergabe öffnen"
          >
            <span className="relative flex aspect-video w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface">
              {track.artwork ? (
                <img src={track.artwork} alt="" className="size-full object-cover" />
              ) : (
                <Headphones className="size-5 text-tertiary" strokeWidth={1.75} />
              )}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[14px] font-medium">{track.title}</span>
              <span className="block truncate text-[12px] text-secondary">
                {player.error ?? track.channel ?? "TubeVault"}
              </span>
            </span>
          </button>
          <button
            type="button"
            onClick={player.toggle}
            aria-label={player.playing ? "Pause" : "Abspielen"}
            className="flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-surface"
          >
            {player.preparing && player.playing ? (
              <Spinner className="size-5" />
            ) : player.playing ? (
              <Pause className="size-5 fill-current" strokeWidth={0} />
            ) : (
              <Play className="size-5 fill-current" strokeWidth={0} />
            )}
          </button>
          <button
            type="button"
            onClick={() => player.skip(15)}
            aria-label="15 Sekunden vor"
            className="hidden size-10 shrink-0 items-center justify-center rounded-full hover:bg-surface sm:flex"
          >
            <RotateCw className="size-5" strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={player.close}
            aria-label="Wiedergabe beenden"
            className="flex size-9 shrink-0 items-center justify-center rounded-full text-secondary hover:bg-surface"
          >
            <X className="size-4" strokeWidth={2} />
          </button>
          <span className="absolute inset-x-0 bottom-0 h-0.5 bg-separator">
            <span className="block h-full bg-accent" style={{ width: `${progress * 100}%` }} />
          </span>
        </div>
      </div>
      <NowPlaying />
    </>
  );
}
