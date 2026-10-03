import { History, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useForgetHistory, useHistory } from "@/api/queries";
import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadMore } from "@/components/ui/LoadMore";
import { PageSpinner } from "@/components/ui/Spinner";
import { Thumbnail } from "@/components/video/Thumbnail";
import { WatchOverlay } from "@/components/video/WatchOverlay";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDate, formatDuration } from "@/lib/format";
import type { VideoSummary } from "@/lib/types";

const weekday = new Intl.DateTimeFormat("de-DE", { weekday: "long" });

function dayLabel(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((start(now) - start(date)) / 86_400_000);
  if (days <= 0) return "Heute";
  if (days === 1) return "Gestern";
  if (days < 7) return weekday.format(date);
  return formatDate(iso);
}

function groupByDay(videos: VideoSummary[]): [string, VideoSummary[]][] {
  const groups = new Map<string, VideoSummary[]>();
  for (const video of videos) {
    const label = video.progress ? dayLabel(video.progress.updated_at) : "Früher";
    groups.set(label, [...(groups.get(label) ?? []), video]);
  }
  return [...groups.entries()];
}

/** What you watched, newest first – grouped by day. */
export function HistoryPage() {
  useDocumentTitle("Verlauf");
  const { items, total, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage, data } =
    useHistory();
  const forget = useForgetHistory();
  const toast = useToast();
  const [confirmClear, setConfirmClear] = useState(false);

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4 md:mb-8">
        <div>
          <h1 className="text-[32px] leading-tight font-bold tracking-tight md:text-[34px]">
            Verlauf
          </h1>
          {total != null && total > 0 && (
            <p className="mt-0.5 text-[15px] text-secondary">
              {total} {total === 1 ? "Video" : "Videos"}
            </p>
          )}
        </div>
        {items.length > 0 && (
          <Button variant="secondary" onClick={() => setConfirmClear(true)}>
            Verlauf löschen
          </Button>
        )}
      </header>
      <LibraryTabs />

      {isLoading ? (
        <PageSpinner />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<History className="size-7" strokeWidth={1.5} />}
          title="Noch nichts gesehen"
        >
          Hier erscheinen die Videos, die du angefangen oder gesehen hast.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-8">
          {groupByDay(items).map(([label, videos]) => (
            <section key={label} aria-label={label}>
              <h2 className="mb-3 px-1 text-[17px] font-semibold">{label}</h2>
              <ul className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
                {videos.map((video) => (
                  <li key={video.id} className="flex items-center gap-3 px-2 py-2.5 sm:px-3">
                    <Link
                      to={`/videos/${video.id}`}
                      className="flex min-w-0 flex-1 items-center gap-3"
                    >
                      <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded-lg sm:w-36">
                        <Thumbnail video={video} className="size-full" />
                        <WatchOverlay video={video} />
                      </div>
                      <div className="min-w-0">
                        <p className="line-clamp-2 text-[15px] leading-snug font-medium">
                          {video.title}
                        </p>
                        <p className="truncate text-[13px] text-secondary">
                          {[video.channel?.name, formatDuration(video.duration_s)]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      </div>
                    </Link>
                    <IconButton
                      label="Aus dem Verlauf entfernen"
                      onClick={() =>
                        forget.mutate(video.id, {
                          onSuccess: () => toast("Aus dem Verlauf entfernt"),
                        })
                      }
                    >
                      <X className="size-[18px]" strokeWidth={1.75} />
                    </IconButton>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <LoadMore
            hasMore={Boolean(hasNextPage)}
            loading={isFetchingNextPage}
            onLoad={() => void fetchNextPage()}
            pageCount={data?.pages.length ?? 0}
          />
        </div>
      )}

      <Dialog open={confirmClear} onClose={() => setConfirmClear(false)} title="Verlauf löschen?">
        <p className="text-[15px] text-secondary">
          Damit vergisst TubeVault auch, wo du in jedem Video warst und was du schon gesehen hast.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmClear(false)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger hover:bg-danger/90"
            loading={forget.isPending}
            onClick={() =>
              forget.mutate(null, {
                onSuccess: () => {
                  setConfirmClear(false);
                  toast("Verlauf gelöscht");
                },
              })
            }
          >
            Löschen
          </Button>
        </div>
      </Dialog>
    </>
  );
}
