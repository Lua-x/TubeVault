import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Input";
import { useAuth } from "@/hooks/auth";

import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
      setBusy(false);
    }
  };

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
