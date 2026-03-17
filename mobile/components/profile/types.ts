/**
 * Profile data types — aligned with backend user profile and history endpoints.
 */

export interface UserProfile {
  user_id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  post_count: number;
  reaction_count: number;
  streak_days: number;
  created_at: string;
}

export interface GlowUpItem {
  post_id: string;
  before_image_url: string;
  after_image_url: string;
  reaction_count: number;
  created_at: string;
}

export interface GlowUpHistoryResponse {
  items: GlowUpItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ReactedPost {
  post_id: string;
  user_id: string;
  username: string;
  before_image_url: string;
  after_image_url: string;
  reaction_count: number;
  created_at: string;
}

export interface ReactedPostsResponse {
  items: ReactedPost[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface UpdateProfilePayload {
  display_name?: string;
  avatar_url?: string;
}

export type ProfileTab = "glowups" | "reactions";
