/**
 * Makeup API client — analyze, generate, and type definitions.
 *
 * Flow:
 *   analyzeMakeup → returns recommended preset ordering (also records consent)
 *   generateMakeup → enqueues the fal job, returns job_id
 *   Poll via existing getJobStatus (analysis.ts) — job carries source_type=makeup_session
 */
import * as Crypto from "expo-crypto";

import { apiFetch } from "./api";
import { MAKEUP_ENDPOINTS } from "../constants/config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MakeupIntensity = "subtle" | "light" | "medium" | "bold";

export interface RecommendedPreset {
  slug: string;
  display_name: string;
  intensity: MakeupIntensity;
}

export interface MakeupAnalyzeResponse {
  mst_bin: number;
  undertone: "warm" | "neutral" | "cool";
  recommended_presets: RecommendedPreset[];
}

export interface MakeupGenerateResponse {
  job_id: string;
  status: string;
  estimated_wait_seconds: number;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function analyzeMakeup(
  uploadId: string,
): Promise<MakeupAnalyzeResponse> {
  return apiFetch<MakeupAnalyzeResponse>(MAKEUP_ENDPOINTS.ANALYZE(uploadId), {
    method: "POST",
  });
}

export async function generateMakeup(
  uploadId: string,
  presetSlug: string,
  intensity: MakeupIntensity,
  idempotencyKey: string = Crypto.randomUUID(),
): Promise<MakeupGenerateResponse> {
  return apiFetch<MakeupGenerateResponse>(MAKEUP_ENDPOINTS.GENERATE(uploadId), {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      preset_slug: presetSlug,
      intensity,
      idempotency_key: idempotencyKey,
    }),
  });
}
