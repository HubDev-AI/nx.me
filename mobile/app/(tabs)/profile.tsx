import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRouter } from "expo-router";

import { THEME } from "../../constants/theme";
import { TAB_BAR_HEIGHT } from "./_layout";
import { PageBackground } from "../../components/ui/PageBackground";
import { EmptyState } from "../../components/ui/EmptyState";
import { Caption } from "../../components/ui/Text";
import {
  AUTH_ENDPOINTS,
  DISMISS_ERRORED_JOB_BODY,
  DISMISS_ERRORED_JOB_CANCEL_LABEL,
  DISMISS_ERRORED_JOB_REMOVE_LABEL,
  DISMISS_ERRORED_JOB_TITLE,
  GLOWUP_ENDPOINTS,
  UNIVERSAL_LINK_ORIGIN,
} from "../../constants/config";
import { clearAllTokens } from "../../lib/auth";
import { apiFetch } from "../../lib/api";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { ProfileHeader } from "../../components/profile/ProfileHeader";
import { GlowUpGrid } from "../../components/profile/GlowUpGrid";
import { EditProfileSheet } from "../../components/profile/EditProfileSheet";
import { useProfile } from "../../components/profile/useProfile";
import { buildProfileMenu } from "../../components/profile/menu";
import { useRadialMenu } from "../../lib/radial-menu-context";
import { useCapabilities } from "../../lib/capabilities";
import { showToast } from "../../lib/toast";
import {
  ShareDialog,
  type ShareDialogJob,
} from "../../components/result/ShareDialog";
import { useShareComposite } from "../../components/result/ShareComposite";
import { saveJob, type JobResult } from "../../lib/analysis";
import type { SaveState } from "../../components/result/ResultActions";
import type { GlowUpItem, UpdateProfilePayload } from "../../components/profile/types";

/** Status values that surface as a dismissable errored cell on the grid. */
const ERRORED_STATUSES = new Set<string>(["failed", "cancelled"]);

/**
 * Statuses that open the Share & Publish / Delete action sheet on long-press.
 * Failed/cancelled cells have their own dismiss path (ERRORED_STATUSES).
 * Queued/processing/finalizing cells swallow long-press (no menu yet —
 * the user has to cancel the generation first before deleting).
 */
const LONG_PRESS_MENU_STATUS = "completed";

// Long-press action sheet copy on a completed cell.
const COMPLETED_MENU_TITLE = "Glow-up options";
const COMPLETED_MENU_SHARE_LABEL = "Share & Publish…";
const COMPLETED_MENU_SHARE_LABEL_NO_PUBLISH = "Share…";
const COMPLETED_MENU_DELETE_LABEL = "Delete";
const COMPLETED_MENU_CANCEL_LABEL = "Cancel";

// Delete-confirm copy — writer review blocker per plan §Unit 9 +
// feedback_female_user_targeting. Placeholder until writer pass lands.
// TODO(writer-review): delete confirm strings below.
const DELETE_CONFIRM_TITLE = "Delete this glow-up?";
const DELETE_CONFIRM_BODY =
  "Links you've already shared will stop working. This can't be undone.";
const DELETE_CONFIRM_LABEL = "Delete";
const DELETE_CONFIRM_CANCEL_LABEL = "Cancel";

// User-visible error strings. Centralized so toast + retry paths stay in sync.
const DELETE_ERROR_MESSAGE = "Couldn't delete — try again.";
const JOB_FETCH_ERROR_MESSAGE = "Couldn't open that glow-up — try again.";
const PUBLISH_ERROR_MESSAGE = "Couldn't publish — try again.";
const SAVE_ERROR_MESSAGE = "Couldn't save on profile. Try again.";
const SAVE_SUCCESS_MESSAGE = "Saved on your profile.";
const SHARE_SAVE_FAILED_MESSAGE = "Couldn't save — try again.";
const SHARE_COMPOSITE_TIMEOUT_MESSAGE =
  "Images didn't finish loading. Try again in a moment.";
const SHARE_RIGHT_LABEL = "Glow Up";

/**
 * Endpoint paths the long-press action sheet consumes. They live here
 * (not in constants/config.ts) so this unit stays confined to its
 * three-file scope; the matching backend-wide builders can move to
 * config.ts in a follow-up pass without changing behavior here.
 */
const JOB_DELETE_PATH = (jobId: string) => `/v1/jobs/${jobId}`;
const POSTS_CREATE_PATH = "/v1/posts";

