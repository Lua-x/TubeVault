import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";

interface PlaylistNameDialogProps {
  open: boolean;
  title: string;
  submitLabel: string;
  initialName?: string;
  loading?: boolean;
  error?: string | null;
  onSubmit: (name: string) => void;
  onClose: () => void;
}

export function PlaylistNameDialog(props: PlaylistNameDialogProps) {
  return (
    <Dialog open={props.open} onClose={props.onClose} title={props.title}>
      {/* Remount the form for every opening so it starts from the initial name. */}
      {props.open && <NameForm {...props} />}
    </Dialog>
  );
}

function NameForm({
  submitLabel,
  initialName = "",
  loading,
  error,
  onSubmit,
  onClose,
}: PlaylistNameDialogProps) {
  const [name, setName] = useState(initialName);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim()) onSubmit(name.trim());
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <TextField
        autoFocus
        label="Name"
        maxLength={200}
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error}
      />
      <div className="flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onClose}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading} disabled={!name.trim()}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
