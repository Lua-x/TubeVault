import { NavLink } from "react-router";

import { cn } from "@/lib/cn";

const TABS = [
  { to: "/library", label: "Videos" },
  { to: "/channels", label: "Kanäle" },
  { to: "/playlists", label: "Playlists" },
  { to: "/folders", label: "Ordner" },
  { to: "/later", label: "Später" },
  { to: "/history", label: "Verlauf" },
  { to: "/device", label: "Gerät" },
];

/** On phones, Channels and Playlists live inside "Library" (the tab bar has no room). */
export function LibraryTabs() {
  return (
    <nav
      aria-label="Bibliothek"
      className="no-scrollbar -mx-4 mb-6 flex gap-2 overflow-x-auto px-4 md:hidden"
    >
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            cn(
              "h-8 rounded-full px-4 text-[14px] leading-8 font-medium transition-colors",
              isActive ? "bg-primary text-canvas" : "bg-surface text-secondary",
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
