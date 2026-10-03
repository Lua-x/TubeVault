import { Check, Copy, Podcast } from "lucide-react";
import { useState } from "react";

import { usePodcastAccess, useRenewPodcastAddress } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { cn } from "@/lib/cn";

interface PodcastButtonProps {
  /** Feed path below the user's podcast address, e.g. "channels/3.xml". */
  feed: string;
  title: string;
  className?: string;
}

/** "Als Podcast": the feed address for a podcast app. */
export function PodcastButton({ feed, title, className }: PodcastButtonProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const { data: access } = usePodcastAccess();
  const create = useRenewPodcastAddress();
  const url = access?.base_url ? `${access.base_url}/${feed}` : null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors hover:bg-surface-hover",
          className,
        )}
      >
        <Podcast className="size-4" strokeWidth={2} />
        Als Podcast
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Als Podcast hören">
        <p className="text-[15px] text-secondary">
          „{title}“ in deiner Podcast-App: neue Videos erscheinen dort als Folgen, nur mit Ton. Die
          App muss deinen Server erreichen – im Heimnetz oder per VPN.
        </p>
        {url ? (
          <>
            <div className="mt-5 flex items-center gap-2 rounded-xl bg-surface p-1 pl-3">
              <input
                readOnly
                value={url}
                aria-label="Feed-Adresse"
                onFocus={(e) => e.target.select()}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-secondary outline-none"
              />
              <Button
                size="sm"
                variant="secondary"
                icon={
                  copied ? (
                    <Check className="size-4" strokeWidth={2.5} />
                  ) : (
                    <Copy className="size-4" strokeWidth={2} />
                  )
                }
                onClick={() => {
                  void navigator.clipboard
                    ?.writeText(url)
                    .then(() => setCopied(true))
                    .catch(() => undefined);
                }}
              >
                {copied ? "Kopiert" : "Kopieren"}
              </Button>
            </div>
            <p className="mt-3 text-[13px] text-tertiary">
              In der Podcast-App „Podcast per Adresse hinzufügen“ wählen und die Adresse einfügen.
              Sie enthält deinen persönlichen Schlüssel – nicht weitergeben.
            </p>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <a
                href={url.replace(/^https?:\/\//, "podcast://")}
                className="inline-flex h-10 items-center rounded-full px-4 text-[15px] font-medium text-accent hover:bg-surface"
              >
                In Apple Podcasts öffnen
              </a>
              <Button onClick={() => setOpen(false)}>Fertig</Button>
            </div>
          </>
        ) : (
          <>
            <p className="mt-3 text-[15px] text-secondary">
              Dafür bekommst du eine persönliche Podcast-Adresse. Sie lässt sich jederzeit in den
              Einstellungen erneuern oder abschalten.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setOpen(false)}>
                Abbrechen
              </Button>
              <Button loading={create.isPending} onClick={() => create.mutate()}>
                Podcast-Adresse erstellen
              </Button>
            </div>
          </>
        )}
      </Dialog>
    </>
  );
}
