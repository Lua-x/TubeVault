import { Plus, Tv } from "lucide-react";
import { useState } from "react";

import { useSubscriptions } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { SubscribeDialog } from "@/components/subscriptions/SubscribeDialog";
import { SubscriptionCard } from "@/components/subscriptions/SubscriptionCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function SubscriptionsPage() {
  useDocumentTitle("Abos");
  const { data: subs, isLoading } = useSubscriptions();
  const [open, setOpen] = useState(false);
  const openDialog = () => setOpen(true);

  const channels = subs?.filter((s) => s.kind === "channel").length ?? 0;
  const playlists = (subs?.length ?? 0) - channels;
  const subtitle = subs?.length
    ? [
        channels ? `${channels} ${channels === 1 ? "Kanal" : "Kanäle"}` : null,
        playlists ? `${playlists} ${playlists === 1 ? "Playlist" : "Playlists"}` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : undefined;

  return (
    <>
      <PageHeader
        title="Abos"
        subtitle={subtitle}
        add={{ label: "Abonnieren", onClick: openDialog }}
        desktopActions
        actions={
          subs && subs.length > 0 ? (
            <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={openDialog}>
              Abonnieren
            </Button>
          ) : undefined
        }
      />
      {isLoading ? (
        <PageSpinner />
      ) : !subs || subs.length === 0 ? (
        <EmptyState
          icon={<Tv className="size-7" strokeWidth={1.5} />}
          title="Noch keine Abos"
          action={
            <Button icon={<Plus className="size-4" strokeWidth={2.25} />} onClick={openDialog}>
              Abonnieren
            </Button>
          }
        >
          Abonniere Kanäle oder Playlists. Neue Videos werden dann automatisch geladen.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {subs.map((sub) => (
            <li key={sub.id}>
              <SubscriptionCard sub={sub} />
            </li>
          ))}
        </ul>
      )}
      <SubscribeDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}
