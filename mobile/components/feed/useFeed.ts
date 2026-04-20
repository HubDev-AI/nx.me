import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { parseApiError, type AppError } from "../../lib/errors";
import {
  FEED_ENDPOINTS,
  FEED_CONFIG,
  FEED_SORT,
} from "../../constants/config";
import type { FeedSortValue } from "../../constants/config";
import type { FeedPost, FeedResponse, ReactionResponse } from "./types";

interface FeedPage {
  posts: FeedPost[];
  nextCursor: string | null;
}

export interface UseFeedReturn {
  posts: FeedPost[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: AppError | null;
  activeSort: FeedSortValue;
  reactedPostIds: Set<string>;
  paginationFailed: boolean;
  loadFeed: () => Promise<void>;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  changeSort: (sort: FeedSortValue) => void;
  reactToPost: (postId: string) => Promise<void>;
  incrementCommentCount: (postId: string) => void;
  removePostsByUser: (userId: string) => void;
}

async function fetchFeedPage(
  sort: FeedSortValue,
  cursor: string | undefined,
): Promise<FeedPage> {
  const params = new URLSearchParams({
    sort,
    limit: String(FEED_CONFIG.PAGE_SIZE),
  });
  if (cursor) {
    params.set("cursor", cursor);
  }
  const response = await apiFetch<FeedResponse>(
    `${FEED_ENDPOINTS.FEED}?${params.toString()}`,
  );
  return {
    posts: response.posts,
    nextCursor: response.next_cursor,
  };
}

/**
 * Custom hook for feed state management.
 * Handles pagination, sort switching, optimistic reactions, and dedup.
 * Uses TanStack useInfiniteQuery for fetch/retry/caching.
 */
export function useFeed(): UseFeedReturn {
  const queryClient = useQueryClient();
  const [activeSort, setActiveSort] = useState<FeedSortValue>(FEED_SORT.NEWEST);
  const [reactedPostIds, setReactedPostIds] = useState<Set<string>>(new Set());
  const reactingRef = useRef<Set<string>>(new Set());

  const query = useInfiniteQuery<FeedPage, unknown>({
    queryKey: ["feed", activeSort],
    queryFn: ({ pageParam }) =>
      fetchFeedPage(activeSort, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    staleTime: 30_000,
  });

  const posts = useMemo(
    () => query.data?.pages.flatMap((p) => p.posts) ?? [],
    [query.data],
  );

  // Seed reactedPostIds from the server's has_reacted flag on every fetch so
  // the heart renders filled on initial load and survives refresh. Any posts
  // the server says are reacted are added to the set; keeping existing
  // entries means a just-clicked like is not clobbered by an in-flight
  // refetch that hasn't seen the write yet.
  useEffect(() => {
    setReactedPostIds((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const post of posts) {
        if (post.has_reacted && !next.has(post.post_id)) {
          next.add(post.post_id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [posts]);

  // Derived state: paginationFailed when there's an error and not currently fetching
  const paginationFailed = !!query.error && !query.isFetching && posts.length > 0;

  // ---------------------------------------------------------------------------
  // Cache mutation helpers
  // ---------------------------------------------------------------------------

  const updateCache = useCallback(
    (
      updater: (
        old: { pages: FeedPage[]; pageParams: unknown[] } | undefined,
      ) => { pages: FeedPage[]; pageParams: unknown[] } | undefined,
    ) => {
      queryClient.setQueryData(["feed", activeSort], updater);
    },
    [queryClient, activeSort],
  );

  // ---------------------------------------------------------------------------
  // Public API methods
  // ---------------------------------------------------------------------------

  const loadFeed = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey: ["feed", activeSort] });
  }, [queryClient, activeSort]);

  const loadMore = useCallback(async () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      await query.fetchNextPage();
    }
    // Intentionally depending on the stable sub-fields we actually read —
    // including `query` would bust identity on every background refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.hasNextPage, query.isFetchingNextPage, query.fetchNextPage]);

  const refresh = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey: ["feed", activeSort] });
  }, [queryClient, activeSort]);

  const changeSort = useCallback(
    (sort: FeedSortValue) => {
      if (sort === activeSort) return;
      setActiveSort(sort);
      // The new sort value changes the queryKey — TanStack will auto-fetch
    },
    [activeSort],
  );

  const reactToPost = useCallback(
    async (postId: string) => {
      // Dedup: synchronous ref check prevents race from rapid taps
      if (reactingRef.current.has(postId)) return;
      reactingRef.current.add(postId);

      // Snapshot state BEFORE the optimistic flip so rollback restores truth.
      const wasReacted = reactedPostIds.has(postId);
      const delta = wasReacted ? -1 : 1;

      // Optimistic: flip reacted state and adjust count by ±1.
      setReactedPostIds((prev) => {
        const next = new Set(prev);
        if (wasReacted) next.delete(postId);
        else next.add(postId);
        return next;
      });
      updateCache((old) => {
        if (!old) return old;
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) =>
              p.post_id === postId
                ? {
                    ...p,
                    reaction_count: Math.max(0, p.reaction_count + delta),
                    has_reacted: !wasReacted,
                  }
                : p,
            ),
          })),
        };
      });

      try {
        const response = await apiFetch<ReactionResponse>(
          FEED_ENDPOINTS.REACT(postId),
          { method: "POST" },
        );

        // Server is truth — reconcile count AND reacted state.
        setReactedPostIds((prev) => {
          const next = new Set(prev);
          if (response.has_reacted) next.add(postId);
          else next.delete(postId);
          return next;
        });
        updateCache((old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              posts: page.posts.map((p) =>
                p.post_id === postId
                  ? {
                      ...p,
                      reaction_count: response.reaction_count,
                      has_reacted: response.has_reacted,
                    }
                  : p,
              ),
            })),
          };
        });
      } catch (err) {
        // Rollback optimistic update on failure
        setReactedPostIds((prev) => {
          const next = new Set(prev);
          if (wasReacted) next.add(postId);
          else next.delete(postId);
          return next;
        });
        updateCache((old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              posts: page.posts.map((p) =>
                p.post_id === postId
                  ? {
                      ...p,
                      reaction_count: Math.max(0, p.reaction_count - delta),
                      has_reacted: wasReacted,
                    }
                  : p,
              ),
            })),
          };
        });
        console.warn("Reaction failed:", err);
      } finally {
        reactingRef.current.delete(postId);
      }
    },
    [reactedPostIds, updateCache],
  );

  const incrementCommentCount = useCallback(
    (postId: string) => {
      updateCache((old) => {
        if (!old) return old;
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) =>
              p.post_id === postId
                ? { ...p, comment_count: (p.comment_count ?? 0) + 1 }
                : p,
            ),
          })),
        };
      });
    },
    [updateCache],
  );

  const removePostsByUser = useCallback(
    (userId: string) => {
      updateCache((old) => {
        if (!old) return old;
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.filter((p) => p.user_id !== userId),
          })),
        };
      });
    },
    [updateCache],
  );

  return {
    posts,
    isLoading: query.isLoading,
    isRefreshing: query.isRefetching && !query.isFetchingNextPage,
    isLoadingMore: query.isFetchingNextPage,
    hasMore: query.hasNextPage ?? false,
    error: query.error ? parseApiError(query.error) : null,
    activeSort,
    reactedPostIds,
    paginationFailed,
    loadFeed,
    loadMore,
    refresh,
    changeSort,
    reactToPost,
    incrementCommentCount,
    removePostsByUser,
  };
}
