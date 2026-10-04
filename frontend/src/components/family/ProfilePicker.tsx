import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useCallback, useState } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/auth";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { FamilyProfile } from "@/lib/types";

import { PinPad } from "./PinPad";
import { ProfileAvatar } from "./ProfileAvatar";

interface ProfilePickerProps {
  /** Big tiles for the TV, chosen with the arrow keys. */
  tv?: boolean;
  /** After a profile was chosen. */
  onDone?: () => void;
  /** Back without switching (only when someone is signed in already). */
  onCancel?: () => void;
  /** Signed out: sign in with a password instead. */
  onPasswordLogin?: () => void;
}

/** "Wer schaut?" – the profiles a family device offers. */
export function ProfilePicker({ tv, onDone, onCancel, onPasswordLogin }: ProfilePickerProps) {
  const { user, status, switchProfile } = useAuth();
  const { data: profiles, error } = useQuery({
    queryKey: ["family", "profiles"],
    queryFn: () => api.get<FamilyProfile[]>("family/profiles"),
    staleTime: 30_000,
  });
  const [asking, setAsking] = useState<FamilyProfile | null>(null);
  const [pinError, setPinError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const choose = async (profile: FamilyProfile, pin?: string) => {
    if (profile.id === user?.id) {
      onDone?.();
      return;
    }
    if (profile.has_pin && pin === undefined) {
      setPinError(null);
      setAsking(profile);
      return;
    }
    setBusy(true);
    try {
      await switchProfile(profile.id, pin);
      setAsking(null);
      onDone?.();
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? "Falsche PIN – bitte noch einmal."
          : err instanceof Error
            ? err.message
            : "Das hat nicht geklappt";
      if (asking || profile.has_pin) setPinError(message);
    } finally {
      setBusy(false);
    }
  };
  const cancelPin = useCallback(() => setAsking(null), []);

  const tileText = tv ? "text-[max(18px,1.4vw)]" : "text-[15px]";
  const avatarSize = tv
    ? "size-[max(8rem,10vw)] text-[max(48px,4vw)]"
    : "size-24 text-[40px] sm:size-28";

  return (
    <main
      className={cn(
        "flex min-h-dvh flex-col items-center justify-center gap-10 bg-canvas px-6 py-12 text-primary",
      )}
    >
      {asking ? (
        <PinPad
          tv={tv}
          title={`PIN für ${asking.username}`}
          error={pinError}
          busy={busy}
          onSubmit={(pin) => void choose(asking, pin)}
          onCancel={cancelPin}
        />
      ) : (
        <>
          <h1
            className={cn("font-bold tracking-tight", tv ? "text-[max(36px,3vw)]" : "text-[32px]")}
          >
            Wer schaut?
          </h1>
          {error ? (
            <p className="max-w-sm text-center text-[15px] text-secondary">{error.message}</p>
          ) : !profiles ? (
            <Spinner className="size-6" />
          ) : profiles.length === 0 ? (
            <p className="max-w-sm text-center text-[15px] text-secondary">
              Noch kein Profil ist für Familiengeräte freigegeben. Das geht unter Einstellungen →
              „Wer schaut?“ – für Kinderprofile in der Benutzerverwaltung.
            </p>
          ) : (
            <ul className="flex max-w-4xl flex-wrap justify-center gap-x-8 gap-y-10">
              {profiles.map((profile) => (
                <li key={profile.id}>
                  <button
                    type="button"
                    data-tv-focus={tv ? "" : undefined}
                    data-tv-key={tv ? `profile-${profile.id}` : undefined}
                    disabled={busy}
                    onClick={() => void choose(profile)}
                    className="group flex flex-col items-center gap-3 rounded-3xl p-2 outline-none"
                  >
                    <span
                      className={cn(
                        "rounded-full transition-[transform,box-shadow] duration-200",
                        "group-hover:scale-105 group-focus-visible:scale-105 group-focus-visible:shadow-[0_0_0_4px_var(--tv-canvas),0_0_0_7px_var(--tv-text)]",
                        tv &&
                          "group-focus:scale-110 group-focus:shadow-[0_0_0_5px_var(--tv-canvas),0_0_0_9px_white]",
                        profile.id === user?.id &&
                          "shadow-[0_0_0_4px_var(--tv-canvas),0_0_0_7px_var(--tv-accent)]",
                      )}
                    >
                      <ProfileAvatar
                        id={profile.id}
                        name={profile.username}
                        className={avatarSize}
                      />
                    </span>
                    <span className={cn("flex items-center gap-1.5 font-medium", tileText)}>
                      {profile.username}
                      {profile.has_pin && (
                        <Lock
                          className="size-4 text-secondary"
                          strokeWidth={2}
                          aria-label="mit PIN"
                        />
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap justify-center gap-3">
            {onCancel && (
              <button
                type="button"
                data-tv-focus={tv ? "" : undefined}
                data-tv-key={tv ? "profiles-cancel" : undefined}
                onClick={onCancel}
                className="h-10 rounded-full bg-surface px-5 text-[14px] font-medium text-secondary outline-none hover:bg-surface-hover focus:text-primary focus-visible:ring-2 focus-visible:ring-accent"
              >
                Zurück
              </button>
            )}
            {onPasswordLogin && (
              <button
                type="button"
                onClick={onPasswordLogin}
                className="h-10 rounded-full px-5 text-[14px] font-medium text-secondary outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-accent"
              >
                Mit Passwort anmelden
              </button>
            )}
          </div>
          {status?.family_device && (
            <p className="text-[13px] text-tertiary">Familiengerät „{status.family_device}“</p>
          )}
        </>
      )}
    </main>
  );
}
