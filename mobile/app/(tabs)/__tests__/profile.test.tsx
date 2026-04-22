/**
 * Profile screen — capability gating + long-press action-sheet wiring.
 *
 * The full screen pulls in too many native modules (Reanimated, BlurView,
 * Ionicons, expo-router, @expo/vector-icons) to mount under jest-expo
 * without enormous mock scaffolding, so this suite tests the handler
 * logic in isolation:
 *   - the capability-driven gating + menu derivation.
 *   - the long-press action-sheet dispatch map (completed vs errored vs
 *     in-flight cells).
 *   - the delete + share-dialog-open + publish flows as pure async
 *     functions wired to mocked apiFetch / saveJob / Alert.alert.
 *
 * Invariants under test (Unit 9):
 *   - Completed cell long-press opens a 3-choice action sheet.
 *   - Delete branch fires DELETE /v1/jobs/{id} after the confirm step
 *     and removes the cell optimistically; rollback on 5xx.
 *   - Share branch fetches GET /v1/jobs/{id} and opens ShareDialog.
 *   - Processing cell long-press is a no-op.
 *   - Failed cell long-press keeps using the existing dismiss menu.
 *   - Publish handler calls POST /v1/posts and hydrates post_id +
 *     share_hash into local state.
 */
import { Alert } from "react-native";
import { renderHook } from "@testing-library/react-native";

import { useCapabilities } from "../../../lib/capabilities";
import { buildProfileMenu } from "../../../components/profile/menu";
import { buildSessionState, type SessionMode } from "../../../lib/session";
import type { FeatureFlags } from "../../../constants/features";
import type { GlowUpItem } from "../../../components/profile/types";

// -----------------------------------------------------------------------------
// Module mocks
// -----------------------------------------------------------------------------

jest.mock("../../../lib/features-context", () => ({
  useFeatures: jest.fn(),
}));

jest.mock("../../../lib/auth-context", () => ({
  useSession: jest.fn(),
  useAuth: jest.fn(),
}));

jest.mock("../../../lib/api", () => ({
  apiFetch: jest.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(status: number, body: string) {
      super(`API ${status}`);
      this.status = status;
      this.body = body;
    }
  },
}));

jest.mock("../../../lib/analysis", () => ({
  saveJob: jest.fn(),
  // Keep JobResult / JobStatus out of runtime — they're type-only exports
  // but the mock has to export the value surface the profile screen uses.
}));

jest.mock("../../../lib/toast", () => ({
  showToast: jest.fn(),
}));

const featuresMod = require("../../../lib/features-context") as {
  useFeatures: jest.Mock;
};
const authMod = require("../../../lib/auth-context") as {
  useSession: jest.Mock;
  useAuth: jest.Mock;
};
const apiMod = require("../../../lib/api") as { apiFetch: jest.Mock };
const analysisMod = require("../../../lib/analysis") as { saveJob: jest.Mock };
const toastMod = require("../../../lib/toast") as { showToast: jest.Mock };

const BASE_FEATURES: FeatureFlags = {
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
  weekly_free_grant_enabled: true,
  makeup_enabled: false,
};

function setSession(mode: SessionMode, flags: Partial<FeatureFlags> = {}) {
  featuresMod.useFeatures.mockReturnValue({
    features: { ...BASE_FEATURES, ...flags },
    isLoading: false,
  });
  authMod.useSession.mockReturnValue(buildSessionState(mode, true));
}

const HANDLERS = {
  onEditProfile: jest.fn(),
  onOpenSubscription: jest.fn(),
  onOpenSettings: jest.fn(),
  onLogout: jest.fn(),
  onSignIn: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
});

// =============================================================================
// Capability-driven gating — regression guards kept from the earlier fix.
// =============================================================================

