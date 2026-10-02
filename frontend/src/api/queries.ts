import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AppSettings,
  Container,
  Job,
  MaxHeight,
  Page,
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
