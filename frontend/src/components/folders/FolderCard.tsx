import { Folder as FolderIcon } from "lucide-react";
import { Link } from "react-router";

import { PlaylistCover } from "@/components/playlists/PlaylistCover";
import type { Folder } from "@/lib/types";

import { folderMeta } from "./tree";

export function FolderCard({ folder }: { folder: Folder }) {
  return (
    <Link to={`/folders/${folder.id}`} className="group flex flex-col gap-3">
      <div className="relative">
        <PlaylistCover
          videos={folder.cover}
          icon={FolderIcon}
          className="w-full shadow-[0_0_0_1px_var(--tv-separator)] transition-[transform,box-shadow] duration-300 ease-out-soft group-hover:scale-[1.03] group-hover:shadow-card"
        />
        {folder.cover.length > 0 && (
          <span className="absolute bottom-2 left-2 flex size-7 items-center justify-center rounded-lg bg-black/65 text-white backdrop-blur-md">
            <FolderIcon className="size-4" strokeWidth={2} />
          </span>
        )}
      </div>
      <div className="px-0.5">
        <h2 className="truncate text-[15px] font-medium">{folder.name}</h2>
        <p className="text-[13px] text-secondary">{folderMeta(folder)}</p>
      </div>
    </Link>
  );
}

export const FOLDER_GRID =
  "grid grid-cols-1 gap-x-5 gap-y-8 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4";
