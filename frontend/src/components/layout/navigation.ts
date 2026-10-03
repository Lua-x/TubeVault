import {
  ArrowDownToLine,
  House,
  Library,
  ListVideo,
  Search,
  Settings,
  ShieldCheck,
  Tv,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  /** Further paths that count as "this section" (e.g. the library's sub pages). */
  also?: string[];
  adminOnly?: boolean;
  /** Hidden for view-only accounts and kids profiles. */
  requiresAdd?: boolean;
  /** Only for them, filling the space of the hidden tabs. */
  onlyViewers?: boolean;
}

/** The items an account can use. */
export function navFor(items: NavItem[], user: { is_admin: boolean; can_add: boolean } | null) {
  return items.filter(
    (item) =>
      (!item.adminOnly || user?.is_admin) &&
      (!item.requiresAdd || user?.can_add) &&
      (!item.onlyViewers || !user?.can_add),
  );
}

export const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Start", icon: House, end: true },
  { to: "/search", label: "Suche", icon: Search },
  { to: "/library", label: "Bibliothek", icon: Library },
  { to: "/channels", label: "Kanäle", icon: UsersRound },
  { to: "/playlists", label: "Playlists", icon: ListVideo },
];

export const SECONDARY_NAV: NavItem[] = [
  { to: "/subscriptions", label: "Abos", icon: Tv, requiresAdd: true },
  { to: "/downloads", label: "Downloads", icon: ArrowDownToLine, requiresAdd: true },
  { to: "/settings", label: "Einstellungen", icon: Settings },
  { to: "/admin", label: "Verwaltung", icon: ShieldCheck, adminOnly: true },
];

/** Phones: five tabs at most, like iOS. Channels and playlists live under "Library". */
export const TAB_NAV: NavItem[] = [
  { to: "/", label: "Start", icon: House, end: true },
  { to: "/library", label: "Bibliothek", icon: Library, also: ["/channels", "/playlists"] },
  { to: "/search", label: "Suche", icon: Search },
  { to: "/subscriptions", label: "Abos", icon: Tv, requiresAdd: true },
  { to: "/downloads", label: "Downloads", icon: ArrowDownToLine, requiresAdd: true },
  { to: "/playlists", label: "Playlists", icon: ListVideo, onlyViewers: true },
];
