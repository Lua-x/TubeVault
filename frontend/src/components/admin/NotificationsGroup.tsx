import { useState } from "react";

import { useNotifications, useSaveNotifications, useTestNotifications } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/hooks/toast";
import type {
  NotificationEvents,
  NotificationSettings,
  NotificationUpdate,
  NotifyService,
} from "@/lib/types";

const SERVICES: { value: NotifyService; label: string }[] = [
  { value: "off", label: "Aus" },
  { value: "ntfy", label: "ntfy" },
  { value: "gotify", label: "Gotify" },
  { value: "webhook", label: "Webhook" },
];

const PLACEHOLDERS: Record<NotifyService, string> = {
  off: "",
  ntfy: "https://ntfy.example.org/tubevault",
  gotify: "http://gotify.local",
  webhook: "http://homeassistant.local:8123/api/webhook/tubevault",
};

const URL_HINTS: Record<NotifyService, string> = {
  off: "",
  ntfy: "Adresse deines ntfy-Servers samt Thema.",
  gotify: "Adresse deines Gotify-Servers.",
  webhook: "TubeVault schickt JSON mit event, title, message und data per POST.",
};

const EVENTS: { key: keyof NotificationEvents; label: string; description?: string }[] = [
  { key: "video_downloaded", label: "Neue Videos geladen" },
  { key: "download_failed", label: "Download fehlgeschlagen" },
  { key: "subscription_error", label: "Abo-Prüfung fehlgeschlagen" },
  { key: "disk_low", label: "Speicherplatz wird knapp", description: "Unter 5 % oder 5 GB frei" },
  {
    key: "ytdlp_update",
    label: "yt-dlp-Update verfügbar",
    description: "Fragt dafür einmal täglich bei PyPI nach",
  },
];

function toForm(settings: NotificationSettings): NotificationUpdate {
  return { service: settings.service, url: settings.url, events: settings.events, token: null };
}

/** Push messages to the admin's own ntfy, Gotify or webhook. */
export function NotificationsGroup() {
  const { data } = useNotifications();
  if (!data) return null;
  // A fresh form whenever the saved settings change (e.g. right after saving).
  return <NotificationsForm key={JSON.stringify(data)} data={data} />;
}

function NotificationsForm({ data }: { data: NotificationSettings }) {
  const save = useSaveNotifications();
  const test = useTestNotifications();
  const toast = useToast();
  const [form, setForm] = useState<NotificationUpdate>(() => toForm(data));

  const set = (patch: Partial<NotificationUpdate>) => setForm({ ...form, ...patch });
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(data));
  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");
  const tokenLabel = form.service === "gotify" ? "App-Token" : "Zugangstoken (optional)";

  return (
    <Group
      title="Benachrichtigungen"
      footer="TubeVault schickt Nachrichten nur an die Adresse, die du hier einträgst – etwa deinen eigenen ntfy- oder Gotify-Server oder Home Assistant. Was innerhalb von 30 Sekunden passiert, kommt als eine Nachricht."
    >
      <Row>
        <SegmentedControl
          label="Dienst"
          value={form.service}
          onChange={(service) => set({ service })}
          options={SERVICES}
        />
      </Row>
      {form.service !== "off" && (
        <>
          <Row>
            <TextField
              label="Adresse"
              type="url"
              inputMode="url"
              autoComplete="off"
              placeholder={PLACEHOLDERS[form.service]}
              value={form.url}
              onChange={(event) => set({ url: event.target.value })}
              hint={URL_HINTS[form.service]}
            />
          </Row>
          {form.service !== "webhook" && (
            <Row className="flex flex-col gap-2">
              <TextField
                label={tokenLabel}
                type="password"
                autoComplete="new-password"
                placeholder={
                  data.has_token && form.token === null
                    ? "Gespeichert – leer lassen zum Behalten"
                    : ""
                }
                value={form.token ?? ""}
                onChange={(event) => set({ token: event.target.value || null })}
              />
              {data.has_token && form.token !== "" && (
                <button
                  type="button"
                  onClick={() => set({ token: "" })}
                  className="self-start text-[13px] font-medium text-accent hover:underline"
                >
                  Gespeicherten Token entfernen
                </button>
              )}
              {form.token === "" && (
                <span className="text-[13px] text-secondary">
                  Der Token wird beim Speichern entfernt.
                </span>
              )}
            </Row>
          )}
          {EVENTS.map(({ key, label, description }) => (
            <Row key={key}>
              <Switch
                label={label}
                description={description}
                checked={form.events[key]}
                onChange={(checked) => set({ events: { ...form.events, [key]: checked } })}
              />
            </Row>
          ))}
        </>
      )}
      <Row className="flex flex-wrap justify-end gap-2.5">
        {form.service !== "off" && (
          <Button
            variant="secondary"
            size="sm"
            loading={test.isPending}
            onClick={() =>
              test.mutate(form, {
                onSuccess: (result) => toast(result.detail, "success"),
                onError: fail,
              })
            }
          >
            Test senden
          </Button>
        )}
        <Button
          size="sm"
          disabled={!dirty}
          loading={save.isPending}
          onClick={() =>
            save.mutate(form, {
              onSuccess: () => toast("Gespeichert", "success"),
              onError: fail,
            })
          }
        >
          Speichern
        </Button>
      </Row>
    </Group>
  );
}
