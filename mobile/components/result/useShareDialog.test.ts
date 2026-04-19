/**
 * useShareDialog — handler triplet behavior + invariants.
 *
 * Covers the R5/R8 blocking-auto-save invariant: a failed save on the
 * Share path MUST abort the native-share hand-off. Also verifies the
 * re-entry guard on Publish, the image-url timeout branch, and the
 * onSaveSuccess / onPublishSuccess patch contracts, plus the
 * `opts.saveJobFn` contract so the hook never calls `saveJob` directly
 * (one save codepath across the result + profile screens).
 *
 * Mocks: `apiFetch`, `parseApiError`, `showToast`. The save path is
 * tested through the parent-supplied `saveJobFn` jest mock so the
 * invariant "hook only calls opts.saveJobFn" is asserted directly.
 * `apiFetch` mirrors the `useSocialAuth.test.ts` pattern (import and
 * cast). No JSX is rendered — `renderHook` drives the hook directly.
 */
import { act, renderHook } from "@testing-library/react-native";

import { useShareDialog } from "./useShareDialog";
import type { ShareDialogJob } from "./ShareDialog";

jest.mock("../../lib/api", () => ({
  apiFetch: jest.fn(),
}));

jest.mock("../../lib/errors", () => ({
  // Pass-through so tests can assert on the thrown message verbatim
  // without coupling to the project-wide copy bucketing.
  parseApiError: jest.fn((err: unknown) => ({
    kind: "unknown",
    message: err instanceof Error ? err.message : String(err),
  })),
}));

jest.mock("../../lib/toast", () => ({
  showToast: jest.fn(),
}));

// Re-imported after `jest.mock` so the casts resolve to the mocked
// module surface. Safe because jest hoists the mocks above imports.
const { apiFetch } = require("../../lib/api") as {
  apiFetch: jest.Mock;
};
const { showToast } = require("../../lib/toast") as {
  showToast: jest.Mock;
};

// ---------- Fixtures ----------

function makeJob(overrides: Partial<ShareDialogJob> = {}): ShareDialogJob {
  return {
    id: "job-1",
    saved_at: null,
    post_id: null,
    share_hash: null,
    ...overrides,
  };
}

interface SetupArgs {
  job?: ShareDialogJob | null;
  username?: string | null;
  imageUrls?: { before: string | null; after: string | null };
  imageUrlsThrows?: unknown;
  generateAndShareImpl?: jest.Mock;
  saveJobFnImpl?: jest.Mock;
}

function setup(args: SetupArgs = {}) {
  const job = args.job === undefined ? makeJob() : args.job;
  const username = args.username === undefined ? "alice" : args.username;
  const images = args.imageUrls ?? {
    before: "https://cdn.example/before.jpg",
    after: "https://cdn.example/after.jpg",
  };

  const getImageUrls = jest.fn(async () => {
    if (args.imageUrlsThrows !== undefined) {
      throw args.imageUrlsThrows;
    }
    return images;
  });
  const generateAndShare = args.generateAndShareImpl ?? jest.fn();
  const saveJobFn =
    args.saveJobFnImpl ??
    jest.fn(async (_id: string) => ({ saved_at: "2026-04-18T12:00:00Z" }));
  const onDialogClose = jest.fn();
  const onSaveSuccess = jest.fn();
  const onPublishSuccess = jest.fn();

  const { result } = renderHook(() =>
    useShareDialog({
      job,
      username,
      generateAndShare,
      getImageUrls,
      onDialogClose,
      saveJobFn,
      onSaveSuccess,
      onPublishSuccess,
    }),
  );

  return {
    result,
    getImageUrls,
    generateAndShare,
    saveJobFn,
    onDialogClose,
    onSaveSuccess,
    onPublishSuccess,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------- handleSave ----------

describe("useShareDialog — handleSave", () => {
  it("happy path: calls opts.saveJobFn with the job id, flips saveState, fires onSaveSuccess with saved_at, toasts success", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => ({
      saved_at: "2026-04-18T12:00:00Z",
    }));
    const { result, saveJobFn, onSaveSuccess } = setup({ saveJobFnImpl });

    await act(async () => {
      await result.current.handleSave();
    });

    // Unified save codepath: hook MUST route through opts.saveJobFn,
    // not a direct saveJob import. Asserts the P3d invariant directly.
    expect(saveJobFn).toHaveBeenCalledWith("job-1");
    expect(result.current.saveState).toBe("saved");
    expect(onSaveSuccess).toHaveBeenCalledWith("2026-04-18T12:00:00Z");
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "success" }),
    );
  });

  it("error path: resets saveState, toasts error, does NOT fire onSaveSuccess", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => {
      throw new Error("save-failed");
    });
    const { result, onSaveSuccess } = setup({ saveJobFnImpl });

    await act(async () => {
      await result.current.handleSave();
    });

    expect(result.current.saveState).toBe("pending");
    expect(onSaveSuccess).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", message: "save-failed" }),
    );
  });

  it("no-op when saveState is not pending (double-submit guard)", async () => {
    const { result, saveJobFn } = setup();

    // First save locks the state to "saved".
    await act(async () => {
      await result.current.handleSave();
    });
    expect(result.current.saveState).toBe("saved");
    saveJobFn.mockClear();

    // Second save must be a no-op.
    await act(async () => {
      await result.current.handleSave();
    });
    expect(saveJobFn).not.toHaveBeenCalled();
  });

  it("no-op when job is null", async () => {
    const { result, saveJobFn } = setup({ job: null });

    await act(async () => {
      await result.current.handleSave();
    });

    expect(saveJobFn).not.toHaveBeenCalled();
  });
});

