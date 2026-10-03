import { CircleAlert, CircleCheck } from "lucide-react";

import { useDlnaStatus, useUsers } from "@/api/queries";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import type { DlnaOptions } from "@/lib/types";

interface DlnaGroupProps {
  value: DlnaOptions;
  /** The setting as saved – the status below belongs to that one, not to the draft. */
  saved: DlnaOptions;
  onChange: (patch: Partial<DlnaOptions>) => void;
}

/** DLNA/UPnP: smart TVs, consoles and VLC find the library in the home network. */
export function DlnaGroup({ value, saved, onChange }: DlnaGroupProps) {
  const { data: users } = useUsers(value.enabled);
  const { data: status } = useDlnaStatus(saved.enabled);

  return (
    <Group
      title="Fernseher im Heimnetz (DLNA)"
      footer={
        <>
          DLNA kennt keine Anmeldung: Jedes Gerät im Heimnetz sieht, was das gewählte Konto sehen
          darf. Anfragen aus dem Internet und über einen Reverse Proxy werden abgelehnt. In Docker
          braucht es <code className="font-mono text-[12px]">network_mode: host</code>, sonst finden
          die Fernseher den Server nicht (siehe Anleitung).
        </>
      }
    >
      <Row>
        <Switch
          label="DLNA-Server"
          description="Smart-TVs, Konsolen, VLC und Kodi zeigen TubeVault als Medienquelle an – ohne App."
          checked={value.enabled}
          onChange={(enabled) => onChange({ enabled })}
        />
      </Row>
      {value.enabled && (
        <>
          <Row>
            <TextField
              label="Name im Netzwerk"
              value={value.name}
              maxLength={64}
              onChange={(e) => onChange({ name: e.target.value })}
            />
          </Row>
          <Row>
            <Select
              inline
              label="Inhalte wie"
              value={value.user_id == null ? "" : String(value.user_id)}
              onChange={(e) =>
                onChange({ user_id: e.target.value ? Number(e.target.value) : null })
              }
            >
              <option value="">Alle Videos</option>
              {users?.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username}
                  {user.restricted ? " (eingeschränkt)" : ""}
                </option>
              ))}
            </Select>
          </Row>
        </>
      )}
      {saved.enabled && status && (
        <Row className="text-[13px]">
          {status.running ? (
            <span className="flex items-start gap-1.5 text-success">
              <CircleCheck className="mt-px size-4 shrink-0" strokeWidth={2} />
              <span className="min-w-0 break-words">
                Läuft – im Heimnetz unter {status.description_url}
              </span>
            </span>
          ) : (
            <span className="flex items-start gap-1.5 text-danger">
              <CircleAlert className="mt-px size-4 shrink-0" strokeWidth={2} />
              <span className="min-w-0 break-words">
                {status.error ?? "Die Ankündigung im Netzwerk läuft nicht."}
              </span>
            </span>
          )}
        </Row>
      )}
    </Group>
  );
}
