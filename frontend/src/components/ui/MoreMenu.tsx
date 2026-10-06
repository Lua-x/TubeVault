import { MoreHorizontal, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/cn";

export interface MoreMenuItem {
  key: string;
  label: string;
  icon: LucideIcon;
  onSelect?: () => void;
  /** A link instead of an action, e.g. a download or an external page. */
  href?: string;
  external?: boolean;
  danger?: boolean;
  disabled?: boolean;
  /** A thin line above this item. */
  separated?: boolean;
}

const MENU_WIDTH = 256;

/** "⋯": the less frequent actions, so the row itself shows only what matters most. */
export function MoreMenu({
  items,
  label = "Weitere Aktionen",
  className,
}: {
  items: MoreMenuItem[];
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [alignRight, setAlignRight] = useState(true);
  const [upwards, setUpwards] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const entries = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    if (!open) return;
    entries.current.find((entry) => entry && !entry.hasAttribute("disabled"))?.focus();
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  if (items.length === 0) return null;

  const toggle = () => {
    // Open towards the side with room: on phones the button can sit at the left edge.
    const rect = button.current?.getBoundingClientRect();
    if (rect) {
      setAlignRight(rect.right - MENU_WIDTH >= 8);
      // Upwards when the menu wouldn't fit below (about 40 px per entry).
      const height = items.length * 41 + 16;
      setUpwards(window.innerHeight - rect.bottom < height && rect.top > height);
    }
    setOpen((value) => !value);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const focusable = entries.current.filter(
      (entry): entry is HTMLElement => entry != null && !entry.hasAttribute("disabled"),
    );
    const index = focusable.indexOf(document.activeElement as HTMLElement);
    const move = (to: number) => {
      event.preventDefault();
      focusable[(to + focusable.length) % focusable.length]?.focus();
    };
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(focusable.length - 1);
    else if (event.key === "Tab") setOpen(false);
  };

  const itemClass = (item: MoreMenuItem) =>
    cn(
      "flex h-10 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] transition-colors outline-none hover:bg-surface focus-visible:bg-surface disabled:opacity-50",
      item.danger && "text-danger",
    );

  return (
    <div ref={root} className={cn("relative", className)} onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
        className="inline-flex size-9 items-center justify-center rounded-full bg-surface transition-colors duration-200 hover:bg-surface-hover"
      >
        <MoreHorizontal className="size-5" strokeWidth={2} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label={label}
            initial={{ opacity: 0, y: upwards ? 6 : -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: upwards ? 6 : -6, scale: 0.97 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            style={{ width: MENU_WIDTH }}
            className={cn(
              "absolute z-30 rounded-2xl border border-separator bg-elevated p-1.5 shadow-card",
              upwards ? "bottom-11" : "top-11",
              alignRight ? "right-0" : "left-0",
              upwards
                ? alignRight
                  ? "origin-bottom-right"
                  : "origin-bottom-left"
                : alignRight
                  ? "origin-top-right"
                  : "origin-top-left",
            )}
          >
            {items.map((item, index) => {
              const Icon = item.icon;
              const content = (
                <>
                  <Icon className="size-[18px] shrink-0" strokeWidth={2} />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                </>
              );
              const ref = (element: HTMLElement | null) => {
                entries.current[index] = element;
              };
              return (
                <div key={item.key}>
                  {item.separated && <div className="mx-3 my-1 h-px bg-separator" />}
                  {item.href ? (
                    <a
                      ref={ref}
                      role="menuitem"
                      href={item.href}
                      target={item.external ? "_blank" : undefined}
                      rel={item.external ? "noreferrer noopener" : undefined}
                      onClick={() => setOpen(false)}
                      className={itemClass(item)}
                    >
                      {content}
                    </a>
                  ) : (
                    <button
                      ref={ref}
                      type="button"
                      role="menuitem"
                      disabled={item.disabled}
                      onClick={() => {
                        setOpen(false);
                        item.onSelect?.();
                      }}
                      className={itemClass(item)}
                    >
                      {content}
                    </button>
                  )}
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
