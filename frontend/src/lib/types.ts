export type Theme = "system" | "dark" | "light";

export interface Preferences {
  theme?: Theme;
  sponsorblock_skip?: boolean;
  autoplay_next?: boolean;
}

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  preferences: Preferences;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthStatus {
  setup_required: boolean;
  user: User | null;
}

export interface Channel {
  id: number;
  youtube_id: string;
  name: string;
  handle: string | null;
  url: string | null;
  has_avatar: boolean;
  has_banner: boolean;
  updated_at: string;
}

export type VideoStatus = "pending" | "downloading" | "ready" | "failed" | "missing";

export interface VideoSummary {
  id: number;
  youtube_id: string;
  title: string;
  channel: Channel | null;
  duration_s: number | null;
  upload_date: string | null;
  status: VideoStatus;
  is_short: boolean;
  was_live: boolean;
  has_thumbnail: boolean;
  added_at: string;
  updated_at: string;
  progress: WatchState | null;
}

export interface WatchState {
  position_s: number;
  watched: boolean;
  updated_at: string;
}

export interface SponsorSegment {
  category: SponsorCategory;
  action: string;
  start_s: number;
  end_s: number;
}

export type SponsorBlockMode = "off" | "skip" | "cut";
export type SponsorCategory =
  | "sponsor"
  | "selfpromo"
  | "interaction"
  | "intro"
  | "outro"
  | "preview"
  | "music_offtopic"
  | "filler";

export interface Segments {
  mode: SponsorBlockMode;
  cut: boolean;
  segments: SponsorSegment[];
}

export interface ChannelCard extends Channel {
  video_count: number;
  unwatched_count: number;
  subscription_id: number | null;
  latest_at: string | null;
}

export interface ChannelDetail extends ChannelCard {
  description: string | null;
}

export interface HomeFeed {
  hero: VideoSummary | null;
  continue_watching: VideoSummary[];
  from_subscriptions: VideoSummary[];
  recently_added: VideoSummary[];
  channels: ChannelCard[];
}

export interface Playlist {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  video_count: number;
  duration_s: number;
  cover: VideoSummary[];
  contains: boolean | null;
}

export interface PlaylistDetail extends Playlist {
  videos: VideoSummary[];
}

export interface Chapter {
  start: number;
  end: number;
  title: string;
}

export interface Subtitle {
  id: number;
  lang: string;
  label: string;
  is_auto: boolean;
}

export interface VideoDetail extends VideoSummary {
  description: string | null;
  view_count: number | null;
  width: number | null;
  height: number | null;
  vcodec: string | null;
  acodec: string | null;
  filesize: number | null;
  container: string | null;
  chapters: Chapter[];
  subtitles: Subtitle[];
  source_url: string | null;
  downloaded_at: string | null;
  sponsorblock_cut: boolean;
  sponsor_segments: SponsorSegment[];
}

export interface Page<T> {
  items: T[];
  total: number;
}

export type JobStatus =
  "queued" | "running" | "paused" | "completed" | "failed" | "cancelled" | "skipped";
export type JobStage = "metadata" | "downloading" | "postprocessing";
export type ErrorKind = "network" | "rate_limited" | "unavailable" | "live" | "unknown";

export interface Job {
  id: number;
  url: string;
  youtube_id: string | null;
  status: JobStatus;
  stage: JobStage | null;
  progress: number;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  speed: number | null;
  eta: number | null;
  attempts: number;
  max_attempts: number;
  next_attempt_at: string | null;
  error_kind: ErrorKind | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  video: VideoSummary | null;
  subscription: { id: number; title: string } | null;
}

export interface QueueState {
  paused: boolean;
  running: number;
  queued: number;
}

export type SubscriptionKind = "channel" | "playlist";
export type ItemState = "queued" | "downloaded" | "filtered" | "skipped" | "failed" | "removed";

export interface SubscriptionDownloadOptions {
  container?: Container | null;
  max_height?: MaxHeight | null;
  prefer_h264?: boolean | null;
  sponsorblock_mode?: SponsorBlockMode | null;
}

