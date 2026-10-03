import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl } from "@/lib/base";

/** After asking TubeVault to restart: wait until it answers again, then load the page fresh. */
export function useAwaitRestart() {
  const [restarting, setRestarting] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  const begin = useCallback(() => {
    setRestarting(true);
    const started = Date.now();
    timer.current = window.setInterval(() => {
      void fetch(apiUrl("health"), { cache: "no-store" })
        .then((response) => {
          if (response.ok && Date.now() - started > 2000) {
            window.clearInterval(timer.current);
            window.location.reload();
          }
        })
        .catch(() => undefined);
    }, 1000);
  }, []);

  return { restarting, begin };
}
