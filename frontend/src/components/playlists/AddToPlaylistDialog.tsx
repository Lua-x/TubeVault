import { Check, Plus } from "lucide-react";
import { useState } from "react";

import {
  useAddToPlaylist,
  useCreatePlaylist,
  usePlaylists,
  useRemoveFromPlaylist,
} from "@/api/queries";
import { Dialog } from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { Playlist } from "@/lib/types";

import { PlaylistCover } from "./PlaylistCover";
import { PlaylistNameDialog } from "./PlaylistNameDialog";

interface AddToPlaylistDialogProps {
  open: boolean;
  onClose: () => void;
  videoId: number;
}

export function AddToPlaylistDialog({ open, onClose, videoId }: AddToPlaylistDialogProps) {
  const { data: playlists, isLoading } = usePlaylists(open ? videoId : undefined);
  const add = useAddToPlaylist();
  const remove = useRemoveFromPlaylist();
  const create = useCreatePlaylist();
  const toast = useToast();
  const [naming, setNaming] = useState(false);

  const toggle = (playlist: Playlist) => {
    const action = playlist.contains
      ? remove.mutateAsync({ id: playlist.id, videoId })
      : add.mutateAsync({ id: playlist.id, videoId });
    action.catch((err: unknown) =>
      toast(err instanceof Error ? err.message : "Fehlgeschlagen", "error"),
    );
  };

  const createAndAdd = async (name: string) => {
    try {
      const playlist = (await create.mutateAsync({ name })) as Playlist;
      await add.mutateAsync({ id: playlist.id, videoId });
      toast(`Zu „${playlist.name}“ hinzugefügt`);
      setNaming(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Fehlgeschlagen", "error");
    }
  };

  return (
    <>
      <Dialog open={open && !naming} onClose={onClose} title="Zur Playlist hinzufügen">
        {isLoading ? (
          <div className="flex justify-center py-8 text-secondary">
            <Spinner />
          </div>
        ) : (
          <ul className="-mx-2 flex flex-col gap-1">
            <li>
              <button
                type="button"
                onClick={() => setNaming(true)}
                className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-[15px] font-medium text-accent hover:bg-surface/60"
              >
                <span className="flex aspect-video w-20 items-center justify-center rounded-lg bg-surface">
                  <Plus className="size-5" strokeWidth={2} />
                </span>
                Neue Playlist
              </button>
            </li>
            {(playlists ?? []).map((playlist) => (
              <li key={playlist.id}>
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={Boolean(playlist.contains)}
                  onClick={() => toggle(playlist)}
                  className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface/60"
                >
                  <PlaylistCover videos={playlist.cover} className="w-20 rounded-lg" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-medium">{playlist.name}</span>
                    <span className="text-[13px] text-tertiary">{playlist.video_count} Videos</span>
                  </span>
                  <span
                    className={cn(
                      "flex size-6 items-center justify-center rounded-full border transition-colors",
                      playlist.contains
                        ? "border-accent-fill bg-accent-fill text-white"
                        : "border-separator text-transparent",
                    )}
                  >
                    <Check className="size-3.5" strokeWidth={3} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
      <PlaylistNameDialog
        open={open && naming}
        title="Neue Playlist"
        submitLabel="Erstellen"
        loading={create.isPending || add.isPending}
        onSubmit={(name) => void createAndAdd(name)}
        onClose={() => setNaming(false)}
      />
    </>
  );
}
