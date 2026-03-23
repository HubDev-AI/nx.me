/**
 * Analysis API client — handles upload, generation, job polling, and cancellation.
 */
import { apiFetch } from "./api";
import { ANALYSIS_ENDPOINTS, ANALYSIS_POLLING } from "../constants/config";

// ---------------------------------------------------------------------------
// Types — kept in sync with backend OpenAPI spec (2026-03-23)
// ---------------------------------------------------------------------------

/** POST /v1/analyses response */
export interface AnalysisCreateResponse {
  analysis_id: string;
  face_shape: string;
  symmetry_score: number;
  recommendations: Suggestion[];
  status: string;
}

/** Individual recommendation item from the backend */
export interface Suggestion {
  rank: number;
  category: string;
  suggestion: string;
}

/** Backend face-validation error codes (used client-side for upload-time checks) */
export type FaceErrorCode =
  | "FACE_NOT_DETECTED"
  | "MULTIPLE_FACES"
  | "FACE_TOO_SMALL"
  | "FACE_OCCLUDED"
  | "LOW_QUALITY"
  | "UNSUPPORTED_FORMAT";

/** POST /v1/analyses/{id}/generate response */
export interface GenerateResponse {
  job_id: string;
  status: string;
  estimated_wait_seconds: number;
  queue_position: number;
}

export type JobStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

/** GET /v1/jobs/{id} response */
export interface JobResult {
  job_id: string;
  status: JobStatus;
  estimated_wait_seconds: number | null;
  elapsed_seconds: number | null;
  before_image_url: string | null;
  after_image_url: string | null;
  identity_preserved: boolean | null;
  failure_reason: string | null;
  credit_refunded: boolean | null;
  retry_eligible: boolean | null;
  user_guidance: string | null;
}

export interface EntitlementInfo {
  remaining_trials: number;
  total_trials: number;
}

// ---------------------------------------------------------------------------
// Face error user-facing messages
// ---------------------------------------------------------------------------

const FACE_ERROR_GUIDANCE: Record<FaceErrorCode, string> = {
  FACE_NOT_DETECTED:
    "No face was detected in the photo. Please upload a clear, front-facing selfie.",
  MULTIPLE_FACES:
    "Multiple faces were detected. Please upload a photo with only your face.",
  FACE_TOO_SMALL:
    "Your face is too small in the frame. Try a closer photo or crop around your face.",
  FACE_OCCLUDED:
    "Part of your face appears to be covered. Remove sunglasses, masks, or obstructions and try again.",
  LOW_QUALITY:
    "The image quality is too low. Use a well-lit photo with minimal blur.",
  UNSUPPORTED_FORMAT:
    "This image format is not supported. Please use JPEG or PNG.",
};

export function getFaceErrorGuidance(code: FaceErrorCode): string {
  return FACE_ERROR_GUIDANCE[code];
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * Upload a photo for analysis (multipart/form-data).
 * Returns the analysis ID and face validation result.
 */
export async function createAnalysis(
  imageUri: string,
  fileName: string,
  mimeType: string,
): Promise<AnalysisCreateResponse> {
  const formData = new FormData();
  formData.append("file", {
    uri: imageUri,
    name: fileName,
    type: mimeType,
  } as unknown as Blob);

  // Do not set Content-Type manually — fetch sets it automatically with the
  // correct multipart boundary when the body is FormData.
  return apiFetch<AnalysisCreateResponse>(ANALYSIS_ENDPOINTS.CREATE, {
    method: "POST",
    body: formData,
  });
}

/**
 * Start generation for an analysis.
 */
export async function startGeneration(
  analysisId: string,
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>(
    ANALYSIS_ENDPOINTS.GENERATE(analysisId),
    { method: "POST" },
  );
}

/**
 * Get current job status.
 */
export async function getJobStatus(jobId: string): Promise<JobResult> {
  return apiFetch<JobResult>(ANALYSIS_ENDPOINTS.JOB_STATUS(jobId));
}

/**
 * Cancel a running generation job.
 */
export async function cancelJob(jobId: string): Promise<void> {
  await apiFetch(ANALYSIS_ENDPOINTS.JOB_CANCEL(jobId), { method: "POST" });
}

/**
 * Request a refund for a completed job ("this doesn't look like me").
 *
 * NOTE: As of 2026-03-20, the backend does not expose /v1/jobs/{id}/refund
 * in its OpenAPI spec. The call will fail gracefully and the UI shows an
 * error alert. Once the backend ships this endpoint, it will work without
 * app changes.
 */
export async function requestRefund(jobId: string): Promise<void> {
  await apiFetch(ANALYSIS_ENDPOINTS.JOB_REFUND(jobId), { method: "POST" });
}

/**
 * Get current entitlement info (trial count etc).
 */
export async function getEntitlement(): Promise<EntitlementInfo> {
  return apiFetch<EntitlementInfo>("/v1/entitlement");
}

// ---------------------------------------------------------------------------
// Polling helper
// ---------------------------------------------------------------------------

/**
 * Poll a job until it reaches a terminal state.
 * Calls onUpdate with each intermediate result.
 * Returns the final JobResult.
 * Respects AbortSignal for cancellation.
 */
export async function pollJob(
  jobId: string,
  onUpdate: (result: JobResult) => void,
  signal?: AbortSignal,
): Promise<JobResult> {
  const terminalStatuses: JobStatus[] = ["completed", "failed", "cancelled"];

  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (signal?.aborted) {
      throw new DOMException("Polling aborted", "AbortError");
    }

    const result = await getJobStatus(jobId);
    onUpdate(result);

    if (terminalStatuses.includes(result.status)) {
      return result;
    }

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, ANALYSIS_POLLING.INTERVAL_MS);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(new DOMException("Polling aborted", "AbortError"));
        },
        { once: true },
      );
    });
  }
}
