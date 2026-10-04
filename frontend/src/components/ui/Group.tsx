import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** iOS-style grouped section: a heading above a rounded card with hairline separators. */
export function Group({
  title,
  footer,
  children,
  className,
}: {
  title?: string;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-2", className)}>
      {title && (
        <h2 className="px-4 text-[13px] font-medium tracking-wide text-secondary uppercase">
          {title}
        </h2>
      )}
      <div className="tv-group-card divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
        {children}
      </div>
      {footer && (
        // Links in the running text are underlined – color alone doesn't set them apart.
        <p className="px-4 text-[13px] text-tertiary [&_a]:underline [&_a]:underline-offset-2">
          {footer}
        </p>
      )}
    </section>
  );
}

export function Row({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("px-4 py-3", className)}>{children}</div>;
}