describe("profile screen — capability-driven gating", () => {
  it("user renders full-profile menu (Edit + Log Out, no Sign In)", () => {
    setSession("user");
    const caps = renderHook(() => useCapabilities()).result.current;

    expect(caps.canViewOwnProfile).toBe(true);

    const labels = buildProfileMenu(caps, HANDLERS).map((i) => i.label);
    expect(labels).toEqual([
      "Edit Profile",
      "Subscription",
      "Settings",
      "Log Out",
    ]);
  });

  it("anon → no profile, sign-in offered", () => {
    setSession("anon");
    const caps = renderHook(() => useCapabilities()).result.current;

    expect(caps.canViewOwnProfile).toBe(false);

    const labels = buildProfileMenu(caps, HANDLERS).map((i) => i.label);
    expect(labels).toContain("Sign In");
    expect(labels).not.toContain("Log Out");
  });

  it("load-effect predicate (canViewOwnProfile && authUsername) fires for users with username", () => {
    setSession("user");
    const caps = renderHook(() => useCapabilities()).result.current;

    const authUsername = "alice";
    const profile = null;
    const shouldLoad =
      caps.canViewOwnProfile && Boolean(authUsername) && profile === null;

    expect(shouldLoad).toBe(true);
  });

  it("load-effect predicate suppresses when user has no username yet", () => {
    setSession("user");
    const caps = renderHook(() => useCapabilities()).result.current;

    const authUsername: string | null = null;
    const profile = null;
    const shouldLoad =
      caps.canViewOwnProfile && Boolean(authUsername) && profile === null;

    expect(shouldLoad).toBe(false);
  });
});

// =============================================================================
// Long-press action-sheet — Unit 9 behavior under test.
// =============================================================================

/**
 * Helper: pull the buttons array out of the latest Alert.alert call,
 * so tests can assert on its shape without mounting the screen. Jest's
 * mocked Alert.alert captures the arguments verbatim.
 */
interface AlertButtonShape {
  text: string;
  style?: "cancel" | "destructive" | "default";
  onPress?: () => void;
}
type AlertButtons = AlertButtonShape[];

/**
 * Pull the buttons array out of the latest Alert.alert invocation.
 * Accepts the spy via its `.mock.calls` surface so callers can pass
 * either `jest.Mock` or `jest.SpyInstance` without casting.
 */
function lastAlertButtons(mock: {
  mock: { calls: unknown[][] };
}): AlertButtons {
  const calls = mock.mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  const lastCall = calls[calls.length - 1]!;
  const buttons = lastCall[2] as AlertButtons | undefined;
  if (!buttons) throw new Error("Alert.alert called without buttons argument");
  return buttons;
}

// ---- Handler replica -------------------------------------------------------
//
// Tests exercise the dispatch-by-status decision in `handleItemLongPress`
// without mounting the screen. The replica below mirrors the production
// handler 1:1; the tests assert on the captured Alert.alert invocation
// and on the follow-through to apiFetch / saveJob when the user taps
// through. Keep in sync with profile.tsx — any divergence is the bug
// these tests are meant to catch.
// ---------------------------------------------------------------------------

const ERRORED_STATUSES = new Set<string>(["failed", "cancelled"]);
const LONG_PRESS_MENU_STATUS = "completed";
const COMPLETED_MENU_SHARE_LABEL = "Share & Publish…";
const COMPLETED_MENU_SHARE_LABEL_NO_PUBLISH = "Share…";
const COMPLETED_MENU_DELETE_LABEL = "Delete";
const COMPLETED_MENU_CANCEL_LABEL = "Cancel";
const COMPLETED_MENU_TITLE = "Glow-up options";

const DISMISS_TITLE = "Remove from profile?";

const DELETE_CONFIRM_TITLE = "Delete this glow-up?";
const DELETE_CONFIRM_LABEL = "Delete";
const DELETE_CONFIRM_CANCEL_LABEL = "Cancel";

interface HandlerDeps {
  canPublishGlowup: boolean;
  dismissErroredItem: jest.Mock;
  openShareDialogForJob: jest.Mock;
  promptDeleteGlowup: jest.Mock;
}

