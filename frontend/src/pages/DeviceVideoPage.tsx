import { ArrowLeft, Headphones, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { useAudioPlayer } from "@/audio/context";
import { Button } from "@/components/ui/Button";
import { VideoPlayer } from "@/components/video/VideoPlayer";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useOffline, type OfflineFiles } from "@/offline/context";
import { forgetLocalProgress, loadLocalProgress, saveLocalProgress } from "@/offline/progress";

/** Progress goes onto the device – and straight to the server when it answers. */
function saveDeviceProgress(
  owner: number | null,
  online: boolean,
  videoId: number,
  seconds: number,
  duration: number,
) {
  saveLocalProgress(owner, videoId, seconds, duration);
  if (online) {
    void api
      .put(`videos/${videoId}/progress`, { position_s: seconds, duration_s: duration })
      .then(() => forgetLocalProgress(owner, videoId))
      .catch(() => undefined);
  }
}

/** Plays a video from this device – no server needed. */
export function DeviceVideoPage({ online }: { online: boolean }) {
  const { id } = useParams();
  const videoId = Number(id);
  const { owner, ready, entries, open } = useOffline();
  const player = useAudioPlayer();
  const entry = entries[videoId];
  const [files, setFiles] = useState<OfflineFiles | null | undefined>(undefined);
  useDocumentTitle(entry?.video.title);

  // Files handed to the audio player stay open after leaving the page; it frees them.
  const handedOver = useRef<OfflineFiles | null>(null);

  useEffect(() => {
    if (!ready || !entry) return;
    let current: OfflineFiles | null = null;
    let cancelled = false;
    void open(videoId).then((result) => {
      if (cancelled) {
        result?.revoke();
        return;
      }
      current = result;
      setFiles(result);
    });
    return () => {
      cancelled = true;
      if (current !== handedOver.current) current?.revoke();
    };
  }, [ready, entry, videoId, open]);

  if (!ready || (entry && files === undefined)) return <PageSpinner />;
  if (!entry || !files) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Nicht auf dem Gerät"
      >
        <Link to="/device" className="text-accent hover:underline">
          Zu den gespeicherten Videos
        </Link>
      </EmptyState>
    );
  }

  const video = entry.video;
  const startAt = loadLocalProgress(owner)[videoId]?.position_s ?? video.progress?.position_s ?? 0;

  return (
    <div className="mx-auto max-w-[1200px]">
      <Link
        to="/device"
        className="mb-4 inline-flex items-center gap-1.5 text-[15px] text-secondary hover:text-primary"
      >
        <ArrowLeft className="size-4" strokeWidth={2} />
        Auf diesem Gerät
      </Link>
      {entry.quality === "audio" ? (
        <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-2xl bg-surface">
          {files.poster ? (
            <img src={files.poster} alt="" className="absolute inset-0 size-full object-cover" />
          ) : (
            <Headphones className="size-12 text-tertiary" strokeWidth={1.25} />
          )}
          <Button
            className="relative shadow-card"
            icon={<Play className="size-4 fill-current" strokeWidth={0} />}
            onClick={() => {
              // Right inside the tap (iOS wants that); the sound outlives this page.
              handedOver.current = files;
              player.play([
                {
                  id: videoId,
                  title: video.title,
                  channel: video.channel?.name ?? null,
                  duration: video.duration_s,
                  artwork: files.poster,
                  startAt,
                  src: files.video,
                  save: (seconds, duration) =>
                    saveDeviceProgress(owner, online, videoId, seconds, duration),
                  release: files.revoke,
                },
              ]);
            }}
          >
            {player.track?.id === videoId ? "Läuft" : "Anhören"}
          </Button>
        </div>
      ) : (
        <div className="aspect-video overflow-hidden rounded-2xl bg-black">
          <VideoPlayer
            video={video}
            source={{ src: files.video, type: "video/mp4" }}
            local={{ poster: files.poster, subtitles: files.subtitles, chapters: files.chapters }}
            startAt={startAt}
            onSave={(seconds, duration) =>
              saveDeviceProgress(owner, online, videoId, seconds, duration)
            }
          />
        </div>
      )}
      <h1 className="mt-5 text-[24px] leading-tight font-bold tracking-tight">{video.title}</h1>
      <p className="mt-1 text-[14px] text-secondary">
        {[video.channel?.name, formatDate(video.upload_date)].filter(Boolean).join(" · ")}
      </p>
      {video.description && (
        <p className="mt-5 line-clamp-6 text-[14px] leading-relaxed whitespace-pre-line text-secondary">
          {video.description}
        </p>
      )}
    </div>
  );
}