/**
 * Request body for POST /v1/posts. Backend spec: `glow_up_job_id`
 * (required) + optional caption (deferred; no UI for captions yet).
 */
interface CreatePostRequest {
  glow_up_job_id: string;
}

/**
 * Subset of POST /v1/posts response we consume. The endpoint returns a
 * full PostResponse; we only need the post id + share hash to hydrate
 * the dialog's local `job.post_id` / `job.share_hash` after publish.
 */
interface CreatePostResponse {
  post_id: string;
  share_hash: string;
}

/**
 * Best-effort decode of an apiFetch error body. apiFetch throws an
 * `ApiError` with `.body` set to the raw response text; we try to
 * extract the `detail` field when present, falling back to a default
 * user-facing string.
 */
function messageForError(err: unknown, fallback: string): string {
  if (err && typeof err === "object" && "body" in err) {
    const body = (err as { body?: unknown }).body;
    if (typeof body === "string" && body.length > 0) {
      try {
        const parsed = JSON.parse(body) as { detail?: unknown };
        if (typeof parsed.detail === "string" && parsed.detail.length > 0) {
          return parsed.detail;
        }
      } catch {
        // Non-JSON body — fall through.
      }
    }
  }
  return fallback;
}

/**
 * Profile screen: shows user avatar, stats, glow-up history grid,
 * and edit profile sheet.
 */
