import { ArrowLeft, Download, ExternalLink, Trash2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useDeleteVideo, useVideo } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { VideoPlayer, type PlayerHandle } from "@/components/video/VideoPlayer";
import { useAuth } from "@/hooks/auth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useToast } from "@/hooks/toast";
import { apiUrl } from "@/lib/base";
import { cn } from "@/lib/cn";
import {
  codecLabel,
  formatBytes,
  formatCount,
  formatDate,
  formatDuration,
  formatResolution,
} from "@/lib/format";
import type { VideoDetail } from "@/lib/types";

export function VideoPage() {
  const { id } = useParams();
  const videoId = Number(id);
  const { data: video, isLoading, error } = useVideo(videoId);
  useDocumentTitle(video?.title);

  if (isLoading) return <PageSpinner />;
  if (error || !video) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Video nicht gefunden"
      >
        <Link to="/" className="text-accent hover:underline">
          Zurück zur Bibliothek
        </Link>
      </EmptyState>
    );
  }
  return <VideoView key={video.id} video={video} />;
}

function VideoView({ video }: { video: VideoDetail }) {
  const player = useRef<PlayerHandle>(null);
  const [time, setTime] = useState(0);
  const onTimeUpdate = useCallback((seconds: number) => setTime(Math.floor(seconds)), []);
  const navigate = useNavigate();

  return (
    <div className="-mx-4 sm:mx-0">
      <div className="mb-3 px-4 sm:px-0 md:mb-4">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 text-secondary"
          icon={<ArrowLeft className="size-4" strokeWidth={2} />}
          onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))}
        >
          Zurück
        </Button>
      </div>

      <div className="mx-auto max-w-[1400px]">
        <VideoPlayer ref={player} video={video} onTimeUpdate={onTimeUpdate} />

        <div className="mt-6 grid gap-10 px-4 sm:px-0 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">
            <h1 className="text-[24px] leading-tight font-bold tracking-tight sm:text-[28px]">
              {video.title}
            </h1>
            <p className="mt-2 text-[15px] text-secondary">
              {[
                video.channel?.name,
                formatDate(video.upload_date),
                video.view_count != null ? `${formatCount(video.view_count)} Aufrufe` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <VideoActions video={video} />
            {video.description && <Description text={video.description} />}
          </div>

          <aside className="flex flex-col gap-8">
            {video.chapters.length > 0 && (
              <section aria-labelledby="chapters-heading">
                <h2 id="chapters-heading" className="mb-3 text-[17px] font-semibold">
                  Kapitel
                </h2>
                <ol className="flex flex-col gap-0.5">
                  {video.chapters.map((chapter, index) => {
                    const active = time >= chapter.start && time < chapter.end;
                    return (
                      <li key={`${chapter.start}-${index}`}>
                        <button
                          type="button"
                          onClick={() => player.current?.seek(chapter.start)}
                          aria-current={active ? "true" : undefined}
                          className={cn(
                            "flex w-full items-baseline gap-3 rounded-lg px-3 py-2 text-left text-[14px] transition-colors duration-200",
                            active
                              ? "bg-surface text-primary"
                              : "text-secondary hover:bg-surface/60 hover:text-primary",
                          )}
                        >
                          <span
                            className={cn(
                              "w-14 shrink-0 text-[13px] tabular-nums",
                              active ? "text-accent" : "text-tertiary",
                            )}
                          >
                            {formatDuration(chapter.start)}
                          </span>
                          <span className="min-w-0">{chapter.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}
            <FileInfo video={video} />
          </aside>
        </div>
      </div>
    </div>
  );
}

function VideoActions({ video }: { video: VideoDetail }) {
  const { user } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const remove = useDeleteVideo();
  const toast = useToast();
  const navigate = useNavigate();

  const confirmDelete = async () => {
    try {
      await remove.mutateAsync(video.id);
      toast("Video gelöscht");
      navigate("/", { replace: true });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Löschen fehlgeschlagen", "error");
      setConfirming(false);
    }
  };

  return (
    <div className="mt-5 flex flex-wrap gap-2.5">
      <a
        href={apiUrl(`videos/${video.id}/download`)}
        className="inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors duration-200 hover:bg-surface-hover"
      >
        <Download className="size-4" strokeWidth={2} />
        Datei laden
      </a>
      {video.source_url && (
        <a
          href={video.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors duration-200 hover:bg-surface-hover"
        >
          <ExternalLink className="size-4" strokeWidth={2} />
          Auf YouTube
        </a>
      )}
      {user?.is_admin && (
        <Button
          variant="danger"
          size="sm"
          className="h-9 px-4 text-[14px]"
          icon={<Trash2 className="size-4" strokeWidth={2} />}
          onClick={() => setConfirming(true)}
        >
          Löschen
        </Button>
      )}
      <Dialog open={confirming} onClose={() => setConfirming(false)} title="Video löschen?">
        <p className="text-[15px] text-secondary">
          „{video.title}“ wird mit Thumbnail und Untertiteln von der Festplatte entfernt.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger hover:bg-danger/90"
            loading={remove.isPending}
            onClick={() => void confirmDelete()}
          >
            Löschen
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

const URL_PATTERN = /(https?:\/\/[^\s<]+)/g;

function Description({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > 280 || text.split("\n").length > 4;
  return (
    <section className="mt-6 rounded-2xl bg-elevated p-4 sm:p-5">
      <div
        className={cn(
          "text-[14px] leading-relaxed break-words whitespace-pre-line text-secondary",
          !expanded && long && "line-clamp-4",
        )}
      >
        {text.split(URL_PATTERN).map((part, index) =>
          index % 2 === 1 ? (
            <a
              key={index}
              href={part}
              target="_blank"
              rel="noreferrer noopener"
              className="text-accent hover:underline"
            >
              {part}
            </a>
          ) : (
            part
          ),
        )}
      </div>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-[14px] font-medium text-primary hover:underline"
        >
          {expanded ? "Weniger" : "Mehr"}
        </button>
      )}
    </section>
  );
}

function FileInfo({ video }: { video: VideoDetail }) {
  const rows: [string, string][] = [
    ["Dauer", formatDuration(video.duration_s)],
    ["Auflösung", formatResolution(video.height)],
    ["Video", codecLabel(video.vcodec)],
    ["Audio", codecLabel(video.acodec)],
    ["Format", video.container?.toUpperCase() ?? ""],
    ["Größe", formatBytes(video.filesize)],
    ["Untertitel", video.subtitles.map((s) => s.label).join(", ")],
    ["Heruntergeladen", formatDate(video.downloaded_at)],
  ];
  const visible = rows.filter(([, value]) => value);
  if (visible.length === 0) return null;
  return (
    <section aria-labelledby="file-heading">
      <h2 id="file-heading" className="mb-3 text-[17px] font-semibold">
        Details
      </h2>
      <dl className="divide-y divide-separator rounded-2xl bg-elevated px-4">
        {visible.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 py-2.5 text-[14px]">
            <dt className="text-secondary">{label}</dt>
            <dd className="text-right">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