// ---------- opts.saveJobFn contract (P3d unification) ----------

describe("useShareDialog — saveJobFn contract", () => {
  // Explicit assertions that the hook routes every save through
  // `opts.saveJobFn` and never calls `saveJob` from `lib/analysis`
  // directly. This is the P3d invariant: one save codepath across the
  // result + profile screens, wired so each screen can layer its own
  // mutation / cache-invalidation behaviour without the hook going
  // around it.
  it("calls opts.saveJobFn(job.id) on standalone handleSave", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => ({
      saved_at: "2026-04-19T00:00:00Z",
    }));
    const { result, saveJobFn } = setup({ saveJobFnImpl });

    await act(async () => {
      await result.current.handleSave();
    });

    expect(saveJobFn).toHaveBeenCalledTimes(1);
    expect(saveJobFn).toHaveBeenCalledWith("job-1");
  });

  it("calls opts.saveJobFn(job.id) on the Share blocking auto-save branch (R5/R8)", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => ({
      saved_at: "2026-04-19T00:00:00Z",
    }));
    const { result, saveJobFn } = setup({ saveJobFnImpl });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJobFn).toHaveBeenCalledTimes(1);
    expect(saveJobFn).toHaveBeenCalledWith("job-1");
  });

  it("propagates saved_at to onSaveSuccess so the parent can merge the timestamp", async () => {
    // Integration-style assertion: on success, the hook fires the
    // onSaveSuccess callback with the exact timestamp that saveJobFn
    // resolved with. Parents (result screen + profile long-press) rely
    // on this to merge `saved_at` into their job snapshot so the Save
    // row disappears on the next render.
    const SAVED_AT = "2026-04-19T13:30:00Z";
    const saveJobFnImpl = jest.fn(async (_id: string) => ({
      saved_at: SAVED_AT,
    }));
    const { result, onSaveSuccess } = setup({ saveJobFnImpl });

    await act(async () => {
      await result.current.handleSave();
    });

    expect(onSaveSuccess).toHaveBeenCalledTimes(1);
    expect(onSaveSuccess).toHaveBeenCalledWith(SAVED_AT);
  });
});

// ---------- handleShare ----------

