import { UsersRound } from "lucide-react";

import { useChannels } from "@/api/queries";
import { ChannelTile } from "@/components/channels/ChannelTile";
import { LibraryTabs } from "@/components/layout/LibraryTabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function ChannelsPage() {
  useDocumentTitle("Kanäle");
  const { data: channels, isLoading } = useChannels();
  return (
    <>
      <PageHeader
        title="Kanäle"
        subtitle={
          channels ? `${channels.length} ${channels.length === 1 ? "Kanal" : "Kanäle"}` : undefined
        }
        settingsShortcut
      />
      <LibraryTabs />
      {isLoading ? (
        <PageSpinner />
      ) : !channels || channels.length === 0 ? (
        <EmptyState
          icon={<UsersRound className="size-7" strokeWidth={1.5} />}
          title="Noch keine Kanäle"
        >
          Sobald Videos in der Bibliothek sind, erscheinen ihre Kanäle hier.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-6 min-[520px]:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8">
          {channels.map((channel) => (
            <li key={channel.id}>
              <ChannelTile channel={channel} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
