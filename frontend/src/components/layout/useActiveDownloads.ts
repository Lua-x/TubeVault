import { useJobs } from "@/api/queries";
import { useCanAdd } from "@/hooks/auth";
import { useLiveConnected } from "@/hooks/live";

export function useActiveDownloadCount(): number {
  const live = useLiveConnected();
  // View-only accounts have no download queue.
  const { data } = useJobs(live, useCanAdd());
  return (data ?? []).filter((job) => job.status === "running" || job.status === "queued").length;
}
