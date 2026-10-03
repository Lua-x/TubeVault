import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useMemo } from "react";

import { api } from "@/lib/api";
import { apiUrl } from "@/lib/base";
import type {
  AdminOverview,
  ApiToken,
  AppSettings,
  ChannelCard,
  ChannelDetail,
  CreatedApiToken,
  Container,
  HardwareInfo,
  HomeFeed,
  HwAccel,
  HwTestResult,
  ImportMode,
  ImportOverview,
  Job,
  LibraryTask,
  LogEntry,
  MaintenanceAction,
  MaxHeight,
  Page,
  PlaybackInfo,
  Playlist,
  PlaylistDetail,
  QueueState,
  RemuxStatus,
  Segments,
  Subscription,
  SubscriptionDetail,
  SubscriptionSettings,
  SystemInfo,
  TokenScope,
  TranscodeSession,
  User,
  VideoDetail,
  YtDlpInfo,
  VideoSummary,
  WatchState,
} from "@/lib/types";

export const keys = {
  videos: ["videos"] as const,
  home: ["videos", "home"] as const,
  channels: ["channels"] as const,
  channel: (id: number) => ["channels", "detail", id] as const,
  playlists: ["playlists"] as const,
  playlist: (id: number) => ["playlists", "detail", id] as const,
  segments: (id: number) => ["videos", "segments", id] as const,
  playback: (id: number) => ["videos", "playback", id] as const,
  libraryTask: ["library", "task"] as const,
  importOverview: ["import"] as const,
  remux: (id: number) => ["videos", "remux", id] as const,
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

export type VideoSort = "relevance" | "added" | "newest" | "oldest" | "title";
export type WatchedFilter = "all" | "unwatched" | "watched" | "in_progress";

export interface VideoListParams {
  q?: string;
  sort?: VideoSort;
  limit?: number;
  channelId?: number;
  watched?: WatchedFilter;
}

function videoSearch(params: VideoListParams, offset = 0): URLSearchParams {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.sort) search.set("sort", params.sort);
  if (params.channelId) search.set("channel_id", String(params.channelId));
  if (params.watched && params.watched !== "all") search.set("watched", params.watched);
  search.set("limit", String(params.limit ?? 120));
  if (offset) search.set("offset", String(offset));
  return search;
}

export function useVideos(params: VideoListParams, enabled = true) {
  return useQuery({
    queryKey: keys.videoList(params),
    queryFn: () => api.get<Page<VideoSummary>>(`videos?${videoSearch(params)}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}

const PAGE_SIZE = 60;

/** The whole list, loaded page by page while scrolling (libraries can be huge). */
export function useVideoPages(params: Omit<VideoListParams, "limit">, enabled = true) {
  const query = useInfiniteQuery({
    queryKey: [...keys.videoList(params), "pages"],
    queryFn: ({ pageParam }) =>
      api.get<Page<VideoSummary>>(
        `videos?${videoSearch({ ...params, limit: PAGE_SIZE }, pageParam)}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((sum, page) => sum + page.items.length, 0);
      return last.items.length > 0 && loaded < last.total ? loaded : undefined;
    },
    placeholderData: keepPreviousData,
    enabled,
  });
  const { data } = query;
  const items = useMemo(() => {
    // New downloads shift the offsets; never show a video twice.
    const seen = new Set<number>();
    return (data?.pages ?? [])
      .flatMap((page) => page.items)
      .filter((video) => !seen.has(video.id) && seen.add(video.id));
  }, [data]);
  return { ...query, items, total: data?.pages[0]?.total, pageCount: data?.pages.length ?? 0 };
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

// --- home, channels -------------------------------------------------------------------

export function useHome() {
  return useQuery({ queryKey: keys.home, queryFn: () => api.get<HomeFeed>("home") });
}

export function useChannels() {
  return useQuery({ queryKey: keys.channels, queryFn: () => api.get<ChannelCard[]>("channels") });
}

export function useChannel(id: number) {
  return useQuery({
    queryKey: keys.channel(id),
    queryFn: () => api.get<ChannelDetail>(`channels/${id}`),
    enabled: Number.isFinite(id),
  });
}

// --- progress ---------------------------------------------------------------------------

/** Progress report that also survives closing the tab (keepalive). Never throws. */
export async function reportProgress(
  videoId: number,
  positionS: number,
  durationS?: number,
): Promise<WatchState | null> {
  try {
    const response = await fetch(apiUrl(`videos/${videoId}/progress`), {
      method: "PUT",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/json", "X-Requested-With": "TubeVault" },
      body: JSON.stringify({ position_s: positionS, duration_s: durationS || null }),
    });
    return response.ok ? ((await response.json()) as WatchState) : null;
  } catch {
    return null;
  }
}

export function useSetWatched() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, watched }: { id: number; watched: boolean }) =>
      api.put<WatchState>(`videos/${id}/watched`, { watched }),
    onSuccess: (state, { id }) => {
      client.setQueryData<VideoDetail>(keys.video(id), (old) =>
        old ? { ...old, progress: state } : old,
      );
      void client.invalidateQueries({ queryKey: keys.videos });
      void client.invalidateQueries({ queryKey: keys.channels });
    },
  });
}

export function useSegments(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.segments(id),
    queryFn: () => api.get<Segments>(`videos/${id}/segments`),
    enabled: enabled && Number.isFinite(id),
    staleTime: 5 * 60_000,
  });
}

// --- playlists ---------------------------------------------------------------------------

export function usePlaylists(videoId?: number) {
  return useQuery({
    queryKey: videoId ? [...keys.playlists, { videoId }] : keys.playlists,
    queryFn: () => api.get<Playlist[]>(videoId ? `playlists?video_id=${videoId}` : "playlists"),
  });
}

