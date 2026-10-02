import { Check, Copy, KeyRound, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useCreateToken, useDeleteToken, useTokens } from "@/api/queries";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/hooks/toast";
import { apiUrl } from "@/lib/base";
import { formatDate, formatRelative } from "@/lib/format";
import type { ApiToken, CreatedApiToken, TokenScope } from "@/lib/types";

const EXPIRY = [
  { value: "", label: "Nie" },
  { value: "30", label: "Nach 30 Tagen" },
  { value: "90", label: "Nach 90 Tagen" },
  { value: "365", label: "Nach einem Jahr" },
];

/** Personal API tokens for scripts and shortcuts. */
export function TokensGroup() {
  const { data: tokens } = useTokens();
  const remove = useDeleteToken();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiToken | null>(null);

  return (
    <Group
      title="API-Tokens"
      footer={
        <>
          Für Skripte und Kurzbefehle, z. B. „Teilen → In TubeVault laden“ auf dem iPhone. Senden
          als <code>Authorization: Bearer &lt;Token&gt;</code>. Alle Schnittstellen stehen in der{" "}
          <a
            href={apiUrl("docs")}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline"
          >
            API-Dokumentation
          </a>
          .
        </>
      }
    >
      {(tokens ?? []).map((token) => (
        <Row key={token.id} className="flex items-center gap-3">
          <KeyRound className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px]">{token.name}</span>
            <span className="block truncate text-[13px] text-secondary">
              <code>{token.prefix}…</code> ·{" "}
              {token.scope === "full" ? "Voller Zugriff" : "Nur lesen"} ·{" "}
              {token.last_used_at
                ? `benutzt ${formatRelative(token.last_used_at)}`
                : "noch nie benutzt"}
              {token.expires_at ? ` · läuft ab am ${formatDate(token.expires_at)}` : ""}
            </span>
          </span>
          <IconButton label={`${token.name} widerrufen`} onClick={() => setRevoking(token)}>
            <Trash2 className="size-4" strokeWidth={2} />
          </IconButton>
        </Row>
      ))}
      <Row className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
          Neues Token
        </Button>
      </Row>

      <CreateTokenDialog open={creating} onClose={() => setCreating(false)} />
      <Dialog open={revoking != null} onClose={() => setRevoking(null)} title="Token widerrufen?">
        <p className="text-[15px] text-secondary">
          Skripte und Kurzbefehle mit „{revoking?.name}“ funktionieren danach nicht mehr.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setRevoking(null)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger hover:bg-danger/90"
            loading={remove.isPending}
            onClick={() =>
              revoking &&
              remove.mutate(revoking.id, {
                onSuccess: () => {
                  setRevoking(null);
                  toast("Token widerrufen");
                },
                onError: (err) => toast(err.message, "error"),
              })
            }
          >
            Widerrufen
          </Button>
        </div>
      </Dialog>
    </Group>
  );
}

function CreateTokenDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateToken();
  const [name, setName] = useState("");
  const [scope, setScope] = useState<TokenScope>("full");
  const [expiry, setExpiry] = useState("");
  const [created, setCreated] = useState<CreatedApiToken | null>(null);
  const [copied, setCopied] = useState(false);

  const close = () => {
    onClose();
    // Reset after the closing animation, so the token doesn't vanish while it fades out.
    setTimeout(() => {
      setCreated(null);
      setName("");
      setCopied(false);
      create.reset();
    }, 300);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { name: name.trim(), scope, expires_days: expiry ? Number(expiry) : null },
      { onSuccess: setCreated },
    );
  };

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
    } catch {
      // Clipboard needs HTTPS; the token can still be selected by hand.
    }
  };

  return (
    <Dialog open={open} onClose={close} title={created ? "Token erstellt" : "Neues API-Token"}>
      {created ? (
        <div className="flex flex-col gap-4">
          <p className="text-[15px] text-secondary">
            Kopiere das Token jetzt – es wird nur dieses eine Mal angezeigt.
          </p>
          <div className="flex items-center gap-2 rounded-xl bg-surface p-3">
            <code className="min-w-0 flex-1 text-[13px] break-all select-all">{created.token}</code>
            <IconButton label="Kopieren" onClick={() => void copy()}>
              {copied ? (
                <Check className="size-4 text-success" strokeWidth={2.5} />
              ) : (
                <Copy className="size-4" strokeWidth={2} />
              )}
            </IconButton>
          </div>
          <div className="flex justify-end">
            <Button onClick={close}>Fertig</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-5">
          <TextField
            label="Name"
            placeholder="z. B. iPhone-Kurzbefehl"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
            maxLength={100}
            error={create.error?.message}
          />
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-secondary">Rechte</span>
            <SegmentedControl
              label="Rechte"
              value={scope}
              onChange={setScope}
              options={[
                { value: "full", label: "Voller Zugriff" },
                { value: "read", label: "Nur lesen" },
              ]}
            />
          </div>
          <Select label="Läuft ab" value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            {EXPIRY.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={close}>
              Abbrechen
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
              Erstellen
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
