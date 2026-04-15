/**
 * Analysis API client — handles upload, generation, job polling, and cancellation.
 *
 * Tier-3 flow (active):
 *   createUpload → analyzeGlowup → generateGlowup → getJob / pollJob
 *
 * Legacy tier-2 flow (kept for backward compat until fully removed):
 *   createAnalysis → startGeneration
 */
import * as Crypto from "expo-crypto";

import { apiFetch } from "./api";
import {
  ANALYSIS_ENDPOINTS,
  ANALYSIS_POLLING,
  GLOWUP_ENDPOINTS,
} from "../constants/config";

// ---------------------------------------------------------------------------
// React Native FormData file descriptor
// ---------------------------------------------------------------------------
// RN's `FormData.append` accepts a `{ uri, name, type }` object as a file
// value, but the DOM typings only allow `Blob | string`. Declare the shape
// once and cast at the single append site — this is the officially sanctioned
// RN pattern (see https://reactnative.dev/docs/network#uploading-files).

interface RNFileDescriptor {
  uri: string;
  name: string;
  type: string;
}

function appendRNFile(form: FormData, field: string, file: RNFileDescriptor): void {
  form.append(field, file as unknown as Blob);
}

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
// Tier-3 types (Glow Up tier3 API — PR #56)
// ---------------------------------------------------------------------------

/** POST /v1/uploads response */
export interface UploadCreateResponse {
  upload_id: string;
  face_detected: boolean;
}

/** Individual recommendation item (tier-3 shape) */
export interface RecommendationItem {
  rank: number;
  category: string;
  suggestion: string;
}

/** POST /v1/uploads/{id}/glowup/analyze response */
export interface GlowupAnalyzeResponse {
  glowup_analysis_id: string;
  face_shape: string;
  symmetry_score: number;
  recommendations: RecommendationItem[];
}

/** POST /v1/uploads/{id}/glowup/generate response */
export interface GlowupGenerateResponse {
  job_id: string;
  status: string;
  estimated_wait_seconds: number;
  queue_position: number;
}

/** POST /v1/jobs/{id}/save response */
export interface JobSaveResponse {
  saved_at: string;
}

/** POST /v1/users/me/face-mod-consent response */
export interface FaceModConsentResponse {
  consented_at: string;
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
// Tier-3 API calls
// ---------------------------------------------------------------------------

/**
 * Upload a photo (multipart/form-data) to the tier-3 upload endpoint.
 * Step 1 of the progressive upload flow — fires immediately after photo pick.
 */
export async function createUpload(file: {
  uri: string;
  name: string;
  type: string;
}): Promise<UploadCreateResponse> {
  const formData = new FormData();
  appendRNFile(formData, "file", {
    uri: file.uri,
    name: file.name,
    type: file.type,
  });

  return apiFetch<UploadCreateResponse>(GLOWUP_ENDPOINTS.UPLOAD, {
    method: "POST",
    body: formData,
  });
}

/**
 * Run the Glow Up analysis on a previously uploaded file.
 * Requires face-mod consent — throws ApiError(428) if consent missing.
 */
export async function analyzeGlowup(
  uploadId: string,
): Promise<GlowupAnalyzeResponse> {
  return apiFetch<GlowupAnalyzeResponse>(
    GLOWUP_ENDPOINTS.ANALYZE(uploadId),
    { method: "POST" },
  );
}

/**
 * Kick off Glow Up image generation for an analyzed upload.
 * idempotencyKey prevents duplicate jobs on retry.
 */
export async function generateGlowup(
  uploadId: string,
  idempotencyKey: string,
): Promise<GlowupGenerateResponse> {
  return apiFetch<GlowupGenerateResponse>(
    GLOWUP_ENDPOINTS.GENERATE(uploadId),
    {
      method: "POST",
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    },
  );
}

/**
 * Save a completed job result. Idempotent — safe to call multiple times.
 */
export async function saveJob(jobId: string): Promise<JobSaveResponse> {
  return apiFetch<JobSaveResponse>(GLOWUP_ENDPOINTS.JOB_SAVE(jobId), {
    method: "POST",
  });
}

/**
 * Grant face-modification consent for the current user. Idempotent.
 */
export async function grantFaceModConsent(): Promise<FaceModConsentResponse> {
  return apiFetch<FaceModConsentResponse>(GLOWUP_ENDPOINTS.FACE_MOD_CONSENT, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Legacy tier-2 API calls (kept while result/card screens still reference them)
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
  appendRNFile(formData, "file", {
    uri: imageUri,
    name: fileName,
    type: mimeType,
  });

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
    {
      method: "POST",
      body: JSON.stringify({
        idempotency_key: Crypto.randomUUID(),
      }),
    },
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
