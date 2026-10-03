import { Search } from "lucide-react";
import { useState } from "react";

import { useChannels, useDeleteUser, useResetTwoFactor, useUpdateUser } from "@/api/queries";
import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { User } from "@/lib/types";

const ACCESS = [
  { value: "all" as const, label: "Alle Kanäle" },
  { value: "selected" as const, label: "Ausgewählte" },
];

/** What a user may see and do – edited by an admin. */
export function UserDialog({
  user,
  isSelf,
  onClose,
}: {
  user: User;
  isSelf: boolean;
  onClose: () => void;
}) {
  const { data: channels } = useChannels();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const resetTwoFactor = useResetTwoFactor();
  const toast = useToast();
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [mayAdd, setMayAdd] = useState(user.may_add);
  const [access, setAccess] = useState(user.channel_access);
  const [selected, setSelected] = useState(() => new Set(user.channel_ids));
  const [filter, setFilter] = useState("");
  const [password, setPassword] = useState("");

  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");
  const visible = (channels ?? []).filter((c) =>
    c.name.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const save = () =>
    update.mutate(
      {
        id: user.id,
        is_admin: isAdmin,
        may_add: mayAdd,
        channel_access: access,
        channel_ids: [...selected],
        ...(password ? { password } : {}),
      },
      {
        onSuccess: () => {
          toast("Gespeichert");
          onClose();
        },
        onError: fail,
      },
    );

  return (
    <Dialog open onClose={onClose} title={user.username} wide>
      <div className="flex flex-col gap-5">
        <Switch
          label="Administrator"
          description="Darf alles: Einstellungen, Benutzer, Verwaltung – und sieht immer alle Kanäle."
          checked={isAdmin}
          disabled={isSelf}
          onChange={setIsAdmin}
        />

        {!isAdmin && (
          <>
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[15px]">Sichtbare Kanäle</span>
                <SegmentedControl
                  label="Sichtbare Kanäle"
                  value={access}
                  onChange={setAccess}
                  options={ACCESS}
                />
              </div>
              {access === "selected" && (
                <div className="rounded-xl bg-surface p-3">
                  <div className="relative mb-2">
                    <Search
                      className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tertiary"
                      strokeWidth={2}
                    />
                    <input
                      type="search"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                      placeholder="Kanal suchen"
                      aria-label="Kanal suchen"
                      className="h-9 w-full rounded-lg bg-elevated pr-3 pl-9 text-[15px] outline-none placeholder:text-tertiary focus:ring-2 focus:ring-accent"
                    />
                  </div>
                  <ul className="max-h-64 overflow-y-auto">
                    {visible.map((channel) => (
                      <li key={channel.id}>
                        <label
                          className={cn(
                            "flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-elevated",
                          )}
                        >
                          <input
                            type="checkbox"
                            className="size-4 accent-[var(--tv-accent)]"
                            checked={selected.has(channel.id)}
                            onChange={() => toggle(channel.id)}
                          />
                          <ChannelAvatar channel={channel} name={channel.name} className="size-7" />
                          <span className="min-w-0 flex-1 truncate text-[14px]">
                            {channel.name}
                          </span>
                        </label>
                      </li>
                    ))}
                    {visible.length === 0 && (
                      <li className="px-2 py-3 text-[14px] text-secondary">
                        Keine Kanäle gefunden.
                      </li>
                    )}
                  </ul>
                  <p className="mt-2 px-1 text-[13px] text-secondary">
                    {selected.size} {selected.size === 1 ? "Kanal" : "Kanäle"} freigegeben. Gilt
                    überall – auch für Suche, Playlists und direkte Links. Wer nur ausgewählte
                    Kanäle sieht, kann nichts hinzufügen.
                  </p>
                </div>
              )}
            </div>
            {access === "all" && (
              <Switch
                label="Darf Videos hinzufügen und abonnieren"
                description="Aus: nur schauen – keine Downloads, Abos oder neuen Videos."
                checked={mayAdd}
                onChange={setMayAdd}
              />
            )}
          </>
        )}

        <TextField
          label="Neues Passwort"
          type="password"
          autoComplete="new-password"
          minLength={8}
          placeholder="Leer lassen, um es zu behalten"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {user.two_factor && !isSelf && (
          <div className="flex items-center justify-between gap-3 text-[14px]">
            <span className="text-secondary">Zwei-Faktor-Anmeldung ist eingeschaltet.</span>
            <Button
              variant="secondary"
              size="sm"
              loading={resetTwoFactor.isPending}
              onClick={() =>
                resetTwoFactor.mutate(user.id, {
                  onSuccess: () => toast("Zwei-Faktor-Anmeldung zurückgesetzt"),
                  onError: fail,
                })
              }
            >
              Zurücksetzen
            </Button>
          </div>
        )}

        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          {!isSelf ? (
            <button
              type="button"
              className="text-[14px] font-medium text-danger hover:underline"
              onClick={() => {
                if (window.confirm(`Benutzer „${user.username}“ wirklich löschen?`)) {
                  remove.mutate(user.id, { onSuccess: onClose, onError: fail });
                }
              }}
            >
              Benutzer löschen
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <Button variant="secondary" onClick={onClose}>
              Abbrechen
            </Button>
            <Button loading={update.isPending} onClick={save}>
              Speichern
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
