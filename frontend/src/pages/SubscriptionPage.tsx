import { ArrowLeft, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  useDeleteSubscription,
  useSubscription,
  useSubscriptionAction,
  useUpdateSubscription,
} from "@/api/queries";
import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import { fromSubscription, toSettings, type FormValues } from "@/components/subscriptions/options";
import { checkStatus, ITEM_STATE_LABEL } from "@/components/subscriptions/status";
import { SubscriptionForm } from "@/components/subscriptions/SubscriptionForm";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PageSpinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn } from "@/lib/cn";
import { formatDate, formatDuration } from "@/lib/format";
import { channelImageUrl } from "@/lib/media";
import type { ItemState, SubscriptionDetail } from "@/lib/types";

export function SubscriptionPage() {
  const { id } = useParams();
  const subId = Number(id);
  const { data: sub, isLoading, error } = useSubscription(subId);
  useDocumentTitle(sub?.title);

  if (isLoading) return <PageSpinner />;
  if (error || !sub) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Abo nicht gefunden"
      >
        <Link to="/subscriptions" className="text-accent hover:underline">
          Zu den Abos
        </Link>
      </EmptyState>
    );
  }
  return <SubscriptionView key={sub.id} sub={sub} />;
}

function SubscriptionView({ sub }: { sub: SubscriptionDetail }) {
  const status = checkStatus(sub);
  const check = useSubscriptionAction(sub.id, "check");
  const toast = useToast();
  const banner = sub.kind === "channel" && sub.channel?.has_banner ? sub.channel : null;

  return (
    <div className="pb-12">
      <Link
        to="/subscriptions"
        className="mb-4 inline-flex items-center gap-1.5 text-[14px] text-secondary transition-colors hover:text-primary"
      >
        <ArrowLeft className="size-4" strokeWidth={2} />
        Abos
      </Link>

      <header className="mb-8 overflow-hidden rounded-3xl bg-elevated shadow-[0_0_0_1px_var(--tv-separator)]">
        <div className="relative h-28 bg-surface sm:h-44">
          {banner && (
            <img
              src={channelImageUrl(banner, "banner")}
              alt=""
              className="size-full object-cover"
            />
          )}
        </div>
        <div className="flex flex-col gap-4 px-5 pb-5 sm:flex-row sm:items-end sm:px-6">
          <ChannelAvatar
            channel={sub.channel}
            name={sub.title}
            kind={sub.kind}
            className="relative z-10 -mt-10 size-20 border-4 border-elevated bg-surface text-[30px] sm:-mt-12 sm:size-24"
          />
          <div className="min-w-0 flex-1">
            <h1 className="text-[26px] leading-tight font-bold tracking-tight sm:text-[30px]">
              {sub.title}
            </h1>
            <p
              className={cn(
                "mt-1 text-[14px]",
                status.tone === "danger" ? "text-danger" : "text-secondary",
              )}
            >
              {sub.kind === "channel" ? "Kanal" : "Playlist"} · {status.text}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              className="h-9 px-4 text-[14px]"
              loading={check.isPending || sub.checking}
              icon={<RefreshCw className="size-4" strokeWidth={2} />}
              onClick={() =>
                check.mutate(undefined, {
                  onSuccess: () => toast("Prüfung gestartet"),
                  onError: (e) => toast(e.message, "error"),
                })
              }
            >
              Jetzt prüfen
            </Button>
            <a
              href={sub.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex h-9 items-center gap-2 rounded-full bg-surface px-4 text-[14px] font-medium transition-colors hover:bg-surface-hover"
            >
              <ExternalLink className="size-4" strokeWidth={2} />
              YouTube
            </a>
          </div>
        </div>
      </header>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <SettingsSection sub={sub} />
        <ItemsSection sub={sub} />
      </div>
    </div>
  );
}

function SettingsSection({ sub }: { sub: SubscriptionDetail }) {
  const [values, setValues] = useState<FormValues>(() => fromSubscription(sub));
  const update = useUpdateSubscription(sub.id);
  const toast = useToast();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await update.mutateAsync(toSettings(values));
      toast("Gespeichert");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Speichern fehlgeschlagen", "error");
    }
  };

  return (
    <section aria-labelledby="settings-heading">
      <h2 id="settings-heading" className="mb-4 text-[20px] font-semibold tracking-tight">
        Einstellungen
      </h2>
      <form onSubmit={submit} className="flex flex-col gap-7">
        <SubscriptionForm mode="edit" values={values} onChange={setValues} />
        <div className="flex items-center justify-between gap-3">
          <DeleteButton sub={sub} />
          <Button type="submit" loading={update.isPending}>
            Speichern
          </Button>
        </div>
      </form>
    </section>
  );
}

