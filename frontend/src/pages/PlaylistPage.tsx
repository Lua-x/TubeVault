import { ArrowLeft, GripVertical, Headphones, Pencil, Play, Trash2, X } from "lucide-react";
import { Reorder, useDragControls } from "motion/react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  useDeletePlaylist,
  usePlaylist,
  useWatchLater,
  useRemoveFromPlaylist,
  useReorderPlaylist,
  useUpdatePlaylist,
} from "@/api/queries";
import { trackFromVideo, useAudioPlayer } from "@/audio/context";
import { SaveAllToDevice } from "@/components/offline/SaveAllToDevice";
import { PodcastButton } from "@/components/podcasts/PodcastButton";
import { PlaylistCover } from "@/components/playlists/PlaylistCover";
import { PlaylistNameDialog } from "@/components/playlists/PlaylistNameDialog";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { Thumbnail } from "@/components/video/Thumbnail";
import { WatchOverlay } from "@/components/video/WatchOverlay";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDuration } from "@/lib/format";
import type { PlaylistDetail, VideoSummary } from "@/lib/types";

export function PlaylistPage() {
  const { id } = useParams();
  const playlistId = Number(id);
  const { data: playlist, isLoading, error } = usePlaylist(playlistId);
  useDocumentTitle(playlist?.name);

  if (isLoading) return <PageSpinner />;
  if (error || !playlist) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Playlist nicht gefunden"
      >
        <Link to="/playlists" className="text-accent hover:underline">
          Zu den Playlists
        </Link>
      </EmptyState>
    );
  }
  return <PlaylistView key={playlist.id} playlist={playlist} />;
}

/** "Später ansehen": the built-in playlist, at /later. */
export function WatchLaterPage() {
  const { data: playlist, isLoading } = useWatchLater();
  useDocumentTitle("Später ansehen");
  if (isLoading || !playlist) return <PageSpinner />;
  return <PlaylistView key={playlist.id} playlist={playlist} />;
}

