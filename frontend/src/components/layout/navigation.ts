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
}

export const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Start", icon: House, end: true },
  { to: "/search", label: "Suche", icon: Search },
  { to: "/library", label: "Bibliothek", icon: Library },
  { to: "/channels", label: "Kanäle", icon: UsersRound },
  { to: "/playlists", label: "Playlists", icon: ListVideo },
];

export const SECONDARY_NAV: NavItem[] = [
  { to: "/subscriptions", label: "Abos", icon: Tv },
  { to: "/downloads", label: "Downloads", icon: ArrowDownToLine },
  { to: "/settings", label: "Einstellungen", icon: Settings },
  { to: "/admin", label: "Verwaltung", icon: ShieldCheck, adminOnly: true },
];

/** Phones: five tabs at most, like iOS. Channels and playlists live under "Library". */
export const TAB_NAV: NavItem[] = [
  { to: "/", label: "Start", icon: House, end: true },
  { to: "/library", label: "Bibliothek", icon: Library, also: ["/channels", "/playlists"] },
  { to: "/search", label: "Suche", icon: Search },
  { to: "/subscriptions", label: "Abos", icon: Tv },
  { to: "/downloads", label: "Downloads", icon: ArrowDownToLine },
];
