import { Clapperboard, Plus, Search } from "lucide-react";
import { useCallback, useDeferredValue, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useVideoPages, type VideoSort, type WatchedFilter } from "@/api/queries";
import { useOpenAddVideo } from "@/components/layout/addVideo";
import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadMore } from "@/components/ui/LoadMore";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { VideoGrid, VideoGridSkeleton } from "@/components/video/VideoGrid";
import { useAuth, useCanAdd, useYoutube } from "@/hooks/auth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { IMPORT_HINT } from "@/lib/mediaServer";

const SORTS: { value: VideoSort; label: string }[] = [
  { value: "added", label: "Zuletzt hinzugefügt" },
  { value: "newest", label: "Neueste zuerst" },
  { value: "oldest", label: "Älteste zuerst" },
  { value: "title", label: "Titel A–Z" },
];

const WATCHED: { value: WatchedFilter; label: string }[] = [
  { value: "all", label: "Alle" },
  { value: "unwatched", label: "Ungesehen" },
  { value: "in_progress", label: "Angefangen" },
  { value: "watched", label: "Gesehen" },
];

export function LibraryPage() {
  useDocumentTitle("Bibliothek");
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const sort = (params.get("sort") as VideoSort | null) ?? "added";
  const watched = (params.get("watched") as WatchedFilter | null) ?? "all";
  const deferredQuery = useDeferredValue(query.trim());
  const {
    items: videos,
    total,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    pageCount,
  } = useVideoPages({
    q: deferredQuery || undefined,
    sort: deferredQuery ? undefined : sort,
    watched,
  });
  const loadMore = useCallback(() => void fetchNextPage(), [fetchNextPage]);
  const openAdd = useOpenAddVideo();
  const canAdd = useCanAdd();
  const { user } = useAuth();
  const importHint = !useYoutube() && Boolean(user?.is_admin);
  const navigate = useNavigate();

  const setParam = (key: string, value: string, fallback: string) => {
    const next = new URLSearchParams(params);
    if (value === fallback) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        title="Bibliothek"
        subtitle={total !== undefined ? `${total} ${total === 1 ? "Video" : "Videos"}` : undefined}
        settingsShortcut
        actions={
          <>
            <div className="relative flex-1 md:w-64 md:flex-none">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tertiary"
                strokeWidth={2}
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="In der Bibliothek suchen"
                aria-label="Bibliothek durchsuchen"
                className="h-9 w-full rounded-lg bg-surface pr-3 pl-9 text-[15px] placeholder:text-tertiary outline-none transition-shadow focus:ring-2 focus:ring-accent"
              />
            </div>
            <Select
              label="Sortierung"
              className="[&>label]:sr-only"
              inline
              value={sort}
              disabled={Boolean(deferredQuery)}
              onChange={(event) => setParam("sort", event.target.value, "added")}
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </>
        }
      />
      <LibraryTabs />
      <div className="no-scrollbar -mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <SegmentedControl
          label="Gesehen-Filter"
          value={watched}
          onChange={(value) => setParam("watched", value, "all")}
          options={WATCHED}
        />
      </div>

      {isLoading ? (
        <VideoGridSkeleton />
      ) : isError ? (
        <EmptyState icon={<Clapperboard className="size-7" strokeWidth={1.5} />} title="Fehler">
          {error.message}
        </EmptyState>
      ) : videos.length === 0 ? (
        deferredQuery || watched !== "all" ? (
          <EmptyState icon={<Search className="size-7" strokeWidth={1.5} />} title="Keine Treffer">
            {deferredQuery
              ? `Für „${deferredQuery}“ wurde nichts gefunden.`
              : "Keine Videos in dieser Ansicht."}
          </EmptyState>
        ) : (
          <EmptyState
            icon={<Clapperboard className="size-7" strokeWidth={1.5} />}
            title="Deine Bibliothek ist leer"
            action={
              importHint ? (
                <Button onClick={() => navigate("/admin/import")}>Videos importieren</Button>
              ) : (
                canAdd && (
                  <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={openAdd}>
                    Video hinzufügen
                  </Button>
                )
              )
            }
          >
            {canAdd
              ? "Füge ein YouTube-Video per Link hinzu oder abonniere einen Kanal."
              : importHint
                ? IMPORT_HINT
                : "Für dein Konto sind noch keine Videos freigegeben."}
          </EmptyState>
        )
      ) : (
        <>
          <VideoGrid videos={videos} />
          <LoadMore
            hasMore={hasNextPage}
            loading={isFetchingNextPage}
            onLoad={loadMore}
            pageCount={pageCount}
          />
        </>
      )}
    </>
  );
}
