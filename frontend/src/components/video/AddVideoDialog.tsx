import { ChevronRight, Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { useAddVideo } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { useAuth } from "@/hooks/auth";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { AddVideoChoices, Container, MaxHeight } from "@/lib/types";

type ContainerChoice = "default" | Container;

const QUALITIES: { value: string; label: string }[] = [
  { value: "", label: "Standard (Einstellungen)" },
  { value: "2160", label: "Bis 4K" },
  { value: "1440", label: "Bis 1440p" },
  { value: "1080", label: "Bis 1080p" },
  { value: "720", label: "Bis 720p" },
  { value: "480", label: "Bis 480p" },
];

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
  const [comments, setComments] = useState<"default" | "yes" | "no">(
    remembered.comments == null ? "default" : remembered.comments ? "yes" : "no",
  );
  const add = useAddVideo();
  const toast = useToast();
  const navigate = useNavigate();

  // Shown next to the collapsed "Optionen", so remembered choices don't go unnoticed.
  const summary = [
    QUALITIES.find((q) => q.value === quality && q.value)?.label,
    container === "default" ? undefined : container.toUpperCase(),
    comments === "default" ? undefined : comments === "yes" ? "Kommentare an" : "Kommentare aus",
  ]
    .filter(Boolean)
    .join(" · ");

  const close = () => {
    onClose();
    add.reset();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const choices: AddVideoChoices = {
      container: container === "default" ? undefined : container,
      max_height: quality ? (Number(quality) as MaxHeight) : undefined,
      comments: comments === "default" ? undefined : comments === "yes",
    };
    try {
      await add.mutateAsync({ url: url.trim(), ...choices });
      if (!sameChoices(choices, remembered)) {
        // Not worth an error message: the download itself is on its way.
        updatePreferences({ add_video: choices }).catch(() => undefined);
      }
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
                  onChange={setContainer}
                  options={[
                    { value: "default", label: "Standard" },
                    { value: "mp4", label: "MP4" },
                    { value: "mkv", label: "MKV" },
                  ]}
                />
              </div>
              <Select
                inline
                label="Qualität"
                value={quality}
                onChange={(event) => setQuality(event.target.value)}
              >
                {QUALITIES.map((q) => (
                  <option key={q.value} value={q.value}>
                    {q.label}
                  </option>
                ))}
              </Select>
              <div className="flex items-center justify-between gap-4">
                <span className="text-[15px]">Kommentare</span>
                <SegmentedControl
                  label="Kommentare speichern"
                  value={comments}
                  onChange={setComments}
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

function sameChoices(a: AddVideoChoices, b: AddVideoChoices): boolean {
  return a.container === b.container && a.max_height === b.max_height && a.comments === b.comments;
}
