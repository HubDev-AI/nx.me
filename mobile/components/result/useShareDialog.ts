/**
 * useShareDialog — consolidated Save / Share / Publish handler logic for
 * the bottom-sheet `ShareDialog` (see `./ShareDialog.tsx`).
 *
 * Consumed by:
 *   - `app/result/[jobId].tsx`    → the result screen's dialog entry.
 *   - `app/(tabs)/profile.tsx`    → long-press on a completed cell.
 *
 * Both screens used to hold near-identical copies of these handlers, with
 * the same R5/R8 blocking-auto-save invariant on Share. This hook
 * centralizes the invariant so a future regression in one screen can't
 * silently re-diverge from the other.
 *
 * State ownership:
 *   - Hook owns `saveState` / `isPublishing` / `publishError` and exposes
 *     them read-only + a `resetPublishError` for the re-open path.
 *   - Parent owns `job` + visibility. It applies any patch via the
 *     optional `onSaveSuccess` / `onPublishSuccess` callbacks (result
 *     mirrors `post_id` + `share_hash` into a local ref; profile patches
 *     its `dialogJob` state).
 *   - Parent owns dialog close via `onDialogClose`, which the hook
 *     invokes BEFORE handing off to the native share sheet (otherwise the
 *     modal scrim sits under the native picker — the result screen used
 *     to close AFTER the sheet; this hook matches profile's behavior).
 *
 * Design decisions (see the advisor thread on PR #167 follow-up):
 *   - `getImageUrls` is a callback, not a hook-internal fetch, so the
 *     result screen can pass through its already-cached `jobQuery.data`
 *     while profile does its own `GET /v1/jobs/{id}` (the /history list
 *     row doesn't carry image URLs).
 *   - `saveJobFn` is a parent-supplied callback for the same reason
 *     (P3d unification): standalone Save (`handleSave`) and the blocking
 *     auto-save on Share (`handleShare`) both route through it, so each
 *     screen can layer its own mutation / cache-invalidation behaviour
 *     (result: `queryClient.invalidateQueries(["job", id])`; profile:
 *     `refresh(profile.username)` via `onSaveSuccess`) without the hook
 *     hitting `saveJob` behind the cache. Every save surface shares one
 *     codepath — no silent divergence between dialog-initiated and
 *     primary-button saves.
 *   - Error messages route through `parseApiError` (the project
 *     standard in `mobile/lib/errors.ts`). This is a minor behavior
 *     change on profile: server-side `detail` strings now flatten to the
 *     generic status-bucket copy, trading verbatim backend messages for
 *     consistency across the app.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import { parseApiError } from "../../lib/errors";
import { showToast } from "../../lib/toast";
import { UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import type { JobSaveResponse } from "../../lib/analysis";
import type { SaveState } from "./ResultActions";
import type { ShareDialogJob } from "./ShareDialog";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** POST /v1/posts endpoint (publish a completed glow-up). */
const POSTS_CREATE_PATH = "/v1/posts";

/** Right-side composite label — matches ResultActions + profile long-press. */
const SHARE_RIGHT_LABEL = "Glow Up";

/** Toast copy — sourced once so both consumers show identical strings. */
const SAVE_SUCCESS_MESSAGE = "Saved on your profile.";
const SHARE_COMPOSITE_TIMEOUT_MESSAGE =
  "Images didn't finish loading. Try again in a moment.";

/**
 * Toast copy for the Share-path blocking-auto-save timeout. Distinct
 * from the composite-timeout copy because the failure mode is
 * different: this one is a stalled network saving the job, not a slow
 * image fetch for the share composite.
 */
const SAVE_TIMEOUT_MESSAGE = "Save timed out — try again.";

/**
 * Upper bound on how long `handleShare` will block waiting for the
 * auto-save (POST /v1/jobs/{id}/save) before giving up. Keeps the
 * Share row from hanging indefinitely on a slow network. Chosen at 15s
 * to comfortably exceed the p99 save latency while still giving the
 * user a timely error affordance.
 */
const SAVE_TIMEOUT_MS = 15_000;

/** Prose shared alongside the image when a live hash URL exists. */
const SHARE_MESSAGE_WITH_URL = (url: string): string =>
  `My NXME glow-up — ${url}`;

