import { Clapperboard, Plus, Tv } from "lucide-react";
import { useNavigate } from "react-router";

import { useHome } from "@/api/queries";
import { ChannelTile } from "@/components/channels/ChannelTile";
import { useOpenAddVideo } from "@/components/layout/addVideo";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { Hero } from "@/components/video/Hero";
import { Row, RowItem } from "@/components/video/Row";
import { VideoCard } from "@/components/video/VideoCard";
import { useCanAdd } from "@/hooks/auth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import type { VideoSummary } from "@/lib/types";

function VideoRow({ title, videos, to }: { title: string; videos: VideoSummary[]; to?: string }) {
  if (videos.length === 0) return null;
  return (
    <Row title={title} to={to}>
      {videos.map((video) => (
        <RowItem key={video.id} wide>
          <VideoCard video={video} />
        </RowItem>
      ))}
    </Row>
  );
}

export function HomePage() {
  useDocumentTitle("Start");
  const { data, isLoading } = useHome();
  const openAdd = useOpenAddVideo();
  const canAdd = useCanAdd();
  const navigate = useNavigate();

  if (isLoading || !data) return <PageSpinner />;

  const empty =
    !data.hero && data.recently_added.length === 0 && data.from_subscriptions.length === 0;

  return (
    <>
      <PageHeader title="Start" settingsShortcut />
      {empty ? (
        <EmptyState
          icon={<Clapperboard className="size-7" strokeWidth={1.5} />}
          title="Willkommen bei TubeVault"
          action={
            canAdd && (
              <div className="flex flex-wrap justify-center gap-3">
                <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={openAdd}>
                  Video hinzufügen
                </Button>
                <Button
                  variant="secondary"
                  icon={<Tv className="size-4" strokeWidth={2} />}
                  onClick={() => navigate("/subscriptions")}
                >
                  Kanal abonnieren
                </Button>
              </div>
            )
          }
        >
          {canAdd
            ? "Füge ein einzelnes Video hinzu oder abonniere einen Kanal – neue Videos erscheinen dann automatisch hier."
            : "Hier erscheinen die Videos, die für dich freigegeben sind."}
        </EmptyState>
      ) : (
        <>
          {data.hero && <Hero video={data.hero} />}
          <VideoRow
            title="Weiterschauen"
            videos={data.continue_watching}
            to="/library?watched=in_progress"
          />
          <VideoRow title="Später ansehen" videos={data.watch_later ?? []} to="/later" />
          <VideoRow title="Neu von deinen Abos" videos={data.from_subscriptions} to="/library" />
          <VideoRow
            title={data.from_subscriptions.length ? "Von dir hinzugefügt" : "Zuletzt hinzugefügt"}
            videos={data.recently_added}
            to="/library"
          />
          {data.channels.length > 0 && (
            <Row title="Kanäle" to="/channels">
              {data.channels.map((channel) => (
                <RowItem key={channel.id}>
                  <ChannelTile channel={channel} />
                </RowItem>
              ))}
            </Row>
          )}
        </>
      )}
    </>
  );
}
