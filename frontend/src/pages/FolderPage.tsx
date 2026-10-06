import { ArrowLeft, ChevronRight, FolderInput, FolderPlus, Pencil, Trash2 } from "lucide-react";
import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  useCreateFolder,
  useDeleteFolder,
  useFolder,
  useRemoveFromFolder,
  useUpdateFolder,
} from "@/api/queries";
import { FOLDER_GRID, FolderCard } from "@/components/folders/FolderCard";
import { MoveFolderDialog } from "@/components/folders/MoveFolderDialog";
import { folderMeta } from "@/components/folders/tree";
import { PlaylistNameDialog } from "@/components/playlists/PlaylistNameDialog";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { VideoGrid } from "@/components/video/VideoGrid";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import type { FolderDetail } from "@/lib/types";

export function FolderPage() {
  const { id } = useParams();
  const { data: folder, isLoading, error } = useFolder(Number(id));
  useDocumentTitle(folder?.name);

  if (isLoading) return <PageSpinner />;
  if (error || !folder) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Ordner nicht gefunden"
      >
        <Link to="/folders" className="text-accent hover:underline">
          Zu den Ordnern
        </Link>
      </EmptyState>
    );
  }
  return <FolderView key={folder.id} folder={folder} />;
}

type Dialogs = "subfolder" | "rename" | "move" | "delete" | null;

function FolderView({ folder }: { folder: FolderDetail }) {
  const [dialog, setDialog] = useState<Dialogs>(null);
  const create = useCreateFolder();
  const update = useUpdateFolder();
  const destroy = useDeleteFolder();
  const remove = useRemoveFromFolder();
  const navigate = useNavigate();
  const toast = useToast();
  const close = () => setDialog(null);
  const up = folder.path.at(-1);

  return (
    <div className="pb-12">
      <nav aria-label="Pfad" className="mb-4 flex flex-wrap items-center gap-1 text-[14px]">
        <Link to="/folders" className="text-secondary transition-colors hover:text-primary">
          Ordner
        </Link>
        {folder.path.map((crumb) => (
          <Fragment key={crumb.id}>
            <ChevronRight className="size-3.5 text-tertiary" strokeWidth={2} aria-hidden />
            <Link
              to={`/folders/${crumb.id}`}
              className="max-w-[12rem] truncate text-secondary transition-colors hover:text-primary"
            >
              {crumb.name}
            </Link>
          </Fragment>
        ))}
      </nav>

      <header className="mb-8">
        <p className="text-[13px] font-semibold tracking-wide text-accent uppercase">Ordner</p>
        <h1 className="mt-1 text-[28px] leading-tight font-bold tracking-tight sm:text-[34px]">
          {folder.name}
        </h1>
        <p className="mt-1 text-[15px] text-secondary">{folderMeta(folder)}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button
            variant="secondary"
            icon={<FolderPlus className="size-4" strokeWidth={2} />}
            onClick={() => setDialog("subfolder")}
          >
            Neuer Ordner
          </Button>
          <Button
            variant="secondary"
            icon={<Pencil className="size-4" strokeWidth={2} />}
            onClick={() => setDialog("rename")}
          >
            Umbenennen
          </Button>
          <Button
            variant="secondary"
            icon={<FolderInput className="size-4" strokeWidth={2} />}
            onClick={() => setDialog("move")}
          >
            Verschieben
          </Button>
          <Button
            variant="danger"
            icon={<Trash2 className="size-4" strokeWidth={2} />}
            onClick={() => setDialog("delete")}
          >
            Löschen
          </Button>
        </div>
      </header>

      {folder.folders.length > 0 && (
        <section aria-labelledby="subfolders" className="mb-10">
          <h2 id="subfolders" className="sr-only">
            Ordner
          </h2>
          <ul className={FOLDER_GRID}>
            {folder.folders.map((sub) => (
              <li key={sub.id}>
                <FolderCard folder={sub} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {folder.videos.length > 0 ? (
        <section aria-labelledby="folder-videos">
          <h2 id="folder-videos" className="mb-4 text-[20px] font-semibold tracking-tight">
            Videos
          </h2>
          <VideoGrid
            videos={folder.videos}
            heading="h3"
            removeLabel="Aus dem Ordner nehmen"
            onRemove={(video) =>
              remove.mutate(
                { id: folder.id, videoId: video.id },
                { onSuccess: () => toast("Aus dem Ordner genommen") },
              )
            }
          />
        </section>
      ) : (
        folder.folders.length === 0 && (
          <p className="rounded-2xl bg-elevated p-8 text-center text-[15px] text-secondary">
            Noch leer. Öffne ein Video und lege es mit „In Ordner“ hier ab.
          </p>
        )
      )}

      <PlaylistNameDialog
        open={dialog === "subfolder"}
        title={`Neuer Ordner in „${folder.name}“`}
        submitLabel="Erstellen"
        loading={create.isPending}
        error={create.error?.message}
        onSubmit={(name) =>
          create.mutate(
            { name, parent_id: folder.id },
            {
              onSuccess: (created) => {
                close();
                navigate(`/folders/${created.id}`);
              },
            },
          )
        }
        onClose={close}
      />
      <PlaylistNameDialog
        open={dialog === "rename"}
        title="Ordner umbenennen"
        submitLabel="Speichern"
        initialName={folder.name}
        loading={update.isPending}
        error={update.error?.message}
        onSubmit={(name) => update.mutate({ id: folder.id, name }, { onSuccess: close })}
        onClose={close}
      />
      <MoveFolderDialog open={dialog === "move"} onClose={close} folder={folder} />
      <Dialog open={dialog === "delete"} onClose={close} title="Ordner löschen?">
        <p className="text-[15px] text-secondary">
          „{folder.name}“{folder.folder_count > 0 ? " und die Ordner darin werden" : " wird"}{" "}
          gelöscht. Die Videos bleiben in der Bibliothek.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={close}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger-fill hover:bg-danger-fill/90"
            loading={destroy.isPending}
            onClick={() =>
              destroy.mutate(folder.id, {
                onSuccess: () => navigate(up ? `/folders/${up.id}` : "/folders", { replace: true }),
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
