import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Input";
import { useAuth } from "@/hooks/auth";

import { AuthLayout } from "./AuthLayout";

export function SetupPage() {
  const { setup } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirm) return;
    setBusy(true);
    setError(null);
    try {
      await setup(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Einrichtung fehlgeschlagen.");
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Willkommen bei TubeVault"
      subtitle="Lege das Administrator-Konto an. Weitere Benutzer kannst du später hinzufügen."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField
          label="Benutzername"
          autoComplete="username"
          autoCapitalize="none"
          pattern="[A-Za-z0-9._\-]{2,64}"
          title="2–64 Zeichen: Buchstaben, Ziffern, Punkt, Unterstrich, Bindestrich"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextField
          label="Passwort"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          autoFocus
          hint="Mindestens 8 Zeichen"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Passwort wiederholen"
          type="password"
          autoComplete="new-password"
          required
          error={mismatch ? "Die Passwörter stimmen nicht überein." : null}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error && (
          <p role="alert" className="px-1 text-[13px] text-danger">
            {error}
          </p>
        )}
        <Button
          type="submit"
          size="lg"
          loading={busy}
          disabled={mismatch || password.length < 8}
          className="mt-2 w-full"
        >
          Konto anlegen
        </Button>
      </form>
    </AuthLayout>
  );
}
