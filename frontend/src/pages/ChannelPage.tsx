import { ArrowLeft, Check, ExternalLink, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { Link, useParams } from "react-router";

import { useChannel, useVideoPages, type VideoSort, type WatchedFilter } from "@/api/queries";
import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import { SubscribeDialog } from "@/components/subscriptions/SubscribeDialog";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadMore } from "@/components/ui/LoadMore";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { PageSpinner } from "@/components/ui/Spinner";
import { VideoGrid, VideoGridSkeleton } from "@/components/video/VideoGrid";
import { PodcastButton } from "@/components/podcasts/PodcastButton";
import { useCanAdd } from "@/hooks/auth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { channelImageUrl } from "@/lib/media";

export function ChannelPage() {
  const { id } = useParams();
  const channelId = Number(id);
  const { data: channel, isLoading, error } = useChannel(channelId);
  const [sort, setSort] = useState<VideoSort>("newest");
  const [watched, setWatched] = useState<WatchedFilter>("all");
  const [subscribing, setSubscribing] = useState(false);
  const canAdd = useCanAdd();
  const videos = useVideoPages({ channelId, sort, watched });
  const { fetchNextPage } = videos;
  const loadMore = useCallback(() => void fetchNextPage(), [fetchNextPage]);
  useDocumentTitle(channel?.name);

  if (isLoading) return <PageSpinner />;
  if (error || !channel) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Kanal nicht gefunden"
      >
        <Link to="/channels" className="text-accent hover:underline">
          Zu den Kanälen
        </Link>
      </EmptyState>
    );
  }

  const counts = [
    `${channel.video_count} ${channel.video_count === 1 ? "Video" : "Videos"}`,
    channel.unwatched_count ? `${channel.unwatched_count} ungesehen` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="pb-12">
      <Link
        to="/channels"
        className="mb-4 inline-flex items-center gap-1.5 text-[14px] text-secondary transition-colors hover:text-primary"
      >
        <ArrowLeft className="size-4" strokeWidth={2} />
        Kanäle
      </Link>
      <header className="mb-8 overflow-hidden rounded-3xl bg-elevated shadow-[0_0_0_1px_var(--tv-separator)]">
        <div className="relative h-28 bg-surface sm:h-48">
          {channel.has_banner && (
            <img
              src={channelImageUrl(channel, "banner")}
              alt=""
              className="size-full object-cover"
            />
          )}
        </div>
        <div className="flex flex-col gap-4 px-5 pb-5 sm:flex-row sm:items-end sm:px-6">
          <ChannelAvatar
            channel={channel}
            name={channel.name}
            className="relative z-10 -mt-10 size-20 border-4 border-elevated text-[30px] sm:-mt-14 sm:size-28"
          />
          <div className="min-w-0 flex-1">
            <h1 className="text-[26px] leading-tight font-bold tracking-tight sm:text-[32px]">
              {channel.name}
            </h1>
            <p className="mt-1 text-[14px] text-secondary">
              {[channel.handle, counts].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {!canAdd || channel.is_local ? null : channel.subscription_id ? (
              <Link
                to={`/subscriptions/${channel.subscription_id}`}
                className="inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors hover:bg-surface-hover"
              >
                <Check className="size-4 text-success" strokeWidth={2.5} />
                Abonniert
              </Link>
            ) : (
              <Button
                size="sm"
                className="h-9 px-4 text-[14px]"
                icon={<Plus className="size-4" strokeWidth={2.25} />}
                onClick={() => setSubscribing(true)}
              >
                Abonnieren
              </Button>
            )}
            <PodcastButton feed={`channels/${channel.id}.xml`} title={channel.name} />
            {channel.url && (
              <a
                href={channel.url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors hover:bg-surface-hover"
              >
                <ExternalLink className="size-4" strokeWidth={2} />
                YouTube
              </a>
            )}
          </div>
        </div>
      </header>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="Gesehen-Filter"
          value={watched}
          onChange={setWatched}
          options={[
            { value: "all", label: "Alle" },
            { value: "unwatched", label: "Ungesehen" },
            { value: "watched", label: "Gesehen" },
          ]}
        />
        <Select
          inline
          label="Sortierung"
          className="[&>label]:sr-only"
          value={sort}
          onChange={(e) => setSort(e.target.value as VideoSort)}
        >
          <option value="newest">Neueste zuerst</option>
          <option value="oldest">Älteste zuerst</option>
          <option value="title">Titel A–Z</option>
        </Select>
      </div>
      {videos.isLoading ? (
        <VideoGridSkeleton />
      ) : videos.items.length > 0 ? (
        <>
          <VideoGrid videos={videos.items} hideChannel />
          <LoadMore
            hasMore={videos.hasNextPage}
            loading={videos.isFetchingNextPage}
            onLoad={loadMore}
            pageCount={videos.pageCount}
          />
        </>
      ) : (
        <p className="py-10 text-center text-[15px] text-secondary">
          Keine Videos in dieser Ansicht.
        </p>
      )}
      <SubscribeDialog
        open={subscribing}
        onClose={() => setSubscribing(false)}
        initialUrl={channel.url ?? `https://www.youtube.com/channel/${channel.youtube_id}`}
      />
    </div>
  );
}
