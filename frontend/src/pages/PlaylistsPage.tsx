import { ListVideo, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useCreatePlaylist, usePlaylists } from "@/api/queries";
import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { PlaylistCover } from "@/components/playlists/PlaylistCover";
import { PlaylistNameDialog } from "@/components/playlists/PlaylistNameDialog";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDuration } from "@/lib/format";
import type { Playlist } from "@/lib/types";

export function PlaylistsPage() {
  useDocumentTitle("Playlists");
  const { data: playlists, isLoading } = usePlaylists();
  const create = useCreatePlaylist();
  const [naming, setNaming] = useState(false);
  const navigate = useNavigate();

  const submit = async (name: string) => {
    try {
      const playlist = (await create.mutateAsync({ name })) as Playlist;
      setNaming(false);
      navigate(`/playlists/${playlist.id}`);
    } catch {
      // shown in the dialog
    }
  };

  return (
    <>
      <PageHeader
        title="Playlists"
        settingsShortcut
        add={{ label: "Neue Playlist", onClick: () => setNaming(true) }}
        desktopActions
        actions={
          <Button
            icon={<Plus className="size-4" strokeWidth={2.25} />}
            onClick={() => setNaming(true)}
          >
            Neue Playlist
          </Button>
        }
      />
      <LibraryTabs />
      {isLoading ? (
        <PageSpinner />
      ) : !playlists ? (
        <EmptyState
          icon={<ListVideo className="size-7" strokeWidth={1.5} />}
          title="Noch keine Playlists"
          action={
            <Button
              icon={<Plus className="size-4" strokeWidth={2.25} />}
              onClick={() => setNaming(true)}
            >
              Neue Playlist
            </Button>
          }
        >
          Stelle Videos in deiner eigenen Reihenfolge zusammen – sie laufen dann nacheinander.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-x-5 gap-y-8 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {playlists.map((playlist) => (
            <li key={playlist.id}>
              <Link
                to={playlist.is_watch_later ? "/later" : `/playlists/${playlist.id}`}
                className="group flex flex-col gap-3"
              >
                <PlaylistCover
                  videos={playlist.cover}
                  watchLater={playlist.is_watch_later}
                  className="w-full shadow-[0_0_0_1px_var(--tv-separator)] transition-[transform,box-shadow] duration-300 ease-out-soft group-hover:scale-[1.03] group-hover:shadow-card"
                />
                <div className="px-0.5">
                  <h3 className="truncate text-[15px] font-medium">{playlist.name}</h3>
                  <p className="text-[13px] text-secondary">
                    {playlist.video_count} {playlist.video_count === 1 ? "Video" : "Videos"}
                    {playlist.duration_s ? ` · ${formatDuration(playlist.duration_s)}` : ""}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {playlists && playlists.every((playlist) => playlist.is_watch_later) && (
        <p className="mt-10 max-w-md px-0.5 text-[15px] text-secondary">
          Stelle Videos in deiner eigenen Reihenfolge zusammen – sie laufen dann nacheinander. Mit
          „Neue Playlist“ geht's los.
        </p>
      )}
      <PlaylistNameDialog
        open={naming}
        title="Neue Playlist"
        submitLabel="Erstellen"
        loading={create.isPending}
        error={create.error?.message}
        onSubmit={(name) => void submit(name)}
        onClose={() => setNaming(false)}
      />
    </>
  );
}
