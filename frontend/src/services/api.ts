import axios from "axios";
import type { PipelineResponse, Review, PublishResult } from "../types";

// In production (Netlify) VITE_API_BASE_URL points to the Render backend.
// In dev, it's empty so Vite's proxy forwards /api → localhost:8000.
const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api/v1`
  : "/api/v1";

const http = axios.create({ baseURL: BASE });

export async function runPipeline(payload: {
  my_posts: { text: string }[];
  competitor_posts: { text: string }[];
  x_username?: string;
  start_date?: string;
  days: number;
  platforms: string[];
  auto_approve: boolean;
}): Promise<PipelineResponse> {
  const res = await http.post("/pipeline/run", payload);
  return res.data.data;
}

export async function getReviews(status?: string): Promise<Review[]> {
  const params = status ? { status } : {};
  const res = await http.get("/reviews", { params });
  return res.data;
}

export async function approveReview(id: number): Promise<Review> {
  const res = await http.patch(`/reviews/${id}/status`, { status: "approved" });
  return res.data;
}

export async function regenerateField(
  id: number,
  action: "rewrite_post" | "regenerate_hashtags" | "regenerate_visual"
): Promise<Review> {
  const res = await http.post(`/reviews/${id}/regenerate`, { action });
  return res.data;
}

export async function publishReview(
  review_id: number,
  platforms: string[]
): Promise<PublishResult> {
  const res = await http.post("/publish", { review_id, platforms });
  return res.data.data;
}

export async function getPublishJobs(): Promise<import("../types").PublishJob[]> {
  const res = await http.get("/publish/jobs");
  return res.data;
}
