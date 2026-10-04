import { useCallback, useEffect, useRef } from "react";

import { useAuth } from "@/hooks/auth";

/** The rate map with one channel changed, or null if nothing changes. */
export function withChannelRate(
  current: Record<string, number> | undefined,
  channelId: number,
  value: number,
): Record<string, number> | null {
  const key = String(channelId);
  if ((current?.[key] ?? 1) === value) return null;
  const next = { ...current };
  if (value === 1) delete next[key];
  else next[key] = value;
  return next;
}

/**
 * The playback speed this account chose for a channel – a talk channel at 1.5×, music at
 * 1×. Kept in the account's preferences, so it follows to every device.
 */
export function useChannelRate(channelId: number | null | undefined) {
  const { user, updatePreferences } = useAuth();
  const rates = user?.preferences.channel_rates;
  const latest = useRef(rates);
  useEffect(() => {
    latest.current = rates;
  });

  const key = channelId == null ? null : String(channelId);
  const rate = (key && rates?.[key]) || 1;

  const save = useCallback(
    (value: number) => {
      if (channelId == null || !user) return;
      const next = withChannelRate(latest.current, channelId, value);
      if (!next) return;
      latest.current = next;
      void updatePreferences({ channel_rates: next }).catch(() => undefined);
    },
    [channelId, user, updatePreferences],
  );

  return [rate, save] as const;
}
