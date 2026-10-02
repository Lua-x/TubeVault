import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { api, request, setUnauthorizedHandler } from "@/lib/api";
import type { AuthStatus, User } from "@/lib/types";

interface AuthContextValue {
  status: AuthStatus | undefined;
  isLoading: boolean;
  error: Error | null;
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
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
        const user = await request<User>(
          "POST",
          "auth/login",
          { username, password },
          {
            quiet401: true,
          },
        );
        setUser(user);
      },
      setup: async (username, password) => {
        setUser(await api.post<User>("auth/setup", { username, password }));
      },
      logout: async () => {
        await api.post("auth/logout").catch(() => undefined);
        client.clear();
        client.setQueryData<AuthStatus>(STATUS_KEY, { setup_required: false, user: null });
      },
      refresh: () => query.refetch(),
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

export function useCurrentUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("No user signed in");
  return user;
}
