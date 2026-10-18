import { KeyRound, Trash2, TriangleAlert, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { useSaveYoutubeCookies, useYoutubeCookies } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { YoutubeCookies } from "@/lib/types";

const day = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium" });
const date = (value: string) => day.format(new Date(value));

function describe(cookies: YoutubeCookies): { title: string; detail: string } {
  if (!cookies.stored) {
    return {
      title: "Keine Cookies hinterlegt",
      detail: "Videos ab 18, für Mitglieder und private Videos lassen sich nicht laden.",
    };
  }
  if (cookies.problem === "expired") {
    return {
      title: "Abgelaufen",
      detail: `Seit ${cookies.expires_at ? date(cookies.expires_at) : "kurzem"}. Bitte neue Cookies hochladen.`,
    };
  }
  if (cookies.problem === "rejected") {
    return {
      title: "Von YouTube abgemeldet",
      detail: "YouTube nimmt die Cookies nicht mehr an. Bitte neue hochladen.",
    };
  }
  const since = cookies.uploaded_at ? `Seit ${date(cookies.uploaded_at)}` : "Hinterlegt";
  const until = cookies.expires_at ? `gültig bis ${date(cookies.expires_at)}` : "ohne Ablaufdatum";
  return { title: "Angemeldet", detail: `${since} · ${until}` };
}

/** cookies.txt for videos YouTube only shows to a signed-in account. */
export function CookiesGroup() {
  const { data } = useYoutubeCookies();
  const save = useSaveYoutubeCookies();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [confirm, setConfirm] = useState(false);
  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Das hat nicht geklappt", "error");

  if (!data) return null;
  const { title, detail } = describe(data);
  const trouble = data.problem !== null;

  return (
    <Group
      title="YouTube-Anmeldung"
      footer="Nur für Videos, bei denen YouTube eine Anmeldung verlangt (ab 18, Mitglieder, privat) – alles andere lädt TubeVault ohne. Exportiere die cookies.txt aus einem privaten Fenster und schließ es danach, sonst verfallen sie schnell; am besten mit einem Zweitkonto. Gespeichert nur unter /config/cookies, nicht in Sicherungen oder Logs."
    >
      <Row className="flex items-center gap-3">
        {trouble ? (
          <TriangleAlert className="size-5 shrink-0 text-danger" strokeWidth={1.75} />
        ) : (
          <KeyRound
            className={cn("size-5 shrink-0", data.stored ? "text-accent" : "text-secondary")}
            strokeWidth={1.75}
          />
        )}
        <span className="min-w-0 flex-1">
          <span className={cn("block text-[15px]", trouble && "text-danger")}>{title}</span>
          <span className="block text-[13px] text-secondary">{detail}</span>
        </span>
      </Row>
      {data.stored && (
        <Row className="flex items-center justify-between gap-4 text-[15px]">
          <span>Zuletzt gebraucht</span>
          <span className="text-secondary">{data.used_at ? date(data.used_at) : "noch nie"}</span>
        </Row>
      )}
      <Row className="flex flex-wrap justify-end gap-2.5">
        <input
          ref={fileInput}
          type="file"
          accept=".txt,text/plain"
          className="hidden"
          aria-label="cookies.txt wählen"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            save.mutate(file, {
              onSuccess: () => toast("YouTube-Cookies hinterlegt", "success"),
              onError: fail,
            });
          }}
        />
        {data.stored && (
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 className="size-4" strokeWidth={2} />}
            onClick={() => setConfirm(true)}
          >
            Entfernen
          </Button>
        )}
        <Button
          size="sm"
          variant={data.stored && !trouble ? "secondary" : "primary"}
          loading={save.isPending && !confirm}
          icon={<Upload className="size-4" strokeWidth={2} />}
          onClick={() => fileInput.current?.click()}
        >
          {data.stored ? "Neue hochladen" : "cookies.txt hochladen"}
        </Button>
      </Row>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="YouTube-Cookies entfernen?">
        <p className="text-[15px] text-secondary">
          Videos ab 18, für Mitglieder und private Videos lassen sich danach nicht mehr laden. Was
          schon in der Bibliothek ist, bleibt.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirm(false)}>
            Abbrechen
          </Button>
          <Button
            variant="danger"
            loading={save.isPending}
            onClick={() =>
              save.mutate(null, {
                onSuccess: () => setConfirm(false),
                onError: fail,
              })
            }
          >
            Entfernen
          </Button>
        </div>
      </Dialog>
    </Group>
  );
}
