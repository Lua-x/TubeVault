import { Folder as FolderIcon, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { useCreateFolder, useFolders } from "@/api/queries";
import { FOLDER_GRID, FolderCard } from "@/components/folders/FolderCard";
import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { PlaylistNameDialog } from "@/components/playlists/PlaylistNameDialog";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function FoldersPage() {
  useDocumentTitle("Ordner");
  const { data: folders, isLoading } = useFolders();
  const create = useCreateFolder();
  const [naming, setNaming] = useState(false);
  const navigate = useNavigate();
  const top = (folders ?? []).filter((folder) => folder.parent_id == null);

  const submit = async (name: string) => {
    try {
      const folder = await create.mutateAsync({ name });
      setNaming(false);
      navigate(`/folders/${folder.id}`);
    } catch {
      // shown in the dialog
    }
  };

  const newButton = (
    <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={() => setNaming(true)}>
      Neuer Ordner
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Ordner"
        settingsShortcut
        add={{ label: "Neuer Ordner", onClick: () => setNaming(true) }}
        desktopActions
        actions={newButton}
      />
      <LibraryTabs />
      {isLoading ? (
        <PageSpinner />
      ) : top.length === 0 ? (
        <EmptyState
          icon={<FolderIcon className="size-7" strokeWidth={1.5} />}
          title="Noch keine Ordner"
          action={newButton}
        >
          Sortiere Videos nach deinem Geschmack – etwa „Kochen“ mit „Backen“ darin. Ein Video kann
          in mehreren Ordnern liegen. Deine Ordner siehst nur du.
        </EmptyState>
      ) : (
        <ul className={FOLDER_GRID}>
          {top.map((folder) => (
            <li key={folder.id}>
              <FolderCard folder={folder} />
            </li>
          ))}
        </ul>
      )}
      <PlaylistNameDialog
        open={naming}
        title="Neuer Ordner"
        submitLabel="Erstellen"
        loading={create.isPending}
        error={create.error?.message}
        onSubmit={(name) => void submit(name)}
        onClose={() => setNaming(false)}
      />
    </>
  );
}