export interface SubscriptionSettings {
  enabled: boolean;
  check_interval_minutes: number;
  include_shorts: boolean;
  include_live: boolean;
  min_duration_s: number | null;
  max_duration_s: number | null;
  date_after: string | null;
  keep_days: number | null;
  keep_last: number | null;
  download_options: SubscriptionDownloadOptions;
}

export interface Subscription extends SubscriptionSettings {
  id: number;
  kind: SubscriptionKind;
  youtube_id: string;
  url: string;
  title: string;
  last_checked_at: string | null;
  next_check_at: string | null;
  last_check_error: string | null;
  backfill: number | null;
  created_at: string;
  channel: Channel | null;
  stats: Record<ItemState, number>;
  checking: boolean;
}

export interface SubscriptionItem {
  id: number;
  youtube_id: string;
  title: string | null;
  upload_date: string | null;
  duration_s: number | null;
  state: ItemState;
  reason: string | null;
  video_id: number | null;
  job_id: number | null;
  first_seen_at: string;
}

export interface SubscriptionDetail extends Subscription {
  items: SubscriptionItem[];
}

export type Container = "mp4" | "mkv";
export type MaxHeight = 2160 | 1440 | 1080 | 720 | 480 | 360;

export interface DownloadOptions {
  container: Container;
  max_height: MaxHeight | null;
  prefer_h264: boolean;
  subtitles: boolean;
  auto_subtitles: boolean;
  subtitle_languages: string[];
  sponsorblock_mode: SponsorBlockMode;
  sponsorblock_categories: SponsorCategory[];
}

export type HwAccel = "none" | "vaapi" | "nvenc";

export interface TranscodeOptions {
  hwaccel: HwAccel;
  vaapi_device: string;
  max_height: 2160 | 1440 | 1080 | 720 | 480;
  max_sessions: number;
  cache_gb: number;
}

export type Layout = "tubevault" | "series";

export interface LibraryOptions {
  layout: Layout;
  write_nfo: boolean;
}

export interface AppSettings {
  downloads: DownloadOptions;
  max_concurrent_downloads: number;
  transcoding: TranscodeOptions;
  library: LibraryOptions;
}

export interface PlaybackInfo {
  container: string | null;
  video_codec: string | null;
  audio_codec: string | null;
  width: number | null;
  height: number | null;
  duration: number;
  can_remux: boolean;
  qualities: number[];
  transcode_height: number;
}

export interface RemuxStatus {
  state: "none" | "running" | "ready" | "failed";
  progress: number;
  error: string | null;
}

export interface HardwareInfo {
  render_devices: string[];
  nvidia: boolean;
  encoders: Record<string, boolean>;
}

export interface HwTestResult {
  ok: boolean;
  seconds: number;
  message: string;
}

export interface TranscodeSession {
  video_id: number;
  title: string | null;
  quality: string;
  height: number;
  mode: string;
  position_s: number;
  paused: boolean;
  idle_s: number;
}

export interface SystemInfo {
  version: string;
  ytdlp_version: string | null;
  ffmpeg_version: string | null;
  media_dir: string;
  disk: { total: number; used: number; free: number } | null;
  video_count: number;
  library_size: number;
}

export type LiveEvent =
  | { type: "ping" }
  | { type: "job.updated"; job: Job }
  | {
      type: "job.progress";
      job_id: number;
      stage: JobStage;
      progress: number;
      downloaded_bytes: number | null;
      total_bytes: number | null;
      speed: number | null;
      eta: number | null;
    }
  | { type: "job.deleted"; job_id: number }
  | { type: "jobs.cleared" }
  | { type: "video.updated"; video: VideoSummary }
  | { type: "video.deleted"; video_id: number }
  | { type: "subscription.updated"; subscription_id: number }
  | { type: "subscription.deleted"; subscription_id: number }
  | { type: "queue.state"; paused: boolean }
  | { type: "channels.updated" }
  | { type: "library.task"; task: LibraryTask };

export interface LibraryTask {
  kind: string;
  label: string;
  state: "running" | "done" | "failed";
  done: number;
  total: number;
  message: string | null;
  started_at: string;
  finished_at: string | null;
}
