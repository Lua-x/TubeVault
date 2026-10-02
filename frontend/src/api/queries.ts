import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AppSettings,
  Container,
  Job,
  MaxHeight,
  Page,
  QueueState,
  Subscription,
  SubscriptionDetail,
  SubscriptionSettings,
  SystemInfo,
  User,
  VideoDetail,
  VideoSummary,
} from "@/lib/types";

export const keys = {
  videos: ["videos"] as const,
  videoList: (params: VideoListParams) => ["videos", "list", params] as const,
  video: (id: number) => ["videos", "detail", id] as const,
  jobs: ["jobs"] as const,
  queue: ["queue"] as const,
  subscriptions: ["subscriptions"] as const,
  subscription: (id: number) => ["subscriptions", "detail", id] as const,
  settings: ["settings"] as const,
  users: ["users"] as const,
  system: ["system"] as const,
};

export type VideoSort = "added" | "newest" | "oldest" | "title";

export interface VideoListParams {
  q?: string;
  sort?: VideoSort;
  limit?: number;
}

export function useVideos(params: VideoListParams) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.sort) search.set("sort", params.sort);
  search.set("limit", String(params.limit ?? 120));
  return useQuery({
    queryKey: keys.videoList(params),
    queryFn: () => api.get<Page<VideoSummary>>(`videos?${search}`),
    placeholderData: keepPreviousData,
  });
}

export function useVideo(id: number) {
  return useQuery({
    queryKey: keys.video(id),
    queryFn: () => api.get<VideoDetail>(`videos/${id}`),
    enabled: Number.isFinite(id),
  });
}

export function useJobs(live: boolean) {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: () => api.get<Page<Job>>("downloads?limit=200"),
    select: (page) => page.items,
    // Polling only as a fallback when the WebSocket is not connected.
    refetchInterval: (query) => {
      if (live) return false;
      const items = query.state.data?.items ?? [];
      return items.some((job) => job.status === "running" || job.status === "queued")
        ? 3000
        : 30000;
    },
  });
}

export interface AddVideoInput {
  url: string;
  container?: Container;
  max_height?: MaxHeight;
}

export function useAddVideo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: AddVideoInput) => api.post<Job>("videos", input),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export function useDeleteVideo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`videos/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.videos }),
  });
}

function useJobAction(action: (id: number) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSettled: () => client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export const useCancelJob = () => useJobAction((id) => api.post(`downloads/${id}/cancel`));
export const usePauseJob = () => useJobAction((id) => api.post(`downloads/${id}/pause`));
export const useResumeJob = () => useJobAction((id) => api.post(`downloads/${id}/resume`));
export const useRetryJob = () => useJobAction((id) => api.post(`downloads/${id}/retry`));
export const useDeleteJob = () => useJobAction((id) => api.delete(`downloads/${id}`));
export function useClearJobs() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete("downloads"),
    onSettled: () => client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export function useAppSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: () => api.get<AppSettings>("settings") });
}

export function useSaveSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (settings: AppSettings) => api.put<AppSettings>("settings", settings),
    onSuccess: (data) => client.setQueryData(keys.settings, data),
  });
}

export function useSystemInfo() {
  return useQuery({ queryKey: keys.system, queryFn: () => api.get<SystemInfo>("system/info") });
}

export function useUsers(enabled: boolean) {
  return useQuery({ queryKey: keys.users, queryFn: () => api.get<User[]>("users"), enabled });
}

export function useCreateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string; is_admin: boolean }) =>
      api.post<User>("users", body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; is_admin?: boolean; password?: string }) =>
      api.patch<User>(`users/${id}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useDeleteUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`users/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.post("auth/me/password", body),
  });
}

// --- queue ------------------------------------------------------------------------

export function useQueueState() {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => api.get<QueueState>("downloads/state"),
    refetchInterval: 60_000,
  });
}

function useQueueAction(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<QueueState>(path),
    onSuccess: (state) => client.setQueryData(keys.queue, state),
    onSettled: () => client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export const usePauseAll = () => useQueueAction("downloads/pause-all");
export const useResumeAll = () => useQueueAction("downloads/resume-all");
export const useRetryFailed = () => useQueueAction("downloads/retry-failed");

// --- subscriptions --------------------------------------------------------------------

export function useSubscriptions() {
  return useQuery({
    queryKey: keys.subscriptions,
    queryFn: () => api.get<Subscription[]>("subscriptions"),
  });
}

export function useSubscription(id: number) {
  return useQuery({
    queryKey: keys.subscription(id),
    queryFn: () => api.get<SubscriptionDetail>(`subscriptions/${id}`),
    enabled: Number.isFinite(id),
  });
}

export interface CreateSubscriptionInput extends SubscriptionSettings {
  url: string;
  backfill: number | null;
}

export function useCreateSubscription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateSubscriptionInput) => api.post<Subscription>("subscriptions", input),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.subscriptions }),
  });
}

export function useUpdateSubscription(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (settings: SubscriptionSettings) =>
      api.put<Subscription>(`subscriptions/${id}`, settings),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.subscriptions }),
  });
}

export function useSubscriptionAction(id: number, action: "check" | "reevaluate") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Subscription>(`subscriptions/${id}/${action}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.subscriptions }),
  });
}

export function useDeleteSubscription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, deleteVideos }: { id: number; deleteVideos: boolean }) =>
      api.delete(`subscriptions/${id}?delete_videos=${deleteVideos}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.subscriptions });
      void client.invalidateQueries({ queryKey: keys.videos });
    },
  });
}
