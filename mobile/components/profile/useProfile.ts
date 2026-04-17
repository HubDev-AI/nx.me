import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import { PROFILE_ENDPOINTS, PROFILE_CONFIG } from "../../constants/config";
import {
  addDismissedJobId,
  getDismissedJobIdsSync,
  loadDismissedJobIds,
} from "../../lib/dismissed-jobs-store";
import type { JobResult } from "../../lib/analysis";
import type {
  UserProfile,
  GlowUpItem,
  GlowUpHistoryResponse,
  UpdateProfilePayload,
  UpdateProfileResponse,
} from "./types";

/**
 * React Native FormData file descriptor. RN's `FormData.append` accepts
 * `{ uri, name, type }` where the DOM typings only allow `Blob | string`;
 * cast at the single append site per the official RN pattern.
 *
 * Mirrors the shape `lib/analysis.ts` uses for selfie uploads so both
 * multipart flows share the same reference point.
 */
interface RNFileDescriptor {
  uri: string;
  name: string;
  type: string;
}

/**
 * Infer the file extension + MIME type from an ImagePicker URI.
 *
 * Backend accepts image/jpeg, image/png, and image/webp for avatars
 * (see app/api/users.py _AVATAR_MIME_TO_EXT). Anything else defaults to
 * jpeg — the request will fail cleanly server-side with a 400 rather
 * than silently producing an un-typed upload.
 */
function fileDescriptorFromUri(uri: string): RNFileDescriptor {
  const lower = uri.toLowerCase();
  let ext = "jpg";
  let type = "image/jpeg";
  if (lower.endsWith(".png")) {
    ext = "png";
    type = "image/png";
  } else if (lower.endsWith(".webp")) {
    ext = "webp";
    type = "image/webp";
  } else if (lower.endsWith(".jpeg")) {
    ext = "jpeg";
    type = "image/jpeg";
  }
  return { uri, name: `avatar.${ext}`, type };
}

/**
 * Filter out items the user has explicitly dismissed via long-press →
 * "Remove from profile". Server still returns the row (audit trail);
 * this is the client-side suppression layer.
 */
function filterDismissed(
  entries: GlowUpItem[],
  dismissed: ReadonlySet<string>,
): GlowUpItem[] {
  if (dismissed.size === 0) return entries;
  return entries.filter(
    (entry) => entry.job_id === null || !dismissed.has(entry.job_id),
  );
}

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
  /**
   * Upload a new avatar image (multipart) and merge the server's refreshed
   * profile row into local state. Caller passes the local file URI from
   * expo-image-picker; the hook handles FormData + the POST.
   */
  uploadAvatar: (username: string, uri: string) => Promise<boolean>;
  /**
   * Remove an errored cell from the local grid + persist the dismissal
   * to AsyncStorage. The next /history refetch will skip the row.
   */
  dismissErroredItem: (jobId: string) => void;
  /**
   * Reconcile a single GET /v1/jobs/{id} poll result back into the
   * grid. PendingGlowUpCell calls this when its observer sees an
   * update; the row's status, after_image_url, and before_image_url
   * are updated in place. No-op for items not currently in glowUps.
   */
  reconcileWithJob: (jobId: string, result: JobResult) => void;
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

  // Hydrate the dismissed-set on mount so the very first /history
  // response is filtered correctly. The store keeps a singleton in-memory
  // mirror — repeated mounts hit cache after the first call.
  useEffect(() => {
    void loadDismissedJobIds();
  }, []);

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

        const dismissed = await loadDismissedJobIds();
        setProfile(profileData);
        setGlowUps(filterDismissed(historyData.entries, dismissed));
        glowUpCursorRef.current = historyData.next_cursor;
        setHasMoreGlowUps(historyData.has_more);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "We couldn't load this profile.",
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

        const dismissed = await loadDismissedJobIds();
        setProfile(profileData);
        setGlowUps(filterDismissed(historyData.entries, dismissed));
        glowUpCursorRef.current = historyData.next_cursor;
        setHasMoreGlowUps(historyData.has_more);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "We couldn't refresh this profile.",
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
        const dismissed = getDismissedJobIdsSync();
        setGlowUps((prev) => [
          ...prev,
          ...filterDismissed(response.entries, dismissed),
        ]);
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

  const dismissErroredItem = useCallback((jobId: string) => {
    // Update the in-memory cache + persist; render flips on the next
    // setGlowUps tick.
    void addDismissedJobId(jobId);
    setGlowUps((prev) => prev.filter((entry) => entry.job_id !== jobId));
  }, []);

  const reconcileWithJob = useCallback(
    (jobId: string, result: JobResult) => {
      setGlowUps((prev) => {
        let touched = false;
        const next = prev.map((entry) => {
          if (entry.job_id !== jobId) return entry;
          if (
            entry.status === result.status &&
            entry.after_image_url === result.after_image_url &&
            entry.before_image_url === result.before_image_url &&
            entry.saved_at === result.saved_at
          ) {
            return entry;
          }
          touched = true;
          return {
            ...entry,
            status: result.status,
            after_image_url:
              result.after_image_url ?? entry.after_image_url,
            before_image_url:
              result.before_image_url ?? entry.before_image_url,
            // saved_at is authoritative from the server; use the new
            // value directly so an admin-side clear also propagates
            // down to the grid.
            saved_at: result.saved_at,
          };
        });
        return touched ? next : prev;
      });
    },
    [],
  );

  // Shared merge of UpdateProfileResponse into the local profile snapshot.
  // Both PATCH and the avatar POST return the same shape, so they both
  // collapse the whole response into the hook's cached profile row.
  const mergeUpdateResponse = useCallback(
    (updated: UpdateProfileResponse) => {
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
    },
    [],
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
        mergeUpdateResponse(updated);
        return true;
      } catch (err) {
        setUpdateError(
          err instanceof Error ? err.message : "We couldn't save those changes.",
        );
        return false;
      } finally {
        setIsUpdating(false);
      }
    },
    [mergeUpdateResponse],
  );

  const uploadAvatar = useCallback(
    async (username: string, uri: string): Promise<boolean> => {
      setIsUpdating(true);
      setUpdateError(null);

      try {
        const file = fileDescriptorFromUri(uri);
        const formData = new FormData();
        // RN's FormData.append signature omits the file-descriptor shape,
        // but it's the officially sanctioned RN pattern — cast at the one
        // append site that needs it. See
        // https://reactnative.dev/docs/network#uploading-files.
        formData.append("file", file as unknown as Blob);

        const updated = await apiFetch<UpdateProfileResponse>(
          PROFILE_ENDPOINTS.AVATAR(username),
          { method: "POST", body: formData },
        );
        mergeUpdateResponse(updated);
        return true;
      } catch (err) {
        setUpdateError(
          err instanceof Error ? err.message : "We couldn't upload that photo.",
        );
        return false;
      } finally {
        setIsUpdating(false);
      }
    },
    [mergeUpdateResponse],
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
    uploadAvatar,
    dismissErroredItem,
    reconcileWithJob,
  };
}
