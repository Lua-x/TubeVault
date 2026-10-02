import { useId } from "react";

import { cn } from "@/lib/cn";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}

/** iOS-style toggle row. */
export function Switch({ checked, onChange, label, description, disabled }: SwitchProps) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="block text-[15px]">
          {label}
        </label>
        {description && <p className="text-[13px] text-secondary">{description}</p>}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-[31px] w-[51px] shrink-0 rounded-full transition-colors duration-200 ease-out-soft",
          "disabled:opacity-50",
          checked ? "bg-success" : "bg-surface-hover",
        )}
      >
        <span
          className={cn(
            "absolute top-[2px] left-[2px] size-[27px] rounded-full bg-white shadow-[0_3px_8px_rgb(0_0_0/0.15),0_1px_1px_rgb(0_0_0/0.16)]",
            "transition-transform duration-200 ease-out-soft",
            checked && "translate-x-5",
          )}
        />
      </button>
    </div>
  );
}
