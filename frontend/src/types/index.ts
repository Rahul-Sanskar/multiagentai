export interface PostInput {
  text: string;
  timestamp?: string;
  likes?: number;
  comments?: number;
  shares?: number;
  views?: number;
}

export interface PipelineStage {
  stage: string;
  success: boolean;
  error?: string | null;
}

export interface CalendarEntry {
  day: number;
  date: string;
  platform: string;
  format: string;
  time: string;
  topic: string | null;
}

export interface PipelineResponse {
  calendar_session_id: string;
  calendar_entries: number;
  reviews_created: number;
  publish_jobs: number;
  stages: PipelineStage[];
  rag_stats: { total_chunks: number; embedding_dim: number };
  calendar: CalendarEntry[];
  my_posts_source: "real_x_api" | "mock" | "manual";
}

export interface Review {
  id: number;
  topic: string;
  post: string;
  hashtags: string[];
  visual_prompt: string;
  status: "pending" | "approved" | "revision";
  platform: string;
  tone: string;
  reviewer_note?: string | null;
  created_at?: string | null;
}

export interface PublishJob {
  id: number;
  review_id: number;
  platform: string;
  status: "queued" | "posted" | "failed";
  post_url?: string | null;
  latency_ms?: number | null;
  error_message?: string | null;
}

export interface PublishResult {
  review_id: number;
  results: {
    job_id: number;
    platform: string;
    status: string;
    post_url?: string | null;
    message: string;
  }[];
  published_count: number;
  failed_count: number;
}
