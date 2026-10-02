import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import {
  useAppSettings,
  useChangePassword,
  useCreateUser,
  useDeleteUser,
  useSaveSettings,
  useSystemInfo,
  useUpdateUser,
  useUsers,
} from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryGroup, LibraryTaskStatus } from "@/components/settings/LibraryGroup";
import { TranscodeGroup } from "@/components/settings/TranscodeGroup";
import { Dialog } from "@/components/ui/Dialog";
import { Button, IconButton } from "@/components/ui/Button";
import { Group, Row } from "@/components/ui/Group";
import { TextField } from "@/components/ui/Input";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { useAuth, useCurrentUser } from "@/hooks/auth";
import { useTheme } from "@/hooks/theme";
import { useToast } from "@/hooks/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import { SPONSOR_CATEGORIES, SPONSORBLOCK_MODES } from "@/lib/sponsorblock";
import type { AppSettings, MaxHeight, Preferences, SponsorCategory, Theme } from "@/lib/types";

export function SettingsPage() {
  useDocumentTitle("Einstellungen");
  const user = useCurrentUser();
  return (
    <>
      <PageHeader title="Einstellungen" />
      <div className="flex max-w-2xl flex-col gap-9 pb-12">
        <AppearanceSection />
        <PlaybackSection />
        {user.is_admin && <DownloadSection />}
        <AccountSection />
        {user.is_admin && <UsersSection />}
        <SystemSection />
      </div>
    </>
  );
}

function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  return (
    <Group title="Darstellung">
      <Row className="flex items-center justify-between gap-4">
        <span className="text-[15px]">Erscheinungsbild</span>
        <SegmentedControl<Theme>
          label="Erscheinungsbild"
          value={theme}
          onChange={setTheme}
          options={[
            { value: "system", label: "System" },
            { value: "light", label: "Hell" },
            { value: "dark", label: "Dunkel" },
          ]}
        />
      </Row>
    </Group>
  );
}

function PlaybackSection() {
  const { user, updatePreferences } = useAuth();
  const toast = useToast();
  const preferences = user?.preferences ?? {};
  const update = (patch: Preferences) =>
    updatePreferences(patch).catch((err: unknown) =>
      toast(err instanceof Error ? err.message : "Speichern fehlgeschlagen", "error"),
    );
  return (
    <Group title="Wiedergabe" footer="Gilt nur für dein Konto.">
      <Row>
        <Switch
          label="Weiter mit nächstem Playlist-Video"
          description="Nach dem Ende startet das nächste Video nach 5 Sekunden."
          checked={preferences.autoplay_next !== false}
          onChange={(autoplay_next) => void update({ autoplay_next })}
        />
      </Row>
      <Row>
        <Switch
          label="SponsorBlock automatisch überspringen"
          description="Sonst erscheint im Player eine Taste zum Überspringen."
          checked={preferences.sponsorblock_skip !== false}
          onChange={(sponsorblock_skip) => void update({ sponsorblock_skip })}
        />
      </Row>
    </Group>
  );
}

const SPONSORBLOCK_FOOTER = {
  off: "Es wird keine Verbindung zu SponsorBlock aufgebaut.",
  skip: "Markierte Abschnitte werden beim Abspielen übersprungen. Abgefragt wird sponsor.ajay.app – dabei verlassen nur die ersten Zeichen eines Hashes der Video-ID den Server.",
  cut: "Markierte Abschnitte werden beim Download dauerhaft aus der Datei entfernt. Gilt für neue Downloads.",
} as const;

const HEIGHTS: { value: string; label: string }[] = [
  { value: "", label: "Beste verfügbare" },
  { value: "2160", label: "4K (2160p)" },
  { value: "1440", label: "1440p" },
  { value: "1080", label: "1080p" },
  { value: "720", label: "720p" },
  { value: "480", label: "480p" },
  { value: "360", label: "360p" },
];

function DownloadSection() {
  const { data } = useAppSettings();
  return data ? <DownloadForm initial={data} /> : null;
}

