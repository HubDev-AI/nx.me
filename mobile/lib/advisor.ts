/**
 * Advisor API client and types.
 *
 * Handles chat messages (premium-only), nudge feed (all tiers),
 * and user memory CRUD. Maps to backend endpoints in app/api/advisor.py.
 */
import { apiFetch, ApiError } from "./api";
import { ADVISOR_ENDPOINTS } from "../constants/config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdvisorMessage {
  id: string;
  role: "user" | "advisor";
  content: string;
  created_at: string;
}

export interface MessagesResponse {
  messages: AdvisorMessage[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Actionable `post_glowup` nudge — the single nudge shape shipped in Nudges v2.
 *
 * Backend contract (`/v1/advisor/nudges`) returns `body` plus a
 * `next_step.{label, seed}` pair; the client flattens the nested pair
 * into `next_step_label` / `next_step_seed` for ergonomic rendering. The
 * `trigger` / `observation_tag` fields were deleted in Unit 3 along with
 * the four legacy trigger paths — do not re-introduce them.
 */
export interface Nudge {
  id: string;
  /** Primary copy rendered on the card and in the detail sheet. */
  body: string;
  /** CTA chip text. Always non-empty in well-formed payloads. */
  next_step_label: string;
  /**
   * Seed text committed server-side when the user taps the CTA. Sent to
   * the backend via `requestNudgeNextStep`; not rendered directly.
   */
  next_step_seed: string;
  read_at: string | null;
  created_at: string;
}

export interface NudgesResponse {
  nudges: Nudge[];
  next_cursor: string | null;
  has_more: boolean;
}

/** Response shape for `POST /v1/advisor/nudges/{id}/next-step`. */
export interface NudgeNextStepResponse {
  seed_text: string;
}

export type MemoryType =
  | "goal"
  | "user_note"
  | "accepted_suggestion"
  | "dismissed_suggestion"
  | "analysis_insight";

export interface UserMemory {
  id: string;
  type: MemoryType;
  content: Record<string, unknown>;
  created_at: string;
}

export interface MemoriesResponse {
  memories: UserMemory[];
  next_cursor: string | null;
  has_more: boolean;
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

/** Fetch conversation history. */
export async function fetchMessages(
  cursor?: string,
): Promise<MessagesResponse> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  const path = query
    ? `${ADVISOR_ENDPOINTS.MESSAGES}?${query}`
    : ADVISOR_ENDPOINTS.MESSAGES;
  return apiFetch<MessagesResponse>(path);
}

/**
 * Send a message to Ada.
 * Throws ApiError with status 402 if the user is not premium.
 */
export async function sendMessage(
  content: string,
): Promise<AdvisorMessage> {
  return apiFetch<AdvisorMessage>(ADVISOR_ENDPOINTS.MESSAGES, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/** Check if an API error is a 402 premium-required response. */
export function isPremiumRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 402;
}

// ---------------------------------------------------------------------------
// Nudges
// ---------------------------------------------------------------------------

/** Fetch nudge feed. */
export async function fetchNudges(
  cursor?: string,
): Promise<NudgesResponse> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  const path = query
    ? `${ADVISOR_ENDPOINTS.NUDGES}?${query}`
    : ADVISOR_ENDPOINTS.NUDGES;
  return apiFetch<NudgesResponse>(path);
}

/** Mark a nudge as read. */
export async function markNudgeRead(nudgeId: string): Promise<void> {
  await apiFetch(ADVISOR_ENDPOINTS.NUDGE_READ(nudgeId), {
    method: "PATCH",
    body: JSON.stringify({ read: true }),
  });
}

/**
 * Exchange a nudge's CTA tap for chat-open seed text.
 *
 * Fires only on user intent (CTA chip press) so the backend Haiku
 * call doesn't run for nudges the user never actions. Throws
 * `ApiError` on failure — callers map 404 → "stale nudge" toast,
 * other errors → generic failure toast.
 */
export async function requestNudgeNextStep(
  nudgeId: string,
): Promise<NudgeNextStepResponse> {
  return apiFetch<NudgeNextStepResponse>(
    ADVISOR_ENDPOINTS.NUDGE_NEXT_STEP(nudgeId),
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

// ---------------------------------------------------------------------------
// Memories
// ---------------------------------------------------------------------------

/**
 * Fetch user memories, optionally filtered by type.
 *
 * `signal` lets callers cancel an in-flight request — used by
 * `MemoryList` to drop the previous tab's fetch when the user taps
 * a different subtab, and to cancel the initial load when React
 * StrictMode double-mounts the effect in development.
 */
export async function fetchMemories(opts?: {
  type?: "goal" | "user_note";
  cursor?: string;
  signal?: AbortSignal;
}): Promise<MemoriesResponse> {
  const params = new URLSearchParams();
  if (opts?.type) params.set("type", opts.type);
  if (opts?.cursor) params.set("cursor", opts.cursor);
  const query = params.toString();
  const path = query
    ? `${ADVISOR_ENDPOINTS.MEMORIES}?${query}`
    : ADVISOR_ENDPOINTS.MEMORIES;
  return apiFetch<MemoriesResponse>(path, { signal: opts?.signal });
}

/** Add a new memory. */
export async function addMemory(
  type: MemoryType,
  content: Record<string, unknown>,
): Promise<UserMemory> {
  return apiFetch<UserMemory>(ADVISOR_ENDPOINTS.MEMORIES, {
    method: "POST",
    body: JSON.stringify({ type, content }),
  });
}

/** Delete a memory. */
export async function deleteMemory(memoryId: string): Promise<void> {
  await apiFetch(ADVISOR_ENDPOINTS.MEMORY_DELETE(memoryId), {
    method: "DELETE",
  });
}