function PlaylistView({ playlist }: { playlist: PlaylistDetail }) {
  const [order, setOrder] = useState(playlist.videos);
  const [syncedFrom, setSyncedFrom] = useState(playlist.videos);
  if (syncedFrom !== playlist.videos) {
    setSyncedFrom(playlist.videos);
    setOrder(playlist.videos);
  }
  const reorder = useReorderPlaylist();
  const remove = useRemoveFromPlaylist();
  const update = useUpdatePlaylist();
  const destroy = useDeletePlaylist();
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const audio = useAudioPlayer();

  const first = order.find((v) => !v.progress?.watched) ?? order[0];
  const saveOrder = () => {
    const ids = order.map((v) => v.id);
    if (ids.join() !== playlist.videos.map((v) => v.id).join()) {
      reorder.mutate({ id: playlist.id, videoIds: ids });
    }
  };

  return (
    <div className="pb-12">
      <Link
        to="/playlists"
        className="mb-4 inline-flex items-center gap-1.5 text-[14px] text-secondary transition-colors hover:text-primary"
      >
        <ArrowLeft className="size-4" strokeWidth={2} />
        Playlists
      </Link>

      <header className="mb-8 flex flex-col gap-6 sm:flex-row sm:items-end">
        <PlaylistCover
          videos={playlist.cover}
          watchLater={playlist.is_watch_later}
          className="w-full shadow-card sm:w-72"
        />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold tracking-wide text-accent uppercase">
            {playlist.is_watch_later ? "Deine Liste" : "Playlist"}
          </p>
          <h1 className="mt-1 text-[28px] leading-tight font-bold tracking-tight sm:text-[34px]">
            {playlist.name}
          </h1>
          <p className="mt-1 text-[15px] text-secondary">
            {playlist.video_count} {playlist.video_count === 1 ? "Video" : "Videos"}
            {playlist.duration_s ? ` · ${formatDuration(playlist.duration_s)}` : ""}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {first && (
              <Button
                icon={<Play className="size-4 fill-current" strokeWidth={0} />}
                onClick={() => navigate(`/videos/${first.id}?playlist=${playlist.id}`)}
              >
                {first === order[0] ? "Abspielen" : "Weiterspielen"}
              </Button>
            )}
            {first && (
              <Button
                variant="secondary"
                icon={<Headphones className="size-4" strokeWidth={2} />}
                onClick={() => {
                  const start = order.indexOf(first);
                  audio.play(order.map(trackFromVideo), Math.max(0, start));
                }}
              >
                Anhören
              </Button>
            )}
            <SaveAllToDevice videos={order} />
            <PodcastButton feed={`playlists/${playlist.id}.xml`} title={playlist.name} />
            {!playlist.is_watch_later && (
              <>
                <Button
                  variant="secondary"
                  icon={<Pencil className="size-4" strokeWidth={2} />}
                  onClick={() => setRenaming(true)}
                >
                  Umbenennen
                </Button>
                <Button
                  variant="danger"
                  icon={<Trash2 className="size-4" strokeWidth={2} />}
                  onClick={() => setConfirmDelete(true)}
                >
                  Löschen
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      {order.length === 0 ? (
        <p className="rounded-2xl bg-elevated p-8 text-center text-[15px] text-secondary">
          {playlist.is_watch_later
            ? "Noch leer. Tippe bei einem Video auf „Später ansehen“ – gesehene Videos verschwinden von selbst wieder."
            : "Noch leer. Öffne ein Video und wähle „Zur Playlist“."}
        </p>
      ) : (
        <Reorder.Group
          axis="y"
          values={order}
          onReorder={setOrder}
          className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated"
        >
          {order.map((video, index) => (
            <PlaylistRow
              key={video.id}
              video={video}
              index={index}
              playlistId={playlist.id}
              onDragEnd={saveOrder}
              onRemove={() =>
                remove.mutate(
                  { id: playlist.id, videoId: video.id },
                  { onSuccess: () => toast("Aus der Playlist entfernt") },
                )
              }
            />
          ))}
        </Reorder.Group>
      )}

      <PlaylistNameDialog
        open={renaming}
        title="Playlist umbenennen"
        submitLabel="Speichern"
        initialName={playlist.name}
        loading={update.isPending}
        error={update.error?.message}
        onSubmit={(name) =>
          update.mutate({ id: playlist.id, name }, { onSuccess: () => setRenaming(false) })
        }
        onClose={() => setRenaming(false)}
      />
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Playlist löschen?"
      >
        <p className="text-[15px] text-secondary">
          „{playlist.name}“ wird gelöscht. Die Videos bleiben in der Bibliothek.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger hover:bg-danger/90"
            loading={destroy.isPending}
            onClick={() =>
              destroy.mutate(playlist.id, {
                onSuccess: () => navigate("/playlists", { replace: true }),
              })
            }
          >
            Löschen
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

interface PlaylistRowProps {
  video: VideoSummary;
  index: number;
  playlistId: number;
  onDragEnd: () => void;
  onRemove: () => void;
}

function PlaylistRow({ video, index, playlistId, onDragEnd, onRemove }: PlaylistRowProps) {
  const controls = useDragControls();
  return (
    <Reorder.Item
      value={video}
      dragListener={false}
      dragControls={controls}
      onDragEnd={onDragEnd}
      className="relative flex items-center gap-3 bg-elevated px-2 py-2.5 sm:px-3"
    >
      <button
        type="button"
        aria-label="Verschieben"
        onPointerDown={(e) => controls.start(e)}
        className="flex size-8 shrink-0 cursor-grab touch-none items-center justify-center rounded-lg text-tertiary hover:text-primary active:cursor-grabbing"
      >
        <GripVertical className="size-4" strokeWidth={2} />
      </button>
      <span className="w-5 shrink-0 text-right text-[13px] text-tertiary tabular-nums">
        {index + 1}
      </span>
      <Link
        to={`/videos/${video.id}?playlist=${playlistId}`}
        className="flex min-w-0 flex-1 items-center gap-3"
        draggable={false}
      >
        <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded-lg sm:w-36">
          <Thumbnail video={video} className="size-full" />
          <WatchOverlay video={video} />
        </div>
        <div className="min-w-0">
          <p className="line-clamp-2 text-[15px] leading-snug font-medium">{video.title}</p>
          <p className="truncate text-[13px] text-secondary">
            {[video.channel?.name, formatDuration(video.duration_s)].filter(Boolean).join(" · ")}
          </p>
        </div>
      </Link>
      <IconButton label="Aus der Playlist entfernen" onClick={onRemove}>
        <X className="size-[18px]" strokeWidth={1.75} />
      </IconButton>
    </Reorder.Item>
  );
}