function DownloadForm({ initial }: { initial: AppSettings }) {
  const save = useSaveSettings();
  const toast = useToast();
  const [draft, setDraft] = useState<AppSettings>(initial);
  const [languages, setLanguages] = useState(initial.downloads.subtitle_languages.join(", "));

  const downloads = draft.downloads;
  const update = (patch: Partial<AppSettings["downloads"]>) =>
    setDraft({ ...draft, downloads: { ...downloads, ...patch } });

  const [savedLayout, setSavedLayout] = useState(initial.library.layout);
  const [confirmMove, setConfirmMove] = useState<AppSettings | null>(null);

  const persist = async (next: AppSettings) => {
    setConfirmMove(null);
    try {
      const saved = await save.mutateAsync(next);
      setDraft(saved);
      setSavedLayout(saved.library.layout);
      setLanguages(saved.downloads.subtitle_languages.join(", "));
      toast("Einstellungen gespeichert");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Speichern fehlgeschlagen", "error");
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next: AppSettings = {
      ...draft,
      downloads: {
        ...downloads,
        subtitle_languages: languages
          .split(/[,\s]+/)
          .map((l) => l.trim())
          .filter(Boolean),
      },
    };
    // Moving every file deserves a confirmation.
    if (next.library.layout !== savedLayout) setConfirmMove(next);
    else void persist(next);
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-9">
      <Group
        title="Downloads"
        footer={
          downloads.container === "mkv"
            ? "MKV spielen Safari und iOS nicht direkt ab. Chrome, Edge und Firefox kommen meist damit klar."
            : "MP4 mit H.264 läuft in jedem Browser und in Jellyfin/Plex."
        }
      >
        <Row className="flex items-center justify-between gap-4">
          <span className="text-[15px]">Format</span>
          <SegmentedControl
            label="Format"
            value={downloads.container}
            onChange={(container) => update({ container })}
            options={[
              { value: "mp4", label: "MP4" },
              { value: "mkv", label: "MKV" },
            ]}
          />
        </Row>
        <Row>
          <Select
            inline
            label="Maximale Qualität"
            value={downloads.max_height == null ? "" : String(downloads.max_height)}
            onChange={(e) =>
              update({ max_height: e.target.value ? (Number(e.target.value) as MaxHeight) : null })
            }
          >
            {HEIGHTS.map((h) => (
              <option key={h.value} value={h.value}>
                {h.label}
              </option>
            ))}
          </Select>
        </Row>
        <Row>
          <Switch
            label="H.264 bevorzugen"
            description="Beste Kompatibilität. YouTube bietet H.264 nur bis 1080p an."
            checked={downloads.prefer_h264}
            onChange={(prefer_h264) => update({ prefer_h264 })}
          />
        </Row>
        <Row>
          <Select
            inline
            label="Gleichzeitige Downloads"
            value={String(draft.max_concurrent_downloads)}
            onChange={(e) =>
              setDraft({ ...draft, max_concurrent_downloads: Number(e.target.value) })
            }
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Row>
      </Group>

      <Group title="Untertitel">
        <Row>
          <Switch
            label="Untertitel laden"
            checked={downloads.subtitles}
            onChange={(subtitles) => update({ subtitles })}
          />
        </Row>
        <Row>
          <Switch
            label="Automatische Untertitel"
            description="Von YouTube erzeugt, nur in der Originalsprache des Videos."
            checked={downloads.auto_subtitles}
            onChange={(auto_subtitles) => update({ auto_subtitles })}
          />
        </Row>
        <Row>
          <TextField
            label="Sprachen"
            hint="Sprachcodes, durch Komma getrennt, z. B. de, en"
            value={languages}
            onChange={(e) => setLanguages(e.target.value)}
          />
        </Row>
      </Group>

      <Group title="SponsorBlock" footer={SPONSORBLOCK_FOOTER[downloads.sponsorblock_mode]}>
        <Row className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-[15px]">Werbung und Füllmaterial</span>
          <SegmentedControl
            label="SponsorBlock"
            value={downloads.sponsorblock_mode}
            onChange={(sponsorblock_mode) => update({ sponsorblock_mode })}
            options={SPONSORBLOCK_MODES}
          />
        </Row>
        {downloads.sponsorblock_mode !== "off" && (
          <Row>
            <p className="text-[15px]">Kategorien</p>
            <CategoryPicker
              value={downloads.sponsorblock_categories}
              onChange={(sponsorblock_categories) => update({ sponsorblock_categories })}
            />
          </Row>
        )}
      </Group>

      <TranscodeGroup
        value={draft.transcoding}
        onChange={(patch) =>
          setDraft({ ...draft, transcoding: { ...draft.transcoding, ...patch } })
        }
      />

      <div className="flex flex-col gap-3">
        <LibraryGroup
          value={draft.library}
          onChange={(patch) => setDraft({ ...draft, library: { ...draft.library, ...patch } })}
        />
        <LibraryTaskStatus />
      </div>

      <div className="flex justify-end">
        <Button type="submit" loading={save.isPending}>
          Speichern
        </Button>
      </div>

      <Dialog
        open={confirmMove != null}
        onClose={() => setConfirmMove(null)}
        title="Bibliothek umziehen?"
      >
        <p className="text-[15px] text-secondary">
          Alle Videos samt Thumbnails, Untertiteln und NFO-Dateien werden in die neue Ordnerstruktur
          verschoben. Bei großen Bibliotheken dauert das ein paar Minuten. Lass Jellyfin oder Plex
          danach die Bibliothek neu scannen.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => setConfirmMove(null)}>
            Abbrechen
          </Button>
          <Button
            type="button"
            loading={save.isPending}
            onClick={() => confirmMove && void persist(confirmMove)}
          >
            Umziehen
          </Button>
        </div>
      </Dialog>
    </form>
  );
}

