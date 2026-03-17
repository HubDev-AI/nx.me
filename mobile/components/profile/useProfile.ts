import { useState, useCallback, useRef } from "react";

import { apiFetch } from "../../lib/api";
import { PROFILE_ENDPOINTS, PROFILE_CONFIG } from "../../constants/config";
import type {
  UserProfile,
  GlowUpItem,
  GlowUpHistoryResponse,
  ReactedPost,
  ReactedPostsResponse,
  UpdateProfilePayload,
  ProfileTab,
} from "./types";

interface UseProfileReturn {
  profile: UserProfile | null;
  glowUps: GlowUpItem[];
  reactedPosts: ReactedPost[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMoreGlowUps: boolean;
  hasMoreReactions: boolean;
  error: string | null;
  activeTab: ProfileTab;
  isUpdating: boolean;
  updateError: string | null;
  loadProfile: (username: string) => Promise<void>;
  refresh: (username: string) => Promise<void>;
  loadMoreGlowUps: (username: string) => Promise<void>;
  loadMoreReactions: (username: string) => Promise<void>;
  changeTab: (tab: ProfileTab) => void;
  updateProfile: (
    username: string,
    payload: UpdateProfilePayload,
  ) => Promise<boolean>;
}

/**
 * Custom hook for profile screen state management.
 * Handles profile data, glow-up history, reactions, and profile editing.
 */
export function useProfile(): UseProfileReturn {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [glowUps, setGlowUps] = useState<GlowUpItem[]>([]);
  const [reactedPosts, setReactedPosts] = useState<ReactedPost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreGlowUps, setHasMoreGlowUps] = useState(true);
  const [hasMoreReactions, setHasMoreReactions] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ProfileTab>("glowups");
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const glowUpCursorRef = useRef<string | null>(null);
  const reactionCursorRef = useRef<string | null>(null);
  const isLoadingRef = useRef(false);

  const fetchProfile = useCallback(async (username: string) => {
    return apiFetch<UserProfile>(PROFILE_ENDPOINTS.PROFILE(username));
  }, []);

  const fetchGlowUps = useCallback(
    async (username: string, cursor: string | null) => {
      const params = new URLSearchParams({
        limit: String(PROFILE_CONFIG.PAGE_SIZE),
      });
      if (cursor) {
        params.set("cursor", cursor);
      }
      return apiFetch<GlowUpHistoryResponse>(
        `${PROFILE_ENDPOINTS.HISTORY(username)}?${params.toString()}`,
      );
    },
    [],
  );

  const fetchReactions = useCallback(
    async (username: string, cursor: string | null) => {
      const params = new URLSearchParams({
        limit: String(PROFILE_CONFIG.PAGE_SIZE),
      });
      if (cursor) {
        params.set("cursor", cursor);
      }
      return apiFetch<ReactedPostsResponse>(
        `${PROFILE_ENDPOINTS.REACTIONS(username)}?${params.toString()}`,
      );
    },
    [],
  );

  const loadProfile = useCallback(
    async (username: string) => {
      if (isLoadingRef.current) return;
      isLoadingRef.current = true;
      setIsLoading(true);
      setError(null);

      try {
        const [profileData, historyData] = await Promise.all([
          fetchProfile(username),
          fetchGlowUps(username, null),
        ]);

        setProfile(profileData);
        setGlowUps(historyData.items);
        glowUpCursorRef.current = historyData.next_cursor;
        setHasMoreGlowUps(historyData.has_more);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load profile",
        );
      } finally {
        setIsLoading(false);
        isLoadingRef.current = false;
      }
    },
    [fetchProfile, fetchGlowUps],
  );

  const refresh = useCallback(
    async (username: string) => {
      setIsRefreshing(true);
      setError(null);

      try {
        const [profileData, historyData] = await Promise.all([
          fetchProfile(username),
          fetchGlowUps(username, null),
        ]);

        setProfile(profileData);
        setGlowUps(historyData.items);
        glowUpCursorRef.current = historyData.next_cursor;
        setHasMoreGlowUps(historyData.has_more);

        // Reset reactions tab
        setReactedPosts([]);
        reactionCursorRef.current = null;
        setHasMoreReactions(true);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to refresh profile",
        );
      } finally {
        setIsRefreshing(false);
      }
    },
    [fetchProfile, fetchGlowUps],
  );

  const loadMoreGlowUps = useCallback(
    async (username: string) => {
      if (isLoadingRef.current || !hasMoreGlowUps || !glowUpCursorRef.current)
        return;
      isLoadingRef.current = true;
      setIsLoadingMore(true);

      try {
        const response = await fetchGlowUps(
          username,
          glowUpCursorRef.current,
        );
        setGlowUps((prev) => [...prev, ...response.items]);
        glowUpCursorRef.current = response.next_cursor;
        setHasMoreGlowUps(response.has_more);
      } catch {
        // Silently fail on load-more — user can scroll again
      } finally {
        setIsLoadingMore(false);
        isLoadingRef.current = false;
      }
    },
    [fetchGlowUps, hasMoreGlowUps],
  );

  const loadMoreReactions = useCallback(
    async (username: string) => {
      if (
        isLoadingRef.current ||
        !hasMoreReactions ||
        !reactionCursorRef.current
      )
        return;
      isLoadingRef.current = true;
      setIsLoadingMore(true);

      try {
        const response = await fetchReactions(
          username,
          reactionCursorRef.current,
        );
        setReactedPosts((prev) => [...prev, ...response.items]);
        reactionCursorRef.current = response.next_cursor;
        setHasMoreReactions(response.has_more);
      } catch {
        // Silently fail on load-more
      } finally {
        setIsLoadingMore(false);
        isLoadingRef.current = false;
      }
    },
    [fetchReactions, hasMoreReactions],
  );

  const changeTab = useCallback(
    (tab: ProfileTab) => {
      if (tab === activeTab) return;
      setActiveTab(tab);

      // Lazy-load reactions tab on first switch
      if (tab === "reactions" && reactedPosts.length === 0 && profile) {
        isLoadingRef.current = true;
        setIsLoadingMore(true);
        fetchReactions(profile.username, null)
          .then((response) => {
            setReactedPosts(response.items);
            reactionCursorRef.current = response.next_cursor;
            setHasMoreReactions(response.has_more);
          })
          .catch(() => {
            // Silent failure for tab switch
          })
          .finally(() => {
            setIsLoadingMore(false);
            isLoadingRef.current = false;
          });
      }
    },
    [activeTab, reactedPosts.length, profile, fetchReactions],
  );

  const updateProfile = useCallback(
    async (
      username: string,
      payload: UpdateProfilePayload,
    ): Promise<boolean> => {
      setIsUpdating(true);
      setUpdateError(null);

      try {
        const updated = await apiFetch<UserProfile>(
          PROFILE_ENDPOINTS.UPDATE(username),
          {
            method: "PATCH",
            body: JSON.stringify(payload),
          },
        );
        setProfile(updated);
        return true;
      } catch (err) {
        setUpdateError(
          err instanceof Error ? err.message : "Failed to update profile",
        );
        return false;
      } finally {
        setIsUpdating(false);
      }
    },
    [],
  );

  return {
    profile,
    glowUps,
    reactedPosts,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMoreGlowUps,
    hasMoreReactions,
    error,
    activeTab,
    isUpdating,
    updateError,
    loadProfile,
    refresh,
    loadMoreGlowUps,
    loadMoreReactions,
    changeTab,
    updateProfile,
  };
}
