import { ShieldCheck } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { renderSVG } from "uqr";

import {
  useDisableTwoFactor,
  useEnableTwoFactor,
  useNewRecoveryCodes,
  useStartTwoFactor,
  useTwoFactor,
} from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { useAuth } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";

type Step = { kind: "setup"; secret: string; uri: string } | { kind: "codes"; codes: string[] };
type CodeAction = "disable" | "codes";

function QrCode({ value }: { value: string }) {
  // Drawn right here: the secret never goes to an outside QR service.
  const svg = useMemo(
    () => renderSVG(value, { border: 2, whiteColor: "#fff", blackColor: "#000" }),
    [value],
  );
  return (
    <div
      role="img"
      aria-label="QR-Code für die Authenticator-App"
      className="mx-auto size-48 overflow-hidden rounded-xl bg-white [&>svg]:size-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const toast = useToast();
  const text = codes.join("\n");
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([`TubeVault – Wiederherstellungscodes\n\n${text}\n`], { type: "text/plain" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "tubevault-wiederherstellungscodes.txt";
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <p className="text-[15px] text-secondary">
        Hebe diese Codes gut auf. Jeder funktioniert einmal, falls dein Handy einmal fehlt. Sie
        werden nur jetzt angezeigt.
      </p>
      <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-xl bg-surface px-4 py-3 font-mono text-[15px] tabular-nums">
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="mt-6 flex flex-wrap justify-end gap-3">
        <Button
          variant="secondary"
          onClick={() =>
            void navigator.clipboard
              ?.writeText(text)
              .then(() => toast("Kopiert"))
              .catch(() => toast("Kopieren nicht möglich", "error"))
          }
        >
          Kopieren
        </Button>
        <Button variant="secondary" onClick={download}>
          Herunterladen
        </Button>
        <Button onClick={onDone}>Fertig</Button>
      </div>
    </>
  );
}

/** Two-factor login with an authenticator app, for the signed-in user. */
export function TwoFactorGroup() {
  const { data } = useTwoFactor();
  const { refresh } = useAuth();
  const start = useStartTwoFactor();
  const enable = useEnableTwoFactor();
  const disable = useDisableTwoFactor();
  const newCodes = useNewRecoveryCodes();
  const toast = useToast();
  const [step, setStep] = useState<Step | null>(null);
  const [action, setAction] = useState<CodeAction | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setStep(null);
    setAction(null);
    setCode("");
    setError(null);
  };
  const message = (err: unknown) => (err instanceof Error ? err.message : "Das hat nicht geklappt");

  const confirmSetup = (event: FormEvent) => {
    event.preventDefault();
    enable.mutate(code, {
      onSuccess: (result) => {
        setCode("");
        setError(null);
        setStep({ kind: "codes", codes: result.recovery_codes });
        void refresh();
      },
      onError: (err) => setError(message(err)),
    });
  };

  const confirmAction = (event: FormEvent) => {
    event.preventDefault();
    if (action === "disable") {
      disable.mutate(code, {
        onSuccess: () => {
          close();
          toast("Zwei-Faktor-Anmeldung ausgeschaltet");
          void refresh();
        },
        onError: (err) => setError(message(err)),
      });
    } else {
      newCodes.mutate(code, {
        onSuccess: (result) => {
          setAction(null);
          setCode("");
          setError(null);
          setStep({ kind: "codes", codes: result.recovery_codes });
        },
        onError: (err) => setError(message(err)),
      });
    }
  };

  if (!data) return null;
  return (
    <Group
      title="Zwei-Faktor-Anmeldung"
      footer="Zusätzlich zum Passwort fragt TubeVault nach einem Code aus einer Authenticator-App wie Aegis, 2FAS, Google Authenticator oder 1Password."
    >
      <Row className="flex items-center gap-3">
        <ShieldCheck
          className={data.enabled ? "size-5 text-success" : "size-5 text-tertiary"}
          strokeWidth={1.75}
        />
        <span className="min-w-0 flex-1">
          <span className="block text-[15px]">{data.enabled ? "Eingeschaltet" : "Aus"}</span>
          {data.enabled && (
            <span className="block text-[13px] text-secondary">
              Noch {data.recovery_codes_left}{" "}
              {data.recovery_codes_left === 1
                ? "Wiederherstellungscode"
                : "Wiederherstellungscodes"}
            </span>
          )}
        </span>
        {data.enabled ? (
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setAction("codes")}>
              Neue Codes
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setAction("disable")}>
              Ausschalten
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            loading={start.isPending}
            onClick={() =>
              start.mutate(undefined, {
                onSuccess: (result) => setStep({ kind: "setup", ...result }),
                onError: (err) => toast(message(err), "error"),
              })
            }
          >
            Einrichten
          </Button>
        )}
      </Row>

      <Dialog
        open={step !== null}
        onClose={close}
        title={step?.kind === "codes" ? "Wiederherstellungscodes" : "Authenticator-App verbinden"}
      >
        {step?.kind === "setup" && (
          <form onSubmit={confirmSetup}>
            <p className="text-[15px] text-secondary">
              Scanne den Code mit deiner Authenticator-App und gib dann die sechs Ziffern ein, die
              sie anzeigt.
            </p>
            <div className="mt-5">
              <QrCode value={step.uri} />
            </div>
            <p className="mt-3 text-center text-[13px] break-all text-tertiary">
              Ohne Kamera:{" "}
              <span className="font-mono text-secondary">
                {step.secret.match(/.{1,4}/g)?.join(" ")}
              </span>
            </p>
            <div className="mt-5">
              <TextField
                label="Code aus der App"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                error={error}
              />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button type="button" variant="secondary" onClick={close}>
                Abbrechen
              </Button>
              <Button type="submit" loading={enable.isPending}>
                Einschalten
              </Button>
            </div>
          </form>
        )}
        {step?.kind === "codes" && <RecoveryCodes codes={step.codes} onDone={close} />}
      </Dialog>

      <Dialog
        open={action !== null}
        onClose={close}
        title={
          action === "disable"
            ? "Zwei-Faktor-Anmeldung ausschalten?"
            : "Neue Wiederherstellungscodes"
        }
      >
        <form onSubmit={confirmAction}>
          <p className="text-[15px] text-secondary">
            {action === "disable"
              ? "Zur Bestätigung einen Code aus der App oder einen Wiederherstellungscode eingeben."
              : "Die bisherigen Codes werden ungültig. Zur Bestätigung einen Code aus der App eingeben."}
          </p>
          <div className="mt-5">
            <TextField
              label="Code"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              error={error}
            />
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={close}>
              Abbrechen
            </Button>
            <Button
              type="submit"
              loading={disable.isPending || newCodes.isPending}
              className={action === "disable" ? "bg-danger hover:bg-danger/90" : undefined}
            >
              {action === "disable" ? "Ausschalten" : "Neue Codes"}
            </Button>
          </div>
        </form>
      </Dialog>
    </Group>
  );
}
