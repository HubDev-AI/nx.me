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
  username_change_cooldown_remaining_seconds?: number | null;
}

/** Matches HistoryEntry in app/api/users.py */
export interface GlowUpItem {
  analysis_id: string;
  /** Job correlation. Null only for legacy analyses without a job row. */
  job_id: string | null;
  /**
   * JobStatus value for the latest job tied to this analysis. Drives the
   * cell variant: queued/processing/finalizing → pending shimmer; completed
   * → thumbnail; failed/cancelled → muted errored. Empty string for legacy.
   */
  status: string;
  face_shape: string | null;
  symmetry_score: number | null;
  recommendations: Record<string, unknown>[];
  before_image_url: string | null;
  after_image_url: string | null;
  created_at: string;
  /**
   * ISO timestamp when the user tapped Save for this job, or null when
   * unsaved. The profile grid renders a small check-mark badge on saved
   * cells so the user can tell at a glance which transformations they
   * have already kept.
   */
  saved_at: string | null;
  /**
   * ID of the currently LIVE public post for this glow-up, or null when
   * the glow-up is not published (or its post was soft-deleted / auto-
   * hidden). "Live" matches migration 0046's partial unique predicate
   * (``is_deleted = FALSE AND is_hidden = FALSE``). Present only on
   * responses from backends with the published-indicator projection —
   * older backends omit the field, hence the optional marker.
   */
  post_id?: string | null;
  /**
   * Discriminator for gallery segmentation. Defaults to "glowup_analysis"
   * for legacy rows; "makeup_session" for makeup jobs.
   */
  source_type?: string;
}

/** Matches HistoryResponse in app/api/users.py */
export interface GlowUpHistoryResponse {
  entries: GlowUpItem[];
  next_cursor: string | null;
  has_more: boolean;
}

/** Matches UpdateProfileRequest in app/api/users.py */
export interface UpdateProfilePayload {
  display_name?: string;
  new_username?: string;
}

/** Matches UpdateProfileResponse in app/api/users.py */
export interface UpdateProfileResponse {
  username: string;
  display_name: string;
  avatar_url: string | null;
  username_change_cooldown_remaining_seconds?: number | null;
}
