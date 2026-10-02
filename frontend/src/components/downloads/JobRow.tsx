import { AlertCircle, Check, Clock, RotateCcw, Trash2, X } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";

import { useCancelJob, useDeleteJob, useRetryJob } from "@/api/queries";
import { IconButton } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Thumbnail } from "@/components/video/Thumbnail";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import { formatBytes, formatEta, formatRelative, formatSpeed } from "@/lib/format";
import type { Job } from "@/lib/types";

const ERROR_HINTS: Record<string, string> = {
  network: "Netzwerkfehler",
  rate_limited: "YouTube bremst gerade (Rate-Limit)",
  unavailable: "Video nicht verfügbar",
  live: "Livestream oder Premiere",
  unknown: "Fehler",
};

function statusLine(job: Job): { text: string; tone: "muted" | "accent" | "danger" | "success" } {
  switch (job.status) {
    case "running": {
      if (job.stage === "metadata") return { text: "Metadaten werden geladen …", tone: "accent" };
      if (job.stage === "postprocessing") return { text: "Wird verarbeitet …", tone: "accent" };
      const parts = [
        `${Math.round(job.progress * 100)} %`,
        job.total_bytes
          ? `${formatBytes(job.downloaded_bytes)} von ${formatBytes(job.total_bytes)}`
          : null,
        formatSpeed(job.speed),
        formatEta(job.eta),
      ].filter(Boolean);
      return { text: parts.join(" · "), tone: "accent" };
    }
    case "queued":
      if (job.next_attempt_at) {
        const reason = job.error_kind ? ERROR_HINTS[job.error_kind] : "Fehler";
        const when =
          new Date(job.next_attempt_at).getTime() <= Date.now()
            ? "gleich"
            : formatRelative(job.next_attempt_at);
        return {
          text: `${reason} – neuer Versuch ${when} (${job.attempts}/${job.max_attempts})`,
          tone: "danger",
        };
      }
      return { text: "In der Warteschlange", tone: "muted" };
    case "completed":
      return {
        text: job.error_message ?? `Fertig ${formatRelative(job.finished_at)}`,
        tone: "success",
      };
    case "failed":
      return { text: job.error_message ?? "Fehlgeschlagen", tone: "danger" };
    case "cancelled":
      return { text: "Abgebrochen", tone: "muted" };
    case "paused":
      return { text: "Pausiert", tone: "muted" };
  }
}

export function JobRow({ job }: { job: Job }) {
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const remove = useDeleteJob();
  const toast = useToast();
  const status = statusLine(job);
  const active = job.status === "running" || job.status === "queued";
  const title = job.video?.title ?? job.url;

  const run = (action: { mutateAsync: (id: number) => Promise<unknown> }) => {
    action.mutateAsync(job.id).catch((err: unknown) => {
      toast(err instanceof Error ? err.message : "Aktion fehlgeschlagen", "error");
    });
  };

  const content = (
    <>
      <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded-lg bg-surface sm:w-36">
        {job.video ? (
          <Thumbnail video={job.video} className="size-full" />
        ) : (
          <div className="flex size-full items-center justify-center text-tertiary">
            <Clock className="size-5" strokeWidth={1.5} />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-[15px] leading-snug font-medium break-all sm:break-normal">
          {title}
        </p>
        {job.video?.channel && (
          <p className="truncate text-[13px] text-secondary">{job.video.channel.name}</p>
        )}
        {job.status === "running" && (
          <ProgressBar
            className="mt-2.5"
            value={job.stage === "downloading" ? job.progress : null}
            label="Download-Fortschritt"
          />
        )}
        <p
          className={cn(
            "mt-1.5 flex items-start gap-1.5 text-[13px]",
            status.tone === "accent" && "text-secondary tabular-nums",
            status.tone === "muted" && "text-tertiary",
            status.tone === "danger" && "text-danger",
            status.tone === "success" && "text-tertiary",
          )}
        >
          {status.tone === "danger" && (
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
          )}
          {job.status === "completed" && (
            <Check className="mt-0.5 size-3.5 shrink-0 text-success" strokeWidth={2.5} />
          )}
          <span className="line-clamp-2">{status.text}</span>
        </p>
      </div>
    </>
  );

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="flex items-center gap-3 px-3 py-3 sm:gap-4 sm:px-4"
    >
      {job.status === "completed" && job.video ? (
        <Link
          to={`/videos/${job.video.id}`}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-lg sm:gap-4"
        >
          {content}
        </Link>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">{content}</div>
      )}
      <div className="flex shrink-0 items-center gap-1">
        {(job.status === "failed" ||
          job.status === "cancelled" ||
          (job.status === "queued" && job.next_attempt_at)) && (
          <IconButton label="Erneut versuchen" onClick={() => run(retry)}>
            <RotateCcw className="size-[18px]" strokeWidth={1.75} />
          </IconButton>
        )}
        {active ? (
          <IconButton label="Abbrechen" onClick={() => run(cancel)}>
            <X className="size-[18px]" strokeWidth={1.75} />
          </IconButton>
        ) : (
          <IconButton label="Aus der Liste entfernen" onClick={() => run(remove)}>
            <Trash2 className="size-[18px]" strokeWidth={1.75} />
          </IconButton>
        )}
      </div>
    </motion.li>
  );
}
