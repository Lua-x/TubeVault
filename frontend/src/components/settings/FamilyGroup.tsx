import { Lock, MonitorSmartphone, UsersRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import {
  useCreateFamilyDevice,
  useFamilyDevices,
  useFamilySettings,
  useRemoveFamilyDevice,
} from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { useAuth, useCurrentUser } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { formatRelative } from "@/lib/format";
import { isTvBrowser } from "@/tv/navigation";

/** The own account on family devices: shown there, with or without a PIN. */
export function FamilyGroup() {
  const user = useCurrentUser();
  const { status } = useAuth();
  const settings = useFamilySettings();
  const toast = useToast();
  const [editingPin, setEditingPin] = useState(false);
  const [pin, setPin] = useState("");
  const pinRequired = user.is_admin || user.two_factor;

  const save = (body: { on_family_devices?: boolean; pin?: string }, done?: string) =>
    settings.mutate(body, {
      onSuccess: () => {
        setEditingPin(false);
        setPin("");
        if (done) toast(done);
      },
      onError: (err) => toast(err.message, "error"),
    });

  return (
    <>
      <Group
        title="Wer schaut?"
        footer={
          pinRequired
            ? "Auf einem Familiengerät – etwa dem Fernseher – wechselt man mit einem Tipp das Profil. Admins und Konten mit Zwei-Faktor-Anmeldung brauchen dort eine PIN."
            : "Auf einem Familiengerät – etwa dem Fernseher – wechselt man mit einem Tipp das Profil, auf Wunsch geschützt mit einer PIN."
        }
      >
        {status?.family_device && (
          <Link
            to="/profiles"
            className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface/40"
          >
            <UsersRound className="size-5 shrink-0 text-accent" strokeWidth={1.75} />
            <span className="flex-1 text-[15px]">Profil wechseln</span>
          </Link>
        )}
        <Row>
          <Switch
            label="Auf Familiengeräten zeigen"
            description={
              user.on_family_devices && pinRequired && !user.has_pin
                ? "Erscheint erst, wenn eine PIN gesetzt ist."
                : undefined
            }
            checked={user.on_family_devices}
            disabled={settings.isPending}
            onChange={(on) => {
              if (on && pinRequired && !user.has_pin) setEditingPin(true);
              else save({ on_family_devices: on });
            }}
          />
        </Row>
        <Row className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 text-[15px]">
            <Lock className="size-4 text-secondary" strokeWidth={2} />
            {user.has_pin ? "PIN ist gesetzt" : "Keine PIN"}
          </span>
          <div className="flex gap-2">
            {user.has_pin && !pinRequired && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => save({ pin: "" }, "PIN entfernt")}
              >
                Entfernen
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => setEditingPin(true)}>
              {user.has_pin ? "Ändern" : "Festlegen"}
            </Button>
          </div>
        </Row>
      </Group>

      <Dialog open={editingPin} onClose={() => setEditingPin(false)} title="PIN festlegen">
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            save(
              { pin, ...(user.on_family_devices ? {} : { on_family_devices: true }) },
              "PIN gespeichert",
            );
          }}
        >
          <TextField
            label="PIN"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            autoFocus
            pattern="[0-9]{4,8}"
            maxLength={8}
            hint="4 bis 8 Ziffern. Nur für Familiengeräte – dein Passwort bleibt, wie es ist."
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setEditingPin(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={pin.length < 4} loading={settings.isPending}>
              Speichern
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

/** Admins: which browsers are family devices – this one can become one. */
export function FamilyDevicesGroup() {
  const { status } = useAuth();
  const { data: devices } = useFamilyDevices(true);
  const create = useCreateFamilyDevice();
  const remove = useRemoveFamilyDevice();
  const toast = useToast();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState(() => (isTvBrowser() ? "Fernseher" : "Familiengerät"));
  const fail = (err: Error) => toast(err.message, "error");

  return (
    <>
      <Group
        title="Familiengeräte"
        footer="Auf einem Familiengerät zeigt TubeVault „Wer schaut?“ statt der Anmeldung. Wer dort erscheint, legt jedes Konto selbst fest (oder ein Admin für Kinderprofile). Entfernen beendet es sofort."
      >
        {(devices ?? []).map((device) => (
          <Row key={device.id} className="flex items-center gap-3">
            <MonitorSmartphone className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px]">
                {device.name}
                {device.current && <span className="text-secondary"> · dieses Gerät</span>}
              </span>
              <span className="block text-[13px] text-secondary">
                {device.last_used_at
                  ? `Zuletzt benutzt ${formatRelative(device.last_used_at)}`
                  : `Eingerichtet ${formatRelative(device.created_at)}`}
              </span>
            </span>
            <Button
              variant="secondary"
              size="sm"
              loading={remove.isPending && remove.variables === device.id}
              onClick={() => remove.mutate(device.id, { onError: fail })}
            >
              Entfernen
            </Button>
          </Row>
        ))}
        {!status?.family_device && (
          <Row className="flex items-center justify-between gap-3">
            <span className="text-[15px]">Dieses Gerät als Familiengerät einrichten</span>
            <Button size="sm" onClick={() => setNaming(true)}>
              Einrichten
            </Button>
          </Row>
        )}
      </Group>

      <Dialog open={naming} onClose={() => setNaming(false)} title="Familiengerät einrichten">
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(name, {
              onSuccess: () => {
                setNaming(false);
                toast("Dieses Gerät zeigt jetzt „Wer schaut?“");
              },
              onError: fail,
            });
          }}
        >
          <TextField
            label="Name"
            autoFocus
            maxLength={64}
            value={name}
            hint="Zum Wiedererkennen in dieser Liste, z. B. „Wohnzimmer“."
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setNaming(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={!name.trim()} loading={create.isPending}>
              Einrichten
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
