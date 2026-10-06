import { describe, expect, it } from "vitest";

import type { Folder } from "@/lib/types";

import { folderMeta, folderTree, withDescendants } from "./tree";

const folder = (id: number, name: string, parent_id: number | null = null): Folder => ({
  id,
  name,
  parent_id,
  created_at: "",
  updated_at: "",
  video_count: 0,
  folder_count: 0,
  cover: [],
  contains: null,
});

const FOLDERS = [
  folder(1, "Technik"),
  folder(2, "Kochen"),
  folder(3, "Backen", 2),
  folder(4, "Brot", 3),
  folder(5, "Asiatisch", 2),
];

describe("folder tree", () => {
  it("lists every folder before the ones inside it, by name", () => {
    expect(folderTree(FOLDERS).map(({ folder: f, depth }) => `${depth}:${f.name}`)).toEqual([
      "0:Kochen",
      "1:Asiatisch",
      "1:Backen",
      "2:Brot",
      "0:Technik",
    ]);
  });

  it("knows where a folder can't go", () => {
    expect([...withDescendants(FOLDERS, 2)].sort()).toEqual([2, 3, 4, 5]);
    expect([...withDescendants(FOLDERS, 1)]).toEqual([1]);
  });

  it("names what is inside", () => {
    expect(folderMeta({ ...folder(1, "x"), video_count: 1 })).toBe("1 Video");
    expect(folderMeta({ ...folder(1, "x"), folder_count: 2, video_count: 5 })).toBe(
      "2 Ordner · 5 Videos",
    );
  });
});
