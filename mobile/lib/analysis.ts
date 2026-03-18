/**
 * Analysis API client — handles upload, generation, job polling, and cancellation.
 */
import { apiFetch } from "./api";
import { ANALYSIS_ENDPOINTS, ANALYSIS_POLLING } from "../constants/config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AnalysisCreateResponse {
  id: string;
  status: string;
  face_validation: FaceValidation | null;
}

export interface FaceValidation {
  passed: boolean;
  error_code: FaceErrorCode | null;
  message: string | null;
}

/** Backend face-validation error codes */
export type FaceErrorCode =
  | "FACE_NOT_DETECTED"
  | "MULTIPLE_FACES"
  | "FACE_TOO_SMALL"
  | "FACE_OCCLUDED"
  | "LOW_QUALITY"
  | "UNSUPPORTED_FORMAT";

export interface GenerateResponse {
  job_id: string;
}

export type JobStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface JobResult {
  id: string;
  status: JobStatus;
  before_url: string | null;
  after_url: string | null;
  suggestions: string[];
  error_code: string | null;
  error_message: string | null;
  created_at: string;
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

  // Use apiFetch but override Content-Type for multipart
  return apiFetch<AnalysisCreateResponse>(ANALYSIS_ENDPOINTS.CREATE, {
    method: "POST",
    body: formData,
    headers: {
      // Let fetch set the multipart boundary automatically
      "Content-Type": "multipart/form-data",
    },
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
 */
export async function requestRefund(jobId: string): Promise<void> {
  await apiFetch(`/v1/jobs/${jobId}/refund`, { method: "POST" });
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
