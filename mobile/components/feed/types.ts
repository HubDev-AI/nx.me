/**
 * Feed data types — aligned with backend FeedPostResponse / FeedResponse.
 */

export interface FeedPost {
  post_id: string;
  user_id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  caption: string | null;
  before_image_url: string;
  after_image_url: string;
  reaction_count: number;
  comment_count: number;
  created_at: string;
  has_reacted: boolean;
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ReactionResponse {
  reaction_count: number;
  has_reacted: boolean;
}
