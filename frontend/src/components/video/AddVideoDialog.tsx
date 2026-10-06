import { ChevronRight, Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { useAddVideo, useAppSettings } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { useAuth } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import { RESOLUTION_HINT, resolutionChoices } from "@/lib/resolutions";
import type { AddVideoChoices, Container, MaxHeight } from "@/lib/types";

type ContainerChoice = "default" | Container;
type CommentsChoice = "default" | "yes" | "no";

function toChoices(
  container: ContainerChoice,
  quality: string,
  comments: CommentsChoice,
): AddVideoChoices {
  return {
    container: container === "default" ? undefined : container,
    max_height: quality ? (Number(quality) as MaxHeight) : undefined,
    comments: comments === "default" ? undefined : comments === "yes",
  };
}

interface AddVideoDialogProps {
  open: boolean;
  onClose: () => void;
  initialUrl?: string;
}

export function AddVideoDialog({ open, onClose, initialUrl }: AddVideoDialogProps) {
  const { user, updatePreferences } = useAuth();
  // The options picked last time (kept in the account, so on every device).
  const remembered = user?.preferences.add_video ?? {};
  const [url, setUrl] = useState(initialUrl ?? "");
  const [advanced, setAdvanced] = useState(false);
  const [container, setContainer] = useState<ContainerChoice>(remembered.container ?? "default");
  const [quality, setQuality] = useState(
    remembered.max_height ? String(remembered.max_height) : "",
  );
  const [comments, setComments] = useState<CommentsChoice>(
    remembered.comments == null ? "default" : remembered.comments ? "yes" : "no",
  );
  const { data: settings } = useAppSettings();
  const qualities = resolutionChoices(settings?.downloads.max_height);
  const add = useAddVideo();
  const toast = useToast();
  const navigate = useNavigate();

  // Shown next to the collapsed "Optionen", so remembered choices don't go unnoticed.
  const summary = [
    quality ? qualities.find((q) => q.value === quality)?.label : undefined,
    container === "default" ? undefined : container.toUpperCase(),
    comments === "default" ? undefined : comments === "yes" ? "Kommentare an" : "Kommentare aus",
  ]
    .filter(Boolean)
    .join(" · ");

  // Every pick is kept for next time right away – also when the dialog is closed without a
  // download. Not worth an error message if that fails.
  const remember = (next: AddVideoChoices) => {
    updatePreferences({ add_video: next }).catch(() => undefined);
  };
  const pickContainer = (value: ContainerChoice) => {
    setContainer(value);
    remember(toChoices(value, quality, comments));
  };
  const pickQuality = (value: string) => {
    setQuality(value);
    remember(toChoices(container, value, comments));
  };
  const pickComments = (value: CommentsChoice) => {
    setComments(value);
    remember(toChoices(container, quality, value));
  };

  const close = () => {
    onClose();
    add.reset();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await add.mutateAsync({ url: url.trim(), ...toChoices(container, quality, comments) });
      toast("Download gestartet");
      setUrl("");
      close();
      navigate("/downloads");
    } catch {
      // error is shown below the input
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Video hinzufügen">
      <form onSubmit={submit} className="flex flex-col gap-5">
        <TextField
          autoFocus
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://www.youtube.com/watch?v=…"
          aria-label="YouTube-URL"
          leading={<Link2 className="size-4" strokeWidth={2} />}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          error={add.error?.message}
          hint="Link zu einem einzelnen YouTube-Video. Kanäle und Playlists abonnierst du unter „Abos“."
        />

        <div>
          <button
            type="button"
            onClick={() => setAdvanced((v) => !v)}
            aria-expanded={advanced}
            className="flex items-center gap-1 px-1 text-[13px] font-medium text-secondary transition-colors hover:text-primary"
          >
            <ChevronRight
              className={cn("size-4 transition-transform duration-200", advanced && "rotate-90")}
              strokeWidth={2}
            />
            Optionen
            {!advanced && summary && <span className="font-normal text-tertiary">· {summary}</span>}
          </button>
          {advanced && (
            <div className="mt-3 flex flex-col gap-4 rounded-2xl bg-surface/50 p-4">
              <div className="flex items-center justify-between gap-4">
                <span className="text-[15px]">Format</span>
                <SegmentedControl
                  label="Format"
                  value={container}
                  onChange={pickContainer}
                  options={[
                    { value: "default", label: "Standard" },
                    { value: "mp4", label: "MP4" },
                    { value: "mkv", label: "MKV" },
                  ]}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Select
                  inline
                  label="Auflösung"
                  value={quality}
                  onChange={(event) => pickQuality(event.target.value)}
                >
                  {qualities.map((q) => (
                    <option key={q.value} value={q.value}>
                      {q.label}
                    </option>
                  ))}
                </Select>
                <p className="text-[13px] text-secondary">{RESOLUTION_HINT}</p>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-[15px]">Kommentare</span>
                <SegmentedControl
                  label="Kommentare speichern"
                  value={comments}
                  onChange={pickComments}
                  options={[
                    { value: "default", label: "Standard" },
                    { value: "yes", label: "An" },
                    { value: "no", label: "Aus" },
                  ]}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={close}>
            Abbrechen
          </Button>
          <Button type="submit" loading={add.isPending} disabled={!url.trim()}>
            Herunterladen
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