function CategoryPicker({
  value,
  onChange,
}: {
  value: SponsorCategory[];
  onChange: (value: SponsorCategory[]) => void;
}) {
  const toggle = (category: SponsorCategory) =>
    onChange(value.includes(category) ? value.filter((c) => c !== category) : [...value, category]);
  return (
    <div className="mt-2.5 flex flex-wrap gap-2">
      {SPONSOR_CATEGORIES.map((category) => {
        const active = value.includes(category.value);
        return (
          <button
            key={category.value}
            type="button"
            aria-pressed={active}
            title={category.hint}
            onClick={() => toggle(category.value)}
            className={cn(
              "h-8 rounded-full px-3.5 text-[13px] font-medium transition-colors duration-200",
              active
                ? "bg-accent text-white hover:bg-accent-hover"
                : "bg-surface text-secondary hover:bg-surface-hover hover:text-primary",
            )}
          >
            {category.label}
          </button>
        );
      })}
    </div>
  );
}

function AccountSection() {
  const change = useChangePassword();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await change.mutateAsync({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      toast("Passwort geändert. Andere Geräte wurden abgemeldet.");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Ändern fehlgeschlagen", "error");
    }
  };

  return (
    <form onSubmit={submit}>
      <Group title="Konto">
        <Row className="flex flex-col gap-4">
          <TextField
            label="Aktuelles Passwort"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <TextField
            label="Neues Passwort"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            hint="Mindestens 8 Zeichen"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" loading={change.isPending}>
              Passwort ändern
            </Button>
          </div>
        </Row>
      </Group>
    </form>
  );
}

function UsersSection() {
  const me = useCurrentUser();
  const { data: users } = useUsers(true);
  const create = useCreateUser();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  const fail = (err: unknown) =>
    toast(err instanceof Error ? err.message : "Aktion fehlgeschlagen", "error");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await create.mutateAsync({ username: username.trim(), password, is_admin: isAdmin });
      setUsername("");
      setPassword("");
      setIsAdmin(false);
      toast("Benutzer angelegt");
    } catch (err) {
      fail(err);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Group title="Benutzer">
        {(users ?? []).map((user) => (
          <Row key={user.id} className="flex items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface text-[13px] font-semibold uppercase">
              {user.username.slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px]">
                {user.username}
                {user.id === me.id && <span className="text-tertiary"> (du)</span>}
              </p>
            </div>
            <label className="flex items-center gap-2 text-[13px] text-secondary">
              <input
                type="checkbox"
                className="size-4 accent-[var(--tv-accent)]"
                checked={user.is_admin}
                disabled={user.id === me.id}
                onChange={(e) =>
                  update.mutateAsync({ id: user.id, is_admin: e.target.checked }).catch(fail)
                }
              />
              Admin
            </label>
            <IconButton
              label={`${user.username} löschen`}
              disabled={user.id === me.id}
              onClick={() => {
                if (window.confirm(`Benutzer „${user.username}“ wirklich löschen?`)) {
                  remove.mutateAsync(user.id).catch(fail);
                }
              }}
            >
              <Trash2 className="size-[18px]" strokeWidth={1.75} />
            </IconButton>
          </Row>
        ))}
      </Group>
      <form onSubmit={submit} className="rounded-2xl bg-elevated p-4">
        <p className="mb-3 text-[15px] font-medium">Neuer Benutzer</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Benutzername"
            autoComplete="off"
            autoCapitalize="none"
            required
            pattern="[A-Za-z0-9._\-]{2,64}"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <TextField
            label="Passwort"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="mt-4 flex items-center justify-between gap-4">
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              className="size-4 accent-[var(--tv-accent)]"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
            />
            Administrator
          </label>
          <Button type="submit" variant="secondary" loading={create.isPending}>
            Anlegen
          </Button>
        </div>
      </form>
    </div>
  );
}

const SOURCE_URL = "https://github.com/Lua-x/TubeVault";

function SystemSection() {
  const { data } = useSystemInfo();
  if (!data) return null;
  const usedShare = data.disk ? data.disk.used / data.disk.total : null;
  const rows: [string, string][] = [
    ["TubeVault", data.version],
    ["yt-dlp", data.ytdlp_version ?? "nicht gefunden"],
    ["ffmpeg", data.ffmpeg_version ?? "nicht gefunden"],
    ["Videos", String(data.video_count)],
    ["Bibliotheksgröße", formatBytes(data.library_size)],
  ];
  return (
    <Group
      title="System"
      footer={
        <>
          TubeVault ist freie Software unter der{" "}
          <a
            href={`${SOURCE_URL}/blob/main/LICENSE`}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline"
          >
            AGPL-3.0
          </a>
          . Den Quellcode findest du auf{" "}
          <a
            href={SOURCE_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline"
          >
            GitHub
          </a>
          .
        </>
      }
    >
      {rows.map(([label, value]) => (
        <Row key={label} className="flex justify-between gap-4 text-[15px]">
          <span>{label}</span>
          <span className="text-secondary">{value}</span>
        </Row>
      ))}
      {data.disk && usedShare != null && (
        <Row>
          <div className="mb-2 flex justify-between gap-4 text-[15px]">
            <span>Speicherplatz</span>
            <span className="text-secondary">
              {formatBytes(data.disk.free)} frei von {formatBytes(data.disk.total)}
            </span>
          </div>
          <ProgressBar value={usedShare} label="Belegter Speicherplatz" />
        </Row>
      )}
    </Group>
  );
}
