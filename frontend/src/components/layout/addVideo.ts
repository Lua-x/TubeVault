import { createContext, useContext } from "react";

/** Opens the "add video" dialog, optionally with a link filled in. */
export type OpenAddVideo = (url?: unknown) => void;

export const AddVideoContext = createContext<OpenAddVideo>(() => undefined);

export function useOpenAddVideo(): OpenAddVideo {
  return useContext(AddVideoContext);
}
