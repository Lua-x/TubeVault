import { AnimatePresence, motion } from "motion/react";
import { Play, SkipForward, X } from "lucide-react";

import { Thumbnail } from "@/components/video/Thumbnail";
import type { VideoSummary } from "@/lib/types";

export interface PlayerNotice {
  id: number;
  message: string;
  action?: { label: string; run: () => void };
  /** Stays until playback starts, then disappears like the others. */
  untilPlay?: boolean;
}

export interface UpNext {
  video: VideoSummary;
  remaining: number;
}

interface PlayerOverlayProps {
  notice: PlayerNotice | null;
  onDismissNotice: () => void;
  skipLabel: string | null;
  onSkip: () => void;
  upNext: UpNext | null;
  onPlayNext: () => void;
  onCancelNext: () => void;
}

const pill =
  "flex items-center gap-1 rounded-full bg-[rgb(28_28_30/0.72)] text-[13px] font-medium text-white shadow-[0_8px_24px_rgb(0_0_0/0.3)] backdrop-blur-xl backdrop-saturate-150";

const spring = { type: "spring", stiffness: 420, damping: 34 } as const;

/** Notices and buttons drawn on top of the video; lives inside the player element. */
export function PlayerOverlay({
  notice,
  onDismissNotice,
  skipLabel,
  onSkip,
  upNext,
  onPlayNext,
  onCancelNext,
}: PlayerOverlayProps) {
  return (
    <>
      <AnimatePresence>
        {notice && (
          <motion.div
            key={notice.id}
            role="status"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={spring}
            className={`${pill} absolute top-3 left-3 py-1 pr-1 pl-3.5 sm:top-4 sm:left-4`}
          >
            <span className="py-1">{notice.message}</span>
            {notice.action ? (
              <button
                type="button"
                onClick={() => {
                  notice.action?.run();
                  onDismissNotice();
                }}
                className="ml-1 rounded-full bg-white/15 px-3 py-1 font-semibold transition-colors duration-200 hover:bg-white/25"
              >
                {notice.action.label}
              </button>
            ) : (
              <span className="pr-2.5" />
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {skipLabel && !upNext && (
          <motion.button
            type="button"
            onClick={onSkip}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 12 }}
            transition={spring}
            className={`${pill} absolute right-3 bottom-[62px] gap-2 px-4 py-2 transition-colors duration-200 hover:bg-[rgb(44_44_46/0.85)] sm:right-4 sm:bottom-[72px]`}
          >
            {skipLabel}
            <SkipForward className="size-4" strokeWidth={2} />
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {upNext && (
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={spring}
            className="absolute right-3 bottom-[62px] flex w-[min(340px,calc(100%-24px))] gap-3 rounded-2xl bg-[rgb(28_28_30/0.78)] p-2.5 text-white shadow-[0_12px_32px_rgb(0_0_0/0.4)] backdrop-blur-xl backdrop-saturate-150 sm:right-4 sm:bottom-[72px]"
          >
            <Thumbnail
              video={upNext.video}
              className="aspect-video w-24 shrink-0 self-start rounded-lg max-sm:hidden"
            />
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="text-[11px] font-semibold tracking-wide text-white/60 uppercase">
                Als Nächstes in {upNext.remaining} s
              </p>
              <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug font-medium">
                {upNext.video.title}
              </p>
              <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
                <button
                  type="button"
                  onClick={onPlayNext}
                  className="inline-flex h-7 items-center gap-1 rounded-full bg-white px-2.5 text-[12px] font-semibold text-black transition-opacity duration-200 hover:opacity-90"
                >
                  <Play className="size-3.5 fill-current" strokeWidth={2} />
                  Abspielen
                </button>
                <button
                  type="button"
                  onClick={onCancelNext}
                  className="inline-flex h-7 items-center gap-1 rounded-full bg-white/15 px-2.5 text-[12px] font-semibold transition-colors duration-200 hover:bg-white/25"
                >
                  <X className="size-3.5" strokeWidth={2} />
                  Abbrechen
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
