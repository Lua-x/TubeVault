import { useJobs } from "@/api/queries";
import { useLiveConnected } from "@/hooks/live";

export function useActiveDownloadCount(): number {
  const live = useLiveConnected();
  const { data } = useJobs(live);
  return (data ?? []).filter((job) => job.status === "running" || job.status === "queued").length;
}
