import { Plus, Settings } from "lucide-react";
import { Link } from "react-router";
import type { ReactNode } from "react";

import { IconButton } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

import { useOpenAddVideo } from "./addVideo";

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Replaces the phone's "add video" button, e.g. with "subscribe". */
  add?: { label: string; onClick: () => void };
  /** Show the actions on larger screens only (phones use the round add button). */
  desktopActions?: boolean;
  /** Phones have no settings tab; offer a shortcut on the main pages. */
  settingsShortcut?: boolean;
}

/** Large title like iOS/macOS. On phones it also carries the "add video" button. */
export function PageHeader({
  title,
  subtitle,
  actions,
  add,
  desktopActions,
  settingsShortcut,
}: PageHeaderProps) {
  const openAddVideo = useOpenAddVideo();
  const addAction = add ?? { label: "Video hinzufügen", onClick: openAddVideo };
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-4 md:mb-8">
      <div className="flex w-full items-center justify-between gap-4 md:w-auto">
        <div className="min-w-0">
          <h1 className="text-[32px] leading-tight font-bold tracking-tight md:text-[34px]">
            {title}
          </h1>
          {subtitle && <p className="mt-0.5 text-[15px] text-secondary">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 md:hidden">
          {settingsShortcut && (
            <Link
              to="/settings"
              aria-label="Einstellungen"
              className="inline-flex size-9 items-center justify-center rounded-full bg-surface text-secondary"
            >
              <Settings className="size-5" strokeWidth={1.75} />
            </Link>
          )}
          <IconButton
            label={addAction.label}
            onClick={addAction.onClick}
            variant="secondary"
            className="text-accent"
          >
            <Plus className="size-5" strokeWidth={2.25} />
          </IconButton>
        </div>
      </div>
      {actions && (
        <div
          className={cn(
            "w-full items-center gap-3 md:flex md:w-auto",
            desktopActions ? "hidden" : "flex",
          )}
        >
          {actions}
        </div>
      )}
    </header>
  );
}
