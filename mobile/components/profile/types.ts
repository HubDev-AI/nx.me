/**
 * Profile data types — aligned with backend user profile and history endpoints.
 *
 * Source of truth: app/api/users.py
 *   ProfileResponse      -> UserProfile
 *   HistoryEntry         -> GlowUpItem
 *   HistoryResponse      -> GlowUpHistoryResponse
 *   UpdateProfileRequest -> UpdateProfilePayload
 */

/** Matches ProfileResponse in app/api/users.py */
export interface UserProfile {
  username: string;
  display_name: string;
  avatar_url: string | null;
  post_count: number;
  total_reactions: number;
  member_since: string;
}

/** Matches HistoryEntry in app/api/users.py */
export interface GlowUpItem {
  analysis_id: string;
  face_shape: string | null;
  symmetry_score: number | null;
  recommendations: Record<string, unknown>[];
  before_image_url: string | null;
  after_image_url: string | null;
  created_at: string;
}

/** Matches HistoryResponse in app/api/users.py */
export interface GlowUpHistoryResponse {
  entries: GlowUpItem[];
  next_cursor: string | null;
  has_more: boolean;
}

/** Matches UpdateProfileRequest in app/api/users.py — only display_name is accepted */
export interface UpdateProfilePayload {
  display_name?: string;
}

/** Matches UpdateProfileResponse in app/api/users.py */
export interface UpdateProfileResponse {
  username: string;
  display_name: string;
  avatar_url: string | null;
}
