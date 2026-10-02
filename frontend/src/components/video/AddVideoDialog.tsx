import { ChevronRight, Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { useAddVideo } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/hooks/toast";
import { cn } from "@/lib/cn";
import type { Container, MaxHeight } from "@/lib/types";

type ContainerChoice = "default" | Container;

const QUALITIES: { value: string; label: string }[] = [
  { value: "", label: "Standard (Einstellungen)" },
  { value: "2160", label: "Bis 4K" },
  { value: "1440", label: "Bis 1440p" },
  { value: "1080", label: "Bis 1080p" },
  { value: "720", label: "Bis 720p" },
  { value: "480", label: "Bis 480p" },
];

export function AddVideoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [container, setContainer] = useState<ContainerChoice>("default");
  const [quality, setQuality] = useState("");
  const add = useAddVideo();
  const toast = useToast();
  const navigate = useNavigate();

  const close = () => {
    onClose();
    add.reset();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await add.mutateAsync({
        url: url.trim(),
        container: container === "default" ? undefined : container,
        max_height: quality ? (Number(quality) as MaxHeight) : undefined,
      });
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
          hint="Link zu einem einzelnen YouTube-Video. Kanäle und Playlists folgen in Version 0.2."
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
