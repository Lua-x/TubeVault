import { Check, Folder as FolderIcon, FolderOpen } from "lucide-react";

import { useFolders, useUpdateFolder } from "@/api/queries";
import { Dialog } from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { Folder } from "@/lib/types";

import { folderTree, withDescendants } from "./tree";

interface MoveFolderDialogProps {
  open: boolean;
  onClose: () => void;
  folder: Folder;
}

/** Pick where a folder goes: to the top or into another folder (never into itself). */
export function MoveFolderDialog({ open, onClose, folder }: MoveFolderDialogProps) {
  const { data: folders, isLoading } = useFolders();
  const update = useUpdateFolder();
  const toast = useToast();
  const blocked = withDescendants(folders ?? [], folder.id);

  const move = (parentId: number | null) => {
    if (parentId === folder.parent_id) return onClose();
    update.mutate(
      { id: folder.id, parent_id: parentId },
      {
        onSuccess: () => {
          toast("Verschoben");
          onClose();
        },
        onError: (err) => toast(err.message, "error"),
      },
    );
  };

  const row = (label: string, parentId: number | null, depth: number, top = false) => {
    const current = parentId === folder.parent_id;
    const Icon = top ? FolderOpen : FolderIcon;
    return (
      <button
        type="button"
        onClick={() => move(parentId)}
        disabled={update.isPending}
        className="flex w-full items-center gap-3 rounded-xl py-2.5 pr-2 text-left text-[15px] hover:bg-surface/60"
        style={{ paddingLeft: `${8 + depth * 20}px` }}
      >
        <Icon className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
        <span className={cn("min-w-0 flex-1 truncate", current && "font-medium")}>{label}</span>
        {current && <Check className="size-4 text-accent" strokeWidth={2.5} aria-label="Hier" />}
      </button>
    );
  };

  return (
    <Dialog open={open} onClose={onClose} title={`„${folder.name}“ verschieben nach …`}>
      {isLoading ? (
        <div className="flex justify-center py-8 text-secondary">
          <Spinner />
        </div>
      ) : (
        <ul className="-mx-2 flex max-h-[60dvh] flex-col gap-0.5 overflow-y-auto">
          <li>{row("Ordner (ganz oben)", null, 0, true)}</li>
          {folderTree(folders ?? [])
            .filter(({ folder: f }) => !blocked.has(f.id))
            .map(({ folder: f, depth }) => (
              <li key={f.id}>{row(f.name, f.id, depth + 1)}</li>
            ))}
        </ul>
      )}
    </Dialog>
  );
}
