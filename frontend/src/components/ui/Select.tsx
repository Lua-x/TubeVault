import { ChevronDown } from "lucide-react";
import { useId, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  inline?: boolean;
}

/** Native select (best on phones), styled to match. */
export function Select({ label, inline, className, children, ...props }: SelectProps) {
  const id = useId();
  return (
    <div
      className={cn(
        inline ? "flex items-center justify-between gap-4" : "flex flex-col gap-1.5",
        className,
      )}
    >
      <label
        htmlFor={id}
        className={inline ? "text-[15px]" : "px-1 text-[13px] font-medium text-secondary"}
      >
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          className={cn(
            "h-9 cursor-pointer appearance-none rounded-lg bg-surface pr-9 pl-3 text-[15px] text-primary",
            "transition-colors duration-200 outline-none hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-accent",
            !inline && "h-11 w-full rounded-xl",
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-tertiary"
          strokeWidth={2}
        />
      </div>
    </div>
  );
}
