import { Check, Folder as FolderIcon, Plus } from "lucide-react";
import { useState } from "react";

import { useAddToFolder, useCreateFolder, useFolders, useRemoveFromFolder } from "@/api/queries";
import { PlaylistNameDialog } from "@/components/playlists/PlaylistNameDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { Folder } from "@/lib/types";

import { folderTree } from "./tree";

interface AddToFolderDialogProps {
  open: boolean;
  onClose: () => void;
  videoId: number;
}

/** Tick the folders a video belongs in – a video can be in several. */
export function AddToFolderDialog({ open, onClose, videoId }: AddToFolderDialogProps) {
  const { data: folders, isLoading } = useFolders(open ? videoId : undefined);
  const add = useAddToFolder();
  const remove = useRemoveFromFolder();
  const create = useCreateFolder();
  const toast = useToast();
  const [naming, setNaming] = useState(false);

  const toggle = (folder: Folder) => {
    const action = folder.contains
      ? remove.mutateAsync({ id: folder.id, videoId })
      : add.mutateAsync({ id: folder.id, videoId });
    action.catch((err: unknown) =>
      toast(err instanceof Error ? err.message : "Fehlgeschlagen", "error"),
    );
  };

  const createAndAdd = async (name: string) => {
    try {
      const folder = await create.mutateAsync({ name });
      await add.mutateAsync({ id: folder.id, videoId });
      toast(`In „${folder.name}“ abgelegt`);
      setNaming(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Fehlgeschlagen", "error");
    }
  };

  return (
    <>
      <Dialog open={open && !naming} onClose={onClose} title="In Ordner ablegen">
        {isLoading ? (
          <div className="flex justify-center py-8 text-secondary">
            <Spinner />
          </div>
        ) : (
          <ul className="-mx-2 flex max-h-[60dvh] flex-col gap-0.5 overflow-y-auto">
            <li>
              <button
                type="button"
                onClick={() => setNaming(true)}
                className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left text-[15px] font-medium text-accent hover:bg-surface/60"
              >
                <Plus className="size-5 shrink-0" strokeWidth={2} />
                Neuer Ordner
              </button>
            </li>
            {folderTree(folders ?? []).map(({ folder, depth }) => (
              <li key={folder.id}>
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={Boolean(folder.contains)}
                  onClick={() => toggle(folder)}
                  className="flex w-full items-center gap-3 rounded-xl py-2.5 pr-2 text-left hover:bg-surface/60"
                  style={{ paddingLeft: `${8 + depth * 20}px` }}
                >
                  <FolderIcon className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-medium">{folder.name}</span>
                    <span className="text-[13px] text-tertiary">
                      {folder.video_count} {folder.video_count === 1 ? "Video" : "Videos"}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full border transition-colors",
                      folder.contains
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
        title="Neuer Ordner"
        submitLabel="Erstellen"
        loading={create.isPending || add.isPending}
        onSubmit={(name) => void createAndAdd(name)}
        onClose={() => setNaming(false)}
      />
    </>
  );
}
