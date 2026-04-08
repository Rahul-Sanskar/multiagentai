import axios from "axios";
import type { PipelineResponse, Review, PublishResult } from "../types";

const http = axios.create({ baseURL: "/api/v1" });

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