export default function ProfileScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const toggleMenuRef = useRef<() => void>(() => {});
  const { username: authUsername, setSessionMode, setUsername: setAuthUsername } = useAuth();
  const caps = useCapabilities();
  const { theme } = useTheme();
  const radialMenu = useRadialMenu();
  const [editSheetVisible, setEditSheetVisible] = useState(false);

  // Share-dialog state. Parent owns visibility + the job snapshot so
  // the dialog can render before the server's post_id/share_hash land
  // from a fresh GET /v1/jobs/{id} poll.
  const [dialogVisible, setDialogVisible] = useState(false);
  const [dialogJob, setDialogJob] = useState<ShareDialogJob | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("pending");
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  /**
   * Client-only filter for cells the user just deleted but the server
   * hasn't re-pulled yet. A successful DELETE /v1/jobs/{id} is immediate
   * on the server, but the next `refresh()` is async — hiding the cell
   * optimistically prevents a stale thumbnail flash between the DELETE
   * and the follow-up /history response.
   */
  const [locallyDeletedJobIds, setLocallyDeletedJobIds] = useState<
    Set<string>
  >(() => new Set());

  // Offscreen composite view-shot helper for Share.
  const { ShareCompositeView, generateAndShare } = useShareComposite();

  const {
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
  } = useProfile();

  // Load profile once the session can view its own profile and the username
  // is known. Gated on canViewOwnProfile (not isUser) so guests with a valid
  // guest token in `auth_required=false` mode also fetch their data.
  useEffect(() => {
    if (caps.canViewOwnProfile && authUsername && profile === null) {
      loadProfile(authUsername);
    }
  }, [caps.canViewOwnProfile, authUsername, profile, loadProfile]);

  // Hide cells the user deleted this session until /history repulls.
  // Once the server-side row is gone the set's entries become no-ops
  // (filter.filter never matches). We never invalidate the set; a
  // fresh mount (or app relaunch) starts empty and the server is the
  // source of truth again.
  const visibleGlowUps = useMemo(
    () =>
      locallyDeletedJobIds.size === 0
        ? glowUps
        : glowUps.filter(
            (entry) =>
              entry.job_id === null || !locallyDeletedJobIds.has(entry.job_id),
          ),
    [glowUps, locallyDeletedJobIds],
  );

  const handleRefresh = useCallback(() => {
    if (profile) {
      refresh(profile.username);
    }
  }, [profile, refresh]);

  const handleLoadMoreGlowUps = useCallback(() => {
    if (profile) {
      loadMoreGlowUps(profile.username);
    }
  }, [profile, loadMoreGlowUps]);

  const handleEditProfile = useCallback(() => {
    setEditSheetVisible(true);
  }, []);

  const handleCloseEditSheet = useCallback(() => {
    setEditSheetVisible(false);
  }, []);

  const handleLogout = useCallback(async () => {
    // Best-effort server-side logout — always clear local tokens even on failure
    try {
      await apiFetch<void>(AUTH_ENDPOINTS.LOGOUT, { method: "POST" });
    } catch {
      // Network error or server unreachable — proceed with local logout
    }
    await clearAllTokens();
    setSessionMode("anon");
  }, [setSessionMode]);

  const handleSaveProfile = useCallback(
    async (payload: UpdateProfilePayload): Promise<boolean> => {
      if (!profile) return false;
      const success = await updateProfile(profile.username, payload);
      // Propagate username change to auth context so all subsequent
      // API calls and navigation use the new username.
      if (success && payload.new_username) {
        setAuthUsername(payload.new_username);
      }
      return success;
    },
    [profile, updateProfile, setAuthUsername],
  );

  const handleUploadAvatar = useCallback(
    async (uri: string): Promise<boolean> => {
      if (!profile) return false;
      return uploadAvatar(profile.username, uri);
    },
    [profile, uploadAvatar],
  );

  const handleSignIn = useCallback(() => {
    router.push("/(auth)/login");
  }, [router]);

  // Tap a glow-up cell → /result/[jobId]. The result screen renders the
  // right branch based on status (waiting / success / terminal-failure)
  // so a single destination covers pending, completed, and errored.
  const handleItemPress = useCallback(
    (item: GlowUpItem) => {
      if (!item.job_id) return; // Legacy row with no job — non-tappable.
      router.push(`/result/${item.job_id}`);
    },
    [router],
  );

  /**
   * Optimistically remove a cell from the grid after a successful DELETE.
   * The server row is already gone; this keeps the UI in sync until the
   * next /history refetch. Error paths clear the set so the cell reappears.
   */
  const markLocallyDeleted = useCallback((jobId: string) => {
    setLocallyDeletedJobIds((prev) => {
      if (prev.has(jobId)) return prev;
      const next = new Set(prev);
      next.add(jobId);
      return next;
    });
  }, []);

  const unmarkLocallyDeleted = useCallback((jobId: string) => {
    setLocallyDeletedJobIds((prev) => {
      if (!prev.has(jobId)) return prev;
      const next = new Set(prev);
      next.delete(jobId);
      return next;
    });
  }, []);

  /**
   * Issue DELETE /v1/jobs/{id} with optimistic removal + rollback on
   * failure. Backend returns 204 idempotently (missing row + wrong
   * owner); any non-2xx is treated as a retryable error surfaced via
   * toast.
   */
  const handleDeleteGlowup = useCallback(
    async (jobId: string) => {
      // Optimistic: hide the cell first so the user sees immediate
      // feedback while the DELETE is in flight.
      markLocallyDeleted(jobId);
      try {
        await apiFetch<void>(JOB_DELETE_PATH(jobId), { method: "DELETE" });
        // Refresh to resync the server-authoritative /history list —
        // drops the locally-filtered row from the underlying array.
        if (profile) {
          await refresh(profile.username);
        }
      } catch (err) {
        // Rollback — server still has the row, so the cell must reappear.
        unmarkLocallyDeleted(jobId);
        showToast({
          kind: "error",
          message: messageForError(err, DELETE_ERROR_MESSAGE),
        });
      }
    },
    [markLocallyDeleted, unmarkLocallyDeleted, profile, refresh],
  );

  /**
   * Confirm-then-delete flow. Second Alert.alert matches the existing
   * DISMISS_ERRORED_JOB_* pattern on failed/cancelled cells so the UX
   * reads the same across the grid.
   */
  const promptDeleteGlowup = useCallback(
    (jobId: string) => {
      Alert.alert(DELETE_CONFIRM_TITLE, DELETE_CONFIRM_BODY, [
        { text: DELETE_CONFIRM_CANCEL_LABEL, style: "cancel" },
        {
          text: DELETE_CONFIRM_LABEL,
          style: "destructive",
          onPress: () => {
            void handleDeleteGlowup(jobId);
          },
        },
      ]);
    },
    [handleDeleteGlowup],
  );

  /**
   * Open the ShareDialog for a completed cell. Fetches fresh
   * post_id/share_hash via GET /v1/jobs/{id} (Unit 3 response shape) so
   * the dialog starts with authoritative state — the /history row only
   * carries saved_at, not post state.
   */
  const openShareDialogForJob = useCallback(async (item: GlowUpItem) => {
    if (!item.job_id) return;
    const jobId = item.job_id;
    try {
      const job = await apiFetch<JobResult>(
        GLOWUP_ENDPOINTS.JOB_STATUS(jobId),
      );
      setDialogJob({
        id: jobId,
        saved_at: job.saved_at,
        post_id: job.post_id ?? null,
        share_hash: job.share_hash ?? null,
      });
      setSaveState(job.saved_at ? "saved" : "pending");
      setPublishError(null);
      setIsPublishing(false);
      setDialogVisible(true);
    } catch (err) {
      showToast({
        kind: "error",
        message: messageForError(err, JOB_FETCH_ERROR_MESSAGE),
      });
    }
  }, []);

  /**
   * Long-press dispatch by status.
   *
   *   completed  → action sheet: Share & Publish… | Delete | Cancel
   *   failed     → existing DISMISS_ERRORED_JOB_* dismiss menu
   *   cancelled  → existing DISMISS_ERRORED_JOB_* dismiss menu
   *   queued     → no-op (user must cancel the generation first)
   *   processing → no-op
   *   finalizing → no-op
   */
  const handleItemLongPress = useCallback(
    (item: GlowUpItem) => {
      if (!item.job_id) return;

      // Failed / cancelled → existing dismiss alert.
      if (ERRORED_STATUSES.has(item.status)) {
        const dismissedJobId = item.job_id;
        Alert.alert(
          DISMISS_ERRORED_JOB_TITLE,
          DISMISS_ERRORED_JOB_BODY,
          [
            { text: DISMISS_ERRORED_JOB_CANCEL_LABEL, style: "cancel" },
            {
              text: DISMISS_ERRORED_JOB_REMOVE_LABEL,
              style: "destructive",
              onPress: () => dismissErroredItem(dismissedJobId),
            },
          ],
        );
        return;
      }

      // In-progress cells swallow the gesture — no menu until the
      // backend delete path accepts non-terminal statuses.
      if (item.status !== LONG_PRESS_MENU_STATUS) return;

      const shareLabel = caps.canPublishGlowup
        ? COMPLETED_MENU_SHARE_LABEL
        : COMPLETED_MENU_SHARE_LABEL_NO_PUBLISH;
      const jobId = item.job_id;
      Alert.alert(COMPLETED_MENU_TITLE, undefined, [
        {
          text: shareLabel,
          onPress: () => {
            void openShareDialogForJob(item);
          },
        },
        {
          text: COMPLETED_MENU_DELETE_LABEL,
          style: "destructive",
          onPress: () => promptDeleteGlowup(jobId),
        },
        { text: COMPLETED_MENU_CANCEL_LABEL, style: "cancel" },
      ]);
    },
    [
      caps.canPublishGlowup,
      dismissErroredItem,
      openShareDialogForJob,
      promptDeleteGlowup,
    ],
  );

  // --- Share-dialog handlers ------------------------------------------------

  const handleCloseDialog = useCallback(() => {
    setDialogVisible(false);
  }, []);

  /**
   * Save row — fires POST /v1/jobs/{id}/save and updates the dialog's
   * local job so the row disappears on the next render (Save row is
   * gated on `saved_at === null`).
   */
  const handleDialogSave = useCallback(async () => {
    if (!dialogJob) return;
    if (saveState !== "pending") return;
    setSaveState("saving");
    try {
      const { saved_at } = await saveJob(dialogJob.id);
      setSaveState("saved");
      setDialogJob((prev) => (prev ? { ...prev, saved_at } : prev));
      showToast({ kind: "success", message: SAVE_SUCCESS_MESSAGE });
      // Refresh so the grid's saved badge hydrates from the server.
      if (profile) {
        void refresh(profile.username);
      }
    } catch (err) {
      setSaveState("pending");
      showToast({
        kind: "error",
        message: messageForError(err, SAVE_ERROR_MESSAGE),
      });
    }
  }, [dialogJob, saveState, profile, refresh]);

  /**
   * Share row — blocking auto-save (per R8). If `saved_at` is null we
   * must save first; any failure there surfaces in the dialog and
   * does NOT proceed to the native share sheet (otherwise we'd leak
   * a link to a job retention will purge). Then assemble the card-web
   * URL from (post_id, share_hash) and hand off to useShareComposite.
   */
  const handleDialogShare = useCallback(async () => {
    if (!dialogJob) return;
    // Need both images to compose the share sheet; guard against a
    // pre-image-URL state so the user sees the save toast error
    // rather than a silent no-op.
    let job: ShareDialogJob = dialogJob;
    if (job.saved_at === null) {
      setSaveState("saving");
      try {
        const { saved_at } = await saveJob(job.id);
        job = { ...job, saved_at };
        setDialogJob(job);
        setSaveState("saved");
      } catch (err) {
        setSaveState("pending");
        showToast({
          kind: "error",
          message: messageForError(err, SHARE_SAVE_FAILED_MESSAGE),
        });
        return;
      }
    }

    // Re-fetch so the composite has before/after URLs — the dialog job
    // shape doesn't carry them.
    let jobDetail: JobResult;
    try {
      jobDetail = await apiFetch<JobResult>(
        GLOWUP_ENDPOINTS.JOB_STATUS(job.id),
      );
    } catch (err) {
      showToast({
        kind: "error",
        message: messageForError(err, JOB_FETCH_ERROR_MESSAGE),
      });
      return;
    }
    if (!jobDetail.before_image_url || !jobDetail.after_image_url) {
      showToast({ kind: "error", message: SHARE_COMPOSITE_TIMEOUT_MESSAGE });
      return;
    }

    const shareUrl =
      job.post_id && job.share_hash && profile?.username
        ? `${UNIVERSAL_LINK_ORIGIN}/${profile.username}/glow-up/${job.share_hash}`
        : undefined;

    // Close the dialog BEFORE handing off to the native share sheet so
    // the modal scrim doesn't sit under the native share picker.
    setDialogVisible(false);
    try {
      await generateAndShare({
        beforeUrl: jobDetail.before_image_url,
        afterUrl: jobDetail.after_image_url,
        rightLabel: SHARE_RIGHT_LABEL,
        shareUrl,
        shareMessage: shareUrl ? `My NXME glow-up — ${shareUrl}` : undefined,
      });
    } catch (err) {
      if (err instanceof Error && err.message.includes("timeout")) {
        showToast({ kind: "error", message: SHARE_COMPOSITE_TIMEOUT_MESSAGE });
      }
      // User-cancelled native share sheet — not an error.
    }
  }, [dialogJob, profile, generateAndShare]);

  /**
   * Publish row — POST /v1/posts (idempotent per Unit 2). On success
   * merge the new post_id + share_hash into the dialog's local job and
   * close. Failures stay in the dialog so the user can retry without
   * re-opening it.
   */
  const handleDialogPublish = useCallback(async () => {
    if (!dialogJob) return;
    if (isPublishing) return;
    setIsPublishing(true);
    setPublishError(null);
    try {
      const body: CreatePostRequest = { glow_up_job_id: dialogJob.id };
      const post = await apiFetch<CreatePostResponse>(POSTS_CREATE_PATH, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setDialogJob((prev) =>
        prev
          ? { ...prev, post_id: post.post_id, share_hash: post.share_hash }
          : prev,
      );
      setDialogVisible(false);
      if (profile) {
        void refresh(profile.username);
      }
    } catch (err) {
      setPublishError(messageForError(err, PUBLISH_ERROR_MESSAGE));
    } finally {
      setIsPublishing(false);
    }
  }, [dialogJob, isPublishing, profile, refresh]);

  // Menu items derive from capabilities — single source of truth keeps this
  // screen and any future profile actions in sync with the (features × session)
  // matrix in mobile/lib/capabilities.ts.
  const menuItems = buildProfileMenu(caps, {
    onEditProfile: handleEditProfile,
    onOpenSubscription: () => router.push("/subscription"),
    onOpenSettings: () => router.push("/settings"),
    onLogout: handleLogout,
    onSignIn: handleSignIn,
  });

  // Keep ref in sync so headerRight button can call it
  toggleMenuRef.current = () => radialMenu.open(menuItems);

  // Put 3-dot button in the actual navigation header
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={() => toggleMenuRef.current?.()}
          style={{ padding: THEME.spacing.sm, marginRight: THEME.spacing.sm }}
          accessibilityLabel="More options"
          accessibilityRole="button"
          hitSlop={8}
        >
          <Ionicons name="ellipsis-horizontal" size={20} color={THEME.colors.textSecondary} />
        </Pressable>
      ),
    });
  }, [navigation]);

  // No profile to show (anon, or impossible-state guest with auth_required=true)
  // — render a centered sign-in CTA. The RadialMenu is mounted globally via
  // RadialMenuProvider, so we only call `open(menuItems)` from the 3-dot
  // button; no local rendering needed.
  if (!caps.canViewOwnProfile) {
    const title = "Sign in to see your profile";
    const subtitle = "Track your glow-ups and reactions";
    return (
      <View style={styles.emptyStateScreen}>
        <PageBackground overlayOpacity={0.85} />
        <EmptyState
          icon="person-circle-outline"
          title={title}
          description={subtitle}
          action={
            caps.canSignIn
              ? {
                  label: "Sign In",
                  onPress: handleSignIn,
                  accessibilityLabel: "Sign in",
                }
              : undefined
          }
        />
      </View>
    );
  }

  // Authenticated but username not yet resolved — surface Log out as the
  // primary recovery action so the button matches the rest of the app's
  // design (same primary-button shape as "Try Again" on error states).
  if (!authUsername) {
    return (
      <View style={styles.emptyStateScreen}>
        <EmptyState
          icon="person-circle-outline"
          title="Complete your profile"
          description="We couldn't determine your username. Please log out and sign in again, or register a new account."
          action={
            caps.canSignOut
              ? {
                  label: "Log out",
                  onPress: handleLogout,
                  accessibilityLabel: "Log out",
                }
              : undefined
          }
        />
      </View>
    );
  }

  // Loading profile
  if (isLoading && !profile) {
    return (
      <View style={styles.emptyStateLoading}>
        <ActivityIndicator size="large" color={theme.accent} />
        <Caption color="secondary" style={styles.loadingText}>
          Loading profile...
        </Caption>
      </View>
    );
  }

  // Error state — prefer Retry if we have a username to retry with,
  // otherwise fall back to Log out (both actions rendered as the standard
  // primary button via EmptyState's action prop).
  if (error && !profile) {
    const errorAction = authUsername
      ? {
          label: "Retry",
          onPress: () => loadProfile(authUsername),
          accessibilityLabel: "Retry loading profile",
        }
      : caps.canSignOut
        ? {
            label: "Log out",
            onPress: handleLogout,
            accessibilityLabel: "Log out",
          }
        : undefined;
    return (
      <View style={styles.emptyStateScreen}>
        <EmptyState
          icon="alert-circle-outline"
          title="Something went wrong"
          description={error}
          action={errorAction}
        />
      </View>
    );
  }

  if (!profile) return null;

  const profileHeader = (
    <ProfileHeader
      profile={profile}
      onEditProfile={handleEditProfile}
      showStats={caps.canSeeFeed}
      showShareProfile={caps.canShareProfile}
    />
  );

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.85} />
      {/* Radial menu — button is in headerRight, menu renders here */}
      {/* Single FlatList: profile header + glow-up grid -- no nested ScrollView */}
      <GlowUpGrid
        items={visibleGlowUps}
        isLoadingMore={isLoadingMore}
        hasMore={hasMoreGlowUps}
        onLoadMore={handleLoadMoreGlowUps}
        onItemPress={handleItemPress}
        onItemLongPress={handleItemLongPress}
        onJobResolved={reconcileWithJob}
        ListHeaderComponent={profileHeader}
        refreshing={isRefreshing}
        onRefresh={handleRefresh}
      />

      {/* Edit Profile sheet */}
      <EditProfileSheet
        visible={editSheetVisible}
        profile={profile}
        isUpdating={isUpdating}
        updateError={updateError}
        onSave={handleSaveProfile}
        onUploadAvatar={handleUploadAvatar}
        onClose={handleCloseEditSheet}
      />

      {/* Share / Publish / Save dialog — opened from long-press on a
          completed cell. Parent owns the job snapshot + dialog state; the
          dialog reads only visibility rules off its props + useCapabilities. */}
      {dialogJob ? (
        <ShareDialog
          visible={dialogVisible}
          onClose={handleCloseDialog}
          job={dialogJob}
          onSave={() => {
            void handleDialogSave();
          }}
          onShare={() => {
            void handleDialogShare();
          }}
          onPublish={() => {
            void handleDialogPublish();
          }}
          saveState={saveState}
          isPublishing={isPublishing}
          publishError={publishError}
        />
      ) : null}

      {/* Offscreen view-shot target — must be in the tree while Share
          runs. Cheap when unused (renders nothing until Share params
          are populated). */}
      {ShareCompositeView}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  /* Shared wrapper for every non-populated Profile state (signed-out,
     username-missing, error). EmptyState (center={true}) does the
     centering; the wrapper just bounds the empty region to the screen
     minus the floating tab bar, matching the Feed / Advisor rhythm. */
  emptyStateScreen: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    paddingBottom: TAB_BAR_HEIGHT,
  },
  /* Loading variant renders an ActivityIndicator + caption pair instead
     of EmptyState, so it does its own centering here. */
  emptyStateLoading: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    paddingBottom: TAB_BAR_HEIGHT,
  },
  loadingText: {
    marginTop: THEME.spacing.md,
  },
});
