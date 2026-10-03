import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { useCurrentUser } from "@/hooks/auth";

import { BACKFILL, HEIGHTS, INTERVALS, KEEP_DAYS, SPONSORBLOCK, type FormValues } from "./options";

interface SubscriptionFormProps {
  values: FormValues;
  onChange: (values: FormValues) => void;
  mode: "create" | "edit";
}

/** All settings of a subscription, grouped like iOS Settings. */
export function SubscriptionForm({ values, onChange, mode }: SubscriptionFormProps) {
  const set = <K extends keyof FormValues>(key: K, value: FormValues[K]) =>
    onChange({ ...values, [key]: value });
  // Cleanup rules delete files, which only admins may do.
  const canCleanUp = useCurrentUser().is_admin;
  const intervals = INTERVALS.some((i) => String(i.value) === values.interval)
    ? INTERVALS
    : [...INTERVALS, { value: Number(values.interval), label: `Alle ${values.interval} Minuten` }];

  return (
    <div className="flex flex-col gap-7">
      <Group title="Prüfen">
        {mode === "edit" && (
          <Row>
            <Switch
              label="Aktiv"
              description="Pausierte Abos werden nicht automatisch geprüft."
              checked={values.enabled}
              onChange={(enabled) => set("enabled", enabled)}
            />
          </Row>
        )}
        <Row>
          <Select
            inline
            label="Auf neue Videos prüfen"
            value={values.interval}
            onChange={(e) => set("interval", e.target.value)}
          >
            {intervals.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Row>
        {mode === "create" && (
          <Row>
            <Select
              inline
              label="Vorhandene Videos"
              value={values.backfill}
              onChange={(e) => set("backfill", e.target.value)}
            >
              {BACKFILL.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Row>
        )}
      </Group>

      <Group
        title="Filter"
        footer="Videos, die nicht passen, werden übersprungen und nicht geladen."
      >
        <Row>
          <Switch
            label="Shorts"
            checked={values.includeShorts}
            onChange={(v) => set("includeShorts", v)}
          />
        </Row>
        <Row>
          <Switch
            label="Livestreams"
            description="Aufzeichnungen beendeter Streams"
            checked={values.includeLive}
            onChange={(v) => set("includeLive", v)}
          />
        </Row>
        <Row className="grid grid-cols-2 gap-3">
          <TextField
            label="Mindestdauer (Min.)"
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            placeholder="–"
            value={values.minMinutes}
            onChange={(e) => set("minMinutes", e.target.value)}
          />
          <TextField
            label="Maximaldauer (Min.)"
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            placeholder="–"
            value={values.maxMinutes}
            onChange={(e) => set("maxMinutes", e.target.value)}
          />
        </Row>
        <Row>
          <TextField
            label="Nur Videos ab"
            type="date"
            value={values.dateAfter}
            onChange={(e) => set("dateAfter", e.target.value)}
          />
        </Row>
      </Group>

      <Group title="Qualität">
        <Row>
          <Select
            inline
            label="Maximale Qualität"
            value={values.maxHeight}
            onChange={(e) => set("maxHeight", e.target.value)}
          >
            {HEIGHTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Row>
        <Row className="flex items-center justify-between gap-4">
          <span className="text-[15px]">Format</span>
          <SegmentedControl
            label="Format"
            value={values.container}
            onChange={(container) => set("container", container)}
            options={[
              { value: "default", label: "Standard" },
              { value: "mp4", label: "MP4" },
              { value: "mkv", label: "MKV" },
            ]}
          />
        </Row>
        <Row className="flex items-center justify-between gap-4">
          <span className="text-[15px]">H.264 bevorzugen</span>
          <SegmentedControl
            label="H.264 bevorzugen"
            value={values.preferH264}
            onChange={(preferH264) => set("preferH264", preferH264)}
            options={[
              { value: "default", label: "Standard" },
              { value: "yes", label: "An" },
              { value: "no", label: "Aus" },
            ]}
          />
        </Row>
        <Row>
          <Select
            inline
            label="SponsorBlock"
            value={values.sponsorblock}
            onChange={(e) => set("sponsorblock", e.target.value as FormValues["sponsorblock"])}
          >
            {SPONSORBLOCK.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Row>
        <Row className="flex items-center justify-between gap-4">
          <span className="text-[15px]">Kommentare speichern</span>
          <SegmentedControl
            label="Kommentare speichern"
            value={values.comments}
            onChange={(comments) => set("comments", comments)}
            options={[
              { value: "default", label: "Standard" },
              { value: "yes", label: "An" },
              { value: "no", label: "Aus" },
            ]}
          />
        </Row>
      </Group>

      <Group
        title="Aufräumen"
        footer={
          canCleanUp
            ? "Gilt nur für Videos aus diesem Abo. Von Hand hinzugefügte Videos bleiben immer."
            : "Aufräumregeln löschen Videos und können deshalb nur Administratoren ändern."
        }
      >
        <Row>
          <Select
            inline
            label="Videos löschen"
            disabled={!canCleanUp}
            value={values.keepDays}
            onChange={(e) => set("keepDays", e.target.value)}
          >
            {KEEP_DAYS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Row>
        <Row>
          <TextField
            label="Nur die neuesten behalten"
            type="number"
            inputMode="numeric"
            min={1}
            placeholder="Alle"
            disabled={!canCleanUp}
            value={values.keepLast}
            onChange={(e) => set("keepLast", e.target.value)}
          />
        </Row>
      </Group>
    </div>
  );
}
