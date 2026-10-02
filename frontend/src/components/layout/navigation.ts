import { ArrowDownToLine, Library, Settings, Tv, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Bibliothek", icon: Library, end: true },
  { to: "/subscriptions", label: "Abos", icon: Tv },
  { to: "/downloads", label: "Downloads", icon: ArrowDownToLine },
  { to: "/settings", label: "Einstellungen", icon: Settings },
];