/** Hash-URL builder — `/{username}/glow-up/{share_hash}` per R5. */
const HASH_URL_SEGMENT = "glow-up";

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/** Sentinel thrown from the `handleShare` save-timeout race. */
class SaveTimeoutError extends Error {
  constructor() {
    super("save timeout");
    this.name = "SaveTimeoutError";
  }
}

/**
 * Race `promise` against a timer for `timeoutMs`. Resolves with the
 * promise's value if it settles first; rejects with `SaveTimeoutError`
 * if the timer fires first. The timer is always cleared in the
 * resolve branch so a late win can't surface a stray error after the
 * share sheet has already opened.
 */
function raceWithTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
): Promise<T> {
  let timerId: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timerId = setTimeout(() => reject(new SaveTimeoutError()), timeoutMs);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timerId !== undefined) clearTimeout(timerId);
  });
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Inputs expected by `useShareComposite().generateAndShare`. Duplicated
 * here (rather than imported) so the hook stays decoupled from the
 * composite's module shape — the parent owns the composite.
 */
export interface GenerateAndShareParams {
  beforeUrl: string;
  afterUrl: string;
  rightLabel: string;
  shareUrl?: string;
  shareMessage?: string;
}

export interface ImageUrlPair {
  before: string | null;
  after: string | null;
}

/** POST /v1/posts response — only the fields this hook consumes. */
interface PostCreateResponse {
  post_id: string;
  share_hash: string;
}

/** POST /v1/posts request body — mirrors backend `CreatePostRequest`. */
interface CreatePostRequest {
  glow_up_job_id: string;
}

export interface UseShareDialogOptions {
  /**
   * Current dialog job snapshot. May be null when the dialog is closed.
   * Handlers no-op on null to keep call-site wiring simple.
   */
  job: ShareDialogJob | null;
  /**
   * Current viewer's username. Used to build the hash share URL. When
   * null we skip the URL entirely (R5: never hand a bare `/{username}`
   * link that would 404).
   */
  username: string | null;
  /**
   * Share composite handle. Always the `generateAndShare` returned by
   * `useShareComposite()` — parent owns the hook so the composite view
   * can stay mounted in the parent's tree.
   */
  generateAndShare: (params: GenerateAndShareParams) => Promise<void>;
  /**
   * Pulls the before/after image URLs for the current job. Called once
   * per Share path. Returns nulls when URLs are not yet available; the
   * hook surfaces a toast and aborts without firing the native sheet.
   */
  getImageUrls: () => Promise<ImageUrlPair>;
  /**
   * Closes the dialog. Invoked BEFORE the native share sheet opens so
   * the modal scrim doesn't sit under the picker, and on Publish
   * success.
   */
  onDialogClose: () => void;
  /**
   * Persists the job to the viewer's profile. Parent-supplied so each
   * screen can route the call through its own TanStack Query mutation
   * (and its cache-invalidation side effects) instead of the hook
   * firing the raw `saveJob` endpoint behind the query cache's back.
   *
   * Single save codepath: standalone Save (`handleSave`) and the
   * blocking auto-save on the Share path (`handleShare`) both go
   * through this opt so every save surface benefits from the same
   * invalidation behaviour. The response shape matches `saveJob`'s —
   * the hook only reads `saved_at`.
   */
  saveJobFn: (jobId: string) => Promise<JobSaveResponse>;
  /**
   * Fires after a successful save (either standalone Save or
   * auto-save-then-share). Receives the fresh `saved_at` timestamp so
   * the parent can merge it into its job snapshot.
   */
  onSaveSuccess?: (saved_at: string) => void;
  /**
   * Fires after a successful publish. Receives the new `post_id` +
   * `share_hash` so the parent can merge them into its job snapshot.
   */
  onPublishSuccess?: (post_id: string, share_hash: string) => void;
}

