import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

import { IconButton } from "./Button";

// The element focused last outside any dialog – where focus goes back when one closes.
// (An autofocused field inside is focused before any effect of the dialog runs.)
let lastOutside: HTMLElement | null = null;
document.addEventListener("focusin", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && !target.closest('[role="dialog"]')) lastOutside = target;
});

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}

/** Centered sheet on desktop, bottom sheet on phones. Closes on Escape and backdrop click. */
export function Dialog({ open, onClose, title, children, wide }: DialogProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  // The latest onClose without re-running the effect below (and losing the opener).
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    // Back to where the dialog was opened from once it closes.
    const opener = lastOutside;
    const focusable = () =>
      Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled") && el.getClientRects().length > 0);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key !== "Tab" || !panelRef.current) return;
      const items = focusable();
      const first = items[0];
      const last = items[items.length - 1];
      const inside = panelRef.current.contains(document.activeElement);
      if (!inside || (event.shiftKey && document.activeElement === first)) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
          <motion.div
            className="absolute inset-0 bg-overlay backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ opacity: 0, y: 40, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
            className={cn(
              "relative max-h-[92dvh] w-full overflow-y-auto overscroll-contain rounded-t-3xl border border-separator bg-elevated p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-card sm:rounded-3xl sm:pb-6",
              // Grouped settings inside a sheet need their own surface to stand out.
              "[&_.tv-group-card]:bg-surface/50",
              wide ? "max-w-2xl" : "max-w-lg",
            )}
          >
            <div className="mb-5 flex items-center justify-between gap-4">
              <h2 id={titleId} className="text-[20px] font-semibold tracking-tight">
                {title}
              </h2>
              <IconButton
                label="Schließen"
                onClick={onClose}
                variant="secondary"
                className="size-8"
              >
                <X className="size-4" strokeWidth={2} />
              </IconButton>
            </div>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
