import { ChevronLeft, ChevronRight } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { Link } from "react-router";

import { IconButton } from "@/components/ui/Button";

interface RowProps {
  title: string;
  to?: string;
  children: ReactNode;
}

/** Horizontally scrolling shelf like on Apple TV, with arrows on hover (desktop). */
export function Row({ title, to, children }: RowProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const scroll = (direction: 1 | -1) => {
    const el = scroller.current;
    if (el) el.scrollBy({ left: direction * el.clientWidth * 0.85, behavior: "smooth" });
  };

  return (
    <section className="group/row relative mb-10" aria-label={title}>
      <div className="mb-3 flex items-end justify-between gap-4">
        <h2 className="text-[20px] font-semibold tracking-tight md:text-[22px]">{title}</h2>
        {to && (
          <Link to={to} className="text-[14px] font-medium text-accent hover:underline">
            Alle anzeigen
          </Link>
        )}
      </div>
      <div className="relative -mx-4 sm:-mx-6 md:-mx-10">
        <div
          ref={scroller}
          className="no-scrollbar flex snap-x snap-mandatory gap-5 overflow-x-auto scroll-smooth scroll-px-4 px-4 pt-1 pb-4 sm:scroll-px-6 sm:px-6 md:scroll-px-10 md:px-10"
        >
          {children}
        </div>
        <div className="pointer-events-none absolute inset-y-0 left-2 hidden items-center opacity-0 transition-opacity duration-200 group-hover/row:opacity-100 md:flex">
          <IconButton
            label="Zurück"
            variant="glass"
            className="pointer-events-auto size-10 shadow-card"
            onClick={() => scroll(-1)}
          >
            <ChevronLeft className="size-5" strokeWidth={2} />
          </IconButton>
        </div>
        <div className="pointer-events-none absolute inset-y-0 right-2 hidden items-center opacity-0 transition-opacity duration-200 group-hover/row:opacity-100 md:flex">
          <IconButton
            label="Weiter"
            variant="glass"
            className="pointer-events-auto size-10 shadow-card"
            onClick={() => scroll(1)}
          >
            <ChevronRight className="size-5" strokeWidth={2} />
          </IconButton>
        </div>
      </div>
    </section>
  );
}

export function RowItem({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div
      className={
        wide ? "w-[78vw] max-w-[340px] shrink-0 snap-start" : "w-[150px] shrink-0 snap-start"
      }
    >
      {children}
    </div>
  );
}
