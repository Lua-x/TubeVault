import { ListVideo, LogOut, Plus } from "lucide-react";
import { NavLink } from "react-router";

import { usePlaylists } from "@/api/queries";
import { IconButton } from "@/components/ui/Button";
import { useAuth } from "@/hooks/auth";
import { cn } from "@/lib/cn";

import { navFor, PRIMARY_NAV, SECONDARY_NAV, type NavItem } from "./navigation";
import { useActiveDownloadCount } from "./useActiveDownloads";

function SidebarLink({ item, badge }: { item: NavItem; badge?: number }) {
  const { to, label, icon: Icon, end } = item;
  return (
    <NavLink
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
          <Icon className={cn("size-[18px]", isActive && "text-accent")} strokeWidth={1.75} />
          <span className="flex-1 truncate">{label}</span>
          {badge ? (
            <span className="min-w-5 rounded-full bg-accent px-1.5 text-center text-[11px] leading-5 font-semibold text-white">
              {badge}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  );
}

export function Sidebar({ onAdd }: { onAdd: () => void }) {
  const { user, logout } = useAuth();
  const active = useActiveDownloadCount();
  const { data: playlists } = usePlaylists();

  return (
    <aside className="glass fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-separator px-3 pt-6 pb-4 md:flex">
      <div className="mb-7 flex items-center gap-2.5 px-3">
        <img src="./favicon.svg" alt="" className="size-7 rounded-[8px]" />
        <span className="text-[17px] font-semibold tracking-tight">TubeVault</span>
      </div>

      {user?.can_add && (
        <button
          type="button"
          onClick={onAdd}
          className="mb-5 flex h-9 items-center gap-2 rounded-full bg-accent px-4 text-[14px] font-medium text-white transition-[background-color,transform] duration-200 ease-out-soft hover:bg-accent-hover active:scale-[0.98]"
        >
          <Plus className="size-4" strokeWidth={2.25} />
          Video hinzufügen
        </button>
      )}

      <nav aria-label="Hauptnavigation" className="no-scrollbar -mx-1 flex-1 overflow-y-auto px-1">
        <div className="flex flex-col gap-0.5">
          {PRIMARY_NAV.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
        </div>

        {playlists && playlists.length > 0 && (
          <div className="mt-5">
            <p className="mb-1 px-3 text-[11px] font-semibold tracking-wide text-tertiary uppercase">
              Meine Playlists
            </p>
            <div className="flex flex-col gap-0.5">
              {playlists.slice(0, 12).map((playlist) => (
                <SidebarLink
                  key={playlist.id}
                  item={{ to: `/playlists/${playlist.id}`, label: playlist.name, icon: ListVideo }}
                />
              ))}
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-col gap-0.5 border-t border-separator pt-4">
          {navFor(SECONDARY_NAV, user).map((item) => (
            <SidebarLink
              key={item.to}
              item={item}
              badge={item.to === "/downloads" ? active : undefined}
            />
          ))}
        </div>
      </nav>

      <div className="mt-4 flex items-center gap-3 border-t border-separator px-2 pt-4">
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
