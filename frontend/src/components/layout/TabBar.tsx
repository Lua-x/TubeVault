import { NavLink, useLocation } from "react-router";

import { cn } from "@/lib/cn";

import { useAuth } from "@/hooks/auth";

import { navFor, TAB_NAV } from "./navigation";
import { useActiveDownloadCount } from "./useActiveDownloads";

/** iOS-style tab bar on phones. */
export function TabBar() {
  const active = useActiveDownloadCount();
  const { user } = useAuth();
  const { pathname } = useLocation();
  return (
    <nav
      aria-label="Hauptnavigation"
      className="glass pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-separator md:hidden"
    >
      <ul className="mx-auto flex max-w-lg">
        {navFor(TAB_NAV, user).map(({ to, label, icon: Icon, end, also }) => {
          const extra = also?.some((path) => pathname.startsWith(path)) ?? false;
          return (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-[52px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors duration-200",
                    isActive || extra ? "text-accent" : "text-tertiary",
                  )
                }
              >
                <span className="relative">
                  <Icon className="size-6" strokeWidth={1.6} />
                  {to === "/downloads" && active > 0 && (
                    <span className="absolute -top-1 -right-2.5 min-w-4 rounded-full bg-danger px-1 text-center text-[10px] leading-4 font-semibold text-white">
                      {active}
                    </span>
                  )}
                </span>
                {label}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
