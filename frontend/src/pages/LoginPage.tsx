import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Input";
import { useAuth } from "@/hooks/auth";

import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const { login, loginWithCode } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = (err: unknown) => {
    setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    setBusy(false);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const next = await login(username, password);
      if (next) {
        setTicket(next);
        setBusy(false);
      }
    } catch (err) {
      fail(err);
    }
  };

  const submitCode = async (event: FormEvent) => {
    event.preventDefault();
    if (!ticket) return;
    setBusy(true);
    setError(null);
    try {
      await loginWithCode(ticket, code);
    } catch (err) {
      fail(err);
      if (err instanceof Error && err.message.includes("abgelaufen")) {
        setTicket(null);
        setCode("");
      }
    }
  };

  if (ticket) {
    return (
      <AuthLayout
        title="Bestätigungscode"
        subtitle="Gib den Code aus deiner Authenticator-App ein – oder einen Wiederherstellungscode."
      >
        <form onSubmit={submitCode} className="flex flex-col gap-4">
          <TextField
            label="Code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoCapitalize="none"
            autoFocus
            required
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          {error && (
            <p role="alert" className="px-1 text-[13px] text-danger">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" loading={busy} className="mt-2 w-full">
            Bestätigen
          </Button>
          <button
            type="button"
            onClick={() => {
              setTicket(null);
              setCode("");
              setError(null);
            }}
            className="text-[14px] text-secondary hover:text-primary"
          >
            Zurück
          </button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="TubeVault" subtitle="Melde dich an, um deine Bibliothek zu öffnen.">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField
          label="Benutzername"
          autoComplete="username"
          autoCapitalize="none"
          autoFocus
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextField
          label="Passwort"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="px-1 text-[13px] text-danger">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" loading={busy} className="mt-2 w-full">
          Anmelden
        </Button>
      </form>
    </AuthLayout>
  );
}
