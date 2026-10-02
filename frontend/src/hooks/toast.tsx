import { AnimatePresence, motion } from "motion/react";
import { CircleAlert, CircleCheck } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Tone = "success" | "error" | "info";
interface ToastAction {
  label: string;
  onClick: () => void;
}
interface Toast {
  id: number;
  message: string;
  tone: Tone;
  action?: ToastAction;
}

type ShowToast = (message: string, tone?: Tone, action?: ToastAction) => void;
const ToastContext = createContext<ShowToast>(() => undefined);
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback(
    (id: number) => setToasts((current) => current.filter((t) => t.id !== id)),
    [],
  );
  const show = useCallback<ShowToast>(
    (message, tone = "success", action) => {
      const id = nextId++;
      setToasts((current) => [...current.slice(-2), { id, message, tone, action }]);
      setTimeout(() => dismiss(id), action ? 6000 : 4000);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-50 flex flex-col items-center gap-2 px-4 md:bottom-8"
      >
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 420, damping: 32 }}
              role={toast.tone === "error" ? "alert" : "status"}
              className="glass pointer-events-auto flex max-w-md items-center gap-2.5 rounded-full border border-separator px-4 py-2.5 text-sm font-medium shadow-card"
            >
              {toast.tone === "error" ? (
                <CircleAlert className="size-4 shrink-0 text-danger" strokeWidth={2} />
              ) : toast.tone === "success" ? (
                <CircleCheck className="size-4 shrink-0 text-accent" strokeWidth={2} />
              ) : null}
              <span>{toast.message}</span>
              {toast.action && (
                <button
                  type="button"
                  className="-mr-1 ml-1 rounded-full px-2 py-0.5 font-semibold text-accent hover:bg-surface"
                  onClick={() => {
                    toast.action?.onClick();
                    dismiss(toast.id);
                  }}
                >
                  {toast.action.label}
                </button>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
