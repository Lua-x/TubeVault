export type Theme = "system" | "dark" | "light";

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  preferences: { theme?: Theme };
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
}

export interface Page<T> {
  items: T[];
  total: number;
}

export type JobStatus = "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";
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
}

export interface AppSettings {
  downloads: DownloadOptions;
  max_concurrent_downloads: number;
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
  | { type: "video.deleted"; video_id: number };
