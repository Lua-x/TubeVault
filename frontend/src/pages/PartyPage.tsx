import { useQueryClient } from "@tanstack/react-query";
import { Link2, LogOut, Play, UsersRound } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router";

import { keys, reportProgress, useVideo } from "@/api/queries";
import { ProfileAvatar } from "@/components/family/ProfileAvatar";
import { Button } from "@/components/ui/Button";
import { PageSpinner } from "@/components/ui/Spinner";
import { PlaybackStatus } from "@/components/video/QualityMenu";
import { VideoPlayer } from "@/components/video/VideoPlayer";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useParty } from "@/hooks/useParty";
import { usePlaybackSource } from "@/hooks/usePlaybackSource";
import type { VideoDetail } from "@/lib/types";

const ACTIONS: Record<string, string> = {
  play: "spielt ab",
  pause: "hat pausiert",
  seek: "hat gespult",
};

/** Watching a video together – everyone in the room sees the same moment. */
export function PartyPage() {
  const roomId = useParams().id ?? "";
  const container = useRef<HTMLDivElement>(null);
  const media = useCallback(() => container.current?.querySelector("video") ?? null, []);
  const party = useParty(roomId, media);
  // NaN keeps the query waiting until the room said which video it is.
  const { data: video } = useVideo(party.videoId ?? Number.NaN);
  useDocumentTitle("Gemeinsam schauen");

  if (party.status === "closed" && !video) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center">
        <UsersRound className="size-8 text-secondary" strokeWidth={1.5} />
        <p className="max-w-sm text-[15px] text-secondary">{party.error}</p>
      </div>
    );
  }
  if (!video) return <PageSpinner />;
  return (
    <div ref={container}>
      <PartyView video={video} party={party} />
    </div>
  );
}

function PartyView({ video, party }: { video: VideoDetail; party: ReturnType<typeof useParty> }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const playback = usePlaybackSource(video);
  const holder = useRef<HTMLDivElement>(null);

  // Tell the others what the viewer did here.
  const report = party.report;
  useEffect(() => {
    const root = holder.current;
    if (!root) return;
    const media = () => root.querySelector("video");
    const onPlay = () => report("play", media()?.currentTime ?? 0);
    const onPause = () => {
      const el = media();
      if (el && !el.ended) report("pause", el.currentTime);
    };
    const onSeeked = () => report("seek", media()?.currentTime ?? 0);
    root.addEventListener("play", onPlay, true);
    root.addEventListener("pause", onPause, true);
    root.addEventListener("seeked", onSeeked, true);
    return () => {
      root.removeEventListener("play", onPlay, true);
      root.removeEventListener("pause", onPause, true);
      root.removeEventListener("seeked", onSeeked, true);
    };
  }, [report]);

  useEffect(() => {
    const action = party.lastAction;
    if (action && ACTIONS[action.action]) toast(`${action.by} ${ACTIONS[action.action]}`);
  }, [party.lastAction, toast]);

  const invite = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: video.title, url });
      else {
        await navigator.clipboard.writeText(url);
        toast("Link kopiert – schick ihn an die anderen");
      }
    } catch {
      // cancelled
    }
  };

  return (
    <div className="flex flex-col gap-5 pb-12">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium tracking-wide text-accent uppercase">
            Gemeinsam schauen
          </p>
          <h1 className="truncate text-[22px] font-bold tracking-tight">{video.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<Link2 className="size-4" />}
            onClick={invite}
          >
            Einladen
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<LogOut className="size-4" />}
            onClick={() => navigate(`/videos/${video.id}`)}
          >
            Verlassen
          </Button>
        </div>
      </header>

      <div ref={holder} className="relative">
        <VideoPlayer
          video={video}
          source={playback.source}
          onSourceError={playback.onSourceError}
          onSave={(position, duration, reason) => {
            void reportProgress(video.id, position, duration).then(() => {
              if (reason === "unmount" || reason === "ended") {
                void client.invalidateQueries({ queryKey: keys.videos });
              }
            });
          }}
          overlay={
            <PlaybackStatus
              preparing={playback.preparing}
              error={playback.error}
              onRetry={playback.retry}
            />
          }
        />
        {!party.ready && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 rounded-2xl bg-black/70 text-center text-white backdrop-blur-sm">
            <p className="max-w-xs text-[15px] text-white/80">
              {party.members.length > 1
                ? `${party.members.map((m) => m.name).join(", ")} sind im Raum.`
                : "Noch bist du allein – lade die anderen mit dem Link ein."}
            </p>
            <Button
              icon={<Play className="size-4 fill-current" strokeWidth={0} />}
              onClick={party.join}
            >
              Mitschauen
            </Button>
          </div>
        )}
      </div>

      <section aria-label="Im Raum" className="flex flex-wrap items-center gap-3">
        {party.members.map((member) => (
          <span
            key={member.id}
            className="flex items-center gap-2 rounded-full bg-elevated py-1 pr-3.5 pl-1 text-[14px]"
          >
            <ProfileAvatar id={member.user_id} name={member.name} className="size-7 text-[12px]" />
            {member.name}
            {member.id === party.you && <span className="text-secondary">(du)</span>}
          </span>
        ))}
      </section>
    </div>
  );
}
