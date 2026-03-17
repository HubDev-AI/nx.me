import { useState, useCallback, useRef } from "react";

import { apiFetch } from "../../lib/api";
import {
  FEED_ENDPOINTS,
  FEED_CONFIG,
  FEED_SORT,
} from "../../constants/config";
import type { FeedSortValue } from "../../constants/config";
import type { FeedPost, FeedResponse, ReactionResponse } from "./types";

interface UseFeedReturn {
  posts: FeedPost[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  activeSort: FeedSortValue;
  reactedPostIds: Set<string>;
  loadFeed: () => Promise<void>;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  changeSort: (sort: FeedSortValue) => void;
  reactToPost: (postId: string) => Promise<void>;
}

/**
 * Custom hook for feed state management.
 * Handles pagination, sort switching, optimistic reactions, and dedup.
 */
export function useFeed(): UseFeedReturn {
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSort, setActiveSort] = useState<FeedSortValue>(FEED_SORT.NEWEST);
  const [reactedPostIds, setReactedPostIds] = useState<Set<string>>(new Set());

  const cursorRef = useRef<string | null>(null);
  const isLoadingRef = useRef(false);

  const fetchFeed = useCallback(
    async (cursor: string | null, sort: FeedSortValue): Promise<FeedResponse> => {
      const params = new URLSearchParams({
        sort,
        limit: String(FEED_CONFIG.PAGE_SIZE),
      });
      if (cursor) {
        params.set("cursor", cursor);
      }
      return apiFetch<FeedResponse>(
        `${FEED_ENDPOINTS.FEED}?${params.toString()}`,
      );
    },
    [],
  );

  const loadFeed = useCallback(async () => {
    if (isLoadingRef.current) return;
    isLoadingRef.current = true;
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetchFeed(null, activeSort);
      setPosts(response.posts);
      cursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load feed",
      );
    } finally {
      setIsLoading(false);
      isLoadingRef.current = false;
    }
  }, [fetchFeed, activeSort]);

  const loadMore = useCallback(async () => {
    if (isLoadingRef.current || !hasMore || !cursorRef.current) return;
    isLoadingRef.current = true;
    setIsLoadingMore(true);

    try {
      const response = await fetchFeed(cursorRef.current, activeSort);
      setPosts((prev) => [...prev, ...response.posts]);
      cursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch (err) {
      // Silently fail on load-more — user can scroll again
      console.warn("Feed loadMore error:", err);
    } finally {
      setIsLoadingMore(false);
      isLoadingRef.current = false;
    }
  }, [fetchFeed, activeSort, hasMore]);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);

    try {
      const response = await fetchFeed(null, activeSort);
      setPosts(response.posts);
      cursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to refresh feed",
      );
    } finally {
      setIsRefreshing(false);
    }
  }, [fetchFeed, activeSort]);

  const changeSort = useCallback(
    (sort: FeedSortValue) => {
      if (sort === activeSort) return;
      setActiveSort(sort);
      setPosts([]);
      cursorRef.current = null;
      setHasMore(true);
      setIsLoading(true);
      setError(null);

      // Fetch with new sort immediately
      isLoadingRef.current = true;
      fetchFeed(null, sort)
        .then((response) => {
          setPosts(response.posts);
          cursorRef.current = response.next_cursor;
          setHasMore(response.has_more);
        })
        .catch((err) => {
          setError(
            err instanceof Error ? err.message : "Failed to load feed",
          );
        })
        .finally(() => {
          setIsLoading(false);
          isLoadingRef.current = false;
        });
    },
    [activeSort, fetchFeed],
  );

  const reactToPost = useCallback(
    async (postId: string) => {
      // Dedup: skip if already reacted in this session
      if (reactedPostIds.has(postId)) return;

      // Optimistic update: increment count and mark as reacted
      setReactedPostIds((prev) => new Set(prev).add(postId));
      setPosts((prev) =>
        prev.map((p) =>
          p.post_id === postId
            ? { ...p, reaction_count: p.reaction_count + 1 }
            : p,
        ),
      );

      try {
        const response = await apiFetch<ReactionResponse>(
          FEED_ENDPOINTS.REACT(postId),
          { method: "POST" },
        );

        // Reconcile with server count
        setPosts((prev) =>
          prev.map((p) =>
            p.post_id === postId
              ? { ...p, reaction_count: response.reaction_count }
              : p,
          ),
        );
      } catch (err) {
        // Rollback optimistic update on failure
        setReactedPostIds((prev) => {
          const next = new Set(prev);
          next.delete(postId);
          return next;
        });
        setPosts((prev) =>
          prev.map((p) =>
            p.post_id === postId
              ? { ...p, reaction_count: Math.max(0, p.reaction_count - 1) }
              : p,
          ),
        );
        console.warn("Reaction failed:", err);
      }
    },
    [reactedPostIds],
  );

  return {
    posts,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMore,
    error,
    activeSort,
    reactedPostIds,
    loadFeed,
    loadMore,
    refresh,
    changeSort,
    reactToPost,
  };
}