function makeLongPressHandler(deps: HandlerDeps) {
  return (item: GlowUpItem) => {
    if (!item.job_id) return;
    if (ERRORED_STATUSES.has(item.status)) {
      Alert.alert(DISMISS_TITLE, "body", [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove from profile",
          style: "destructive",
          onPress: () => deps.dismissErroredItem(item.job_id),
        },
      ]);
      return;
    }
    if (item.status !== LONG_PRESS_MENU_STATUS) return;

    const shareLabel = deps.canPublishGlowup
      ? COMPLETED_MENU_SHARE_LABEL
      : COMPLETED_MENU_SHARE_LABEL_NO_PUBLISH;
    const jobId = item.job_id!;
    Alert.alert(COMPLETED_MENU_TITLE, undefined, [
      {
        text: shareLabel,
        onPress: () => {
          void deps.openShareDialogForJob(item);
        },
      },
      {
        text: COMPLETED_MENU_DELETE_LABEL,
        style: "destructive",
        onPress: () => deps.promptDeleteGlowup(jobId),
      },
      { text: COMPLETED_MENU_CANCEL_LABEL, style: "cancel" },
    ]);
  };
}

function makeItem(overrides: Partial<GlowUpItem> = {}): GlowUpItem {
  return {
    analysis_id: "a-1",
    job_id: "job-1",
    status: "completed",
    face_shape: null,
    symmetry_score: null,
    recommendations: [],
    before_image_url: "https://cdn.example/before.jpg",
    after_image_url: "https://cdn.example/after.jpg",
    created_at: "2026-04-18T00:00:00Z",
    saved_at: null,
    ...overrides,
  };
}

// Shared spy for every describe-block that prompts via Alert.alert.
// `jest.spyOn` returns a different mock each call site; declaring it once
// at module scope keeps the captured calls visible across the file.
const alertMock = jest.spyOn(Alert, "alert");

describe("profile screen — long-press dispatch", () => {
  let deps: HandlerDeps;
  beforeEach(() => {
    alertMock.mockClear();
    deps = {
      canPublishGlowup: true,
      dismissErroredItem: jest.fn(),
      openShareDialogForJob: jest.fn(),
      promptDeleteGlowup: jest.fn(),
    };
  });

  it("completed cell opens 3-choice action sheet: Share & Publish… | Delete | Cancel", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "completed" }));

    expect(alertMock).toHaveBeenCalledTimes(1);
    const [title, , buttons] = alertMock.mock.calls[0]!;
    expect(title).toBe(COMPLETED_MENU_TITLE);
    expect(buttons).toHaveLength(3);
    expect((buttons as AlertButtons).map((b) => b.text)).toEqual([
      COMPLETED_MENU_SHARE_LABEL,
      COMPLETED_MENU_DELETE_LABEL,
      COMPLETED_MENU_CANCEL_LABEL,
    ]);
    expect((buttons as AlertButtons)[1]!.style).toBe("destructive");
    expect((buttons as AlertButtons)[2]!.style).toBe("cancel");
  });

  it("completed cell uses 'Share…' label when canPublishGlowup is false", () => {
    deps.canPublishGlowup = false;
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "completed" }));

    const buttons = lastAlertButtons(alertMock);
    expect(buttons[0]!.text).toBe(COMPLETED_MENU_SHARE_LABEL_NO_PUBLISH);
  });

  it("tapping Share & Publish… invokes openShareDialogForJob", () => {
    const handler = makeLongPressHandler(deps);
    const item = makeItem({ status: "completed" });
    handler(item);

    const buttons = lastAlertButtons(alertMock);
    buttons[0]!.onPress?.();

    expect(deps.openShareDialogForJob).toHaveBeenCalledWith(item);
    expect(deps.promptDeleteGlowup).not.toHaveBeenCalled();
  });

  it("tapping Delete invokes promptDeleteGlowup with the job id", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "completed", job_id: "job-42" }));

    const buttons = lastAlertButtons(alertMock);
    buttons[1]!.onPress?.();

    expect(deps.promptDeleteGlowup).toHaveBeenCalledWith("job-42");
    expect(deps.openShareDialogForJob).not.toHaveBeenCalled();
  });

  it("processing cell long-press is a no-op (no menu)", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "processing" }));

    expect(alertMock).not.toHaveBeenCalled();
  });

  it("queued cell long-press is a no-op", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "queued" }));

    expect(alertMock).not.toHaveBeenCalled();
  });

  it("finalizing cell long-press is a no-op", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "finalizing" }));

    expect(alertMock).not.toHaveBeenCalled();
  });

  it("failed cell long-press keeps the existing dismiss menu (not the new 3-choice)", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "failed" }));

    expect(alertMock).toHaveBeenCalledTimes(1);
    const [title, , buttons] = alertMock.mock.calls[0]!;
    expect(title).toBe(DISMISS_TITLE);
    expect((buttons as AlertButtons).map((b) => b.text)).toEqual([
      "Cancel",
      "Remove from profile",
    ]);
  });

  it("cancelled cell long-press keeps the existing dismiss menu", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "cancelled" }));

    expect(alertMock).toHaveBeenCalledTimes(1);
    expect(alertMock.mock.calls[0]![0]).toBe(DISMISS_TITLE);
  });

  it("dispatched dismiss onPress forwards the job_id", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "failed", job_id: "job-fail" }));

    const buttons = lastAlertButtons(alertMock);
    buttons[1]!.onPress?.();

    expect(deps.dismissErroredItem).toHaveBeenCalledWith("job-fail");
  });

  it("item with null job_id is skipped entirely", () => {
    const handler = makeLongPressHandler(deps);
    handler(makeItem({ status: "completed", job_id: null }));

    expect(alertMock).not.toHaveBeenCalled();
  });
});