function DeleteButton({ sub }: { sub: SubscriptionDetail }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [deleteVideos, setDeleteVideos] = useState(false);
  const remove = useDeleteSubscription();
  const toast = useToast();
  const navigate = useNavigate();

  const confirm = async () => {
    try {
      await remove.mutateAsync({ id: sub.id, deleteVideos });
      toast(`„${sub.title}“ nicht mehr abonniert`);
      navigate("/subscriptions", { replace: true });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Löschen fehlgeschlagen", "error");
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        className="-ml-3 text-danger"
        icon={<Trash2 className="size-4" strokeWidth={2} />}
        onClick={() => setOpen(true)}
      >
        Abo löschen
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Abo löschen?">
        <p className="text-[15px] text-secondary">
          „{sub.title}“ wird nicht mehr geprüft. Ausstehende Downloads werden abgebrochen.
        </p>
        {user?.is_admin && (
          <label className="mt-5 flex items-start gap-3 rounded-2xl bg-surface/60 p-4 text-[15px]">
            <input
              type="checkbox"
              className="mt-1 size-4 accent-[var(--tv-accent)]"
              checked={deleteVideos}
              onChange={(e) => setDeleteVideos(e.target.checked)}
            />
            <span>
              Auch die {sub.stats.downloaded} heruntergeladenen Videos löschen
              <span className="block text-[13px] text-secondary">
                Videos, die du von Hand hinzugefügt hast oder die ein anderes Abo behält, bleiben
                erhalten.
              </span>
            </span>
          </label>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger-fill hover:bg-danger-fill/90"
            loading={remove.isPending}
            onClick={() => void confirm()}
          >
            Löschen
          </Button>
        </div>
      </Dialog>
    </>
  );
}

type ItemFilter = "all" | ItemState;

function ItemsSection({ sub }: { sub: SubscriptionDetail }) {
  const [filter, setFilter] = useState<ItemFilter>("all");
  const reevaluate = useSubscriptionAction(sub.id, "reevaluate");
  const toast = useToast();
  const items = filter === "all" ? sub.items : sub.items.filter((item) => item.state === filter);
  const options: { value: ItemFilter; label: string }[] = [
    { value: "all", label: "Alle" },
    { value: "downloaded", label: `Geladen ${sub.stats.downloaded}` },
    { value: "queued", label: `Wartend ${sub.stats.queued}` },
    { value: "filtered", label: `Gefiltert ${sub.stats.filtered}` },
  ];

  return (
    <section aria-labelledby="items-heading">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="items-heading" className="text-[20px] font-semibold tracking-tight">
          Videos
        </h2>
        <SegmentedControl label="Filter" value={filter} onChange={setFilter} options={options} />
      </div>
      {filter === "filtered" && sub.stats.filtered > 0 && (
        <div className="mb-4 flex items-center justify-between gap-4 rounded-2xl bg-elevated p-4 text-[14px] text-secondary">
          <span>Filter geändert? Gefilterte Videos können neu bewertet werden.</span>
          <Button
            size="sm"
            variant="secondary"
            loading={reevaluate.isPending}
            onClick={() =>
              reevaluate.mutate(undefined, {
                onSuccess: () => toast("Wird neu bewertet"),
                onError: (e) => toast(e.message, "error"),
              })
            }
          >
            Neu bewerten
          </Button>
        </div>
      )}
      {items.length === 0 ? (
        <p className="rounded-2xl bg-elevated p-6 text-center text-[14px] text-tertiary">
          {sub.last_checked_at ? "Keine Videos in dieser Ansicht." : "Noch nicht geprüft."}
        </p>
      ) : (
        <ul className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
          {items.map((item) => {
            const meta = [formatDate(item.upload_date), formatDuration(item.duration_s)]
              .filter(Boolean)
              .join(" · ");
            const title = item.title ?? item.youtube_id;
            return (
              <li key={item.id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  {item.video_id && item.state === "downloaded" ? (
                    <Link
                      to={`/videos/${item.video_id}`}
                      className="line-clamp-1 text-[15px] hover:underline"
                    >
                      {title}
                    </Link>
                  ) : (
                    <p className="line-clamp-1 text-[15px]">{title}</p>
                  )}
                  <p className="text-[12px] text-tertiary">
                    {meta}
                    {item.reason && (meta ? " · " : "") + item.reason}
                  </p>
                </div>
                <StateLabel state={item.state} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const STATE_DOT: Record<ItemState, string> = {
  downloaded: "bg-success",
  queued: "bg-accent",
  failed: "bg-danger",
  filtered: "bg-tertiary",
  skipped: "bg-tertiary",
  removed: "bg-tertiary",
};

function StateLabel({ state }: { state: ItemState }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5 text-[12px] text-secondary">
      <span className={cn("size-1.5 rounded-full", STATE_DOT[state])} aria-hidden />
      {ITEM_STATE_LABEL[state]}
    </span>
  );
}
