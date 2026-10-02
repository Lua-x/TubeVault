import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/cn";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: ReactNode;
  error?: string | null;
  leading?: ReactNode;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hint, error, leading, className, id, ...props },
  ref,
) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label htmlFor={inputId} className="px-1 text-[13px] font-medium text-secondary">
          {label}
        </label>
      )}
      <div className="relative">
        {leading && (
          <span className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-tertiary">
            {leading}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || hint ? hintId : undefined}
          className={cn(
            "h-11 w-full rounded-xl bg-surface px-3.5 text-[15px] text-primary placeholder:text-tertiary",
            "border border-transparent transition-[border-color,box-shadow] duration-200 outline-none",
            "focus:border-accent focus:ring-4 focus:ring-accent/20",
            error && "border-danger focus:border-danger focus:ring-danger/20",
            leading ? "pl-10" : undefined,
          )}
          {...props}
        />
      </div>
      {(error || hint) && (
        <p id={hintId} className={cn("px-1 text-[13px]", error ? "text-danger" : "text-tertiary")}>
          {error || hint}
        </p>
      )}
    </div>
  );
});