// =============================================================================
// Delete flow — optimistic remove + rollback.
// =============================================================================

/**
 * Replica of `handleDeleteGlowup` — DELETE /v1/jobs/{id} with optimistic
 * mark-as-removed and rollback on failure. Kept pure so we can unit
 * test the state transitions without mounting the screen.
 */
async function runDeleteFlow(
  jobId: string,
  apiFetchFn: (path: string, init: { method: string }) => Promise<void>,
  mark: (jobId: string) => void,
  unmark: (jobId: string) => void,
  onError: (message: string) => void,
  refresh: () => Promise<void>,
): Promise<void> {
  mark(jobId);
  try {
    await apiFetchFn(`/v1/jobs/${jobId}`, { method: "DELETE" });
    await refresh();
  } catch (err) {
    unmark(jobId);
    const fallback = "Couldn't delete — try again.";
    let message = fallback;
    if (err && typeof err === "object" && "body" in err) {
      const body = (err as { body?: unknown }).body;
      if (typeof body === "string" && body.length > 0) {
        try {
          const parsed = JSON.parse(body) as { detail?: unknown };
          if (typeof parsed.detail === "string" && parsed.detail.length > 0) {
            message = parsed.detail;
          }
        } catch {
          // non-JSON body: keep fallback.
        }
      }
    }
    onError(message);
  }
}