describe("useShareDialog — handleShare (R5/R8)", () => {
  it("already-saved job: skips auto-save, closes dialog before sharing, passes hash URL", async () => {
    const { result, generateAndShare, onDialogClose, saveJobFn } = setup({
      job: makeJob({
        saved_at: "2026-04-17T00:00:00Z",
        post_id: "post-xyz",
        share_hash: "abc123",
      }),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJobFn).not.toHaveBeenCalled();
    // Close-before-share ordering matters for the modal scrim UX.
    expect(onDialogClose).toHaveBeenCalledTimes(1);
    expect(generateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({
        shareUrl: "https://nxme.ai/alice/glow-up/abc123",
        shareMessage: "My NXME glow-up — https://nxme.ai/alice/glow-up/abc123",
      }),
    );
  });

  it("unsaved job: saves first via saveJobFn, then shares (blocking auto-save)", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => ({
      saved_at: "2026-04-18T12:00:00Z",
    }));
    const { result, generateAndShare, saveJobFn, onSaveSuccess } = setup({
      saveJobFnImpl,
    });

    await act(async () => {
      await result.current.handleShare();
    });

    // Same unified save codepath as standalone Save — asserts the
    // auto-save branch also routes through opts.saveJobFn.
    expect(saveJobFn).toHaveBeenCalledWith("job-1");
    expect(onSaveSuccess).toHaveBeenCalledWith("2026-04-18T12:00:00Z");
    expect(generateAndShare).toHaveBeenCalledTimes(1);
    // Save-toast does NOT fire on Share path — user only asked to
    // Share, not Save. (Toast suppression is a hook invariant; the
    // only toast surfaces on the save-failure branch below.)
    expect(showToast).not.toHaveBeenCalled();
  });

  it("save failure on Share path: share is NOT called, error toasted, dialog stays open", async () => {
    const saveJobFnImpl = jest.fn(async (_id: string) => {
      throw new Error("save-failed");
    });
    const { result, generateAndShare, onDialogClose, saveJobFn } = setup({
      saveJobFnImpl,
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJobFn).toHaveBeenCalledWith("job-1");
    // R5/R8: save failure MUST abort the native share.
    expect(generateAndShare).not.toHaveBeenCalled();
    expect(onDialogClose).not.toHaveBeenCalled();
    expect(result.current.saveState).toBe("pending");
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error" }),
    );
  });

  it("missing image URL pair: toasts timeout message, does not share", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
      imageUrls: { before: null, after: null },
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "error",
        message: expect.stringContaining("Images didn't finish loading"),
      }),
    );
  });

  it("unpublished job (no post_id): share runs without shareUrl", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({ shareUrl: undefined, shareMessage: undefined }),
    );
  });

  it("getImageUrls rejection: toasts error, does not share", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
      imageUrlsThrows: new Error("network down"),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", message: "network down" }),
    );
  });

  it("re-entry guard: second tap while auto-save is in flight is a no-op", async () => {
    // Unsaved job — first Share tap enters the blocking-auto-save branch.
    // Hold `saveJobFn` open so the second tap lands while the first is in
    // flight. Without the ref guard this would fire saveJobFn twice.
    let resolveFirst: ((value: { saved_at: string }) => void) | null = null;
    const saveJobFnImpl = jest.fn(
      () =>
        new Promise<{ saved_at: string }>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const { result, generateAndShare, saveJobFn } = setup({ saveJobFnImpl });

    // First tap — enters auto-save and parks.
    await act(async () => {
      void result.current.handleShare();
      // Let setState / initial await queue drain.
      await Promise.resolve();
    });
    expect(saveJobFn).toHaveBeenCalledTimes(1);

    // Second tap while first is pending — guard rejects it.
    await act(async () => {
      await result.current.handleShare();
    });
    expect(saveJobFn).toHaveBeenCalledTimes(1);
    expect(generateAndShare).not.toHaveBeenCalled();

    // Cleanup — resolve the first save so the act queue drains and the
    // finally releases the guard.
    await act(async () => {
      resolveFirst?.({ saved_at: "2026-04-18T12:00:00Z" });
      await Promise.resolve();
    });
  });

  it("save timeout: toasts timeout message, does NOT open the share sheet", async () => {
    // Never-resolving save → raceWithTimeout fires its timer. Fake timers
    // keep this deterministic; only this test flips them on.
    jest.useFakeTimers();
    try {
      const saveJobFnImpl = jest.fn(
        () => new Promise<{ saved_at: string }>(() => {}),
      );
      const { result, generateAndShare, onDialogClose } = setup({
        saveJobFnImpl,
      });

      let sharePromise!: Promise<void>;
      await act(async () => {
        sharePromise = result.current.handleShare();
        // Flush the initial setState + await so the race is armed.
        await Promise.resolve();
      });

      // Advance past the 15s timeout window.
      await act(async () => {
        jest.advanceTimersByTime(15_000);
        await sharePromise;
      });

      expect(generateAndShare).not.toHaveBeenCalled();
      expect(onDialogClose).not.toHaveBeenCalled();
      expect(result.current.saveState).toBe("pending");
      expect(showToast).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "error",
          message: expect.stringContaining("Save timed out"),
        }),
      );
    } finally {
      jest.useRealTimers();
    }
  });
});

