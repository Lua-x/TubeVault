import { Play } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";

import { formatDuration, formatRelative } from "@/lib/format";
import type { VideoSummary } from "@/lib/types";

import { thumbnailUrl } from "@/lib/media";

import { Thumbnail } from "./Thumbnail";

/**
 * Big feature card with a blurred backdrop taken from the thumbnail: the newest video on the
 * start page, a recommendation in the library (`label`).
 */
export function Hero({ video, label }: { video: VideoSummary; label?: string }) {
  const resume =
    video.progress && !video.progress.watched && video.progress.position_s >= 10
      ? video.progress.position_s
      : null;
  const meta = [
    video.channel?.name,
    formatRelative(video.upload_date),
    formatDuration(video.duration_s),
  ].filter(Boolean);

  return (
    <motion.section
      initial={{ opacity: 0, scale: 0.985 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="relative mb-12 overflow-hidden rounded-3xl border border-separator"
      aria-label={label ?? "Neuestes Video"}
    >
      {video.has_thumbnail && (
        <div
          aria-hidden
          className="absolute inset-0 scale-125 bg-cover bg-center opacity-60 blur-3xl saturate-150"
          style={{ backgroundImage: `url("${thumbnailUrl(video)}")` }}
        />
      )}
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-r from-canvas/90 via-canvas/60 to-canvas/20"
      />

      <div className="relative grid items-center gap-6 p-5 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-10 lg:p-10">
        <div className="order-2 min-w-0 lg:order-1">
          <p className="text-[13px] font-semibold tracking-wide text-accent uppercase">
            {label ?? (resume != null ? "Weiterschauen" : "Neu")}
          </p>
          <h2 className="mt-2 line-clamp-3 text-[26px] leading-tight font-bold tracking-tight sm:text-[34px]">
            {video.title}
          </h2>
          {meta.length > 0 && <p className="mt-3 text-[15px] text-secondary">{meta.join(" · ")}</p>}
          <Link
            to={`/videos/${video.id}`}
            className="mt-6 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-6 text-[15px] font-semibold text-canvas transition-transform duration-200 ease-out-soft hover:scale-[1.03] active:scale-[0.98]"
          >
            <Play className="size-4 fill-current" strokeWidth={0} />
            {resume != null ? `Fortsetzen bei ${formatDuration(resume)}` : "Abspielen"}
          </Link>
          {resume != null && video.duration_s ? (
            <div className="mt-4 h-1 w-48 overflow-hidden rounded-full bg-primary/20">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(resume / video.duration_s, 1) * 100}%` }}
              />
            </div>
          ) : null}
        </div>
        <Link
          to={`/videos/${video.id}`}
          tabIndex={-1}
          aria-hidden
          className="order-1 block overflow-hidden rounded-2xl shadow-card lg:order-2"
        >
          <Thumbnail video={video} eager size="large" className="aspect-video w-full" />
        </Link>
      </div>
    </motion.section>
  );
}
