import { ArrowDownToLine, Pause, Play, RotateCcw } from "lucide-react";
import { AnimatePresence } from "motion/react";

import {
  useClearJobs,
  useJobs,
  usePauseAll,
  useQueueState,
  useResumeAll,
  useRetryFailed,
} from "@/api/queries";
import { JobRow } from "@/components/downloads/JobRow";
import { PageHeader } from "@/components/layout/PageHeader";
import { useOpenAddVideo } from "@/components/layout/addVideo";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { useLiveConnected } from "@/hooks/live";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import type { Job } from "@/lib/types";

const ACTIVE = new Set<Job["status"]>(["running", "queued", "paused"]);

export function DownloadsPage() {
  useDocumentTitle("Downloads");
  const live = useLiveConnected();
  const { data: jobs, isLoading } = useJobs(live);
  const clear = useClearJobs();
  const openAdd = useOpenAddVideo();
  const { data: queue } = useQueueState();
  const pauseAll = usePauseAll();
  const resumeAll = useResumeAll();
  const retryFailed = useRetryFailed();
  const paused = queue?.paused ?? false;

  if (isLoading) return <PageSpinner />;

  const all = jobs ?? [];
  const active = all
    .filter((job) => ACTIVE.has(job.status))
    .sort((a, b) => Number(b.status === "running") - Number(a.status === "running") || a.id - b.id);
  const finished = all.filter((job) => !ACTIVE.has(job.status));
  const failedCount = finished.filter((job) => job.status === "failed").length;

  return (
    <>
      <PageHeader
        title="Downloads"
        subtitle={
          paused
            ? "Warteschlange pausiert"
            : active.length > 0
              ? `${active.length} aktiv`
              : live
                ? "Keine aktiven Downloads"
                : "Verbindung wird hergestellt …"
        }
        actions={
          paused ? (
            <Button
              loading={resumeAll.isPending}
              icon={<Play className="size-4 fill-current" strokeWidth={0} />}
              onClick={() => resumeAll.mutate()}
            >
              Fortsetzen
            </Button>
          ) : active.length > 0 ? (
            <Button
              variant="secondary"
              loading={pauseAll.isPending}
              icon={<Pause className="size-4" strokeWidth={2} />}
              onClick={() => pauseAll.mutate()}
            >
              Alle pausieren
            </Button>
          ) : undefined
        }
      />

      {paused && (
        <div
          role="status"
          className="mb-8 flex items-center gap-3 rounded-2xl bg-elevated px-4 py-3 text-[14px] text-secondary"
        >
          <Pause className="size-4 shrink-0 text-accent" strokeWidth={2} />
          Die Warteschlange ist pausiert. Neue Downloads starten erst nach dem Fortsetzen –
          angefangene machen dort weiter, wo sie aufgehört haben.
        </div>
      )}

      {all.length === 0 ? (
        <EmptyState
          icon={<ArrowDownToLine className="size-7" strokeWidth={1.5} />}
          title="Keine Downloads"
          action={<Button onClick={openAdd}>Video hinzufügen</Button>}
        >
          Hier siehst du den Fortschritt deiner Downloads live.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-10">
          {active.length > 0 && (
            <section aria-labelledby="active-heading">
              <h2
                id="active-heading"
                className="mb-3 px-1 text-[20px] font-semibold tracking-tight"
              >
                Aktiv
              </h2>
              <ul className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
                <AnimatePresence initial={false}>
                  {active.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </AnimatePresence>
              </ul>
            </section>
          )}
          {finished.length > 0 && (
            <section aria-labelledby="history-heading">
              <div className="mb-3 flex items-center justify-between px-1">
                <h2 id="history-heading" className="text-[20px] font-semibold tracking-tight">
                  Verlauf
                </h2>
                <div className="flex items-center gap-1">
                  {failedCount > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-accent"
                      loading={retryFailed.isPending}
                      icon={<RotateCcw className="size-3.5" strokeWidth={2} />}
                      onClick={() => retryFailed.mutate()}
                    >
                      Fehlgeschlagene wiederholen
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-accent"
                    loading={clear.isPending}
                    onClick={() => clear.mutate()}
                  >
                    Verlauf leeren
                  </Button>
                </div>
              </div>
              <ul className="divide-y divide-separator overflow-hidden rounded-2xl bg-elevated">
                <AnimatePresence initial={false}>
                  {finished.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </AnimatePresence>
              </ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}
