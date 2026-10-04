import { ChevronDown, History, Search, X } from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { useChannels, useVideoPages, type VideoListParams, type VideoSort } from "@/api/queries";
import { ChannelTile } from "@/components/channels/ChannelTile";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadMore } from "@/components/ui/LoadMore";
import { Spinner } from "@/components/ui/Spinner";
import { Row, RowItem } from "@/components/video/Row";
import { VideoGrid } from "@/components/video/VideoGrid";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn } from "@/lib/cn";

const RECENT_KEY = "tubevault.recentSearches";

function loadRecent(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as unknown;
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function saveRecent(query: string) {
  try {
    const recent = [query, ...loadRecent().filter((q) => q !== query)].slice(0, 8);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  } catch {
    // ignore
  }
}

type Duration = NonNullable<VideoListParams["duration"]>;
type Uploaded = NonNullable<VideoListParams["uploaded"]>;

const DURATIONS: { value: Duration; label: string }[] = [
  { value: "any", label: "Jede Länge" },
  { value: "short", label: "Unter 4 Min." },
  { value: "medium", label: "4–20 Min." },
  { value: "long", label: "Über 20 Min." },
];
const UPLOADED: { value: Uploaded; label: string }[] = [
  { value: "any", label: "Jederzeit" },
  { value: "week", label: "Diese Woche" },
  { value: "month", label: "Diesen Monat" },
  { value: "year", label: "Dieses Jahr" },
];
const SORTS: { value: VideoSort; label: string }[] = [
  { value: "relevance", label: "Relevanz" },
  { value: "newest", label: "Neueste zuerst" },
  { value: "oldest", label: "Älteste zuerst" },
  { value: "added", label: "Zuletzt hinzugefügt" },
  { value: "title", label: "Titel" },
];

interface FilterProps<T extends string> {
  label: string;
  value: T;
  fallback: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** A pill that is a native select underneath – keyboard and touch friendly. */
function Filter<T extends string>({ label, value, fallback, options, onChange }: FilterProps<T>) {
  const active = value !== fallback;
  return (
    <label
      className={cn(
        "relative inline-flex h-9 shrink-0 items-center gap-1 rounded-full pr-3 pl-4 text-[14px] font-medium transition-colors",
        active ? "bg-primary text-canvas" : "bg-surface text-secondary hover:bg-surface-hover",
      )}
    >
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <span aria-hidden>{options.find((o) => o.value === value)?.label}</span>
      <ChevronDown className="size-4" strokeWidth={2} aria-hidden />
    </label>
  );
}

const normalize = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");

export function SearchPage() {
  useDocumentTitle("Suche");
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [recent, setRecent] = useState(loadRecent);
  const input = useRef<HTMLInputElement>(null);
  const deferred = useDeferredValue(query.trim());
  const [duration, setDuration] = useState<Duration>(
    () => (params.get("duration") as Duration | null) ?? "any",
  );
  const [uploaded, setUploaded] = useState<Uploaded>(
    () => (params.get("uploaded") as Uploaded | null) ?? "any",
  );
  const [channelId, setChannelId] = useState(params.get("channel") ?? "");
  const [sort, setSort] = useState<VideoSort>(
    () => (params.get("sort") as VideoSort | null) ?? "relevance",
  );
  const filtered = duration !== "any" || uploaded !== "any" || channelId !== "";
  // Filters alone work too: "everything long from this week".
  const searching = deferred.length > 0 || filtered;
  const videos = useVideoPages(
    {
      q: deferred,
      duration,
      uploaded,
      channelId: channelId ? Number(channelId) : undefined,
      // Without words there is no relevance – newest first then.
      sort: !deferred && sort === "relevance" ? "newest" : sort,
    },
    searching,
  );
  const { fetchNextPage } = videos;
  const loadMore = useCallback(() => void fetchNextPage(), [fetchNextPage]);
  const isFetching = videos.isFetching && !videos.isFetchingNextPage;
  const { data: channels } = useChannels();

  useEffect(() => {
    const id = setTimeout(() => {
      const next: Record<string, string> = {};
      if (deferred) next.q = deferred;
      if (duration !== "any") next.duration = duration;
      if (uploaded !== "any") next.uploaded = uploaded;
      if (channelId) next.channel = channelId;
      if (sort !== "relevance") next.sort = sort;
      setParams(next, { replace: true });
      if (deferred.length >= 3) {
        saveRecent(deferred);
        setRecent(loadRecent());
      }
    }, 600);
    return () => clearTimeout(id);
  }, [deferred, duration, uploaded, channelId, sort, setParams]);

  const words = normalize(deferred).split(/\s+/).filter(Boolean);
  const matchingChannels = deferred
    ? (channels ?? []).filter((c) => words.every((w) => normalize(c.name).includes(w)))
    : [];
  const results = videos.items;

  return (
    <>
      <h1 className="mb-6 text-[32px] leading-tight font-bold tracking-tight md:text-[34px]">
        Suche
      </h1>
      <div className="relative mb-8 max-w-2xl">
        <Search
          className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-tertiary"
          strokeWidth={2}
        />
        <input
          ref={input}
          autoFocus
          type="search"
          enterKeyHint="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Titel, Beschreibung oder Kanal"
          aria-label="Suchen"
          className="h-12 w-full rounded-2xl bg-surface pr-12 pl-12 text-[17px] placeholder:text-tertiary outline-none transition-shadow focus:ring-2 focus:ring-accent [&::-webkit-search-cancel-button]:hidden"
        />
        {query && (
          <button
            type="button"
            aria-label="Suche leeren"
            onClick={() => {
              setQuery("");
              input.current?.focus();
            }}
            className="absolute top-1/2 right-3 flex size-7 -translate-y-1/2 items-center justify-center rounded-full bg-surface-hover text-secondary"
          >
            <X className="size-4" strokeWidth={2.25} />
          </button>
        )}
      </div>
      <div
        role="group"
        aria-label="Filter"
        className="no-scrollbar -mx-4 -mt-4 mb-8 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0"
      >
        <Filter
          label="Länge"
          value={duration}
          fallback="any"
          options={DURATIONS}
          onChange={setDuration}
        />
        <Filter
          label="Hochgeladen"
          value={uploaded}
          fallback="any"
          options={UPLOADED}
          onChange={setUploaded}
        />
        {channels && channels.length > 1 && (
          <Filter
            label="Kanal"
            value={channelId}
            fallback=""
            options={[
              { value: "", label: "Alle Kanäle" },
              ...channels.map((c) => ({ value: String(c.id), label: c.name })),
            ]}
            onChange={setChannelId}
          />
        )}
        <Filter
          label="Sortierung"
          value={sort}
          fallback="relevance"
          options={SORTS}
          onChange={setSort}
        />
        {(filtered || sort !== "relevance") && (
          <button
            type="button"
            onClick={() => {
              setDuration("any");
              setUploaded("any");
              setChannelId("");
              setSort("relevance");
            }}
            className="h-9 shrink-0 px-2 text-[14px] font-medium text-accent"
          >
            Zurücksetzen
          </button>
        )}
      </div>

      {!searching ? (
        recent.length > 0 ? (
          <section aria-labelledby="recent-heading" className="max-w-2xl">
            <h2
              id="recent-heading"
              className="mb-2 text-[13px] font-medium text-secondary uppercase"
            >
              Zuletzt gesucht
            </h2>
            <ul className="divide-y divide-separator rounded-2xl bg-elevated">
              {recent.map((item) => (
                <li key={item}>
                  <button
                    type="button"
                    onClick={() => setQuery(item)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left text-[15px] hover:bg-surface/50"
                  >
                    <History className="size-4 text-tertiary" strokeWidth={2} />
                    {item}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <EmptyState
            icon={<Search className="size-7" strokeWidth={1.5} />}
            title="Durchsuche deine Bibliothek"
          >
            Titel, Beschreibungen und Kanalnamen – auch Wortanfänge und ohne Umlaute.
          </EmptyState>
        )
      ) : (
        <>
          {matchingChannels.length > 0 && (
            <Row title="Kanäle">
              {matchingChannels.map((channel) => (
                <RowItem key={channel.id}>
                  <ChannelTile channel={channel} />
                </RowItem>
              ))}
            </Row>
          )}
          <div className="mb-4 flex items-center gap-3">
            <h2 className="text-[20px] font-semibold tracking-tight">Videos</h2>
            {isFetching && <Spinner className="size-4 text-tertiary" />}
            {videos.total !== undefined && (
              <span className="text-[14px] text-tertiary">{videos.total}</span>
            )}
          </div>
          {results.length > 0 ? (
            <>
              <VideoGrid videos={results} heading="h3" />
              <LoadMore
                hasMore={videos.hasNextPage}
                loading={videos.isFetchingNextPage}
                onLoad={loadMore}
                pageCount={videos.pageCount}
              />
            </>
          ) : (
            !isFetching && (
              <p className="py-10 text-center text-[15px] text-secondary">
                {deferred ? `Keine Videos zu „${deferred}“.` : "Keine Videos mit diesen Filtern."}
              </p>
            )
          )}
        </>
      )}
    </>
  );
}
