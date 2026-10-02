import { Clapperboard, Plus, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { useVideos, type VideoSort } from "@/api/queries";
import { useOpenAddVideo } from "@/components/layout/addVideo";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Select";
import { Hero } from "@/components/video/Hero";
import { VideoGrid, VideoGridSkeleton } from "@/components/video/VideoGrid";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

const SORTS: { value: VideoSort; label: string }[] = [
  { value: "added", label: "Zuletzt hinzugefügt" },
  { value: "newest", label: "Neueste zuerst" },
  { value: "oldest", label: "Älteste zuerst" },
  { value: "title", label: "Titel A–Z" },
];

export function LibraryPage() {
  useDocumentTitle("Bibliothek");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<VideoSort>("added");
  const deferredQuery = useDeferredValue(query.trim());
  const { data, isLoading, isError, error } = useVideos({ q: deferredQuery || undefined, sort });
  const openAdd = useOpenAddVideo();

  const videos = data?.items ?? [];
  const showHero = !deferredQuery && sort === "added" && videos.length > 3;
  const [hero, ...rest] = videos;

  return (
    <>
      <PageHeader
        title="Bibliothek"
        subtitle={data ? `${data.total} ${data.total === 1 ? "Video" : "Videos"}` : undefined}
        actions={
          <>
            <div className="relative flex-1 md:w-72 md:flex-none">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tertiary"
                strokeWidth={2}
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Suchen"
                aria-label="Bibliothek durchsuchen"
                className="h-9 w-full rounded-lg bg-surface pr-3 pl-9 text-[15px] placeholder:text-tertiary outline-none transition-shadow focus:ring-2 focus:ring-accent"
              />
            </div>
            <Select
              label="Sortierung"
              className="[&>label]:sr-only"
              inline
              value={sort}
              onChange={(event) => setSort(event.target.value as VideoSort)}
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

      {isLoading ? (
        <VideoGridSkeleton />
      ) : isError ? (
        <EmptyState icon={<Clapperboard className="size-7" strokeWidth={1.5} />} title="Fehler">
          {error.message}
        </EmptyState>
      ) : videos.length === 0 ? (
        deferredQuery ? (
          <EmptyState icon={<Search className="size-7" strokeWidth={1.5} />} title="Keine Treffer">
            Für „{deferredQuery}“ wurde nichts gefunden.
          </EmptyState>
        ) : (
          <EmptyState
            icon={<Clapperboard className="size-7" strokeWidth={1.5} />}
            title="Deine Bibliothek ist leer"
            action={
              <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={openAdd}>
                Video hinzufügen
              </Button>
            }
          >
            Füge ein YouTube-Video per Link hinzu. Es wird heruntergeladen und erscheint dann hier.
          </EmptyState>
        )
      ) : (
        <>
          {showHero && hero && <Hero video={hero} />}
          <VideoGrid videos={showHero ? rest : videos} />
        </>
      )}
    </>
  );
}