export interface UseShareDialogReturn {
  /** Save-row flight state. Mirrors the ShareDialog prop. */
  saveState: SaveState;
  /** Publish-confirm in-flight flag. Mirrors the ShareDialog prop. */
  isPublishing: boolean;
  /**
   * Inline error surfaced on the Publish confirm panel. Null when no
   * publish has failed since the last reset.
   */
  publishError: string | null;
  /** Save row handler — POST /v1/jobs/{id}/save. */
  handleSave: () => Promise<void>;
  /**
   * Share row handler — R5/R8 blocking auto-save then native share.
   * Save failure aborts share; sheet timeouts surface a toast.
   */
  handleShare: () => Promise<void>;
  /** Publish confirm handler — POST /v1/posts. */
  handlePublish: () => Promise<void>;
  /** Clears the inline publish error (call on dialog re-open). */
  resetPublishError: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useShareDialog(
  opts: UseShareDialogOptions,
): UseShareDialogReturn {
  const {
    job,
    username,
    generateAndShare,
    getImageUrls,
    onDialogClose,
    saveJobFn,
    onSaveSuccess,
    onPublishSuccess,
  } = opts;

  const [saveState, setSaveState] = useState<SaveState>(
    job?.saved_at ? "saved" : "pending",
  );
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  // Sync saveState with job.saved_at when the parent swaps jobs or
  // server state hydrates asynchronously. Covers:
  //   - Profile opens the dialog for a different cell — previous
  //     `saved` flag must not leak across jobs.
  //   - Result screen hydrates `saved_at` from a background poll after
  //     the dialog has already mounted.
  // We only promote pending→saved; "saving" stays until the handler
  // resolves so a poll can't flip the row mid-request.
  const jobId = job?.id ?? null;
  const savedAt = job?.saved_at ?? null;
  useEffect(() => {
    setSaveState((prev) => {
      if (savedAt !== null) return "saved";
      // New job without saved_at — reset from a prior "saved" flag so
      // the Save row re-appears. Don't clobber an in-flight "saving".
      if (prev === "saved") return "pending";
      return prev;
    });
  }, [jobId, savedAt]);

  const resetPublishError = useCallback(() => {
    setPublishError(null);
  }, []);

  // ---- Save -----------------------------------------------------------
  //
  // POST /v1/jobs/{id}/save via parent-supplied `saveJobFn`. On success
  // fire `onSaveSuccess(saved_at)` so the parent can merge the fresh
  // timestamp into its job snapshot (otherwise the Save row wouldn't
  // disappear on the next render — ShareDialog gates it on
  // `job.saved_at === null`).
  //
  // `saveJobFn` is parent-supplied so the screen can route the call
  // through its own mutation/cache-invalidation wrapper instead of the
  // hook hitting the raw endpoint behind the query cache's back. Both
  // this standalone Save and the blocking auto-save on Share (below)
  // funnel through the same opt — one save codepath.
  const handleSave = useCallback(async () => {
    if (!job) return;
    if (saveState !== "pending") return;
    setSaveState("saving");
    try {
      const { saved_at } = await saveJobFn(job.id);
      setSaveState("saved");
      onSaveSuccess?.(saved_at);
      showToast({ kind: "success", message: SAVE_SUCCESS_MESSAGE });
    } catch (err) {
      setSaveState("pending");
      const app = parseApiError(err);
      showToast({ kind: "error", message: app.message });
    }
  }, [job, saveState, saveJobFn, onSaveSuccess]);

  // Re-entry guard for `handleShare` — mirrors `isPublishing` but lives
  // in a ref so the in-flight flag doesn't churn a re-render. A rapid
  // double-tap on Share during the blocking auto-save (Step 1 below)
  // must not fire `saveJob` twice; the ref is set before the first
  // async hop and cleared in the trailing finally so every exit path
  // (success, abort, thrown) releases it.
  const isSharingRef = useRef<boolean>(false);

  // ---- Share ----------------------------------------------------------
  //
  // R5/R8 critical path. Auto-save is BLOCKING: on failure we surface a
  // toast and do NOT open the native sheet (otherwise we'd leak a
  // card-web URL that retention will purge within days). The auto-save
  // is additionally raced against SAVE_TIMEOUT_MS so a stalled network
  // can't hang the Share row indefinitely — timeout surfaces the same
  // "abort share" branch as a save-failure.
  const handleShare = useCallback(async () => {
    if (!job) return;
    if (isSharingRef.current) return; // Re-entry guard — no double-submit.
    isSharingRef.current = true;
    try {
      // Step 1 — block on auto-save when the job isn't saved yet (R8).
      // Wrapped in `raceWithTimeout` so a slow network can't hang the
      // Share row forever; on either failure or timeout we MUST abort
      // and never open the native sheet. Routes through `saveJobFn`
      // so the Share auto-save benefits from the same invalidation
      // wiring as the standalone Save path.
      if (job.saved_at === null) {
        setSaveState("saving");
        try {
          const { saved_at } = await raceWithTimeout(
            saveJobFn(job.id),
            SAVE_TIMEOUT_MS,
          );
          setSaveState("saved");
          onSaveSuccess?.(saved_at);
        } catch (err) {
          setSaveState("pending");
          // Timeout uses its own copy; other failures flow through the
          // project-standard error bucket so server-side `detail`
          // strings get normalised consistently with the rest of the app.
          if (err instanceof SaveTimeoutError) {
            showToast({ kind: "error", message: SAVE_TIMEOUT_MESSAGE });
          } else {
            const app = parseApiError(err);
            showToast({ kind: "error", message: app.message });
          }
          return; // Abort — do NOT open the sheet on save failure/timeout.
        }
      }

      // Step 2 — fetch image URLs. Parent decides whether this reads from
      // a cached query (result) or fires a fresh GET (profile).
      let images: ImageUrlPair;
      try {
        images = await getImageUrls();
      } catch (err) {
        const app = parseApiError(err);
        showToast({ kind: "error", message: app.message });
        return;
      }
      if (!images.before || !images.after) {
        showToast({ kind: "error", message: SHARE_COMPOSITE_TIMEOUT_MESSAGE });
        return;
      }

      // Step 3 — build the share URL. Only when a live post exists AND we
      // know the viewer's username. Bare `/{username}` is forbidden per R5.
      const shareUrl =
        job.post_id && job.share_hash && username
          ? `${UNIVERSAL_LINK_ORIGIN}/${username}/${HASH_URL_SEGMENT}/${job.share_hash}`
          : undefined;

      // Step 4 — close dialog BEFORE the native sheet so the modal scrim
      // doesn't stack under the picker. This is a behavior change on the
      // result screen (previously closed after), intentionally adopted
      // from profile for UX consistency.
      onDialogClose();

      try {
        await generateAndShare({
          beforeUrl: images.before,
          afterUrl: images.after,
          rightLabel: SHARE_RIGHT_LABEL,
          shareUrl,
          shareMessage: shareUrl ? SHARE_MESSAGE_WITH_URL(shareUrl) : undefined,
        });
      } catch (err) {
        // Only surface the image-load timeout — user-cancelled native
        // sheet throws too, and that's not an error worth toasting.
        if (err instanceof Error && err.message.includes("timeout")) {
          showToast({
            kind: "error",
            message: SHARE_COMPOSITE_TIMEOUT_MESSAGE,
          });
        }
      }
    } finally {
      // Always release the re-entry guard — the inner early-returns above
      // don't reset it, so without this trailing finally a failed
      // auto-save would wedge the Share row until the next remount.
      isSharingRef.current = false;
    }
  }, [
    job,
    username,
    generateAndShare,
    getImageUrls,
    onDialogClose,
    saveJobFn,
    onSaveSuccess,
  ]);

  // ---- Publish --------------------------------------------------------
  //
  // POST /v1/posts. On 201, merge post_id + share_hash via
  // `onPublishSuccess` and close the dialog. On 4xx, surface the error
  // inline inside the confirm panel and keep the dialog open for retry.
  const handlePublish = useCallback(async () => {
    if (!job) return;
    if (isPublishing) return; // Re-entry guard — no double-submit.
    setIsPublishing(true);
    setPublishError(null);
    try {
      const body: CreatePostRequest = { glow_up_job_id: job.id };
      const res = await apiFetch<PostCreateResponse>(POSTS_CREATE_PATH, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onPublishSuccess?.(res.post_id, res.share_hash);
      onDialogClose();
    } catch (err) {
      const app = parseApiError(err);
      setPublishError(app.message);
    } finally {
      setIsPublishing(false);
    }
  }, [job, isPublishing, onDialogClose, onPublishSuccess]);

  return {
    saveState,
    isPublishing,
    publishError,
    handleSave,
    handleShare,
    handlePublish,
    resetPublishError,
  };
}
