/**
 * Comment data types — aligned with backend CommentResponse / CommentsListResponse.
 */

export interface Comment {
  comment_id: string;
  post_id: string;
  user_id: string;
  content: string;
  is_deleted: boolean;
  created_at: string;
  /** Author display name (null if account deleted) */
  display_name: string | null;
  /** Author avatar URL (null if no avatar or account deleted) */
  avatar_url: string | null;
}

export interface CommentsResponse {
  comments: Comment[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CreateCommentResponse {
  comment_id: string;
  post_id: string;
  user_id: string;
  content: string;
  is_deleted: boolean;
  created_at: string;
  display_name: string | null;
  avatar_url: string | null;
}
