import { Copy } from "lucide-react";

import { useOidcInfo } from "@/api/queries";
import { Group, Row } from "@/components/ui/Group";
import { useToast } from "@/hooks/toast";

/** Login through an OpenID Connect provider: set up via environment variables. */
export function OidcInfoGroup() {
  const { data } = useOidcInfo();
  const toast = useToast();
  if (!data) return null;

  const rows: [string, string][] = data.enabled
    ? [
        ["Anbieter", data.name],
        ["Aussteller", data.issuer ?? "–"],
        ["Neue Konten", data.auto_create ? "automatisch anlegen" : "nur verknüpfte"],
        ["Admin-Gruppe", data.admin_group ?? "–"],
        ["Anmeldung mit Passwort", data.password_login ? "erlaubt" : "abgeschaltet"],
      ]
    : [];

  return (
    <Group
      title="Anmeldung über OIDC"
      footer={
        data.enabled
          ? undefined
          : "Nicht eingerichtet. Mit Authelia, Authentik, Keycloak oder Pocket ID per Umgebungsvariablen einschalten – die README zeigt wie."
      }
    >
      {rows.map(([label, value]) => (
        <Row key={label} className="flex items-center justify-between gap-4 text-[15px]">
          <span>{label}</span>
          <span className="min-w-0 truncate text-secondary">{value}</span>
        </Row>
      ))}
      <Row className="flex flex-col gap-1">
        <span className="text-[15px]">Rücksprung-Adresse</span>
        <span className="flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded-lg bg-surface px-2.5 py-1.5 text-[13px] text-secondary">
            {data.redirect_uri}
          </code>
          <button
            type="button"
            aria-label="Adresse kopieren"
            title="Kopieren"
            onClick={() =>
              void navigator.clipboard
                ?.writeText(data.redirect_uri)
                .then(() => toast("Kopiert"))
                .catch(() => toast("Kopieren nicht möglich", "error"))
            }
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-secondary hover:bg-surface hover:text-primary"
          >
            <Copy className="size-4" strokeWidth={2} />
          </button>
        </span>
        <span className="text-[13px] text-tertiary">
          Beim Anmeldedienst als Redirect-URI eintragen.
        </span>
      </Row>
    </Group>
  );
}
