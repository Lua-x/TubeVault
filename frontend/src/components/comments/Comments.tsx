import {
  BadgeCheck,
  ChevronDown,
  Heart,
  MessageSquare,
  Pin,
  RefreshCw,
  ThumbsUp,
} from "lucide-react";
import { useState } from "react";

import { useComments, useDeleteComments, useFetchComments } from "@/api/queries";
import { Button, IconButton } from "@/components/ui/Button";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Spinner } from "@/components/ui/Spinner";
import { RichText } from "@/components/video/RichText";
import { useAuth, useCanAdd } from "@/hooks/auth";
import { cn } from "@/lib/cn";
import { formatCount, formatDate, formatRelative } from "@/lib/format";
import type { Comment, CommentThread, VideoDetail } from "@/lib/types";

type Sort = "top" | "new";

function hue(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}

/** No pictures from YouTube: a coloured initial instead. */
function Avatar({ name, small }: { name: string; small?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold text-white",
        small ? "size-7 text-[12px]" : "size-9 text-[14px]",
      )}
      style={{ backgroundColor: `hsl(${hue(name)} 40% 42%)` }}
    >
      {name.replace(/^@/, "").charAt(0).toUpperCase() || "?"}
    </span>
  );
}

interface ItemProps {
  comment: Comment;
  duration: number | null;
  onSeek: (seconds: number) => void;
  small?: boolean;
}