export function usePlaylist(id: number | null) {
  return useQuery({
    queryKey: keys.playlist(id ?? -1),
    queryFn: () => api.get<PlaylistDetail>(`playlists/${id}`),
    enabled: id != null && Number.isFinite(id),
  });
}

function usePlaylistMutation<TInput>(fn: (input: TInput) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => client.invalidateQueries({ queryKey: keys.playlists }),
  });
}

export const useCreatePlaylist = () =>
  usePlaylistMutation((body: { name: string; description?: string | null }) =>
    api.post<Playlist>("playlists", body),
  );
export const useUpdatePlaylist = () =>
  usePlaylistMutation(
    ({ id, ...body }: { id: number; name: string; description?: string | null }) =>
      api.patch<Playlist>(`playlists/${id}`, body),
  );
export const useDeletePlaylist = () =>
  usePlaylistMutation((id: number) => api.delete(`playlists/${id}`));
export const useAddToPlaylist = () =>
  usePlaylistMutation(({ id, videoId }: { id: number; videoId: number }) =>
    api.post<Playlist>(`playlists/${id}/items`, { video_id: videoId }),
  );
export const useRemoveFromPlaylist = () =>
  usePlaylistMutation(({ id, videoId }: { id: number; videoId: number }) =>
    api.delete(`playlists/${id}/items/${videoId}`),
  );
export const useReorderPlaylist = () =>
  usePlaylistMutation(({ id, videoIds }: { id: number; videoIds: number[] }) =>
    api.put<Playlist>(`playlists/${id}/order`, { video_ids: videoIds }),
  );

// --- playback and transcoding ------------------------------------------------------

export function usePlayback(id: number) {
  return useQuery({
    queryKey: keys.playback(id),
    queryFn: () => api.get<PlaybackInfo>(`videos/${id}/playback`),
    staleTime: 10 * 60_000,
    retry: false,
  });
}

/** Starts the remux when enabled and polls until it is ready (or failed). */
export function useRemux(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.remux(id),
    queryFn: () => api.post<RemuxStatus>(`videos/${id}/remux`),
    enabled,
    staleTime: Infinity,
    retry: false,
    refetchInterval: (query) => (query.state.data?.state === "running" ? 1000 : false),
  });
}

export function useHardware(enabled: boolean) {
  return useQuery({
    queryKey: ["transcoding", "hardware"],
    queryFn: () => api.get<HardwareInfo>("transcoding/hardware"),
    enabled,
    staleTime: 60_000,
  });
}

export function useHwTest() {
  return useMutation({
    mutationFn: (body: { hwaccel: HwAccel; vaapi_device: string }) =>
      api.post<HwTestResult>("transcoding/test", body),
  });
}

export function useTranscodeSessions(enabled: boolean) {
  return useQuery({
    queryKey: ["transcoding", "sessions"],
    queryFn: () => api.get<TranscodeSession[]>("transcoding/sessions"),
    enabled,
    refetchInterval: 5000,
  });
}

/** The running (or last) library task; kept current by `library.task` live events. */
export function useLibraryTask(enabled: boolean) {
  return useQuery({
    queryKey: keys.libraryTask,
    queryFn: () => api.get<LibraryTask | null>("library/task"),
    enabled,
  });
}

// --- import ------------------------------------------------------------------------

export function useImportOverview() {
  return useQuery({
    queryKey: keys.importOverview,
    queryFn: () => api.get<ImportOverview>("import"),
  });
}

export function useStartImportScan() {
  return useMutation({ mutationFn: () => api.post<LibraryTask>("import/scan") });
}

export function useStartImport() {
  return useMutation({
    mutationFn: (body: { keys: string[]; mode: ImportMode; fetch_metadata: boolean }) =>
      api.post<LibraryTask>("import/run", body),
  });
}

// --- administration ----------------------------------------------------------------

export function useAdminOverview() {
  return useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api.get<AdminOverview>("admin/overview"),
    refetchInterval: 30_000,
  });
}

export function useAdminLogs(level: string) {
  return useQuery({
    queryKey: ["admin", "logs", level],
    queryFn: () => api.get<LogEntry[]>(`admin/logs?level=${level}&limit=400`),
  });
}

export function useYtDlp() {
  return useQuery({
    queryKey: ["admin", "ytdlp"],
    queryFn: () => api.get<YtDlpInfo>("admin/ytdlp"),
  });
}

export function useCheckYtDlp() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.get<YtDlpInfo>("admin/ytdlp?check=true"),
    onSuccess: (info) => client.setQueryData(["admin", "ytdlp"], info),
  });
}

export function useUpdateYtDlp() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ updated: boolean; message: string; info: YtDlpInfo }>("admin/ytdlp/update"),
    onSuccess: (result) =>
      client.setQueryData<YtDlpInfo>(["admin", "ytdlp"], (old) => ({
        ...result.info,
        latest: old?.latest ?? null,
      })),
  });
}

export function useRestart() {
  return useMutation({ mutationFn: () => api.post("admin/restart") });
}

export function useMaintenance() {
  return useMutation({
    mutationFn: (action: MaintenanceAction) => api.post<LibraryTask>(`admin/maintenance/${action}`),
  });
}

// --- API tokens ----------------------------------------------------------------------

export function useTokens() {
  return useQuery({ queryKey: ["tokens"], queryFn: () => api.get<ApiToken[]>("auth/tokens") });
}

export function useCreateToken() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; scope: TokenScope; expires_days: number | null }) =>
      api.post<CreatedApiToken>("auth/tokens", body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["tokens"] }),
  });
}

export function useDeleteToken() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`auth/tokens/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["tokens"] }),
  });
}
