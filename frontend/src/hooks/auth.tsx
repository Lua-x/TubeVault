import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { api, request, setUnauthorizedHandler } from "@/lib/api";
import type { AuthStatus, Preferences, TwoFactorChallenge, User } from "@/lib/types";

interface AuthContextValue {
  status: AuthStatus | undefined;
  isLoading: boolean;
  error: Error | null;
  user: User | null;
  /** Resolves to a ticket when the code from the authenticator app is still needed. */
  login: (username: string, password: string) => Promise<string | null>;
  loginWithCode: (ticket: string, code: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
  /** Merges into the signed-in user's preferences (optimistically). */
  updatePreferences: (patch: Preferences) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const STATUS_KEY = ["auth", "status"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => request<AuthStatus>("GET", "auth/status", undefined, { quiet401: true }),
    staleTime: Infinity,
    retry: 1,
  });

  const setUser = useCallback(
    (user: User | null) => {
      client.setQueryData<AuthStatus>(STATUS_KEY, (old) => ({
        oidc_name: old?.oidc_name ?? null,
        password_login: old?.password_login ?? true,
        setup_required: user ? false : (old?.setup_required ?? false),
        user,
      }));
    },
    [client],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
    });
    return () => setUnauthorizedHandler(null);
  }, [setUser]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status: query.data,
      isLoading: query.isLoading,
      error: query.error,
      user: query.data?.user ?? null,
      login: async (username, password) => {
        const result = await request<User | TwoFactorChallenge>(
          "POST",
          "auth/login",
          { username, password },
          { quiet401: true },
        );
        if ("two_factor" in result && result.two_factor === true && "ticket" in result) {
          return result.ticket;
        }
        setUser(result as User);
        return null;
      },
      loginWithCode: async (ticket, code) => {
        setUser(
          await request<User>("POST", "auth/login/2fa", { ticket, code }, { quiet401: true }),
        );
      },
      setup: async (username, password) => {
        setUser(await api.post<User>("auth/setup", { username, password }));
      },
      logout: async () => {
        await api.post("auth/logout").catch(() => undefined);
        const previous = client.getQueryData<AuthStatus>(STATUS_KEY);
        client.clear();
        client.setQueryData<AuthStatus>(STATUS_KEY, {
          oidc_name: previous?.oidc_name ?? null,
          password_login: previous?.password_login ?? true,
          setup_required: false,
          user: null,
        });
      },
      refresh: () => query.refetch(),
      updatePreferences: async (patch) => {
        const current = query.data?.user;
        if (!current) return;
        setUser({ ...current, preferences: { ...current.preferences, ...patch } });
        try {
          setUser(await api.put<User>("auth/me/preferences", patch));
        } catch (err) {
          setUser(current);
          throw err;
        }
      },
    }),
    [query, client, setUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** May add videos, subscribe and manage downloads (not view-only accounts). */
export function useCanAdd(): boolean {
  return useAuth().user?.can_add ?? false;
}

export function useCurrentUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("No user signed in");
  return user;
}