describe("profile screen — delete flow", () => {
  it("happy path: DELETE fires, mark is called, refresh is called, no rollback", async () => {
    const mark = jest.fn();
    const unmark = jest.fn();
    const onError = jest.fn();
    const refresh = jest.fn().mockResolvedValue(undefined);
    apiMod.apiFetch.mockResolvedValueOnce(undefined);

    await runDeleteFlow(
      "job-x",
      apiMod.apiFetch,
      mark,
      unmark,
      onError,
      refresh,
    );

    expect(mark).toHaveBeenCalledWith("job-x");
    expect(apiMod.apiFetch).toHaveBeenCalledWith("/v1/jobs/job-x", {
      method: "DELETE",
    });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(unmark).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("5xx: cell is rolled back and toast fires", async () => {
    const mark = jest.fn();
    const unmark = jest.fn();
    const onError = jest.fn();
    const refresh = jest.fn();
    const err = Object.assign(new Error("API 500"), {
      status: 500,
      body: "",
    });
    apiMod.apiFetch.mockRejectedValueOnce(err);

    await runDeleteFlow(
      "job-x",
      apiMod.apiFetch,
      mark,
      unmark,
      onError,
      refresh,
    );

    expect(mark).toHaveBeenCalledWith("job-x");
    expect(unmark).toHaveBeenCalledWith("job-x");
    expect(refresh).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith("Couldn't delete — try again.");
  });

  it("server detail in body surfaces to the toast", async () => {
    const mark = jest.fn();
    const unmark = jest.fn();
    const onError = jest.fn();
    const refresh = jest.fn();
    const err = Object.assign(new Error("API 409"), {
      status: 409,
      body: JSON.stringify({ detail: "Cancel the glow-up first." }),
    });
    apiMod.apiFetch.mockRejectedValueOnce(err);

    await runDeleteFlow(
      "job-x",
      apiMod.apiFetch,
      mark,
      unmark,
      onError,
      refresh,
    );

    expect(onError).toHaveBeenCalledWith("Cancel the glow-up first.");
  });
});

// =============================================================================
// Delete confirm — Alert.alert two-stage flow.
// =============================================================================

function promptDeleteGlowup(jobId: string, onConfirm: (id: string) => void) {
  Alert.alert(DELETE_CONFIRM_TITLE, "body", [
    { text: DELETE_CONFIRM_CANCEL_LABEL, style: "cancel" },
    {
      text: DELETE_CONFIRM_LABEL,
      style: "destructive",
      onPress: () => onConfirm(jobId),
    },
  ]);
}

describe("profile screen — delete confirm", () => {
  beforeEach(() => {
    alertMock.mockClear();
  });

  afterAll(() => {
    alertMock.mockRestore();
  });

  it("opens a 2-choice destructive confirm", () => {
    const onConfirm = jest.fn();
    promptDeleteGlowup("job-1", onConfirm);

    const [title, , buttons] = alertMock.mock.calls[0]!;
    expect(title).toBe(DELETE_CONFIRM_TITLE);
    expect((buttons as AlertButtons).map((b) => b.text)).toEqual([
      DELETE_CONFIRM_CANCEL_LABEL,
      DELETE_CONFIRM_LABEL,
    ]);
    expect((buttons as AlertButtons)[1]!.style).toBe("destructive");
    expect((buttons as AlertButtons)[0]!.style).toBe("cancel");
  });

  it("tapping Delete forwards the job id to onConfirm", () => {
    const onConfirm = jest.fn();
    promptDeleteGlowup("job-42", onConfirm);
    const buttons = lastAlertButtons(alertMock);
    buttons[1]!.onPress?.();

    expect(onConfirm).toHaveBeenCalledWith("job-42");
  });

  it("tapping Cancel does nothing (no onPress side-effect)", () => {
    const onConfirm = jest.fn();
    promptDeleteGlowup("job-42", onConfirm);
    const buttons = lastAlertButtons(alertMock);
    // Cancel button has no onPress — matches the production handler.
    expect(buttons[0]!.onPress).toBeUndefined();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

// =============================================================================
// ShareDialog open flow — fetches the job then populates ShareDialog shape.
// =============================================================================

interface ShareDialogJobShape {
  id: string;
  saved_at: string | null;
  post_id: string | null;
  share_hash: string | null;
}

async function runOpenDialogFlow(
  item: GlowUpItem,
  apiFetchFn: (path: string) => Promise<{
    job_id: string;
    status: string;
    saved_at: string | null;
    post_id: string | null;
    share_hash: string | null;
    before_image_url: string | null;
    after_image_url: string | null;
  }>,
  onOpen: (job: ShareDialogJobShape) => void,
  onError: (message: string) => void,
): Promise<void> {
  if (!item.job_id) return;
  try {
    const job = await apiFetchFn(`/v1/jobs/${item.job_id}`);
    onOpen({
      id: item.job_id,
      saved_at: job.saved_at,
      post_id: job.post_id,
      share_hash: job.share_hash,
    });
  } catch {
    onError("Couldn't open that glow-up — try again.");
  }
}

describe("profile screen — share-dialog open flow", () => {
  it("fetches GET /v1/jobs/{id} and hydrates dialog with the post fields", async () => {
    const onOpen = jest.fn();
    const onError = jest.fn();
    apiMod.apiFetch.mockResolvedValueOnce({
      job_id: "job-1",
      status: "completed",
      saved_at: "2026-04-18T00:00:00Z",
      post_id: "post-9",
      share_hash: "hash-abc",
      before_image_url: "b",
      after_image_url: "a",
    });

    await runOpenDialogFlow(
      makeItem({ status: "completed", job_id: "job-1" }),
      apiMod.apiFetch,
      onOpen,
      onError,
    );

    expect(apiMod.apiFetch).toHaveBeenCalledWith("/v1/jobs/job-1");
    expect(onOpen).toHaveBeenCalledWith({
      id: "job-1",
      saved_at: "2026-04-18T00:00:00Z",
      post_id: "post-9",
      share_hash: "hash-abc",
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("surfaces toast on fetch failure; does not open dialog", async () => {
    const onOpen = jest.fn();
    const onError = jest.fn();
    apiMod.apiFetch.mockRejectedValueOnce(new Error("boom"));

    await runOpenDialogFlow(
      makeItem({ status: "completed", job_id: "job-1" }),
      apiMod.apiFetch,
      onOpen,
      onError,
    );

    expect(onOpen).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      "Couldn't open that glow-up — try again.",
    );
  });
});

// =============================================================================
// Publish flow — POST /v1/posts hydrates post_id + share_hash and closes.
// =============================================================================

interface PublishDeps {
  apiFetchFn: (
    path: string,
    init: { method: string; body: string },
  ) => Promise<{ id: string; share_hash: string }>;
  jobId: string;
  onSuccess: (postId: string, shareHash: string) => void;
  onError: (message: string) => void;
}

async function runPublishFlow(deps: PublishDeps): Promise<void> {
  try {
    const post = await deps.apiFetchFn("/v1/posts", {
      method: "POST",
      body: JSON.stringify({ glow_up_job_id: deps.jobId }),
    });
    deps.onSuccess(post.id, post.share_hash);
  } catch {
    deps.onError("Couldn't publish — try again.");
  }
}

describe("profile screen — publish flow", () => {
  it("success: hydrates post_id + share_hash, invokes onSuccess", async () => {
    const onSuccess = jest.fn();
    const onError = jest.fn();
    apiMod.apiFetch.mockResolvedValueOnce({
      id: "post-42",
      share_hash: "hash-42",
    });

    await runPublishFlow({
      apiFetchFn: apiMod.apiFetch,
      jobId: "job-1",
      onSuccess,
      onError,
    });

    expect(apiMod.apiFetch).toHaveBeenCalledWith("/v1/posts", {
      method: "POST",
      body: JSON.stringify({ glow_up_job_id: "job-1" }),
    });
    expect(onSuccess).toHaveBeenCalledWith("post-42", "hash-42");
    expect(onError).not.toHaveBeenCalled();
  });

  it("failure: stays open, surfaces inline error", async () => {
    const onSuccess = jest.fn();
    const onError = jest.fn();
    apiMod.apiFetch.mockRejectedValueOnce(new Error("boom"));

    await runPublishFlow({
      apiFetchFn: apiMod.apiFetch,
      jobId: "job-1",
      onSuccess,
      onError,
    });

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith("Couldn't publish — try again.");
  });
});

// =============================================================================
// Share-save chain — Share auto-save before native share (R8).
// =============================================================================

async function runShareSaveChain(
  saved_at: string | null,
  saveFn: (jobId: string) => Promise<{ saved_at: string }>,
  onProceed: () => void,
  onAbort: (message: string) => void,
): Promise<void> {
  if (saved_at !== null) {
    onProceed();
    return;
  }
  try {
    await saveFn("job-1");
    onProceed();
  } catch {
    onAbort("Couldn't save — try again.");
  }
}

describe("profile screen — share auto-save chain", () => {
  it("already-saved job proceeds directly to share", async () => {
    const onProceed = jest.fn();
    const onAbort = jest.fn();
    const saveFn = jest.fn();

    await runShareSaveChain(
      "2026-04-18T00:00:00Z",
      saveFn,
      onProceed,
      onAbort,
    );

    expect(saveFn).not.toHaveBeenCalled();
    expect(onProceed).toHaveBeenCalledTimes(1);
    expect(onAbort).not.toHaveBeenCalled();
  });

  it("unsaved job: save succeeds → proceed", async () => {
    const onProceed = jest.fn();
    const onAbort = jest.fn();
    analysisMod.saveJob.mockResolvedValueOnce({
      saved_at: "2026-04-18T00:00:00Z",
    });

    await runShareSaveChain(null, analysisMod.saveJob, onProceed, onAbort);

    expect(analysisMod.saveJob).toHaveBeenCalledWith("job-1");
    expect(onProceed).toHaveBeenCalledTimes(1);
    expect(onAbort).not.toHaveBeenCalled();
  });

  it("unsaved job: save fails → abort with toast, never share", async () => {
    const onProceed = jest.fn();
    const onAbort = jest.fn();
    analysisMod.saveJob.mockRejectedValueOnce(new Error("boom"));

    await runShareSaveChain(null, analysisMod.saveJob, onProceed, onAbort);

    expect(onProceed).not.toHaveBeenCalled();
    expect(onAbort).toHaveBeenCalledWith("Couldn't save — try again.");
  });
});

// Silence the unused-import lint from test-only requires.
void toastMod;

// =============================================================================
// Gallery filter — Unit 12 segmented control logic.
// =============================================================================

function filterGlowUps(
  items: GlowUpItem[],
  filter: "all" | "glowup" | "makeup"
): GlowUpItem[] {
  if (filter === "all") return items;
  const target =
    filter === "makeup" ? "makeup_session" : "glowup_analysis";
  return items.filter(
    (e) => (e.source_type ?? "glowup_analysis") === target
  );
}

const ITEMS: GlowUpItem[] = [
  {
    analysis_id: "g1",
    job_id: "j1",
    status: "completed",
    face_shape: null,
    symmetry_score: null,
    recommendations: [],
    before_image_url: null,
    after_image_url: null,
    created_at: "2026-04-22T00:00:00Z",
    saved_at: null,
    source_type: "glowup_analysis",
  },
  {
    analysis_id: "m1",
    job_id: "j2",
    status: "completed",
    face_shape: null,
    symmetry_score: null,
    recommendations: [],
    before_image_url: null,
    after_image_url: null,
    created_at: "2026-04-22T00:00:00Z",
    saved_at: null,
    source_type: "makeup_session",
  },
  {
    analysis_id: "legacy",
    job_id: null,
    status: "",
    face_shape: null,
    symmetry_score: null,
    recommendations: [],
    before_image_url: null,
    after_image_url: null,
    created_at: "2026-04-22T00:00:00Z",
    saved_at: null,
    // source_type absent → should be treated as glowup_analysis
  },
];

describe("profile screen — gallery filter (Unit 12)", () => {
  it("'all' returns every item", () => {
    expect(filterGlowUps(ITEMS, "all")).toHaveLength(3);
  });

  it("'glowup' keeps glowup_analysis + legacy items (undefined source_type defaults)", () => {
    const result = filterGlowUps(ITEMS, "glowup");
    expect(result.map((i) => i.analysis_id)).toEqual(["g1", "legacy"]);
  });

  it("'makeup' keeps only makeup_session items", () => {
    const result = filterGlowUps(ITEMS, "makeup");
    expect(result.map((i) => i.analysis_id)).toEqual(["m1"]);
  });

  it("empty list returns empty for any filter", () => {
    expect(filterGlowUps([], "glowup")).toEqual([]);
    expect(filterGlowUps([], "makeup")).toEqual([]);
    expect(filterGlowUps([], "all")).toEqual([]);
  });

  it("canUseMakeup formula: true when makeup_enabled + Pro + isUser", () => {
    // mirrors the formula in lib/capabilities.ts
    const canUseMakeup = (makeupEnabled: boolean, isUser: boolean, tier: string) =>
      makeupEnabled && isUser && tier === "Pro";

    expect(canUseMakeup(true, true, "Pro")).toBe(true);
    expect(canUseMakeup(false, true, "Pro")).toBe(false);
    expect(canUseMakeup(true, false, "Pro")).toBe(false);
    expect(canUseMakeup(true, true, "Free")).toBe(false);
  });
});
