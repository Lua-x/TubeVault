import type { Folder } from "@/lib/types";

/** The folders as an indented list: every folder followed by the ones inside it. */
export function folderTree(folders: Folder[]): { folder: Folder; depth: number }[] {
  const byParent = new Map<number | null, Folder[]>();
  for (const folder of folders) {
    const siblings = byParent.get(folder.parent_id) ?? [];
    siblings.push(folder);
    byParent.set(folder.parent_id, siblings);
  }
  const ordered: { folder: Folder; depth: number }[] = [];
  const visit = (parent: number | null, depth: number) => {
    const children = [...(byParent.get(parent) ?? [])].sort((a, b) =>
      a.name.localeCompare(b.name, "de", { sensitivity: "base" }),
    );
    for (const folder of children) {
      ordered.push({ folder, depth });
      visit(folder.id, depth + 1);
    }
  };
  visit(null, 0);
  return ordered;
}

/** The folder and everything inside it – where it can't be moved to. */
export function withDescendants(folders: Folder[], id: number): Set<number> {
  const found = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const folder of folders) {
      if (folder.parent_id != null && found.has(folder.parent_id) && !found.has(folder.id)) {
        found.add(folder.id);
        grew = true;
      }
    }
  }
  return found;
}

export function folderMeta(folder: Folder): string {
  const parts = [];
  if (folder.folder_count) parts.push(`${folder.folder_count} Ordner`);
  parts.push(`${folder.video_count} ${folder.video_count === 1 ? "Video" : "Videos"}`);
  return parts.join(" · ");
}
