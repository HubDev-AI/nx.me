import { useState, useCallback, useRef, useEffect } from "react";

import { apiFetch } from "../../lib/api";
import { getStoredJwt } from "../../lib/auth";
import { FEED_ENDPOINTS, COMMENTS_CONFIG } from "../../constants/config";
import type { Comment, CommentsResponse, CreateCommentResponse } from "./types";

interface UseCommentsReturn {
  comments: Comment[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  isAuthenticated: boolean;
  isPosting: boolean;
  postError: string | null;
  paginationFailed: boolean;
  loadComments: (postId: string) => Promise<void>;
  loadMore: (postId: string) => Promise<void>;
  postComment: (postId: string, content: string) => Promise<void>;
  reset: () => void;
}

/**
 * Custom hook for comment list state management.
 * Handles pagination, optimistic posting, auth gating, and rollback on error.
 */
export function useComments(): UseCommentsReturn {
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isPosting, setIsPosting] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);
  const [paginationFailed, setPaginationFailed] = useState(false);

  const cursorRef = useRef<string | null>(null);
  const isLoadingRef = useRef(false);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const checkAuth = useCallback(async () => {
    const jwt = await getStoredJwt();
    const authed = jwt !== null;
    setIsAuthenticated(authed);
    return authed;
  }, []);

  const loadComments = useCallback(
    async (postId: string) => {
      if (isLoadingRef.current) return;
      isLoadingRef.current = true;
      setIsLoading(true);
      setError(null);
      setPostError(null);

      try {
        await checkAuth();
        const params = new URLSearchParams({
          limit: String(COMMENTS_CONFIG.PAGE_SIZE),
        });
        const response = await apiFetch<CommentsResponse>(
          `${FEED_ENDPOINTS.COMMENTS(postId)}?${params.toString()}`,
        );
        setComments(response.comments);
        cursorRef.current = response.next_cursor;
        setHasMore(response.has_more);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "We couldn't load comments.",
        );
      } finally {
        setIsLoading(false);
        isLoadingRef.current = false;
      }
    },
    [checkAuth],
  );

  const loadMore = useCallback(
    async (postId: string) => {
      if (isLoadingRef.current || !hasMore || !cursorRef.current) return;
      isLoadingRef.current = true;
      setIsLoadingMore(true);

      try {
        const params = new URLSearchParams({
          limit: String(COMMENTS_CONFIG.PAGE_SIZE),
          cursor: cursorRef.current,
        });
        const response = await apiFetch<CommentsResponse>(
          `${FEED_ENDPOINTS.COMMENTS(postId)}?${params.toString()}`,
        );
        setComments((prev) => [...prev, ...response.comments]);
        cursorRef.current = response.next_cursor;
        setHasMore(response.has_more);
        retryCountRef.current = 0;
        setPaginationFailed(false);
      } catch {
        retryCountRef.current += 1;
        if (retryCountRef.current < 3) {
          const delay = retryCountRef.current === 1 ? 2000 : 3000;
          isLoadingRef.current = false;
          setIsLoadingMore(false);
          retryTimeoutRef.current = setTimeout(() => {
            loadMore(postId);
          }, delay);
          return;
        }
        setPaginationFailed(true);
      } finally {
        setIsLoadingMore(false);
        isLoadingRef.current = false;
      }
    },
    [hasMore],
  );

  const postComment = useCallback(
    async (postId: string, content: string) => {
      setIsPosting(true);
      setPostError(null);

      // Create optimistic comment with temporary ID
      const tempId = `temp_${Date.now()}`;
      const optimisticComment: Comment = {
        comment_id: tempId,
        post_id: postId,
        user_id: "me",
        content,
        is_deleted: false,
        created_at: new Date().toISOString(),
        display_name: "You",
        avatar_url: null,
      };

      // Optimistic: prepend to list
      setComments((prev) => [optimisticComment, ...prev]);

      try {
        const response = await apiFetch<CreateCommentResponse>(
          FEED_ENDPOINTS.COMMENTS(postId),
          {
            method: "POST",
            body: JSON.stringify({ content }),
          },
        );

        // Replace optimistic comment with server response
        setComments((prev) =>
          prev.map((c) =>
            c.comment_id === tempId
              ? {
                  comment_id: response.comment_id,
                  post_id: response.post_id,
                  user_id: response.user_id,
                  content: response.content,
                  is_deleted: response.is_deleted,
                  created_at: response.created_at,
                  display_name: response.display_name,
                  avatar_url: response.avatar_url,
                }
              : c,
          ),
        );
      } catch (err) {
        // Rollback: remove optimistic comment
        setComments((prev) => prev.filter((c) => c.comment_id !== tempId));
        setPostError(
          err instanceof Error ? err.message : "Couldn't post that comment.",
        );
      } finally {
        setIsPosting(false);
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setComments([]);
    setIsLoading(false);
    setIsLoadingMore(false);
    setHasMore(true);
    setError(null);
    setPostError(null);
    setIsPosting(false);
    setPaginationFailed(false);
    cursorRef.current = null;
    retryCountRef.current = 0;
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  // Cleanup retry timeout on unmount
  useEffect(() => {
    return () => {
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  return {
    comments,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    isAuthenticated,
    isPosting,
    postError,
    paginationFailed,
    loadComments,
    loadMore,
    postComment,
    reset,
  };
}
