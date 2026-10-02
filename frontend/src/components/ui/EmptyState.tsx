import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ icon, title, children, action }: EmptyStateProps) {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center py-24 text-center">
      <div className="mb-5 flex size-16 items-center justify-center rounded-2xl bg-surface text-secondary">
        {icon}
      </div>
      <h2 className="text-[20px] font-semibold tracking-tight">{title}</h2>
      {children && <p className="mt-2 text-[15px] text-secondary">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
