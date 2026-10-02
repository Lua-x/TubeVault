import { Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { useCreateSubscription } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";
import { useToast } from "@/hooks/toast";

import { backfillValue, DEFAULT_VALUES, toSettings, type FormValues } from "./options";
import { SubscriptionForm } from "./SubscriptionForm";

export function SubscribeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [values, setValues] = useState<FormValues>(DEFAULT_VALUES);
  const create = useCreateSubscription();
  const toast = useToast();
  const navigate = useNavigate();

  const close = () => {
    onClose();
    create.reset();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const sub = await create.mutateAsync({
        url: url.trim(),
        backfill: backfillValue(values),
        ...toSettings(values),
      });
      toast(`„${sub.title}“ abonniert`);
      setUrl("");
      setValues(DEFAULT_VALUES);
      close();
      navigate(`/subscriptions/${sub.id}`);
    } catch {
      // shown below the input
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Abonnieren" wide>
      <form onSubmit={submit} className="flex flex-col gap-7">
        <TextField
          autoFocus
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://www.youtube.com/@kanal oder Playlist-Link"
          aria-label="Kanal- oder Playlist-URL"
          leading={<Link2 className="size-4" strokeWidth={2} />}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          error={create.error?.message}
          hint="Kanal (@name, /channel/…) oder Playlist (…?list=…)"
        />
        <SubscriptionForm mode="create" values={values} onChange={setValues} />
        <div className="sticky bottom-[calc(-1.5rem-env(safe-area-inset-bottom))] -mx-6 -mb-[calc(1.5rem+env(safe-area-inset-bottom))] flex justify-end gap-3 border-t border-separator bg-elevated/85 px-6 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom))] backdrop-blur-xl sm:-bottom-6 sm:-mb-6 sm:pb-4">
          <Button type="button" variant="secondary" onClick={close}>
            Abbrechen
          </Button>
          <Button type="submit" loading={create.isPending} disabled={!url.trim()}>
            Abonnieren
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
