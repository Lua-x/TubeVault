import { cn } from "@/lib/cn";

interface ProgressBarProps {
  value: number | null;
  className?: string;
  label?: string;
}

/** Thin capsule. `null` renders an indeterminate shimmer. */
export function ProgressBar({ value, className, label }: ProgressBarProps) {
  const percent = value == null ? null : Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? undefined}
      className={cn("relative h-1 overflow-hidden rounded-full bg-surface-hover", className)}
    >
      {percent == null ? (
        <div className="absolute inset-y-0 w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-accent" />
      ) : (
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out-soft"
          style={{ width: `${percent}%` }}
        />
      )}
    </div>
  );
}
