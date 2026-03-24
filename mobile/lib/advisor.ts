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
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface MessagesResponse {
  messages: AdvisorMessage[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface Nudge {
  id: string;
  trigger: string;
  content: string;
  read_at: string | null;
  created_at: string;
}

export interface NudgesResponse {
  nudges: Nudge[];
  has_more: boolean;
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

// ---------------------------------------------------------------------------
// Memories
// ---------------------------------------------------------------------------

/** Fetch all user memories. */
export async function fetchMemories(): Promise<MemoriesResponse> {
  return apiFetch<MemoriesResponse>(ADVISOR_ENDPOINTS.MEMORIES);
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
