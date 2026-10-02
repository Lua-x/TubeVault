import { CircleAlert, CircleCheck } from "lucide-react";

import { useHardware, useHwTest } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import type { HwAccel, TranscodeOptions } from "@/lib/types";

const ACCELS: { value: HwAccel; label: string }[] = [
  { value: "none", label: "Software" },
  { value: "vaapi", label: "Intel/AMD" },
  { value: "nvenc", label: "NVIDIA" },
];
const HEIGHTS = [2160, 1440, 1080, 720, 480] as const;
const CACHE_SIZES = [5, 10, 25, 50, 100, 250];

interface TranscodeGroupProps {
  value: TranscodeOptions;
  onChange: (patch: Partial<TranscodeOptions>) => void;
}

/** Hardware acceleration and limits for converting videos (admins only). */
export function TranscodeGroup({ value, onChange }: TranscodeGroupProps) {
  const { data: hardware } = useHardware(true);
  const test = useHwTest();

  const encoder =
    value.hwaccel === "vaapi" ? "h264_vaapi" : value.hwaccel === "nvenc" ? "h264_nvenc" : "libx264";
  const missingEncoder = hardware && hardware.encoders[encoder] === false;
  const devices = hardware?.render_devices ?? [];
  let footer =
    "Gebraucht wird das nur für Geräte, die eine Datei nicht direkt abspielen können, oder wenn du eine kleinere Qualität wählst. Die Originale bleiben unverändert.";
  if (value.hwaccel === "vaapi") {
    footer = devices.length
      ? `Im Container gefunden: ${devices.join(", ")}.`
      : "Im Container ist keine GPU sichtbar – gib /dev/dri frei (siehe Anleitung).";
  } else if (value.hwaccel === "nvenc") {
    footer = hardware?.nvidia
      ? "NVIDIA-GPU im Container gefunden."
      : "Im Container ist keine NVIDIA-GPU sichtbar – dafür braucht es das NVIDIA Container Toolkit (siehe Anleitung).";
  }

  return (
    <Group title="Umwandlung" footer={footer}>
      <Row className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[15px]">Hardware-Beschleunigung</span>
        <SegmentedControl
          label="Hardware-Beschleunigung"
          value={value.hwaccel}
          onChange={(hwaccel) => {
            test.reset();
            onChange({ hwaccel });
          }}
          options={ACCELS}
        />
      </Row>
      {value.hwaccel === "vaapi" && (
        <Row>
          <TextField
            label="Gerät"
            value={value.vaapi_device}
            onChange={(e) => onChange({ vaapi_device: e.target.value })}
            hint="Meist /dev/dri/renderD128"
          />
        </Row>
      )}
      <Row className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-[13px]">
          {test.data ? (
            <span
              className={
                test.data.ok
                  ? "flex items-center gap-1.5 text-success"
                  : "flex items-start gap-1.5 text-danger"
              }
            >
              {test.data.ok ? (
                <CircleCheck className="size-4 shrink-0" strokeWidth={2} />
              ) : (
                <CircleAlert className="mt-px size-4 shrink-0" strokeWidth={2} />
              )}
              <span className="break-words whitespace-pre-line">
                {test.data.ok
                  ? `Funktioniert (${test.data.seconds.toLocaleString("de-DE")} s für 2 s Testvideo)`
                  : test.data.message}
              </span>
            </span>
          ) : missingEncoder ? (
            <span className="text-danger">Dieses ffmpeg kennt den Encoder {encoder} nicht.</span>
          ) : (
            <span className="text-secondary">Kurzer Test mit einem 2-Sekunden-Video</span>
          )}
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={test.isPending}
          onClick={() => test.mutate({ hwaccel: value.hwaccel, vaapi_device: value.vaapi_device })}
        >
          Prüfen
        </Button>
      </Row>
      <Row>
        <Select
          inline
          label="Höchste Qualität beim Umwandeln"
          value={String(value.max_height)}
          onChange={(e) =>
            onChange({ max_height: Number(e.target.value) as TranscodeOptions["max_height"] })
          }
        >
          {HEIGHTS.map((h) => (
            <option key={h} value={h}>
              {h === 2160 ? "4K (2160p)" : `${h}p`}
            </option>
          ))}
        </Select>
      </Row>
      <Row>
        <Select
          inline
          label="Gleichzeitige Umwandlungen"
          value={String(value.max_sessions)}
          onChange={(e) => onChange({ max_sessions: Number(e.target.value) })}
        >
          {[1, 2, 3, 4, 6, 8].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
      </Row>
      <Row>
        <Select
          inline
          label="Zwischenspeicher"
          value={String(value.cache_gb)}
          onChange={(e) => onChange({ cache_gb: Number(e.target.value) })}
        >
          {CACHE_SIZES.map((gb) => (
            <option key={gb} value={gb}>
              {gb} GB
            </option>
          ))}
        </Select>
      </Row>
    </Group>
  );
}
