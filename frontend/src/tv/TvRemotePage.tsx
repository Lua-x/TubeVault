import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router";
import { renderSVG } from "uqr";

import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { basePath } from "@/lib/base";

import { useInitialFocus, useTvNavigation } from "./navigation";
import { useRemoteReceiver } from "./remote";

/** "Handy verbinden": the code (and a QR code) a phone pairs with. */
export function TvRemotePage() {
  useDocumentTitle("Handy verbinden");
  const navigate = useNavigate();
  const receiver = useRemoteReceiver();
  const back = useCallback(() => navigate(-1), [navigate]);
  useTvNavigation({ onBack: back });
  useInitialFocus(true);
  const code = receiver?.code ?? null;
  const link = code ? `${window.location.origin}${basePath()}remote?code=${code}` : null;
  const qr = useMemo(
    () => (link ? renderSVG(link, { border: 2, whiteColor: "#fff", blackColor: "#000" }) : ""),
    [link],
  );
  const buttonClass =
    "rounded-full bg-surface px-[1.6vw] py-[0.7vw] text-[max(16px,1.1vw)] font-medium text-secondary outline-none focus:bg-primary focus:text-canvas";

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-[2.5vw] bg-canvas px-[4vw] text-primary">
      <h1 className="text-[max(32px,2.8vw)] font-bold tracking-tight">Handy verbinden</h1>
      <div className="flex flex-wrap items-center justify-center gap-[4vw]">
        <div
          className="size-[max(14rem,18vw)] overflow-hidden rounded-3xl bg-white p-3"
          aria-hidden
          // The QR code is made here from our own text – no outside markup.
          dangerouslySetInnerHTML={{ __html: qr }}
        />
        <div className="flex max-w-[34vw] flex-col gap-[1.2vw]">
          <p className="text-[max(18px,1.3vw)] text-secondary">
            Kamera auf den Code richten – oder in TubeVault auf dem Handy „Fernbedienung“ öffnen und
            diese Zahl eingeben:
          </p>
          <p
            className="font-mono text-[max(44px,4.5vw)] font-semibold tracking-[0.15em] tabular-nums"
            aria-label={code ? `Code ${code.split("").join(" ")}` : "Code wird erzeugt"}
          >
            {code ? `${code.slice(0, 3)} ${code.slice(3)}` : "··· ···"}
          </p>
          <p className="text-[max(15px,1vw)] text-tertiary">Gilt 10 Minuten.</p>
          {receiver && receiver.phones.length > 0 && (
            <p className="text-[max(17px,1.2vw)] text-success">
              Verbunden: {receiver.phones.map((p) => p.name).join(", ")}
            </p>
          )}
        </div>
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          data-tv-focus
          data-tv-key="video-remote-done"
          onClick={back}
          className={buttonClass}
        >
          Fertig
        </button>
        <button
          type="button"
          data-tv-focus
          data-tv-key="remote-new-code"
          onClick={() => receiver?.newCode()}
          className={buttonClass}
        >
          Neuer Code
        </button>
        {receiver && receiver.phones.length > 0 && (
          <button
            type="button"
            data-tv-focus
            data-tv-key="remote-unpair"
            onClick={() => receiver.unpair()}
            className={buttonClass}
          >
            Handys trennen
          </button>
        )}
      </div>
    </main>
  );
}
