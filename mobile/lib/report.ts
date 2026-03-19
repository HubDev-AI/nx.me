/**
 * Report API — POST /v1/posts/{postId}/report
 *
 * Rate limited to 5 reports per hour per user (server-enforced).
 */
import { apiFetch } from "./api";

interface ReportResponse {
  report_id: string;
  status: string;
}

export async function reportPost(
  postId: string,
  reason?: string,
): Promise<ReportResponse> {
  return apiFetch<ReportResponse>(`/v1/posts/${postId}/report`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}
