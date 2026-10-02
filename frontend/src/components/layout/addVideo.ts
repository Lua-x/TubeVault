import { createContext, useContext } from "react";

export const AddVideoContext = createContext<() => void>(() => undefined);

export function useOpenAddVideo(): () => void {
  return useContext(AddVideoContext);
}
