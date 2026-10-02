import { LogOut, Plus } from "lucide-react";
import { NavLink } from "react-router";

import { IconButton } from "@/components/ui/Button";
import { useAuth } from "@/hooks/auth";
import { cn } from "@/lib/cn";

import { NAV_ITEMS } from "./navigation";
import { useActiveDownloadCount } from "./useActiveDownloads";

export function Sidebar({ onAdd }: { onAdd: () => void }) {
  const { user, logout } = useAuth();
  const active = useActiveDownloadCount();

  return (
    <aside className="glass fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-separator px-3 pt-6 pb-4 md:flex">
      <div className="mb-7 flex items-center gap-2.5 px-3">
        <img src="./favicon.svg" alt="" className="size-7 rounded-[8px]" />
        <span className="text-[17px] font-semibold tracking-tight">TubeVault</span>
      </div>

      <button
        type="button"
        onClick={onAdd}
        className="mb-5 flex h-9 items-center gap-2 rounded-full bg-accent px-4 text-[14px] font-medium text-white transition-[background-color,transform] duration-200 ease-out-soft hover:bg-accent-hover active:scale-[0.98]"
      >
        <Plus className="size-4" strokeWidth={2.25} />
        Video hinzufügen
      </button>

      <nav aria-label="Hauptnavigation" className="flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "group flex h-9 items-center gap-3 rounded-lg px-3 text-[14px] transition-colors duration-200",
                isActive
                  ? "bg-surface font-medium text-primary"
                  : "text-secondary hover:bg-surface/60 hover:text-primary",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cn("size-[18px]", isActive ? "text-accent" : "")}
                  strokeWidth={1.75}
                />
                <span className="flex-1">{label}</span>
                {to === "/downloads" && active > 0 && (
                  <span className="min-w-5 rounded-full bg-accent px-1.5 text-center text-[11px] leading-5 font-semibold text-white">
                    {active}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto flex items-center gap-3 border-t border-separator px-2 pt-4">
        <div className="flex size-8 items-center justify-center rounded-full bg-surface text-[13px] font-semibold uppercase">
          {user?.username.slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-medium">{user?.username}</p>
          <p className="text-[12px] text-tertiary">
            {user?.is_admin ? "Administrator" : "Benutzer"}
          </p>
        </div>
        <IconButton label="Abmelden" onClick={() => void logout()}>
          <LogOut className="size-[18px]" strokeWidth={1.75} />
        </IconButton>
      </div>
    </aside>
  );
}
