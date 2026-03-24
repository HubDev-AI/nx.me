import { useState, useCallback, useRef } from "react";

import { apiFetch } from "../../lib/api";
import { PROFILE_ENDPOINTS, PROFILE_CONFIG } from "../../constants/config";
import type {
  UserProfile,
  GlowUpItem,
  GlowUpHistoryResponse,
  UpdateProfilePayload,
  UpdateProfileResponse,
} from "./types";

interface UseProfileReturn {
  profile: UserProfile | null;
  glowUps: GlowUpItem[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMoreGlowUps: boolean;
  error: string | null;
  isUpdating: boolean;
  updateError: string | null;
  loadProfile: (username: string) => Promise<void>;
  refresh: (username: string) => Promise<void>;
  loadMoreGlowUps: (username: string) => Promise<void>;
  updateProfile: (
    username: string,
    payload: UpdateProfilePayload,
  ) => Promise<boolean>;
}

/**
 * Custom hook for profile screen state management.
 * Handles profile data, glow-up history, and profile editing.
 *
 * Backed by:
 *   GET  /v1/users/{username}/profile  (ProfileResponse)
 *   GET  /v1/users/{username}/history  (HistoryResponse)
 *   PATCH /v1/users/{username}         (UpdateProfileResponse)
 */
export function useProfile(): UseProfileReturn {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [glowUps, setGlowUps] = useState<GlowUpItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreGlowUps, setHasMoreGlowUps] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const glowUpCursorRef = useRef<string | null>(null);
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
        setGlowUps(historyData.entries);
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
        setGlowUps(historyData.entries);
        glowUpCursorRef.current = historyData.next_cursor;
        setHasMoreGlowUps(historyData.has_more);
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
        setGlowUps((prev) => [...prev, ...response.entries]);
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

  const updateProfile = useCallback(
    async (
      username: string,
      payload: UpdateProfilePayload,
    ): Promise<boolean> => {
      setIsUpdating(true);
      setUpdateError(null);

      try {
        const updated = await apiFetch<UpdateProfileResponse>(
          PROFILE_ENDPOINTS.UPDATE(username),
          {
            method: "PATCH",
            body: JSON.stringify(payload),
          },
        );
        // Merge the updated fields back into the current profile snapshot
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                username: updated.username,
                display_name: updated.display_name,
                avatar_url: updated.avatar_url,
                username_change_cooldown_remaining_seconds:
                  updated.username_change_cooldown_remaining_seconds ?? null,
              }
            : prev,
        );
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
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMoreGlowUps,
    error,
    isUpdating,
    updateError,
    loadProfile,
    refresh,
    loadMoreGlowUps,
    updateProfile,
  };
}