// ---------- handlePublish ----------

describe("useShareDialog — handlePublish", () => {
  it("success: POSTs /v1/posts, fires onPublishSuccess(post_id, share_hash), closes dialog, resets flag", async () => {
    apiFetch.mockResolvedValue({
      post_id: "post-xyz",
      share_hash: "abc123",
    });
    const { result, onPublishSuccess, onDialogClose } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/posts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ glow_up_job_id: "job-1" }),
      }),
    );
    expect(onPublishSuccess).toHaveBeenCalledWith("post-xyz", "abc123");
    expect(onDialogClose).toHaveBeenCalledTimes(1);
    expect(result.current.isPublishing).toBe(false);
    expect(result.current.publishError).toBeNull();
  });

  it("4xx: sets publishError, resets isPublishing, keeps dialog open", async () => {
    apiFetch.mockRejectedValue(new Error("already published"));
    const { result, onDialogClose, onPublishSuccess } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(result.current.publishError).toBe("already published");
    expect(result.current.isPublishing).toBe(false);
    expect(onPublishSuccess).not.toHaveBeenCalled();
    expect(onDialogClose).not.toHaveBeenCalled();
  });

  it("re-entry guard: second tap while first is in flight is a no-op", async () => {
    // Never-resolving promise so the first tap stays in flight.
    let resolveFirst: ((value: unknown) => void) | null = null;
    apiFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const { result } = setup();

    await act(async () => {
      void result.current.handlePublish();
      // Allow the first call's setState to flush.
      await Promise.resolve();
    });
    expect(result.current.isPublishing).toBe(true);
    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Second tap while first is pending — guard rejects it.
    await act(async () => {
      await result.current.handlePublish();
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Cleanup — resolve the first call so act queue drains.
    await act(async () => {
      resolveFirst?.({ post_id: "post-1", share_hash: "h1" });
      await Promise.resolve();
    });
  });

  it("resetPublishError clears a prior error", async () => {
    apiFetch.mockRejectedValue(new Error("boom"));
    const { result } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });
    expect(result.current.publishError).toBe("boom");

    act(() => {
      result.current.resetPublishError();
    });
    expect(result.current.publishError).toBeNull();
  });

  it("no-op when job is null", async () => {
    const { result } = setup({ job: null });

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(apiFetch).not.toHaveBeenCalled();
  });
});

// ---------- saveState sync with job.saved_at ----------

describe("useShareDialog — saveState sync", () => {
  it("initializes to 'saved' when job.saved_at is present at mount", () => {
    const { result } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    });
    expect(result.current.saveState).toBe("saved");
  });

  it("promotes pending → saved when job.saved_at hydrates after mount", () => {
    const { result, rerender } = renderHookWithJob(makeJob());
    expect(result.current.saveState).toBe("pending");

    act(() => {
      rerender(makeJob({ saved_at: "2026-04-18T00:00:00Z" }));
    });
    expect(result.current.saveState).toBe("saved");
  });

  it("resets saved → pending when the parent swaps to a different unsaved job", () => {
    const { result, rerender } = renderHookWithJob(
      makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    );
    expect(result.current.saveState).toBe("saved");

    act(() => {
      rerender(makeJob({ id: "job-2", saved_at: null }));
    });
    expect(result.current.saveState).toBe("pending");
  });
});

/** renderHook helper that threads a changing `job` through rerenders. */
function renderHookWithJob(initial: ShareDialogJob | null) {
  const { result, rerender } = renderHook(
    ({ job }: { job: ShareDialogJob | null }) =>
      useShareDialog({
        job,
        username: "alice",
        generateAndShare: jest.fn(),
        getImageUrls: jest.fn(async () => ({
          before: "https://cdn/before.jpg",
          after: "https://cdn/after.jpg",
        })),
        onDialogClose: jest.fn(),
        saveJobFn: jest.fn(async () => ({
          saved_at: "2026-04-18T12:00:00Z",
        })),
      }),
    { initialProps: { job: initial } },
  );
  return {
    result,
    rerender: (next: ShareDialogJob | null) => rerender({ job: next }),
  };
}