function CommentItem({ comment, duration, onSeek, small }: ItemProps) {
  const [expanded, setExpanded] = useState(false);
  const long = comment.text.length > 420 || comment.text.split("\n").length > 6;
  return (
    <div className="flex gap-3">
      <Avatar name={comment.author} small={small} />
      <div className="min-w-0 flex-1">
        {comment.is_pinned && (
          <p className="mb-0.5 flex items-center gap-1 text-[12px] text-secondary">
            <Pin className="size-3" strokeWidth={2} /> Angepinnt
          </p>
        )}
        <p className="flex flex-wrap items-center gap-x-1.5 text-[13px]">
          <span
            className={cn(
              "font-semibold",
              comment.author_is_uploader && "rounded-full bg-surface px-2 py-0.5",
            )}
          >
            {comment.author}
          </span>
          {comment.author_is_verified && (
            <BadgeCheck
              className="size-3.5 text-secondary"
              strokeWidth={2}
              aria-label="Bestätigt"
            />
          )}
          {comment.published_at && (
            <time dateTime={comment.published_at} className="text-tertiary">
              {formatRelative(comment.published_at)}
            </time>
          )}
        </p>
        <p
          className={cn(
            "mt-0.5 text-[14px] leading-relaxed break-words whitespace-pre-line",
            !expanded && long && "line-clamp-6",
          )}
        >
          <RichText text={comment.text} duration={duration} onSeek={onSeek} />
        </p>
        {long && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-[13px] font-medium text-secondary hover:text-primary"
          >
            {expanded ? "Weniger" : "Mehr"}
          </button>
        )}
        {(Boolean(comment.like_count) || comment.is_favorited) && (
          <p className="mt-1.5 flex items-center gap-4 text-[13px] text-secondary">
            {Boolean(comment.like_count) && (
              <span className="flex items-center gap-1.5">
                <ThumbsUp className="size-3.5" strokeWidth={2} />
                <span className="tabular-nums">{formatCount(comment.like_count)}</span>
                <span className="sr-only">Likes</span>
              </span>
            )}
            {comment.is_favorited && (
              <span className="flex items-center gap-1.5">
                <Heart className="size-3.5 fill-danger text-danger" strokeWidth={2} />
                vom Ersteller
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

function Thread({
  thread,
  duration,
  onSeek,
}: Omit<ItemProps, "comment"> & { thread: CommentThread }) {
  const [open, setOpen] = useState(false);
  const count = thread.replies.length;
  return (
    <li>
      <CommentItem comment={thread} duration={duration} onSeek={onSeek} />
      {count > 0 && (
        <div className="mt-1 pl-12">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex items-center gap-1 rounded-full py-1 text-[13px] font-medium text-accent"
          >
            <ChevronDown
              className={cn("size-4 transition-transform duration-200", open && "rotate-180")}
              strokeWidth={2}
            />
            {count === 1 ? "1 Antwort" : `${count} Antworten`}
          </button>
          {open && (
            <ul className="mt-2 flex flex-col gap-4">
              {thread.replies.map((reply) => (
                <li key={reply.id}>
                  <CommentItem comment={reply} duration={duration} onSeek={onSeek} small />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

/** Comments saved with the video – read without YouTube. */
export function Comments({ video, onSeek }: { video: VideoDetail; onSeek: (s: number) => void }) {
  const [sort, setSort] = useState<Sort>("top");
  const canAdd = useCanAdd();
  const isAdmin = useAuth().user?.is_admin ?? false;
  const { items, info, fetchNextPage, hasNextPage, isFetchingNextPage } = useComments(
    video.id,
    sort,
  );
  const load = useFetchComments(video.id);
  const remove = useDeleteComments(video.id);

  if (!info) return null;
  const saved = info.fetched_at !== null;
  // Nothing saved and nothing this account could do about it: no section at all.
  if (!saved && !info.fetching && !info.error && !canAdd) return null;
  const count = info.comment_count ?? info.saved;
  const busy = info.fetching || load.isPending;

  return (
    <section aria-labelledby="comments-heading" className="mt-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="comments-heading" className="text-[20px] font-semibold tracking-tight">
          Kommentare
          {saved && count > 0 && (
            <span className="ml-2 font-normal text-secondary tabular-nums">
              {formatCount(count)}
            </span>
          )}
        </h2>
        {saved && info.total > 0 && (
          <div className="flex items-center gap-1">
            <SegmentedControl
              label="Sortierung"
              value={sort}
              onChange={setSort}
              options={[
                { value: "top", label: "Beliebt" },
                { value: "new", label: "Neu" },
              ]}
            />
            {canAdd && (
              <IconButton
                label="Kommentare neu laden"
                onClick={() => load.mutate()}
                disabled={busy}
              >
                <RefreshCw className={cn("size-4", busy && "animate-spin")} strokeWidth={2} />
              </IconButton>
            )}
          </div>
        )}
      </div>

      {info.fetching && (
        <p className="mb-4 flex items-center gap-2 text-[14px] text-secondary">
          <Spinner className="size-4" /> Kommentare werden von YouTube geladen …
        </p>
      )}
      {info.error && !info.fetching && (
        <p className="mb-4 rounded-xl bg-danger/10 px-4 py-3 text-[14px] text-danger">
          {info.error}
        </p>
      )}

      {!saved && !info.fetching && (
        <div className="flex flex-col items-start gap-3 rounded-2xl bg-elevated p-5">
          <p className="flex items-center gap-2 text-[15px] text-secondary">
            <MessageSquare className="size-4" strokeWidth={2} />
            Für dieses Video sind keine Kommentare gespeichert.
          </p>
          {canAdd && (
            <Button variant="secondary" size="sm" loading={busy} onClick={() => load.mutate()}>
              Kommentare laden
            </Button>
          )}
        </div>
      )}

      {saved && info.total === 0 && !info.fetching && (
        <p className="rounded-2xl bg-elevated p-5 text-[15px] text-secondary">
          Keine Kommentare – vielleicht sind sie bei diesem Video abgeschaltet.
        </p>
      )}

      {items.length > 0 && (
        <ul className="flex flex-col gap-6">
          {items.map((thread) => (
            <Thread key={thread.id} thread={thread} duration={video.duration_s} onSeek={onSeek} />
          ))}
        </ul>
      )}

      {hasNextPage && (
        <div className="mt-6 flex justify-center">
          <Button
            variant="secondary"
            loading={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            Weitere Kommentare
          </Button>
        </div>
      )}

      {saved && (
        <p className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-tertiary">
          <span>
            {formatCount(info.saved)} gespeichert am {formatDate(info.fetched_at)}
          </span>
          {isAdmin && (
            <button
              type="button"
              className="text-tertiary underline-offset-2 hover:text-danger hover:underline"
              onClick={() => {
                if (window.confirm("Gespeicherte Kommentare dieses Videos löschen?")) {
                  remove.mutate();
                }
              }}
            >
              Löschen
            </button>
          )}
        </p>
      )}
    </section>
  );
}
