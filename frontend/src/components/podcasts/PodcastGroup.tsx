import { useState } from "react";

import { useDisablePodcasts, usePodcastAccess, useRenewPodcastAddress } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";

/** Settings: the personal podcast address – create, renew, switch off. */
export function PodcastGroup() {
  const { data: access } = usePodcastAccess();
  const renew = useRenewPodcastAddress();
  const disable = useDisablePodcasts();
  const [confirm, setConfirm] = useState<"renew" | "off" | null>(null);
  if (!access) return null;

  return (
    <Group
      title="Podcasts"
      footer="Kanäle und Playlists lassen sich als Podcast abonnieren („Als Podcast“ auf ihrer Seite). Die Adresse enthält einen persönlichen Schlüssel, der nur diese Feeds öffnet."
    >
      <Row className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[15px]">Podcast-Adresse</p>
          <p className="text-[13px] text-secondary">
            {access.enabled ? "Eingeschaltet" : "Aus – wird beim ersten „Als Podcast“ erstellt"}
          </p>
        </div>
        <div className="flex gap-2">
          {access.enabled ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setConfirm("renew")}>
                Erneuern
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setConfirm("off")}>
                Ausschalten
              </Button>
            </>
          ) : (
            <Button size="sm" loading={renew.isPending} onClick={() => renew.mutate()}>
              Erstellen
            </Button>
          )}
        </div>
      </Row>
      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title={confirm === "renew" ? "Neue Podcast-Adresse?" : "Podcasts ausschalten?"}
      >
        <p className="text-[15px] text-secondary">
          {confirm === "renew"
            ? "Die bisherigen Adressen funktionieren danach nicht mehr – in der Podcast-App musst du die Feeds neu hinzufügen."
            : "Alle Podcast-Feeds hören sofort auf zu funktionieren."}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirm(null)}>
            Abbrechen
          </Button>
          <Button
            className={confirm === "off" ? "bg-danger hover:bg-danger/90" : undefined}
            loading={renew.isPending || disable.isPending}
            onClick={() => {
              const done = { onSuccess: () => setConfirm(null) };
              if (confirm === "renew") renew.mutate(undefined, done);
              else disable.mutate(undefined, done);
            }}
          >
            {confirm === "renew" ? "Erneuern" : "Ausschalten"}
          </Button>
        </div>
      </Dialog>
    </Group>
  );
}
