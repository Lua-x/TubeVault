import { useEffect, useRef } from "react";

import { Button } from "./Button";

interface LoadMoreProps {
  hasMore: boolean;
  loading: boolean;
  onLoad: () => void;
  /** Changes whenever a page arrives, so a still-visible end of the list loads the next one. */
  pageCount: number;
}

/** Loads the next page shortly before the end of the list comes into view. */
export function LoadMore({ hasMore, loading, onLoad, pageCount }: LoadMoreProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!hasMore || loading || !element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) onLoad();
      },
      { rootMargin: "0px 0px 1200px 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasMore, loading, onLoad, pageCount]);

  if (!hasMore) return null;
  return (
    <div ref={ref} className="flex justify-center pt-10">
      {/* Also a button: for keyboards, screen readers and when scrolling is not possible. */}
      <Button variant="secondary" loading={loading} onClick={onLoad}>
        Mehr laden
      </Button>
    </div>
  );
}
