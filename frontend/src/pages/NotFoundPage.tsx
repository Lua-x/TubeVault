import { Compass } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/ui/EmptyState";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function NotFoundPage() {
  useDocumentTitle("Nicht gefunden");
  return (
    <EmptyState
      icon={<Compass className="size-7" strokeWidth={1.5} />}
      title="Seite nicht gefunden"
    >
      <Link to="/" className="text-accent hover:underline">
        Zur Bibliothek
      </Link>
    </EmptyState>
  );
}
